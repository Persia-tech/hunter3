"""Yahoo Finance implementation of the market-data provider contract."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import yfinance as yf

from backend.app.models.price import PriceRecord


class YFinanceProvider:
    """Download adjusted daily closing prices through ``yfinance``.

    Yahoo's ``end`` argument is exclusive, so this class adds one day to make
    the public provider contract's end date inclusive.
    """

    def get_historical_prices(
        self, provider_ticker: str, start_date: date, end_date: date
    ) -> list[PriceRecord]:
        history = yf.Ticker(provider_ticker).history(
            start=start_date.isoformat(),
            end=(end_date + timedelta(days=1)).isoformat(),
            interval="1d",
            auto_adjust=True,
            actions=False,
        )
        return self._normalize_history(history)

    def get_latest_price(self, provider_ticker: str) -> PriceRecord | None:
        history = yf.Ticker(provider_ticker).history(
            period="5d",
            interval="1d",
            auto_adjust=True,
            actions=False,
        )
        prices = self._normalize_history(history)
        return prices[-1] if prices else None

    @staticmethod
    def _normalize_history(history: Any) -> list[PriceRecord]:
        if history is None or history.empty or "Close" not in history:
            return []

        prices: list[PriceRecord] = []
        for index, close in history["Close"].items():
            if close is None:
                continue
            price = Decimal(str(close))
            if not price.is_finite() or price <= 0:
                continue
            prices.append(PriceRecord(date=index.date(), price=price))
        return sorted(prices, key=lambda record: record.date)

