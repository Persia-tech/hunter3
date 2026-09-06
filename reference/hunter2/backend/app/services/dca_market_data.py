"""Provider-independent access to normalized market prices."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date, timedelta
from decimal import Decimal
from time import sleep

from backend.app.config import (
    CRYPTO_LOOKUP_WINDOW_DAYS,
    MARKET_DATA_MAX_ATTEMPTS,
    MARKET_DATA_RETRY_DELAY_SECONDS,
)
from backend.app.models.asset import Asset
from backend.app.models.price import HistoricalPriceSeries, PricePoint, PriceRecord
from backend.app.providers.dca_provider_base import MarketDataProvider

LOGGER = logging.getLogger(__name__)


class MarketDataError(RuntimeError):
    """Raised when a provider request fails or returns invalid data."""


class PriceNotFoundError(MarketDataError):
    """Raised when no reliable price is available for a request."""


class MarketDataService:
    """Retrieve prices without exposing provider-specific objects to callers."""

    def __init__(
        self,
        provider: MarketDataProvider,
        lookup_window_days: int = 10,
        *,
        max_attempts: int = MARKET_DATA_MAX_ATTEMPTS,
        retry_delay_seconds: float = MARKET_DATA_RETRY_DELAY_SECONDS,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        if lookup_window_days < 0:
            raise ValueError("lookup_window_days cannot be negative")
        self._provider = provider
        self._lookup_window_days = lookup_window_days
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least one")
        self._max_attempts = max_attempts
        self._retry_delay_seconds = retry_delay_seconds
        self._sleeper = sleeper

    def get_historical_prices(
        self, asset: Asset, start_date: date, end_date: date
    ) -> list[PriceRecord]:
        """Return validated prices for an inclusive date range."""

        if end_date < start_date:
            raise ValueError("end_date cannot be before start_date")
        try:
            prices = self._call_provider(
                "historical",
                asset.symbol,
                self._provider.get_historical_prices,
                asset.provider_ticker,
                start_date,
                end_date,
            )
        except Exception as exc:
            raise MarketDataError(
                f"Could not retrieve historical prices for {asset.symbol}."
            ) from exc

        valid_prices = self._validate_prices(prices, start_date, end_date)
        if not valid_prices:
            raise PriceNotFoundError(
                f"No prices found for {asset.symbol} from {start_date} through {end_date}."
            )
        return valid_prices

    def get_historical_series(
        self, asset: Asset, start_date: date, requested_end_date: date
    ) -> HistoricalPriceSeries:
        """Fetch completed observations and expose their actual trailing boundary."""

        prices = self.get_historical_prices(asset, start_date, requested_end_date)
        return HistoricalPriceSeries(
            prices=tuple(prices),
            requested_start_date=start_date,
            requested_end_date=requested_end_date,
        )

    def resolve_points_from_series(
        self,
        asset: Asset,
        requested_dates: tuple[date, ...],
        series: HistoricalPriceSeries,
    ) -> tuple[PricePoint, ...]:
        """Resolve contribution dates solely from already-fetched completed data."""

        days_to_search = self._lookup_window_for(asset)
        points: list[PricePoint] = []
        for requested_date in requested_dates:
            limit = min(
                requested_date + timedelta(days=days_to_search),
                series.last_available_date,
            )
            match = next(
                (
                    item
                    for item in series.prices
                    if requested_date <= item.date <= limit
                ),
                None,
            )
            if match is None:
                raise PriceNotFoundError(
                    f"No completed price found for {asset.symbol} on or after "
                    f"{requested_date} within {days_to_search} day(s)."
                )
            points.append(PricePoint(requested_date, match.date, match.price))
        return tuple(points)

    def get_latest_price(self, asset: Asset) -> PriceRecord:
        """Return the provider's latest validated price for an asset."""

        try:
            latest = self._call_provider(
                "latest", asset.symbol, self._provider.get_latest_price, asset.provider_ticker
            )
        except Exception as exc:
            raise MarketDataError(
                f"Could not retrieve the latest price for {asset.symbol}."
            ) from exc

        if latest is None or not self._is_valid_price(latest):
            raise PriceNotFoundError(f"No latest price is available for {asset.symbol}.")
        return latest

    def get_price_on_or_after_date(self, asset: Asset, requested_date: date) -> PricePoint:
        """Find the requested day's price, or the next exchange trading day's price.

        All matches are real completed provider candles. Exchange-traded assets use
        the exchange lookup window; 24/7 assets use the bounded crypto gap window.
        """

        return self.get_prices_on_or_after_dates(asset, (requested_date,))[0]

    def get_prices_on_or_after_dates(
        self, asset: Asset, requested_dates: tuple[date, ...]
    ) -> tuple[PricePoint, ...]:
        """Resolve many scheduled dates using one historical provider request.

        Returned points preserve the input order and duplicates. This makes a
        daily DCA calculation efficient without merging separate contributions.
        """

        if not requested_dates:
            return ()

        days_to_search = self._lookup_window_for(asset)
        search_start = min(requested_dates)
        search_end = max(requested_dates) + timedelta(days=days_to_search)
        try:
            prices = self.get_historical_prices(asset, search_start, search_end)
        except PriceNotFoundError as exc:
            raise PriceNotFoundError(
                f"No price found for one or more requested {asset.symbol} dates "
                f"within {days_to_search} day(s)."
            ) from exc

        points: list[PricePoint] = []
        for requested_date in requested_dates:
            requested_end = requested_date + timedelta(days=days_to_search)
            matching_price = next(
                (
                    price
                    for price in prices
                    if requested_date <= price.date <= requested_end
                ),
                None,
            )
            if matching_price is None:
                raise PriceNotFoundError(
                    f"No price found for {asset.symbol} on or after {requested_date} "
                    f"within {days_to_search} day(s)."
                )
            points.append(
                PricePoint(
                    requested_date=requested_date,
                    actual_date=matching_price.date,
                    price=matching_price.price,
                )
            )
        return tuple(points)

    def _lookup_window_for(self, asset: Asset) -> int:
        """Return the centralized forward search bound for an asset's market."""

        return CRYPTO_LOOKUP_WINDOW_DAYS if asset.trades_24_7 else self._lookup_window_days

    @classmethod
    def _validate_prices(
        cls, prices: list[PriceRecord], start_date: date, end_date: date
    ) -> list[PriceRecord]:
        return sorted(
            (
                price
                for price in prices
                if start_date <= price.date <= end_date and cls._is_valid_price(price)
            ),
            key=lambda record: record.date,
        )

    @staticmethod
    def _is_valid_price(record: PriceRecord) -> bool:
        value: Decimal = record.price
        return value.is_finite() and value > 0

    def _call_provider(self, operation: str, symbol: str, function, *args):  # type: ignore[no-untyped-def]
        """Retry provider exceptions only; empty/invalid data is deterministic."""

        for attempt in range(1, self._max_attempts + 1):
            try:
                return function(*args)
            except Exception as exc:
                LOGGER.warning(
                    "Market provider failure operation=%s asset=%s attempt=%s type=%s",
                    operation,
                    symbol,
                    attempt,
                    type(exc).__name__,
                )
                if attempt == self._max_attempts:
                    raise
                self._sleeper(self._retry_delay_seconds)
        raise AssertionError("unreachable")

