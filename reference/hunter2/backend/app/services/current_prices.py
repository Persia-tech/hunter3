"""Retrieve a normalized snapshot of every supported asset's latest price."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone
from threading import Lock
from time import monotonic

from backend.app.config import CURRENT_PRICE_CACHE_TTL_SECONDS
from backend.app.models.asset import SUPPORTED_ASSETS
from backend.app.models.current_prices import CurrentPrice, CurrentPricesResult
from backend.app.services.dca_market_data import MarketDataError, MarketDataService

LOGGER = logging.getLogger(__name__)


class CurrentPricesError(RuntimeError):
    """Raised when no supported asset can be priced."""

    def __init__(self, unavailable_symbols: tuple[str, ...]) -> None:
        self.unavailable_symbols = unavailable_symbols
        super().__init__("No current prices could be retrieved")


class CurrentPricesService:
    """Fetch latest prices sequentially through the shared market-data layer."""

    def __init__(
        self,
        market_data: MarketDataService,
        clock: Callable[[], datetime] | None = None,
        monotonic_clock: Callable[[], float] = monotonic,
        cache_ttl_seconds: float = CURRENT_PRICE_CACHE_TTL_SECONDS,
    ) -> None:
        self._market_data = market_data
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._monotonic_clock = monotonic_clock
        self._cache_ttl_seconds = cache_ttl_seconds
        self._cached: tuple[float, CurrentPricesResult] | None = None
        self._cache_lock = Lock()

    def get_all(self) -> CurrentPricesResult:
        with self._cache_lock:
            now = self._monotonic_clock()
            if self._cached is not None and now - self._cached[0] < self._cache_ttl_seconds:
                return self._cached[1]
            result = self._fetch_all()
            self._cached = (now, result)
            return result

    def _fetch_all(self) -> CurrentPricesResult:
        prices: list[CurrentPrice] = []
        unavailable: list[str] = []
        for asset in SUPPORTED_ASSETS.values():
            try:
                record = self._market_data.get_latest_price(asset)
            except MarketDataError:
                LOGGER.warning("Current price unavailable asset=%s", asset.symbol)
                unavailable.append(asset.symbol)
            else:
                prices.append(CurrentPrice(asset=asset, price=record.price))

        unavailable_symbols = tuple(unavailable)
        if not prices:
            raise CurrentPricesError(unavailable_symbols)
        fetched_at = self._clock()
        if fetched_at.tzinfo is None or fetched_at.utcoffset() is None:
            raise ValueError("CurrentPricesService clock must return a timezone-aware datetime")
        return CurrentPricesResult(tuple(prices), unavailable_symbols, fetched_at)


