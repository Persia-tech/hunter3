"""Research-only Bitcoin top/overheating confluence analysis.

This module keeps the three top-risk signal families separate:
- price/technical overheating via Overheat score,
- statistical valuation via high Quantile percentile,
- on-chain valuation via high MVRV historical percentile.

Thresholds are fixed in advance. No composite weights are fitted and no
production score is changed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from statistics import median


@dataclass(frozen=True, slots=True)
class TopConfluencePoint:
    date: date
    price: float
    overheat_score: float
    quantile_percentile: float
    mvrv_percentile: float
    future_return_365d_pct: float | None
    future_max_drawdown_365d_pct: float | None


@dataclass(frozen=True, slots=True)
class TopSpec:
    label: str
    require_overheat: bool = False
    require_quantile: bool = False
    require_mvrv: bool = False


@dataclass(frozen=True, slots=True)
class TopSummary:
    label: str
    count: int
    valid_365d: int
    median_return_365d_pct: float | None
    negative_365d_rate_pct: float | None
    loss_30pct_365d_rate_pct: float | None
    drawdown_30pct_rate_pct: float | None


OVERHEAT_THRESHOLD = 60.0
QUANTILE_HIGH_THRESHOLD = 90.0
MVRV_HIGH_THRESHOLD = 90.0

DEFAULT_TOP_SPECS = (
    TopSpec("Overheat >= 60", require_overheat=True),
    TopSpec("Quantile >= 90", require_quantile=True),
    TopSpec("MVRV pct >= 90", require_mvrv=True),
    TopSpec("Quantile >= 90 + MVRV pct >= 90", require_quantile=True, require_mvrv=True),
    TopSpec("Overheat >= 60 + Quantile >= 90", require_overheat=True, require_quantile=True),
    TopSpec("Overheat >= 60 + MVRV pct >= 90", require_overheat=True, require_mvrv=True),
    TopSpec(
        "Overheat >= 60 + Quantile >= 90 + MVRV pct >= 90",
        require_overheat=True,
        require_quantile=True,
        require_mvrv=True,
    ),
)


def condition_matches(
    point: TopConfluencePoint,
    spec: TopSpec,
    *,
    overheat_threshold: float = OVERHEAT_THRESHOLD,
    quantile_threshold: float = QUANTILE_HIGH_THRESHOLD,
    mvrv_threshold: float = MVRV_HIGH_THRESHOLD,
) -> bool:
    if spec.require_overheat and point.overheat_score < overheat_threshold:
        return False
    if spec.require_quantile and point.quantile_percentile < quantile_threshold:
        return False
    if spec.require_mvrv and point.mvrv_percentile < mvrv_threshold:
        return False
    return True


def _rate(values: list[float], predicate) -> float | None:  # type: ignore[no-untyped-def]
    if not values:
        return None
    return 100.0 * sum(1 for value in values if predicate(value)) / len(values)


def summarize_top_spec(
    points: list[TopConfluencePoint],
    spec: TopSpec,
    *,
    overheat_threshold: float = OVERHEAT_THRESHOLD,
    quantile_threshold: float = QUANTILE_HIGH_THRESHOLD,
    mvrv_threshold: float = MVRV_HIGH_THRESHOLD,
) -> TopSummary:
    selected = [
        point
        for point in points
        if condition_matches(
            point,
            spec,
            overheat_threshold=overheat_threshold,
            quantile_threshold=quantile_threshold,
            mvrv_threshold=mvrv_threshold,
        )
    ]
    returns = [p.future_return_365d_pct for p in selected if p.future_return_365d_pct is not None]
    drawdowns = [
        p.future_max_drawdown_365d_pct
        for p in selected
        if p.future_max_drawdown_365d_pct is not None
    ]
    return TopSummary(
        label=spec.label,
        count=len(selected),
        valid_365d=len(returns),
        median_return_365d_pct=median(returns) if returns else None,
        negative_365d_rate_pct=_rate(returns, lambda value: value < 0),
        loss_30pct_365d_rate_pct=_rate(returns, lambda value: value <= -30),
        drawdown_30pct_rate_pct=_rate(drawdowns, lambda value: value <= -30),
    )


def summarize_default_top_confluence(points: list[TopConfluencePoint]) -> list[TopSummary]:
    return [summarize_top_spec(points, spec) for spec in DEFAULT_TOP_SPECS]


def independent_top_episodes(
    points: list[TopConfluencePoint],
    spec: TopSpec,
    *,
    cooldown_days: int = 90,
    overheat_threshold: float = OVERHEAT_THRESHOLD,
    quantile_threshold: float = QUANTILE_HIGH_THRESHOLD,
    mvrv_threshold: float = MVRV_HIGH_THRESHOLD,
) -> list[TopConfluencePoint]:
    """Return independent first entries into a fixed top-risk condition."""
    if cooldown_days < 0:
        raise ValueError("cooldown_days must be non-negative")

    episodes: list[TopConfluencePoint] = []
    was_inside = False
    last_selected: date | None = None
    for point in sorted(points, key=lambda item: item.date):
        inside = condition_matches(
            point,
            spec,
            overheat_threshold=overheat_threshold,
            quantile_threshold=quantile_threshold,
            mvrv_threshold=mvrv_threshold,
        )
        entered = inside and not was_inside
        if entered:
            far_enough = last_selected is None or (point.date - last_selected).days >= cooldown_days
            if far_enough:
                episodes.append(point)
                last_selected = point.date
        was_inside = inside
    return episodes
