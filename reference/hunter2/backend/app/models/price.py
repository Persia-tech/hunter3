"""Provider-independent market price models."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class PriceRecord:
    """A closing market price for one calendar date."""

    date: date
    price: Decimal


@dataclass(frozen=True, slots=True)
class PricePoint:
    """A requested date and the actual market date used to price it."""

    requested_date: date
    actual_date: date
    price: Decimal


@dataclass(frozen=True, slots=True)
class HistoricalPriceSeries:
    """Validated completed daily observations for one requested period."""

    prices: tuple[PriceRecord, ...]
    requested_start_date: date
    requested_end_date: date

    @property
    def first_available_date(self) -> date:
        return self.prices[0].date

    @property
    def last_available_date(self) -> date:
        """The provider-independent effective historical end date."""

        return self.prices[-1].date

    def through(self, end_date: date) -> "HistoricalPriceSeries":
        """Return the same fetched series restricted to a common boundary."""

        prices = tuple(item for item in self.prices if item.date <= end_date)
        if not prices:
            raise ValueError("No historical prices exist through the requested boundary")
        return HistoricalPriceSeries(
            prices=prices,
            requested_start_date=self.requested_start_date,
            requested_end_date=self.requested_end_date,
        )


