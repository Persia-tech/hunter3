from __future__ import annotations

from datetime import date

import yfinance as yf

from backend.app.models.market import Candle


class YFinanceProvider:
    def _history(
        self,
        symbol: str,
        period: str,
        interval: str,
    ) -> list[Candle]:
        ticker = yf.Ticker(symbol)

        df = ticker.history(
            period=period,
            interval=interval,
            auto_adjust=True,
            actions=False,
        )

        if df.empty:
            return []

        candles: list[Candle] = []

        for timestamp, row in df.iterrows():
            close = row.get("Close")

            if close is None:
                continue

            try:
                close_value = float(close)
            except (TypeError, ValueError):
                continue

            if close_value <= 0:
                continue

            candles.append(
                Candle(
                    timestamp=date(
                        timestamp.year,
                        timestamp.month,
                        timestamp.day,
                    ),
                    close=close_value,
                )
            )

        return candles

    def completed_weekly_history(
        self,
        symbol: str,
        years: int = 5,
    ) -> list[Candle]:
        candles = self._history(
            symbol=symbol,
            period=f"{years}y",
            interval="1wk",
        )

        # Drop the newest candle because the current week
        # may still be incomplete.
        if len(candles) > 1:
            candles = candles[:-1]

        return candles

    def daily_history(
        self,
        symbol: str,
        years: int = 2,
    ) -> list[Candle]:
        return self._history(
            symbol=symbol,
            period=f"{years}y",
            interval="1d",
        )

    def full_history(
        self,
        symbol: str,
    ) -> list[Candle]:
        return self._history(
            symbol=symbol,
            period="max",
            interval="1d",
        )