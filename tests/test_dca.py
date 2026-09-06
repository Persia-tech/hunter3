from datetime import date
from decimal import Decimal

from backend.app.models.asset import get_asset
from backend.app.models.dca import DCAFrequency
from backend.app.models.price import HistoricalPriceSeries, PriceRecord
from backend.app.services.dca_calculator import DCACalculator
from backend.app.services.dca_market_data import MarketDataService


class Provider:
    def get_historical_prices(self, _ticker, start, end):
        return [PriceRecord(date(2024, 1, 1), Decimal("10")), PriceRecord(date(2024, 2, 1), Decimal("20"))]
    def get_latest_price(self, _ticker):
        return PriceRecord(date(2024, 2, 1), Decimal("20"))


def test_dca_reference_regression():
    result = DCACalculator(MarketDataService(Provider())).calculate(
        get_asset("BTC"), date(2024, 1, 1), date(2024, 2, 1), DCAFrequency.MONTHLY, Decimal("100")
    )
    assert result.number_of_purchases == 2
    assert result.total_units == Decimal("15")
    assert result.total_invested == Decimal("200")
    assert result.current_value == Decimal("300")
    assert result.total_return_percentage == Decimal("50.0")
