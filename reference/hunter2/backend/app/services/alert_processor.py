"""End-to-end alert processing for Hunter2."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.app.db.repository import MarketRepository
from backend.app.models.market import MarketTemperature
from backend.app.services.alert_engine import (
    AlertEvaluation,
    AlertEvaluationError,
    apply_evaluation_to_state,
    evaluate_rule,
)


@dataclass(frozen=True)
class AlertNotification:
    """Notification produced by one matching alert rule."""

    rule_id: int
    telegram_user_id: str
    delivery_channel: str
    symbol: str
    metric: str
    operator: str
    current_value: Any
    evaluation: AlertEvaluation


class AlertProcessor:
    """Persist snapshots and evaluate all matching alert rules."""

    def __init__(self, repository: MarketRepository) -> None:
        self._repository = repository

    def process_temperature(
        self,
        temperature: MarketTemperature,
    ) -> list[AlertNotification]:
        self._repository.save_market_snapshot(temperature)

        rules = self._repository.get_alert_rules_for_symbol(
            temperature.symbol,
            asset_class=temperature.asset_class.value,
        )

        notifications: list[AlertNotification] = []

        for rule in rules:
            try:
                current_value = self._get_metric_value(
                    temperature,
                    rule.metric,
                )

                state = self._repository.get_or_create_alert_state(rule)

                evaluation = evaluate_rule(
                    rule,
                    state,
                    current_value,
                )

                if evaluation.should_notify:
                    notifications.append(
                        AlertNotification(
                            rule_id=rule.id,
                            telegram_user_id=rule.telegram_user_id,
                            delivery_channel=rule.delivery_channel,
                            symbol=temperature.symbol,
                            metric=rule.metric,
                            operator=rule.operator,
                            current_value=current_value,
                            evaluation=evaluation,
                        )
                    )

                apply_evaluation_to_state(
                    state,
                    evaluation,
                    notified=False,
                )

            except AlertEvaluationError:
                continue

        return notifications

    def process_and_commit(
        self,
        temperature: MarketTemperature,
    ) -> list[AlertNotification]:
        try:
            notifications = self.process_temperature(temperature)
            self._repository.commit()
            return notifications
        except Exception:
            self._repository.rollback()
            raise

    @staticmethod
    def _get_metric_value(
        temperature: MarketTemperature,
        metric: str,
    ) -> Any:
        if not hasattr(temperature, metric):
            raise AlertEvaluationError(
                f"Unsupported market metric: {metric}"
            )

        value = getattr(temperature, metric)

        if hasattr(value, "value"):
            return value.value

        return value
