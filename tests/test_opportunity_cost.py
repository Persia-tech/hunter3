from datetime import date, timedelta
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
                PriceRecord(date(2018, 11, 23), Decimal("15")),
                PriceRecord(date(2020, 11, 17), Decimal("20")),
            ],
            "BTC-USD": [
                PriceRecord(date(2017, 11, 3), Decimal("5")),
                PriceRecord(date(2018, 11, 23), Decimal("8")),
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


def custom_item(**overrides):
    custom = {
        "id": "custom:sony-tv", "name": "Sony OLED TV",
        "purchase_date": "2018-11-23", "price_usd": "1999.99",
        "quantity": 1, "category": "Electronics",
    }
    custom.update(overrides)
    return {"custom": custom}


def opportunity_client(monkeypatch):
    monkeypatch.setenv("LOCAL_DEV_AUTH_BYPASS", "1")
    provider = Provider()
    market = MarketDataService(provider, max_attempts=1)

    class Calculator:
        _market_data = market

    return TestClient(create_app(calculator=Calculator())), provider


def test_custom_purchase_calculation_and_quantity(monkeypatch):
    client, _ = opportunity_client(monkeypatch)
    response = client.post("/api/opportunity-cost/calculate", json={
        "asset": "AAPL", "items": [custom_item(quantity=2)],
    })
    assert response.status_code == 200
    result = response.json()
    assert result["summary"]["total_spent"] == "3999.98"
    assert Decimal(result["summary"]["investment_units"]) == Decimal("3999.98") / Decimal("15")
    assert result["items"][0]["product"]["custom"] is True
    assert result["items"][0]["quantity"] == 2


def test_invalid_custom_price_date_and_future_date(monkeypatch):
    client, _ = opportunity_client(monkeypatch)
    base = {"asset": "AAPL"}
    assert client.post("/api/opportunity-cost/calculate", json={**base, "items": [custom_item(price_usd="0")]}).status_code == 422
    assert client.post("/api/opportunity-cost/calculate", json={**base, "items": [custom_item(purchase_date="not-a-date")]}).status_code == 422
    future = (date.today() + timedelta(days=366)).isoformat()
    response = client.post("/api/opportunity-cost/calculate", json={**base, "items": [custom_item(purchase_date=future)]})
    assert response.status_code == 422
    assert "future" in response.text


def test_custom_purchase_before_asset_inception(monkeypatch):
    client, _ = opportunity_client(monkeypatch)
    response = client.post("/api/opportunity-cost/calculate", json={
        "asset": "NVDA", "items": [custom_item()],
    })
    assert response.status_code == 200
    assert response.json()["items"][0]["eligible"] is False


def test_compare_multiple_assets_ranking_mixed_items_and_cache(monkeypatch):
    client, provider = opportunity_client(monkeypatch)
    payload = {"assets": ["AAPL", "BTC", "NVDA"], "items": [
        {"product_id": "iphone-x", "quantity": 1}, custom_item(),
    ]}
    response = client.post("/api/opportunity-cost/compare", json=payload)
    assert response.status_code == 200
    body = response.json()
    values = [Decimal(result["summary"]["current_value"]) for result in body["results"]]
    assert values == sorted(values, reverse=True)
    assert {item["product"]["custom"] for item in body["results"][0]["items"]} == {False, True}
    assert provider.history_calls == 3
    client.post("/api/opportunity-cost/compare", json=payload)
    assert provider.history_calls == 3


def test_compare_accepts_five_assets_and_rejects_six(monkeypatch):
    client, _ = opportunity_client(monkeypatch)
    five = ["BTC", "AAPL", "NVDA", "SPY", "QQQ"]
    assert client.post("/api/opportunity-cost/compare", json={"assets": five, "items": [custom_item()]}).status_code == 200
    response = client.post("/api/opportunity-cost/compare", json={
        "assets": five + ["GLD"], "items": [custom_item()],
    })
    assert response.status_code == 422


def test_current_price_snapshot_is_consistent_across_comparison_paths():
    class MovingProvider(Provider):
        def __init__(self):
            super().__init__()
            self.latest_calls: dict[str, int] = {}

        def get_latest_price(self, ticker):
            self.latest_calls[ticker] = self.latest_calls.get(ticker, 0) + 1
            base = super().get_latest_price(ticker)
            if base is None:
                return None
            return PriceRecord(base.date, base.price + self.latest_calls[ticker] - 1)

    provider = MovingProvider()
    service = OpportunityCostService(MarketDataService(provider, max_attempts=1))
    snapshot_id = service.create_snapshot()
    manual = service.rank((get_asset("BTC"),), purchases(), snapshot_id)[0]
    automatic = service.rank((get_asset("AAPL"), get_asset("BTC")), purchases(), snapshot_id)
    repeated_btc = next(result for result in automatic if result.asset.symbol == "BTC")

    assert manual.current_price == repeated_btc.current_price
    assert manual.current_value == repeated_btc.current_value
    assert provider.latest_calls["BTC-USD"] == 1
