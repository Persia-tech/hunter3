"""Research-only confluence analysis for independent Bitcoin signal families.

This module intentionally does not create a composite score or fit weights. It
joins already point-in-time/no-look-ahead research outputs by date and evaluates
predeclared threshold combinations.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from statistics import median


@dataclass(frozen=True, slots=True)
class ConfluencePoint:
    date: date
    price: float
    opportunity_score: float
    quantile_percentile: float
    mvrv_percentile: float
    future_return_365d_pct: float | None
    future_max_drawdown_365d_pct: float | None


@dataclass(frozen=True, slots=True)
class ConfluenceSummary:
    label: str
    count: int
    valid_365d: int
    median_return_365d_pct: float | None
    positive_365d_rate_pct: float | None
    gain_50pct_365d_rate_pct: float | None
    drawdown_30pct_rate_pct: float | None


@dataclass(frozen=True, slots=True)
class ConfluenceSpec:
    label: str
    require_opportunity: bool = False
    require_quantile: bool = False
    require_mvrv: bool = False


DEFAULT_SPECS = (
    ConfluenceSpec("Opportunity >= 60", require_opportunity=True),
    ConfluenceSpec("Quantile <= 10", require_quantile=True),
    ConfluenceSpec("MVRV pct <= 20", require_mvrv=True),
    ConfluenceSpec("Quantile <= 10 + MVRV pct <= 20", require_quantile=True, require_mvrv=True),
    ConfluenceSpec("Opportunity >= 60 + MVRV pct <= 20", require_opportunity=True, require_mvrv=True),
    ConfluenceSpec("Opportunity >= 60 + Quantile <= 10", require_opportunity=True, require_quantile=True),
    ConfluenceSpec(
        "Opportunity >= 60 + Quantile <= 10 + MVRV pct <= 20",
        require_opportunity=True,
        require_quantile=True,
        require_mvrv=True,
    ),
)


def condition_matches(
    point: ConfluencePoint,
    spec: ConfluenceSpec,
    *,
    opportunity_threshold: float = 60.0,
    quantile_threshold: float = 10.0,
    mvrv_percentile_threshold: float = 20.0,
) -> bool:
    if spec.require_opportunity and point.opportunity_score < opportunity_threshold:
        return False
    if spec.require_quantile and point.quantile_percentile > quantile_threshold:
        return False
    if spec.require_mvrv and point.mvrv_percentile > mvrv_percentile_threshold:
        return False
    return True


def _rate(values: list[float], predicate) -> float | None:  # type: ignore[no-untyped-def]
    if not values:
        return None
    return 100.0 * sum(1 for value in values if predicate(value)) / len(values)


def summarize_spec(points: list[ConfluencePoint], spec: ConfluenceSpec) -> ConfluenceSummary:
    selected = [point for point in points if condition_matches(point, spec)]
    returns = [p.future_return_365d_pct for p in selected if p.future_return_365d_pct is not None]
    drawdowns = [
        p.future_max_drawdown_365d_pct
        for p in selected
        if p.future_max_drawdown_365d_pct is not None
    ]
    return ConfluenceSummary(
        label=spec.label,
        count=len(selected),
        valid_365d=len(returns),
        median_return_365d_pct=median(returns) if returns else None,
        positive_365d_rate_pct=_rate(returns, lambda value: value > 0),
        gain_50pct_365d_rate_pct=_rate(returns, lambda value: value >= 50),
        drawdown_30pct_rate_pct=_rate(drawdowns, lambda value: value <= -30),
    )


def summarize_default_confluence(points: list[ConfluencePoint]) -> list[ConfluenceSummary]:
    return [summarize_spec(points, spec) for spec in DEFAULT_SPECS]


def independent_confluence_episodes(
    points: list[ConfluencePoint],
    spec: ConfluenceSpec,
    *,
    cooldown_days: int = 90,
) -> list[ConfluencePoint]:
    """Return first entries into a confluence condition with cooldown suppression."""
    if cooldown_days < 0:
        raise ValueError("cooldown_days must be non-negative")

    episodes: list[ConfluencePoint] = []
    was_inside = False
    last_selected: date | None = None
    for point in sorted(points, key=lambda item: item.date):
        inside = condition_matches(point, spec)
        entered = inside and not was_inside
        if entered:
            far_enough = last_selected is None or (point.date - last_selected).days >= cooldown_days
            if far_enough:
                episodes.append(point)
                last_selected = point.date
        was_inside = inside
    return episodes
