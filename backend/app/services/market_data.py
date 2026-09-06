"""Market-data interfaces used by Hunter2."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from backend.app.models.market import Candle


class HistoricalPriceProvider(Protocol):
    """Interface implemented by historical market-data providers."""

    def completed_weekly_history(
        self,
        symbol: str,
        years: int = 5,
    ) -> Sequence[Candle]:
        """Return completed weekly candles, oldest to newest."""
        ...

    def daily_history(
        self,
        symbol: str,
        years: int = 2,
    ) -> Sequence[Candle]:
        """Return daily candles, oldest to newest."""
        ...

    def full_history(
        self,
        symbol: str,
    ) -> Sequence[Candle]:
        """Return the longest available daily history."""
        ...