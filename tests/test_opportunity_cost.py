from datetime import date
from decimal import Decimal

from backend.app.data.product_catalog import PRODUCT_BY_ID
from backend.app.models.asset import get_asset
from backend.app.models.opportunity_cost import Purchase
from backend.app.models.price import PriceRecord
from backend.app.services.dca_market_data import MarketDataService
from backend.app.services.opportunity_cost import OpportunityCostService
from backend.app.api.dca import create_app
from fastapi.testclient import TestClient


class Provider:
    def __init__(self):
        self.history_calls = 0

    def get_historical_prices(self, ticker, start, end):
        self.history_calls += 1
        values = {
            "AAPL": [
                PriceRecord(date(2017, 11, 6), Decimal("10")),
                PriceRecord(date(2020, 11, 17), Decimal("20")),
            ],
            "BTC-USD": [
                PriceRecord(date(2017, 11, 3), Decimal("5")),
                PriceRecord(date(2020, 11, 17), Decimal("25")),
            ],
            "NVDA": [PriceRecord(date(2020, 11, 17), Decimal("5"))],
        }
        return [row for row in values.get(ticker, []) if start <= row.date <= end]

    def get_latest_price(self, ticker):
        prices = {"AAPL": "40", "BTC-USD": "50", "NVDA": "100"}
        value = prices.get(ticker)
        return PriceRecord(date(2026, 1, 2), Decimal(value)) if value else None


def purchases():
    return (
        Purchase(PRODUCT_BY_ID["iphone-x"], 2),
        Purchase(PRODUCT_BY_ID["macbook-air-m1"], 1),
    )


def test_multiple_dates_weekend_quantity_totals_and_cache():
    provider = Provider()
    service = OpportunityCostService(MarketDataService(provider, max_attempts=1))
    result = service.calculate(get_asset("AAPL"), purchases())
    assert result.items[0].price_date == date(2017, 11, 6)
    assert result.total_spent == Decimal("2997")
    assert result.total_units == Decimal("249.75")
    assert result.current_value == Decimal("9990.00")
    assert result.gain == Decimal("6993.00")
    service.calculate(get_asset("AAPL"), purchases())
    assert provider.history_calls == 1


def test_asset_inception_and_missing_history_are_item_level_unavailable():
    service = OpportunityCostService(MarketDataService(Provider(), max_attempts=1))
    result = service.calculate(get_asset("NVDA"), purchases())
    assert result.items[0].eligible is False
    assert result.items[0].reason == "Not available at that time"
    assert result.items[1].eligible is True
    assert result.eligible_spent == Decimal("999")
    assert result.current_value == Decimal("19980")


def test_best_alternative_ranks_independent_purchase_histories():
    service = OpportunityCostService(MarketDataService(Provider(), max_attempts=1))
    ranked = service.rank((get_asset("AAPL"), get_asset("BTC"), get_asset("NVDA")), purchases())
    assert [row.asset.symbol for row in ranked] == ["BTC", "NVDA", "AAPL"]
    assert sum(item.eligible for item in ranked[1].items) == 1


def test_catalog_and_calculation_endpoints(monkeypatch):
    monkeypatch.setenv("LOCAL_DEV_AUTH_BYPASS", "1")
    market = MarketDataService(Provider(), max_attempts=1)

    class Calculator:
        _market_data = market

    client = TestClient(create_app(calculator=Calculator()))
    catalog = client.get("/api/opportunity-cost/products?category=iPhone")
    assert catalog.status_code == 200
    assert all(row["category"] == "iPhone" for row in catalog.json()["products"])
    response = client.post("/api/opportunity-cost/calculate", json={
        "asset": "AAPL", "items": [{"product_id": "iphone-x", "quantity": 2}]
    })
    assert response.status_code == 200
    assert response.json()["summary"]["total_spent"] == "1998"
