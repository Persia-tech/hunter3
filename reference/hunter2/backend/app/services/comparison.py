"""Fair, reusable multi-asset DCA comparisons."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import date
from decimal import Decimal

from backend.app.config import MAX_COMPARE_ASSETS
from backend.app.models.asset import Asset
from backend.app.models.comparison import DCAComparisonResult
from backend.app.models.dca import DCAFrequency, DCAResult
from backend.app.models.price import HistoricalPriceSeries
from backend.app.services.dca_calculator import DCACalculationError, DCACalculator
from backend.app.services.limits import validate_comparison_workload, validate_dca_workload

LOGGER = logging.getLogger(__name__)


class DCAComparisonError(RuntimeError):
    """Raised when an asset prevents a complete comparison."""

    def __init__(self, asset: Asset) -> None:
        self.asset = asset
        super().__init__(f"Could not calculate {asset.symbol}")


class DCAComparisonService:
    """Apply one complete DCA strategy independently to every asset."""

    def __init__(self, calculator: DCACalculator) -> None:
        self._calculator = calculator

    def compare(
        self,
        assets: Iterable[Asset],
        start_date: date,
        end_date: date,
        frequency: DCAFrequency,
        investment_amount: Decimal,
    ) -> DCAComparisonResult | tuple[DCAResult, ...]:
        """Calculate sequentially and rank by return, then symbol."""

        selected = tuple(assets)
        if len(selected) < 2:
            raise ValueError("At least two assets are required")
        if len({asset.symbol for asset in selected}) != len(selected):
            raise ValueError("Duplicate assets are not allowed")
        if len(selected) > MAX_COMPARE_ASSETS:
            raise ValueError("You selected too many assets. Please choose up to 10.")
        purchase_count = validate_dca_workload(start_date, end_date, frequency)
        validate_comparison_workload(len(selected), purchase_count)

        if not hasattr(self._calculator, "get_historical_series"):
            return self._compare_legacy(
                selected, start_date, end_date, frequency, investment_amount
            )

        available: list[tuple[Asset, HistoricalPriceSeries]] = []
        unavailable: list[str] = []
        for asset in selected:
            try:
                series = self._calculator.get_historical_series(
                    asset, start_date, end_date
                )
            except (DCACalculationError, ValueError):
                LOGGER.warning("Comparison history unavailable asset=%s", asset.symbol)
                unavailable.append(asset.symbol)
                continue
            available.append((asset, series))
        if len(available) < 2:
            failed = next(
                asset for asset in selected if asset.symbol in unavailable
            )
            raise DCAComparisonError(failed)

        common_dates = set(item.date for item in available[0][1].prices)
        for _asset, series in available[1:]:
            common_dates.intersection_update(item.date for item in series.prices)
        if not common_dates:
            raise DCAComparisonError(available[0][0])
        common_end = max(common_dates)
        results: list[DCAResult] = []
        for asset, series in available:
            try:
                results.append(
                    self._calculator.calculate_from_series(
                        asset,
                        start_date,
                        end_date,
                        frequency,
                        investment_amount,
                        series,
                        effective_end_date=common_end,
                    )
                )
            except (DCACalculationError, ValueError):
                unavailable.append(asset.symbol)
        if len(results) < 2:
            raise DCAComparisonError(available[0][0])
        ranked = tuple(
            sorted(
                results,
                key=lambda result: (-result.total_return_percentage, result.asset.symbol),
            )
        )
        return DCAComparisonResult(ranked, tuple(unavailable))

    def _compare_legacy(
        self,
        selected: tuple[Asset, ...],
        start_date: date,
        end_date: date,
        frequency: DCAFrequency,
        investment_amount: Decimal,
    ) -> tuple[DCAResult, ...]:
        results: list[DCAResult] = []
        for asset in selected:
            try:
                results.append(
                    self._calculator.calculate(
                        asset, start_date, end_date, frequency, investment_amount
                    )
                )
            except (DCACalculationError, ValueError) as exc:
                raise DCAComparisonError(asset) from exc
        return tuple(
            sorted(
                results,
                key=lambda item: (
                    -item.total_return_percentage,
                    item.asset.symbol,
                ),
            )
        )


