"""Domain results for equal-capital DCA versus lump-sum comparisons."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum

from backend.app.models.asset import Asset
from backend.app.models.dca import DCAResult


class StrategyWinner(str, Enum):
    DCA = "DCA"
    LUMP_SUM = "LUMP_SUM"
    TIE = "TIE"


@dataclass(frozen=True, slots=True)
class LumpSumResult:
    asset: Asset
    total_invested: Decimal
    units: Decimal
    entry_price: Decimal
    current_price: Decimal
    requested_start_date: date
    execution_date: date

    @property
    def current_value(self) -> Decimal:
        return self.units * self.current_price

    @property
    def profit_loss(self) -> Decimal:
        return self.current_value - self.total_invested

    @property
    def total_return_percentage(self) -> Decimal:
        return self.profit_loss / self.total_invested * Decimal(100)


@dataclass(frozen=True, slots=True)
class DCAvsLumpSumResult:
    dca: DCAResult
    lump_sum: LumpSumResult

    @property
    def winner(self) -> StrategyWinner:
        dca_return = self.dca.total_return_percentage
        lump_return = self.lump_sum.total_return_percentage
        if dca_return > lump_return:
            return StrategyWinner.DCA
        if lump_return > dca_return:
            return StrategyWinner.LUMP_SUM
        return StrategyWinner.TIE

    @property
    def return_difference(self) -> Decimal:
        """Absolute difference in percentage points, not relative percent."""

        return abs(self.dca.total_return_percentage - self.lump_sum.total_return_percentage)

    @property
    def value_difference(self) -> Decimal:
        """Absolute ending-value difference; both strategies have equal capital."""

        return abs(self.dca.current_value - self.lump_sum.current_value)


