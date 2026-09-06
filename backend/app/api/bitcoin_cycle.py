"""Read-only Bitcoin cycle API."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.api.alerts import require_telegram_user
from backend.app.models.asset import get_asset
from backend.app.providers.dca_yfinance_provider import YFinanceProvider
from backend.app.services.bitcoin_cycle import calculate_bitcoin_cycle
from backend.app.services.dca_market_data import MarketDataError, MarketDataService


router = APIRouter(prefix="/api/bitcoin-cycle", tags=["bitcoin-cycle"])
BTC_HISTORY_START = date(2014, 9, 17)


@router.get("")
def get_bitcoin_cycle(
    _user_id: str = Depends(require_telegram_user),
) -> dict[str, object]:
    """Return the latest price-only Bitcoin cycle indicators and scores."""

    asset = get_asset("BTC")
    market = MarketDataService(YFinanceProvider())
    end_date = date.today()

    try:
        records = market.get_historical_prices(asset, BTC_HISTORY_START, end_date)
        result = calculate_bitcoin_cycle(records)
    except (MarketDataError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Bitcoin cycle data is temporarily unavailable",
        ) from exc

    return {
        "symbol": "BTC",
        "as_of": result.as_of.isoformat(),
        "price": result.price,
        "opportunity_score": result.opportunity_score,
        "overheat_score": result.overheat_score,
        "weekly_rsi": result.weekly_rsi,
        "divergence": result.divergence.value,
        "sma_200w": result.sma_200w,
        "distance_200w_pct": result.distance_200w_pct,
        "sma_200d": result.sma_200d,
        "mayer_multiple": result.mayer_multiple,
        "pi_cycle": {
            "sma_111d": result.pi_111dma,
            "sma_350d_x2": result.pi_350dma_x2,
            "ratio": result.pi_ratio,
        },
        "ath": result.ath,
        "ath_drawdown_pct": result.ath_drawdown_pct,
        "momentum_1y_pct": result.momentum_1y_pct,
        "source": "price-only",
    }
