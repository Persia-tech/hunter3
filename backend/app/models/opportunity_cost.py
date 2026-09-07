"""Product purchases and date-by-date opportunity-cost results."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from backend.app.models.asset import Asset


@dataclass(frozen=True, slots=True)
class Product:
    id: str
    brand: str
    category: str
    family: str
    model: str
    release_date: date
    launch_price_usd: Decimal
    source_url: str
    active: bool = True
    display_order: int = 0
    image_url: str | None = None


@dataclass(frozen=True, slots=True)
class Purchase:
    product: Product
    quantity: int


@dataclass(frozen=True, slots=True)
class OpportunityItem:
    purchase: Purchase
    price_date: date | None
    asset_price: Decimal | None
    units: Decimal
    current_value: Decimal
    reason: str | None = None

    @property
    def cost(self) -> Decimal:
        return self.purchase.product.launch_price_usd * self.purchase.quantity

    @property
    def eligible(self) -> bool:
        return self.asset_price is not None


@dataclass(frozen=True, slots=True)
class OpportunityResult:
    asset: Asset
    current_price: Decimal
    current_price_date: date
    items: tuple[OpportunityItem, ...]

    @property
    def total_spent(self) -> Decimal:
        return sum((item.cost for item in self.items), Decimal(0))

    @property
    def eligible_spent(self) -> Decimal:
        return sum((item.cost for item in self.items if item.eligible), Decimal(0))

    @property
    def total_units(self) -> Decimal:
        return sum((item.units for item in self.items), Decimal(0))

    @property
    def current_value(self) -> Decimal:
        return sum((item.current_value for item in self.items), Decimal(0))

    @property
    def gain(self) -> Decimal:
        return self.current_value - self.eligible_spent

    @property
    def return_pct(self) -> Decimal:
        if not self.eligible_spent:
            return Decimal(0)
        return (self.current_value / self.eligible_spent - Decimal(1)) * Decimal(100)
