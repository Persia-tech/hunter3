"""Domain models for a single-asset dollar-cost averaging calculation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum

from backend.app.models.asset import Asset


class DCAFrequency(str, Enum):
    """Supported intervals between scheduled contributions."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


@dataclass(frozen=True, slots=True)
class DCAPurchase:
    """One contribution, including its intended and actual market dates."""

    scheduled_date: date
    execution_date: date
    amount_invested: Decimal
    price: Decimal
    units_purchased: Decimal


@dataclass(frozen=True, slots=True)
class DCAResult:
    """Raw values from a completed DCA calculation.

    Aggregate values are properties derived from purchases so duplicated stored
    totals cannot become inconsistent.
    """

    asset: Asset
    start_date: date
    end_date: date
    frequency: DCAFrequency
    investment_per_period: Decimal
    purchases: tuple[DCAPurchase, ...]
    latest_price: Decimal
    requested_end_date: date | None = None

    @property
    def effective_end_date(self) -> date:
        return self.end_date

    @property
    def number_of_purchases(self) -> int:
        return len(self.purchases)

    @property
    def total_invested(self) -> Decimal:
        return sum((purchase.amount_invested for purchase in self.purchases), Decimal(0))

    @property
    def total_units(self) -> Decimal:
        return sum((purchase.units_purchased for purchase in self.purchases), Decimal(0))

    @property
    def average_purchase_price(self) -> Decimal:
        return self.total_invested / self.total_units

    @property
    def current_value(self) -> Decimal:
        return self.total_units * self.latest_price

    @property
    def profit_loss(self) -> Decimal:
        return self.current_value - self.total_invested

    @property
    def total_return_percentage(self) -> Decimal:
        return self.profit_loss / self.total_invested * Decimal(100)

    @property
    def first_purchase_price(self) -> Decimal:
        return self.purchases[0].price

    @property
    def last_purchase_price(self) -> Decimal:
        return self.purchases[-1].price

    @property
    def first_execution_date(self) -> date:
        return self.purchases[0].execution_date

    @property
    def last_execution_date(self) -> date:
        return self.purchases[-1].execution_date


