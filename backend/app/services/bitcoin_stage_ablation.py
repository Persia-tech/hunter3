"""Research-only ablation of Bitcoin staged accumulation components.

The experiment keeps signal thresholds and allocation schedules fixed. It asks
whether adding Stage 2 (MVRV confirmation) and/or Stage 3 (independent
Opportunity confirmation) changes outcomes relative to Stage 1 alone.
Untriggered or deliberately omitted tranches remain cash.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from statistics import median

from backend.app.services.bitcoin_confluence_research import (
    ConfluencePoint,
    independent_confluence_episodes,
)
from backend.app.services.bitcoin_staged_accumulation import (
    STAGE1_SPEC,
    STAGE3_SPEC,
    STAGED_ALLOCATIONS,
)


@dataclass(frozen=True, slots=True)
class AblationResult:
    episode_date: date
    allocation: str
    variant: str
    stage2_date: date | None
    stage3_date: date | None
    invested_pct: float
    average_entry_price: float | None
    horizon_days: int
    return_pct: float
    max_drawdown_pct: float

    @property
    def return_365d_pct(self) -> float:
        """Backward-compatible alias for the original 365-day report code."""
        return self.return_pct


@dataclass(frozen=True, slots=True)
class AblationSummary:
    allocation: str
    variant: str
    episodes: int
    horizon_days: int
    median_return_pct: float | None
    positive_rate_pct: float | None
    median_max_drawdown_pct: float | None
    worst_max_drawdown_pct: float | None
    median_invested_pct: float | None

    @property
    def median_return_365d_pct(self) -> float | None:
        """Backward-compatible alias for the original 365-day report code."""
        return self.median_return_pct


VARIANTS = (
    "Stage 1 only",
    "Stage 1 + Stage 2",
    "Stage 1 + Stage 3",
    "Stage 1 + Stage 2 + Stage 3",
)


def _first_match(
    points: list[ConfluencePoint],
    *,
    start: date,
    end: date,
) -> ConfluencePoint | None:
    for point in points:
        if start <= point.date <= end:
            return point
    return None


def _simulate(
    window: list[ConfluencePoint],
    *,
    purchases: list[tuple[date, float]],
    episode_date: date,
    allocation: str,
    variant: str,
    stage2_date: date | None,
    stage3_date: date | None,
    horizon_days: int,
) -> AblationResult:
    cash = 100.0
    btc = 0.0
    spent = 0.0
    purchase_map: dict[date, float] = {}
    for day, amount in purchases:
        purchase_map[day] = purchase_map.get(day, 0.0) + amount

    values: list[float] = []
    for point in window:
        amount = min(purchase_map.get(point.date, 0.0), cash)
        if amount > 0:
            btc += amount / point.price
            cash -= amount
            spent += amount
        values.append(cash + btc * point.price)

    peak = values[0]
    max_drawdown = 0.0
    for value in values:
        peak = max(peak, value)
        if peak > 0:
            max_drawdown = min(max_drawdown, (value / peak - 1.0) * 100.0)

    average_entry = spent / btc if btc > 0 else None
    return AblationResult(
        episode_date=episode_date,
        allocation=allocation,
        variant=variant,
        stage2_date=stage2_date,
        stage3_date=stage3_date,
        invested_pct=spent,
        average_entry_price=average_entry,
        horizon_days=horizon_days,
        return_pct=values[-1] - 100.0,
        max_drawdown_pct=max_drawdown,
    )


def evaluate_stage_ablation(
    points: list[ConfluencePoint],
    *,
    horizon_days: int = 365,
    cooldown_days: int = 90,
    deployment_window_days: int = 365,
) -> list[AblationResult]:
    """Evaluate predeclared stage ablations for every fixed allocation schedule.

    Stage 1 is an independent Quantile <=10 episode. Stage 2 is the first daily
    Quantile <=10 + MVRV <=20 confirmation after Stage 1. Stage 3 is the first
    globally independent Opportunity >=60 episode after Stage 1 (or, for the
    full three-stage variant, after Stage 2). No omitted tranche is reassigned.

    ``horizon_days`` changes only the outcome-measurement window. New Stage-2 or
    Stage-3 deployments are never allowed later than ``deployment_window_days``
    after Stage 1. For horizons shorter than that deployment window, only stages
    observable by the outcome date can be executed. This prevents a 730-day
    outcome study from silently turning a later, unrelated cycle signal into a
    new tranche of the original accumulation episode.
    """
    if horizon_days < 1:
        raise ValueError("horizon_days must be positive")
    if deployment_window_days < 1:
        raise ValueError("deployment_window_days must be positive")

    ordered = sorted(points, key=lambda item: item.date)
    by_date = {point.date: point for point in ordered}
    stage1_episodes = independent_confluence_episodes(
        ordered, STAGE1_SPEC, cooldown_days=cooldown_days
    )
    stage3_episodes = independent_confluence_episodes(
        ordered, STAGE3_SPEC, cooldown_days=cooldown_days
    )

    rows: list[AblationResult] = []
    for entry in stage1_episodes:
        outcome_end_date = entry.date + timedelta(days=horizon_days)
        if outcome_end_date not in by_date:
            continue

        deployment_end_date = min(
            outcome_end_date,
            entry.date + timedelta(days=deployment_window_days),
        )
        window = [
            point for point in ordered if entry.date <= point.date <= outcome_end_date
        ]
        deployment_points = [
            point for point in ordered if entry.date <= point.date <= deployment_end_date
        ]

        stage2 = next(
            (
                point
                for point in deployment_points
                if point.quantile_percentile <= 10.0 and point.mvrv_percentile <= 20.0
            ),
            None,
        )
        stage3_from_stage1 = _first_match(
            stage3_episodes, start=entry.date, end=deployment_end_date
        )
        stage3_after_stage2 = (
            _first_match(stage3_episodes, start=stage2.date, end=deployment_end_date)
            if stage2 is not None
            else None
        )

        for allocation_name, (stage1_amount, stage2_amount, stage3_amount) in STAGED_ALLOCATIONS:
            variant_purchases: dict[str, list[tuple[date, float]]] = {
                "Stage 1 only": [(entry.date, stage1_amount)],
                "Stage 1 + Stage 2": [(entry.date, stage1_amount)],
                "Stage 1 + Stage 3": [(entry.date, stage1_amount)],
                "Stage 1 + Stage 2 + Stage 3": [(entry.date, stage1_amount)],
            }
            if stage2 is not None:
                variant_purchases["Stage 1 + Stage 2"].append((stage2.date, stage2_amount))
                variant_purchases["Stage 1 + Stage 2 + Stage 3"].append(
                    (stage2.date, stage2_amount)
                )
            if stage3_from_stage1 is not None:
                variant_purchases["Stage 1 + Stage 3"].append(
                    (stage3_from_stage1.date, stage3_amount)
                )
            if stage3_after_stage2 is not None:
                variant_purchases["Stage 1 + Stage 2 + Stage 3"].append(
                    (stage3_after_stage2.date, stage3_amount)
                )

            for variant in VARIANTS:
                rows.append(
                    _simulate(
                        window,
                        purchases=variant_purchases[variant],
                        episode_date=entry.date,
                        allocation=allocation_name,
                        variant=variant,
                        stage2_date=(
                            stage2.date
                            if stage2 is not None and "Stage 2" in variant
                            else None
                        ),
                        stage3_date=(
                            stage3_after_stage2.date
                            if variant == "Stage 1 + Stage 2 + Stage 3"
                            and stage3_after_stage2 is not None
                            else stage3_from_stage1.date
                            if variant == "Stage 1 + Stage 3"
                            and stage3_from_stage1 is not None
                            else None
                        ),
                        horizon_days=horizon_days,
                    )
                )
    return rows


def summarize_stage_ablation(rows: list[AblationResult]) -> list[AblationSummary]:
    summaries: list[AblationSummary] = []
    horizons = sorted({row.horizon_days for row in rows})
    for horizon_days in horizons:
        horizon_rows = [row for row in rows if row.horizon_days == horizon_days]
        for allocation_name, _ in STAGED_ALLOCATIONS:
            for variant in VARIANTS:
                selected = [
                    row
                    for row in horizon_rows
                    if row.allocation == allocation_name and row.variant == variant
                ]
                returns = [row.return_pct for row in selected]
                drawdowns = [row.max_drawdown_pct for row in selected]
                invested = [row.invested_pct for row in selected]
                summaries.append(
                    AblationSummary(
                        allocation=allocation_name,
                        variant=variant,
                        episodes=len(selected),
                        horizon_days=horizon_days,
                        median_return_pct=median(returns) if returns else None,
                        positive_rate_pct=(
                            100.0 * sum(value > 0 for value in returns) / len(returns)
                            if returns
                            else None
                        ),
                        median_max_drawdown_pct=median(drawdowns) if drawdowns else None,
                        worst_max_drawdown_pct=min(drawdowns) if drawdowns else None,
                        median_invested_pct=median(invested) if invested else None,
                    )
                )
    return summaries
