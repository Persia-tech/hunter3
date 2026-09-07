"""No-look-ahead validation helpers for Bitcoin on-chain valuation metrics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from statistics import median

from backend.app.services.bitcoin_onchain_research import OnChainResearchRow


@dataclass(frozen=True, slots=True)
class OnChainBacktestPoint:
    date: date
    price_usd: float
    mvrv: float | None
    mvrv_z: float | None
    mvrv_percentile: float | None
    mvrv_z_percentile: float | None
    future_return_180d_pct: float | None
    future_return_365d_pct: float | None
    future_max_drawdown_365d_pct: float | None


@dataclass(frozen=True, slots=True)
class ThresholdSummary:
    label: str
    count: int
    median_return_365d_pct: float | None
    positive_365d_rate_pct: float | None
    drawdown_30pct_rate_pct: float | None


def expanding_percentile(value: float, history: list[float]) -> float | None:
    """Return a mid-rank percentile using only the supplied historical sample.

    Callers are responsible for supplying only values known through the date
    being evaluated. Including today's observation is intentional and matches
    the existing no-look-ahead backtest convention used by this research layer.
    """
    if not history:
        return None
    less = sum(1 for item in history if item < value)
    equal = sum(1 for item in history if item == value)
    return 100.0 * (less + 0.5 * equal) / len(history)


# Backward-compatible private alias for existing research code/tests.
def _percentile(value: float, history: list[float]) -> float | None:
    return expanding_percentile(value, history)


def build_onchain_point_in_time_backtest(
    rows: list[OnChainResearchRow],
    *,
    minimum_history_days: int = 730,
) -> list[OnChainBacktestPoint]:
    """Build expanding-history percentile signals without future leakage.

    Today's percentile is calculated from metric values available through today
    only. Future returns/drawdowns are copied from precomputed validation labels
    and never participate in percentile calculation.
    """
    if minimum_history_days < 30:
        raise ValueError("minimum_history_days must be at least 30")

    ordered = sorted(rows, key=lambda row: row.date)
    mvrv_history: list[float] = []
    mvrv_z_history: list[float] = []
    points: list[OnChainBacktestPoint] = []

    for index, row in enumerate(ordered):
        mvrv = None if row.mvrv is None else float(row.mvrv)
        mvrv_z = None if row.mvrv_z is None else float(row.mvrv_z)

        if mvrv is not None:
            mvrv_history.append(mvrv)
        if mvrv_z is not None:
            mvrv_z_history.append(mvrv_z)

        if index + 1 < minimum_history_days or row.price_usd is None:
            continue

        points.append(
            OnChainBacktestPoint(
                date=row.date,  # type: ignore[arg-type]
                price_usd=float(row.price_usd),
                mvrv=mvrv,
                mvrv_z=mvrv_z,
                mvrv_percentile=None if mvrv is None else expanding_percentile(mvrv, mvrv_history),
                mvrv_z_percentile=None if mvrv_z is None else expanding_percentile(mvrv_z, mvrv_z_history),
                future_return_180d_pct=row.future_return_180d_pct,
                future_return_365d_pct=row.future_return_365d_pct,
                future_max_drawdown_365d_pct=row.future_max_drawdown_365d_pct,
            )
        )

    return points


def _rate(values: list[float], predicate) -> float | None:  # type: ignore[no-untyped-def]
    if not values:
        return None
    return 100.0 * sum(1 for value in values if predicate(value)) / len(values)


def summarize_condition(points: list[OnChainBacktestPoint], *, label: str, predicate) -> ThresholdSummary:  # type: ignore[no-untyped-def]
    selected = [point for point in points if predicate(point)]
    returns = [
        point.future_return_365d_pct
        for point in selected
        if point.future_return_365d_pct is not None
    ]
    drawdowns = [
        point.future_max_drawdown_365d_pct
        for point in selected
        if point.future_max_drawdown_365d_pct is not None
    ]
    return ThresholdSummary(
        label=label,
        count=len(selected),
        median_return_365d_pct=median(returns) if returns else None,
        positive_365d_rate_pct=_rate(returns, lambda value: value > 0),
        drawdown_30pct_rate_pct=_rate(drawdowns, lambda value: value <= -30),
    )


def independent_episodes(
    points: list[OnChainBacktestPoint],
    *,
    predicate,
    cooldown_days: int = 90,
) -> list[OnChainBacktestPoint]:  # type: ignore[no-untyped-def]
    """Return first entries into a condition, suppressing clustered re-entries."""
    episodes: list[OnChainBacktestPoint] = []
    was_true = False
    last_selected: date | None = None
    for point in points:
        active = bool(predicate(point))
        crossed = active and not was_true
        if crossed:
            far_enough = last_selected is None or (point.date - last_selected).days >= cooldown_days
            if far_enough:
                episodes.append(point)
                last_selected = point.date
        was_true = active
    return episodes


def default_threshold_summaries(points: list[OnChainBacktestPoint]) -> list[ThresholdSummary]:
    """Evaluate predeclared fixed and expanding-percentile valuation conditions."""
    specs = (
        ("MVRV <= 1.0", lambda p: p.mvrv is not None and p.mvrv <= 1.0),
        ("MVRV <= 1.5", lambda p: p.mvrv is not None and p.mvrv <= 1.5),
        ("MVRV >= 3.0", lambda p: p.mvrv is not None and p.mvrv >= 3.0),
        ("MVRV >= 4.0", lambda p: p.mvrv is not None and p.mvrv >= 4.0),
        ("MVRV pct <= 10", lambda p: p.mvrv_percentile is not None and p.mvrv_percentile <= 10),
        ("MVRV pct <= 20", lambda p: p.mvrv_percentile is not None and p.mvrv_percentile <= 20),
        ("MVRV pct >= 80", lambda p: p.mvrv_percentile is not None and p.mvrv_percentile >= 80),
        ("MVRV pct >= 90", lambda p: p.mvrv_percentile is not None and p.mvrv_percentile >= 90),
        ("MVRV-Z pct <= 10", lambda p: p.mvrv_z_percentile is not None and p.mvrv_z_percentile <= 10),
        ("MVRV-Z pct <= 20", lambda p: p.mvrv_z_percentile is not None and p.mvrv_z_percentile <= 20),
        ("MVRV-Z pct >= 80", lambda p: p.mvrv_z_percentile is not None and p.mvrv_z_percentile >= 80),
        ("MVRV-Z pct >= 90", lambda p: p.mvrv_z_percentile is not None and p.mvrv_z_percentile >= 90),
    )
    return [summarize_condition(points, label=label, predicate=predicate) for label, predicate in specs]
