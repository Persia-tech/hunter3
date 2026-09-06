"""PostgreSQL repository helpers for Hunter2."""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models import AlertRule, AlertState, MarketSnapshot
from backend.app.models.market import MarketTemperature


class MarketRepository:
    """Persistence operations for market snapshots and alerts."""
    def get_alert_state(
        self,
        rule_id: int,
    ) -> AlertState | None:
        statement = select(AlertState).where(
            AlertState.rule_id == rule_id
        )

        return self._session.scalar(statement)

    def __init__(self, session: Session) -> None:
        self._session = session

    def save_market_snapshot(
        self,
        temperature: MarketTemperature,
    ) -> MarketSnapshot:
        snapshot = MarketSnapshot(
            symbol=temperature.symbol,
            name=temperature.name,
            asset_class=temperature.asset_class.value,
            as_of=temperature.as_of,
            current_price=temperature.current_price,
            opportunity_score=temperature.opportunity_score,
            overheat_score=temperature.overheat_score,
            classification=temperature.classification,
            trend=temperature.trend.value,
            divergence=temperature.divergence.value,
            weekly_rsi=temperature.weekly_rsi,
            previous_weekly_rsi=temperature.previous_weekly_rsi,
            stochastic_rsi=temperature.stochastic_rsi,
            previous_stochastic_rsi=temperature.previous_stochastic_rsi,
            sma_200w=temperature.sma_200w,
            distance_200w_percent=temperature.distance_200w_percent,
            ath=temperature.ath,
            drawdown_percent=temperature.drawdown_percent,
            sma_200d=temperature.sma_200d,
            sma_10m=temperature.sma_10m,
            momentum_12m=temperature.momentum_12m,
            recovery_signal=temperature.recovery_signal,
            history_status=temperature.history_status,
        )

        self._session.add(snapshot)
        return snapshot

    def save_market_snapshots(
        self,
        temperatures: Iterable[MarketTemperature],
    ) -> list[MarketSnapshot]:
        snapshots = [
            self.save_market_snapshot(temperature)
            for temperature in temperatures
        ]
        return snapshots

    def get_enabled_alert_rules(self) -> list[AlertRule]:
        statement = (
            select(AlertRule)
            .where(AlertRule.enabled.is_(True))
            .order_by(AlertRule.id)
        )

        return list(
            self._session.scalars(statement).all()
        )

    def get_alert_rules_for_symbol(
        self,
        symbol: str,
        *,
        asset_class: str | None = None,
    ) -> list[AlertRule]:
        rules = self.get_enabled_alert_rules()

        return [
            rule
            for rule in rules
            if self._rule_matches_scope(
                rule,
                symbol=symbol,
                asset_class=asset_class,
            )
        ]

    def get_or_create_alert_state(
        self,
        rule: AlertRule,
    ) -> AlertState:
        if rule.state is not None:
            return rule.state

        statement = select(AlertState).where(
            AlertState.rule_id == rule.id
        )

        state = self._session.scalar(statement)

        if state is not None:
            return state

        state = AlertState(
            rule_id=rule.id,
            is_active=False,
            trigger_count=0,
        )

        self._session.add(state)
        self._session.flush()

        return state

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()

    @staticmethod
    def _rule_matches_scope(
        rule: AlertRule,
        *,
        symbol: str,
        asset_class: str | None,
    ) -> bool:
        scope_type = rule.scope_type
        scope_value = rule.scope_value

        if scope_type == "all":
            return True

        if scope_type == "symbol":
            return (
                scope_value is not None
                and scope_value.upper() == symbol.upper()
            )

        if scope_type == "asset_class":
            return (
                scope_value is not None
                and asset_class is not None
                and scope_value.lower() == asset_class.lower()
            )

        return False