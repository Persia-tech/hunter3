"""Provider-independent current-price snapshot models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from backend.app.models.asset import Asset


@dataclass(frozen=True, slots=True)
class CurrentPrice:
    asset: Asset
    price: Decimal


@dataclass(frozen=True, slots=True)
class CurrentPricesResult:
    prices: tuple[CurrentPrice, ...]
    unavailable_symbols: tuple[str, ...]
    fetched_at: datetime


