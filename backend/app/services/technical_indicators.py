"""Pure long-term technical indicators.

Inputs are oldest-to-newest completed candles. Partial weekly candles should be
kept outside these calculations by the market-data adapter.
"""

from __future__ import annotations

from collections.abc import Sequence

from backend.app.models.market import Divergence


def simple_moving_average(values: Sequence[float], period: int) -> float | None:
    if period <= 0:
        raise ValueError("period must be positive")
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def rsi_series(values: Sequence[float], period: int = 14) -> list[float | None]:
    """Return Wilder RSI aligned with values, including leading None entries."""
    result: list[float | None] = [None] * len(values)

    if period <= 0:
        raise ValueError("period must be positive")

    if len(values) <= period:
        return result

    changes = [values[i] - values[i - 1] for i in range(1, len(values))]

    gain = sum(max(change, 0.0) for change in changes[:period]) / period
    loss = sum(max(-change, 0.0) for change in changes[:period]) / period

    def value() -> float:
        if loss == 0:
            return 100.0 if gain else 50.0

        return 100.0 - 100.0 / (1.0 + gain / loss)

    result[period] = value()

    for index in range(period + 1, len(values)):
        change = changes[index - 1]

        gain = (gain * (period - 1) + max(change, 0.0)) / period
        loss = (loss * (period - 1) + max(-change, 0.0)) / period

        result[index] = value()

    return result


def rsi(values: Sequence[float], period: int = 14) -> float | None:
    series = rsi_series(values, period)
    return series[-1] if series else None


def stochastic_rsi_series(
    values: Sequence[float],
    rsi_period: int = 14,
    stochastic_period: int = 14,
) -> list[float | None]:

    rsi_values = rsi_series(values, rsi_period)

    result: list[float | None] = [None] * len(values)

    for index, current in enumerate(rsi_values):

        start = index - stochastic_period + 1

        if current is None or start < 0:
            continue

        window = rsi_values[start : index + 1]

        if any(item is None for item in window):
            continue

        numeric = [float(item) for item in window if item is not None]

        low = min(numeric)
        high = max(numeric)

        result[index] = (
            50.0
            if high == low
            else 100 * (current - low) / (high - low)
        )

    return result


def stochastic_rsi(values: Sequence[float]) -> float | None:
    series = stochastic_rsi_series(values)
    return series[-1] if series else None


def ath_drawdown(values: Sequence[float]) -> tuple[float, float]:

    if not values:
        raise ValueError("values must not be empty")

    ath = max(values)

    drawdown = (values[-1] - ath) / ath * 100

    return ath, drawdown


def momentum(values: Sequence[float], periods: int) -> float | None:

    if periods <= 0:
        raise ValueError("periods must be positive")

    if len(values) <= periods:
        return None

    previous = values[-periods - 1]

    if previous == 0:
        return None

    return values[-1] / previous - 1


def _swings(
    values: Sequence[float],
    radius: int,
    low: bool,
) -> list[int]:

    indexes: list[int] = []

    for index in range(radius, len(values) - radius):

        window = values[index - radius : index + radius + 1]

        target = min(window) if low else max(window)

        if values[index] == target and window.count(target) == 1:
            indexes.append(index)

    return indexes


def detect_rsi_divergence(
    prices: Sequence[float],
    rsi_values: Sequence[float | None],
    radius: int = 2,
    lookback: int = 26,
    minimum_separation: int = 3,
) -> Divergence:
    """Conservative divergence based on confirmed weekly swing pairs."""

    if (
        len(prices) != len(rsi_values)
        or len(prices) < radius * 2 + minimum_separation + 1
    ):
        return Divergence.NONE

    start = max(0, len(prices) - lookback)

    numeric_rsi = [
        value if value is not None else float("nan")
        for value in rsi_values
    ]

    lows = [
        i
        for i in _swings(prices, radius, True)
        if i >= start and rsi_values[i] is not None
    ]

    highs = [
        i
        for i in _swings(prices, radius, False)
        if i >= start and rsi_values[i] is not None
    ]

    if len(lows) >= 2:

        first, second = lows[-2:]

        if (
            second - first >= minimum_separation
            and prices[second] < prices[first] * 0.995
            and numeric_rsi[second] > numeric_rsi[first] + 2
        ):
            return Divergence.BULLISH

    if len(highs) >= 2:

        first, second = highs[-2:]

        if (
            second - first >= minimum_separation
            and prices[second] > prices[first] * 1.005
            and numeric_rsi[second] < numeric_rsi[first] - 2
        ):
            return Divergence.BEARISH

    return Divergence.NONE