"""Research-only outcome-horizon sensitivity for Bitcoin top-stage ablation.

Only the evaluation horizon changes across 180, 365, and 730 days. The top
warning, confirmation rules, 90-day cooldown, and fixed de-risking allocations
remain unchanged. Stage 2 / Stage 3 detection continues to use the predeclared
180-day confirmation window from the underlying persistent-confirmation study.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from statistics import median

from backend.app.services.bitcoin_top_confluence_research import TopConfluencePoint
from backend.app.services.bitcoin_top_stage_ablation import (
    STAGED_DERISK_ALLOCATIONS,
    VARIANTS,
    evaluate_top_stage_ablation,
)


DEFAULT_HORIZONS = (180, 365, 730)


@dataclass(frozen=True, slots=True)
class TopHorizonResult:
    warning_date: date
    horizon_days: int
    allocation: str
    variant: str
    stage2_date: date | None
    stage3_date: date | None
    sold_pct: float
    sold_before_30dd_pct: float
    return_pct: float
    max_drawdown_pct: float
    peak_upside_forfeited_pct_points: float
    excess_return_vs_hold_pct_points: float


@dataclass(frozen=True, slots=True)
class TopHorizonSummary:
    horizon_days: int
    allocation: str
    variant: str
    episodes: int
    median_return_pct: float | None
    positive_rate_pct: float | None
    median_max_drawdown_pct: float | None
    worst_max_drawdown_pct: float | None
    median_peak_upside_forfeited_pct_points: float | None
    median_sold_before_30dd_pct: float | None
    median_sold_pct: float | None
    median_excess_vs_hold_pct_points: float | None


def evaluate_top_stage_horizon_sensitivity(
    points: list[TopConfluencePoint],
    *,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    cooldown_days: int = 90,
) -> list[TopHorizonResult]:
    if not horizons or any(horizon < 1 for horizon in horizons):
        raise ValueError("horizons must contain positive integers")

    rows: list[TopHorizonResult] = []
    for horizon_days in horizons:
        base_rows = evaluate_top_stage_ablation(
            points,
            cooldown_days=cooldown_days,
            horizon_days=horizon_days,
        )
        for row in base_rows:
            rows.append(
                TopHorizonResult(
                    warning_date=row.warning_date,
                    horizon_days=horizon_days,
                    allocation=row.allocation,
                    variant=row.variant,
                    stage2_date=row.stage2_date,
                    stage3_date=row.stage3_date,
                    sold_pct=row.sold_pct,
                    sold_before_30dd_pct=row.sold_before_30dd_pct,
                    return_pct=row.return_365d_pct,
                    max_drawdown_pct=row.max_drawdown_pct,
                    peak_upside_forfeited_pct_points=row.peak_upside_forfeited_pct_points,
                    excess_return_vs_hold_pct_points=row.excess_return_vs_hold_pct_points,
                )
            )
    return rows


def _median(values: list[float]) -> float | None:
    return median(values) if values else None


def summarize_top_stage_horizon_sensitivity(
    rows: list[TopHorizonResult],
) -> list[TopHorizonSummary]:
    summaries: list[TopHorizonSummary] = []
    for horizon_days in sorted({row.horizon_days for row in rows}):
        horizon_rows = [row for row in rows if row.horizon_days == horizon_days]
        for allocation_name, _ in STAGED_DERISK_ALLOCATIONS:
            for variant in VARIANTS:
                selected = [
                    row
                    for row in horizon_rows
                    if row.allocation == allocation_name and row.variant == variant
                ]
                returns = [row.return_pct for row in selected]
                drawdowns = [row.max_drawdown_pct for row in selected]
                summaries.append(
                    TopHorizonSummary(
                        horizon_days=horizon_days,
                        allocation=allocation_name,
                        variant=variant,
                        episodes=len(selected),
                        median_return_pct=_median(returns),
                        positive_rate_pct=(
                            100.0 * sum(value > 0 for value in returns) / len(returns)
                            if returns
                            else None
                        ),
                        median_max_drawdown_pct=_median(drawdowns),
                        worst_max_drawdown_pct=min(drawdowns) if drawdowns else None,
                        median_peak_upside_forfeited_pct_points=_median(
                            [row.peak_upside_forfeited_pct_points for row in selected]
                        ),
                        median_sold_before_30dd_pct=_median(
                            [row.sold_before_30dd_pct for row in selected]
                        ),
                        median_sold_pct=_median([row.sold_pct for row in selected]),
                        median_excess_vs_hold_pct_points=_median(
                            [row.excess_return_vs_hold_pct_points for row in selected]
                        ),
                    )
                )
    return summaries
