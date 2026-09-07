"""Read-only current Bitcoin research state for the Mini App.

This endpoint deliberately keeps the independently validated research signals
separate. It exposes the current quantile percentile, MVRV percentile, and the
fixed persistent-weakness top confirmation without combining them into a score.
"""

from __future__ import annotations

from datetime import date
from functools import lru_cache

from fastapi import APIRouter, Depends

from backend.app.api.alerts import require_telegram_user
from backend.app.models.asset import get_asset
from backend.app.models.onchain import BitcoinOnChainRecord
from backend.app.models.price import PriceRecord
from backend.app.providers.coinmetrics_community_provider import CoinMetricsCommunityProvider
from backend.app.providers.dca_yfinance_provider import YFinanceProvider
from backend.app.services.bitcoin_onchain_backtest import expanding_percentile
from backend.app.services.bitcoin_quantile import fit_bitcoin_quantile_model, snapshot_bitcoin_quantile
from backend.app.services.bitcoin_top_live_state import evaluate_live_top_stage2
from backend.app.services.dca_market_data import MarketDataService


router = APIRouter(prefix="/api/bitcoin-research-state", tags=["bitcoin-research"])
BTC_PRICE_START = date(2014, 9, 17)
BTC_MVRV_START = date(2010, 7, 18)


def _freshness_label(days_old: int) -> str:
    if days_old <= 0:
        return "LIVE"
    if days_old == 1:
        return "CURRENT"
    if days_old == 2:
        return "ACCEPTABLE"
    return "STALE"


@lru_cache(maxsize=4)
def _research_state_for_day(today: date) -> dict[str, object]:
    response: dict[str, object] = {
        "as_of": today.isoformat(),
        "quantile": None,
        "mvrv": None,
        "top_stage2": None,
    }
    price_records: list[PriceRecord] = []
    onchain_rows: list[BitcoinOnChainRecord] = []

    # Quantile model: fit only to observations available through the current day.
    # The result is cached by date so normal UI refreshes do not repeatedly refit.
    try:
        asset = get_asset("BTC")
        price_records = MarketDataService(YFinanceProvider()).get_historical_prices(
            asset,
            BTC_PRICE_START,
            today,
        )
        if price_records:
            model = fit_bitcoin_quantile_model(price_records)
            latest = price_records[-1]
            snapshot = snapshot_bitcoin_quantile(
                model,
                day=latest.date,
                price=float(latest.price),
            )
            response["quantile"] = {
                "as_of": snapshot.as_of.isoformat(),
                "price": snapshot.price,
                "percentile": snapshot.percentile,
                "bands": [
                    {"quantile": quantile, "price": price}
                    for quantile, price in snapshot.bands
                ],
                "method": snapshot.method,
            }
    except Exception as exc:  # Keep the rest of the overview usable if one provider fails.
        response["quantile_error"] = str(exc)

    # MVRV: use the newest non-null Community observation and calculate its
    # historical percentile using only observations available through that date.
    try:
        onchain_rows = CoinMetricsCommunityProvider().get_bitcoin_daily_metrics(
            start_date=BTC_MVRV_START,
            end_date=today,
        )
        rows = [row for row in onchain_rows if row.mvrv is not None]
        if rows:
            latest = rows[-1]
            history = [
                float(row.mvrv)
                for row in rows
                if row.date <= latest.date and row.mvrv is not None
            ]
            percentile = expanding_percentile(float(latest.mvrv), history)
            if percentile is not None:
                age_days = (today - latest.date).days
                response["mvrv"] = {
                    "as_of": latest.date.isoformat(),
                    "price": latest.price_usd,
                    "value": float(latest.mvrv),
                    "percentile": percentile,
                    "history_observations": len(history),
                    "age_days": age_days,
                    "freshness": _freshness_label(age_days),
                    "source": "Coin Metrics Community",
                }
    except Exception as exc:
        response["mvrv_error"] = str(exc)

    # Top Stage 2: reproduce the fixed research rule point-in-time. The helper
    # first looks for an independent MVRV >=90 warning. If no recent warning
    # exists it returns immediately without doing expensive daily cycle replay.
    if price_records and onchain_rows:
        try:
            stage2 = evaluate_live_top_stage2(
                price_records,
                onchain_rows,
                as_of=today,
            )
            response["top_stage2"] = {
                "active": stage2.active,
                "warning_date": stage2.warning_date.isoformat() if stage2.warning_date else None,
                "confirmation_date": (
                    stage2.confirmation_date.isoformat() if stage2.confirmation_date else None
                ),
                "warning_age_days": stage2.warning_age_days,
                "current_any2_streak_days": stage2.current_any2_streak_days,
                "primitive_count": stage2.primitive_count,
                "primitives": {
                    "below_50d_sma": stage2.below_50d_sma,
                    "momentum_30d_negative": stage2.momentum_30d_negative,
                    "drawdown_10pct": stage2.drawdown_10pct,
                    "overheat_rollover_20": stage2.overheat_rollover_20,
                },
                "rule": "Any-2 sustained 14d after independent MVRV pct >=90 warning",
                "reason": stage2.reason,
            }
        except Exception as exc:
            response["top_stage2_error"] = str(exc)

    return response


@router.get("")
def get_bitcoin_research_state(
    _user_id: str = Depends(require_telegram_user),
) -> dict[str, object]:
    """Return current independent Bitcoin research metrics for display."""
    return _research_state_for_day(date.today())
