from datetime import date, datetime, timezone

import pytest

from backend.app.models.market import Asset, AssetClass, Candle
from backend.app.providers.yfinance_provider import YFinanceProvider
from backend.app.services.market_temperature import calculate_temperature


def candles(count, start=100.0, step=1.0):
    return [Candle(date(2020, 1, 1), start + index * step) for index in range(count)]


def test_reference_indicator_and_score_semantics_are_preserved():
    result = calculate_temperature(
        Asset("TEST", "Test", AssetClass.BROAD_MARKET_ETF),
        weekly=candles(210),
        daily=candles(220, 200),
        full_history=candles(230),
        now=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert result.weekly_rsi == 100.0
    assert result.sma_200w == pytest.approx(209.5)
    assert result.sma_200d == pytest.approx(319.5)
    assert result.sma_10m == pytest.approx(288.0)
    assert result.momentum_12m == pytest.approx(52 / 257)
    assert result.drawdown_percent == 0.0
    assert result.opportunity_score == 0
    assert result.overheat_score == 80
    assert result.classification == "Overbought"


def test_provider_always_excludes_newest_possibly_partial_week(monkeypatch):
    provider = YFinanceProvider()
    history = candles(3)
    monkeypatch.setattr(provider, "_history", lambda **_kwargs: history)
    assert provider.completed_weekly_history("TEST") == history[:-1]


def test_market_temperature_universe_matches_reference():
    from scripts.refresh_market_temperature import MARKET_ASSETS
    assert [asset.symbol for asset in MARKET_ASSETS] == [
        "BTC-USD", "ETH-USD", "SPY", "VOO", "VTI", "QQQ", "SCHD", "AAPL", "MSFT", "GOOGL",
        "AMZN", "NVDA", "META", "TSLA", "GLD", "SLV", "PPLT", "XLE", "VDE", "XLB",
    ]
