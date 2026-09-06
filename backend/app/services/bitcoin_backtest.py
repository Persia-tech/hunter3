"""Historical validation helpers for the Bitcoin cycle engine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from statistics import median

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


@dataclass(frozen=True, slots=True)
class BacktestBandSummary:
    band: str
    count: int
    median_return_180d_pct: float | None
    median_return_365d_pct: float | None
    median_return_730d_pct: float | None
    positive_365d_rate_pct: float | None
    gain_50pct_365d_rate_pct: float | None
    drawdown_30pct_365d_rate_pct: float | None
    median_max_gain_365d_pct: float | None
    median_max_drawdown_365d_pct: float | None


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


def _median(values: list[float]) -> float | None:
    return median(values) if values else None


def _rate(values: list[float], predicate) -> float | None:  # type: ignore[no-untyped-def]
    if not values:
        return None
    return sum(1 for value in values if predicate(value)) / len(values) * 100


def summarize_score_bands(
    points: list[BitcoinBacktestPoint],
    *,
    score_name: str,
) -> list[BacktestBandSummary]:
    """Summarize realized future outcomes for fixed 20-point score bands.

    This is a validation-only view. Future outcomes never feed back into the
    score calculation. Bands are fixed before looking at outcomes so the report
    is easier to compare between model revisions.
    """
    if score_name not in {"opportunity_score", "overheat_score"}:
        raise ValueError("score_name must be opportunity_score or overheat_score")

    bands = (
        (0, 19, "00-19"),
        (20, 39, "20-39"),
        (40, 59, "40-59"),
        (60, 79, "60-79"),
        (80, 100, "80-100"),
    )

    summaries: list[BacktestBandSummary] = []
    for low, high, label in bands:
        selected = [
            point
            for point in points
            if low <= int(getattr(point, score_name)) <= high
        ]

        r180 = [
            point.future_return_180d_pct
            for point in selected
            if point.future_return_180d_pct is not None
        ]
        r365 = [
            point.future_return_365d_pct
            for point in selected
            if point.future_return_365d_pct is not None
        ]
        r730 = [
            point.future_return_730d_pct
            for point in selected
            if point.future_return_730d_pct is not None
        ]
        gains = [
            point.future_max_gain_365d_pct
            for point in selected
            if point.future_max_gain_365d_pct is not None
        ]
        drawdowns = [
            point.future_max_drawdown_365d_pct
            for point in selected
            if point.future_max_drawdown_365d_pct is not None
        ]

        summaries.append(
            BacktestBandSummary(
                band=label,
                count=len(selected),
                median_return_180d_pct=_median(r180),
                median_return_365d_pct=_median(r365),
                median_return_730d_pct=_median(r730),
                positive_365d_rate_pct=_rate(r365, lambda value: value > 0),
                gain_50pct_365d_rate_pct=_rate(r365, lambda value: value >= 50),
                drawdown_30pct_365d_rate_pct=_rate(drawdowns, lambda value: value <= -30),
                median_max_gain_365d_pct=_median(gains),
                median_max_drawdown_365d_pct=_median(drawdowns),
            )
        )

    return summaries
