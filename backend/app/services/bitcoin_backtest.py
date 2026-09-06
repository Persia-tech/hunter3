"""Historical validation helpers for the Bitcoin cycle engine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from backend.app.models.price import PriceRecord
from backend.app.services.bitcoin_cycle import BitcoinCycleResult, calculate_bitcoin_cycle


@dataclass(frozen=True, slots=True)
class BitcoinBacktestPoint:
    as_of: date
    price: float
    opportunity_score: int
    overheat_score: int
    future_return_180d_pct: float | None
    future_return_365d_pct: float | None
    future_return_730d_pct: float | None
    future_max_gain_365d_pct: float | None
    future_max_drawdown_365d_pct: float | None


def _future_return(prices: list[float], index: int, days: int) -> float | None:
    target = index + days
    if target >= len(prices):
        return None
    return (prices[target] / prices[index] - 1.0) * 100


def _future_extremes(prices: list[float], index: int, days: int) -> tuple[float | None, float | None]:
    if index + 1 >= len(prices):
        return None, None

    end = min(len(prices), index + days + 1)
    window = prices[index + 1 : end]
    if not window:
        return None, None

    base = prices[index]
    max_gain = (max(window) / base - 1.0) * 100
    max_drawdown = (min(window) / base - 1.0) * 100
    return max_gain, max_drawdown


def build_bitcoin_backtest(
    records: list[PriceRecord],
    *,
    minimum_history_days: int = 400,
    step_days: int = 1,
) -> list[BitcoinBacktestPoint]:
    """Run the BTC cycle engine point-in-time through history.

    Each snapshot only receives records available on that date, preventing
    look-ahead in the indicators themselves. Future returns are attached only
    afterward for validation and are never inputs to the score.
    """
    if minimum_history_days < 400:
        raise ValueError("minimum_history_days must be at least 400")
    if step_days < 1:
        raise ValueError("step_days must be positive")

    ordered = sorted(records, key=lambda item: item.date)
    if len(ordered) < minimum_history_days:
        return []

    prices = [float(item.price) for item in ordered]
    points: list[BitcoinBacktestPoint] = []

    for index in range(minimum_history_days - 1, len(ordered), step_days):
        result: BitcoinCycleResult = calculate_bitcoin_cycle(ordered[: index + 1])
        max_gain, max_drawdown = _future_extremes(prices, index, 365)

        points.append(
            BitcoinBacktestPoint(
                as_of=result.as_of,
                price=result.price,
                opportunity_score=result.opportunity_score,
                overheat_score=result.overheat_score,
                future_return_180d_pct=_future_return(prices, index, 180),
                future_return_365d_pct=_future_return(prices, index, 365),
                future_return_730d_pct=_future_return(prices, index, 730),
                future_max_gain_365d_pct=max_gain,
                future_max_drawdown_365d_pct=max_drawdown,
            )
        )

    return points


def nearest_backtest_point(
    points: list[BitcoinBacktestPoint],
    target: date,
) -> BitcoinBacktestPoint | None:
    if not points:
        return None
    return min(points, key=lambda point: abs((point.as_of - target).days))
