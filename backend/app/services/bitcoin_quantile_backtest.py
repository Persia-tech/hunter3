"""No-look-ahead validation helpers for the research Bitcoin quantile model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from statistics import median
from typing import Callable

from backend.app.models.price import PriceRecord
from backend.app.services.bitcoin_quantile import (
    BitcoinQuantileModel,
    BitcoinQuantileSnapshot,
    fit_bitcoin_quantile_model,
    snapshot_bitcoin_quantile,
)


@dataclass(frozen=True, slots=True)
class QuantileBacktestPoint:
    as_of: date
    price: float
    quantile_percentile: float
    model_fit_date: date
    future_return_180d_pct: float | None
    future_return_365d_pct: float | None
    future_max_gain_365d_pct: float | None
    future_max_drawdown_365d_pct: float | None


@dataclass(frozen=True, slots=True)
class QuantileThresholdSummary:
    label: str
    count: int
    median_return_365d_pct: float | None
    positive_365d_rate_pct: float | None
    gain_50pct_365d_rate_pct: float | None
    drawdown_30pct_365d_rate_pct: float | None


def _future_return(prices: list[float], index: int, days: int) -> float | None:
    target = index + days
    if target >= len(prices):
        return None
    return (prices[target] / prices[index] - 1.0) * 100.0


def _future_extremes(prices: list[float], index: int, days: int) -> tuple[float | None, float | None]:
    if index + 1 >= len(prices):
        return None, None
    end = min(len(prices), index + days + 1)
    window = prices[index + 1 : end]
    if not window:
        return None, None
    base = prices[index]
    return (
        (max(window) / base - 1.0) * 100.0,
        (min(window) / base - 1.0) * 100.0,
    )


def build_quantile_backtest(
    records: list[PriceRecord],
    *,
    minimum_history_days: int = 730,
    refit_days: int = 90,
    fit_initializations: int = 2,
    fit_maxiter: int = 900,
    fit_model_func: Callable[..., BitcoinQuantileModel] = fit_bitcoin_quantile_model,
    snapshot_func: Callable[..., BitcoinQuantileSnapshot] = snapshot_bitcoin_quantile,
) -> list[QuantileBacktestPoint]:
    """Build an expanding-window, point-in-time quantile backtest.

    The expensive quantile model is refit on an expanding history every
    ``refit_days`` calendar observations. Between refits, the most recently
    fitted model is carried forward. Each fit only sees prices available on
    its fit date, so the percentile input is free of future data. Forward
    returns are attached afterward as validation labels only.
    """
    if minimum_history_days < 365:
        raise ValueError("minimum_history_days must be at least 365")
    if refit_days < 1:
        raise ValueError("refit_days must be positive")
    if fit_initializations < 1:
        raise ValueError("fit_initializations must be positive")
    if fit_maxiter < 1:
        raise ValueError("fit_maxiter must be positive")

    ordered = sorted(records, key=lambda item: item.date)
    if len(ordered) < minimum_history_days:
        return []

    prices = [float(item.price) for item in ordered]
    points: list[QuantileBacktestPoint] = []
    model: BitcoinQuantileModel | None = None
    model_fit_date: date | None = None
    last_fit_index: int | None = None

    start_index = minimum_history_days - 1
    for index in range(start_index, len(ordered)):
        should_refit = model is None or last_fit_index is None or (index - last_fit_index) >= refit_days
        if should_refit:
            model = fit_model_func(
                ordered[: index + 1],
                initializations=fit_initializations,
                maxiter=fit_maxiter,
            )
            model_fit_date = ordered[index].date
            last_fit_index = index

        assert model is not None
        assert model_fit_date is not None
        current = ordered[index]
        snapshot = snapshot_func(
            model,
            day=current.date,
            price=float(current.price),
        )
        max_gain, max_drawdown = _future_extremes(prices, index, 365)

        points.append(
            QuantileBacktestPoint(
                as_of=current.date,
                price=float(current.price),
                quantile_percentile=float(snapshot.percentile),
                model_fit_date=model_fit_date,
                future_return_180d_pct=_future_return(prices, index, 180),
                future_return_365d_pct=_future_return(prices, index, 365),
                future_max_gain_365d_pct=max_gain,
                future_max_drawdown_365d_pct=max_drawdown,
            )
        )

    return points


def independent_threshold_episodes(
    points: list[QuantileBacktestPoint],
    *,
    threshold: float,
    direction: str,
    cooldown_days: int = 90,
) -> list[QuantileBacktestPoint]:
    """Return distinct threshold-entry episodes with a cooldown."""
    if direction not in {"low", "high"}:
        raise ValueError("direction must be 'low' or 'high'")
    if cooldown_days < 0:
        raise ValueError("cooldown_days must be non-negative")

    episodes: list[QuantileBacktestPoint] = []
    was_inside = False
    last_selected: date | None = None

    for point in points:
        inside = (
            point.quantile_percentile <= threshold
            if direction == "low"
            else point.quantile_percentile >= threshold
        )
        entered = inside and not was_inside
        if entered:
            far_enough = last_selected is None or (point.as_of - last_selected).days >= cooldown_days
            if far_enough:
                episodes.append(point)
                last_selected = point.as_of
        was_inside = inside

    return episodes


def _median(values: list[float]) -> float | None:
    return median(values) if values else None


def _rate(values: list[float], predicate) -> float | None:  # type: ignore[no-untyped-def]
    if not values:
        return None
    return 100.0 * sum(1 for value in values if predicate(value)) / len(values)


def summarize_threshold(
    points: list[QuantileBacktestPoint],
    *,
    threshold: float,
    direction: str,
) -> QuantileThresholdSummary:
    if direction not in {"low", "high"}:
        raise ValueError("direction must be 'low' or 'high'")
    selected = [
        point
        for point in points
        if (
            point.quantile_percentile <= threshold
            if direction == "low"
            else point.quantile_percentile >= threshold
        )
    ]
    returns = [point.future_return_365d_pct for point in selected if point.future_return_365d_pct is not None]
    drawdowns = [
        point.future_max_drawdown_365d_pct
        for point in selected
        if point.future_max_drawdown_365d_pct is not None
    ]
    symbol = "<=" if direction == "low" else ">="
    return QuantileThresholdSummary(
        label=f"Q% {symbol} {threshold:g}",
        count=len(selected),
        median_return_365d_pct=_median(returns),
        positive_365d_rate_pct=_rate(returns, lambda value: value > 0),
        gain_50pct_365d_rate_pct=_rate(returns, lambda value: value >= 50),
        drawdown_30pct_365d_rate_pct=_rate(drawdowns, lambda value: value <= -30),
    )


def summarize_percentile_bands(points: list[QuantileBacktestPoint]) -> list[tuple[str, int, float | None]]:
    bands = (
        (0.0, 10.0, "00-10"),
        (10.0, 25.0, "10-25"),
        (25.0, 50.0, "25-50"),
        (50.0, 75.0, "50-75"),
        (75.0, 90.0, "75-90"),
        (90.0, 100.000001, "90-100"),
    )
    result: list[tuple[str, int, float | None]] = []
    for low, high, label in bands:
        selected = [
            point
            for point in points
            if low <= point.quantile_percentile < high and point.future_return_365d_pct is not None
        ]
        returns = [point.future_return_365d_pct for point in selected if point.future_return_365d_pct is not None]
        result.append((label, len(selected), _median(returns)))
    return result
