"""Interface implemented by replaceable market-data providers."""

from datetime import date
from typing import Protocol

from backend.app.models.price import PriceRecord


class MarketDataProvider(Protocol):
    """The small provider contract consumed by :class:`MarketDataService`."""

    def get_historical_prices(
        self, provider_ticker: str, start_date: date, end_date: date
    ) -> list[PriceRecord]:
        """Return normalized daily prices for an inclusive date range."""
        ...

    def get_latest_price(self, provider_ticker: str) -> PriceRecord | None:
        """Return the latest price, or ``None`` when the provider has none."""
        ...

