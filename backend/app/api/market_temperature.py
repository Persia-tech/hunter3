"""Read-only API for the latest persisted Market Temperature snapshots."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from backend.app.api.alerts import get_db, require_telegram_user
from backend.app.db.models import MarketSnapshot
from backend.app.db.repository import MarketRepository


router = APIRouter(prefix="/api/market-temperature", tags=["market-temperature"])


class MarketSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    symbol: str
    name: str
    asset_class: str
    as_of: datetime
    current_price: float
    opportunity_score: int
    overheat_score: int
    classification: str
    trend: str
    divergence: str
    weekly_rsi: float | None
    previous_weekly_rsi: float | None
    stochastic_rsi: float | None
    previous_stochastic_rsi: float | None
    sma_200w: float | None
    distance_200w_percent: float | None
    ath: float
    drawdown_percent: float
    sma_200d: float | None
    sma_10m: float | None
    momentum_12m: float | None
    recovery_signal: bool
    history_status: str


@router.get("", response_model=list[MarketSnapshotResponse])
def list_market_temperatures(
    _user_id: str = Depends(require_telegram_user),
    session: Session = Depends(get_db),
) -> list[MarketSnapshot]:
    return MarketRepository(session).get_latest_market_snapshots()


@router.get("/{symbol}", response_model=MarketSnapshotResponse)
def get_market_temperature(
    symbol: str,
    _user_id: str = Depends(require_telegram_user),
    session: Session = Depends(get_db),
) -> MarketSnapshot:
    snapshot = MarketRepository(session).get_latest_market_snapshot(symbol)
    if snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Market snapshot not found",
        )
    return snapshot
