"""Pure single-asset dollar-cost averaging calculations."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from backend.app.models.asset import Asset
from backend.app.models.dca import DCAFrequency, DCAPurchase, DCAResult
from backend.app.models.price import HistoricalPriceSeries
from backend.app.services.limits import validate_dca_workload
from backend.app.services.dca_market_data import MarketDataError, MarketDataService
from backend.app.services.dca_dates import generate_dca_dates


class DCACalculationError(RuntimeError):
    """Raised when required market data prevents a complete DCA calculation."""


class DCACalculator:
    """Calculate one asset's DCA outcome using an injected market-data service."""

    def __init__(self, market_data: MarketDataService) -> None:
        self._market_data = market_data

    def calculate(
        self,
        asset: Asset,
        start_date: date,
        end_date: date,
        frequency: DCAFrequency,
        investment_amount: Decimal,
    ) -> DCAResult:
        """Execute every scheduled contribution and value the resulting units."""

        self._validate_investment_amount(investment_amount)
        if end_date < start_date:
            raise ValueError("end_date cannot be before start_date")
        validate_dca_workload(start_date, end_date, frequency)
        try:
            series = self._market_data.get_historical_series(asset, start_date, end_date)
        except MarketDataError as exc:
            raise DCACalculationError(
                f"Could not retrieve completed historical data for {asset.symbol}."
            ) from exc
        return self.calculate_from_series(
            asset, start_date, end_date, frequency, investment_amount, series
        )

    def calculate_from_series(
        self,
        asset: Asset,
        start_date: date,
        requested_end_date: date,
        frequency: DCAFrequency,
        investment_amount: Decimal,
        series: HistoricalPriceSeries,
        *,
        effective_end_date: date | None = None,
    ) -> DCAResult:
        """Calculate from one fetched completed series, optionally at a common end."""

        self._validate_investment_amount(investment_amount)
        effective_end = effective_end_date or series.last_available_date
        if effective_end > requested_end_date or effective_end < start_date:
            raise ValueError("effective_end_date is outside the requested period")
        bounded = series.through(effective_end)
        if bounded.last_available_date != effective_end:
            raise DCACalculationError(
                f"No completed valuation price exists for {asset.symbol} on "
                f"{effective_end}."
            )
        scheduled_dates = generate_dca_dates(start_date, effective_end, frequency)
        purchases: list[DCAPurchase] = []

        try:
            price_points = self._market_data.resolve_points_from_series(
                asset, scheduled_dates, bounded
            )
        except MarketDataError as exc:
            raise DCACalculationError(
                f"Could not price every scheduled {asset.symbol} contribution."
            ) from exc

        for scheduled_date, price_point in zip(scheduled_dates, price_points, strict=True):
            purchases.append(
                DCAPurchase(
                    scheduled_date=scheduled_date,
                    execution_date=price_point.actual_date,
                    amount_invested=investment_amount,
                    price=price_point.price,
                    units_purchased=investment_amount / price_point.price,
                )
            )

        return DCAResult(
            asset=asset,
            start_date=start_date,
            end_date=effective_end,
            frequency=frequency,
            investment_per_period=investment_amount,
            purchases=tuple(purchases),
            latest_price=bounded.prices[-1].price,
            requested_end_date=requested_end_date,
        )

    def get_historical_series(
        self, asset: Asset, start_date: date, end_date: date
    ) -> HistoricalPriceSeries:
        """Expose the central completed-series fetch for comparison orchestration."""
        try:
            return self._market_data.get_historical_series(asset, start_date, end_date)
        except MarketDataError as exc:
            raise DCACalculationError(
                f"Could not retrieve completed historical data for {asset.symbol}."
            ) from exc

    @staticmethod
    def _validate_investment_amount(investment_amount: Decimal) -> None:
        if not isinstance(investment_amount, Decimal):
            raise ValueError("investment_amount must be a Decimal")
        if not investment_amount.is_finite() or investment_amount <= 0:
            raise ValueError("investment_amount must be finite and greater than zero")


