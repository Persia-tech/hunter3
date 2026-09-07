"""Read-only current Bitcoin research state for the Mini App.

This endpoint deliberately keeps the independently validated research signals
separate. It exposes the current quantile percentile and MVRV percentile without
combining them into a trading score.
"""

from __future__ import annotations

from datetime import date
from functools import lru_cache

from fastapi import APIRouter, Depends

from backend.app.api.alerts import require_telegram_user
from backend.app.models.asset import get_asset
from backend.app.providers.coinmetrics_community_provider import CoinMetricsCommunityProvider
from backend.app.providers.dca_yfinance_provider import YFinanceProvider
from backend.app.services.bitcoin_onchain_backtest import expanding_percentile
from backend.app.services.bitcoin_quantile import fit_bitcoin_quantile_model, snapshot_bitcoin_quantile
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
    }

    # Quantile model: fit only to observations available through the current day.
    # The result is cached by date so normal UI refreshes do not repeatedly refit.
    try:
        asset = get_asset("BTC")
        records = MarketDataService(YFinanceProvider()).get_historical_prices(
            asset,
            BTC_PRICE_START,
            today,
        )
        if records:
            model = fit_bitcoin_quantile_model(records)
            latest = records[-1]
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
        onchain = CoinMetricsCommunityProvider().get_bitcoin_daily_metrics(
            start_date=BTC_MVRV_START,
            end_date=today,
        )
        rows = [row for row in onchain if row.mvrv is not None]
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

    return response


@router.get("")
def get_bitcoin_research_state(
    _user_id: str = Depends(require_telegram_user),
) -> dict[str, object]:
    """Return current independent Bitcoin research metrics for display."""
    return _research_state_for_day(date.today())
