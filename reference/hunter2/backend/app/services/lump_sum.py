"""Equal-capital DCA versus lump-sum strategy comparison."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from backend.app.models.asset import Asset
from backend.app.models.dca import DCAFrequency
from backend.app.models.lump_sum import DCAvsLumpSumResult, LumpSumResult
from backend.app.services.dca_calculator import DCACalculationError, DCACalculator
from backend.app.services.limits import RequestLimitError
from backend.app.services.dca_market_data import MarketDataError, MarketDataService


class DCAvsLumpSumError(RuntimeError):
    """Raised when a complete and fair strategy comparison cannot be produced."""


class DCAvsLumpSumService:
    def __init__(self, calculator: DCACalculator, market_data: MarketDataService) -> None:
        self._calculator = calculator
        self._market_data = market_data

    def compare(
        self,
        asset: Asset,
        start_date: date,
        end_date: date,
        frequency: DCAFrequency,
        investment_amount: Decimal,
    ) -> DCAvsLumpSumResult:
        """Run DCA, then invest its exact total capital once at the start."""

        try:
            dca = self._calculator.calculate(
                asset, start_date, end_date, frequency, investment_amount
            )
            total_capital = dca.total_invested
            if (
                dca.number_of_purchases == 0
                or total_capital <= 0
                or dca.total_units <= 0
                or not dca.latest_price.is_finite()
                or dca.latest_price <= 0
            ):
                raise DCAvsLumpSumError("DCA produced an invalid result")
            entry = self._market_data.get_price_on_or_after_date(asset, start_date)
            lump_sum = LumpSumResult(
                asset=asset,
                total_invested=total_capital,
                units=total_capital / entry.price,
                entry_price=entry.price,
                current_price=dca.latest_price,
                requested_start_date=start_date,
                execution_date=entry.actual_date,
            )
        except (DCAvsLumpSumError, RequestLimitError):
            raise
        except (DCACalculationError, MarketDataError, ValueError, ArithmeticError) as exc:
            raise DCAvsLumpSumError("Could not complete strategy comparison") from exc
        return DCAvsLumpSumResult(dca=dca, lump_sum=lump_sum)


