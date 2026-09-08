"""Research-only horizon sensitivity for staged Bitcoin accumulation ablations.

This module changes only the evaluation horizon. Stage definitions, independent
signal semantics, allocation schedules, and cooldown rules remain fixed.
"""

from __future__ import annotations

from backend.app.services.bitcoin_confluence_research import ConfluencePoint
from backend.app.services.bitcoin_stage_ablation import (
    AblationResult,
    AblationSummary,
    evaluate_stage_ablation,
    summarize_stage_ablation,
)


DEFAULT_HORIZONS = (180, 365, 730)


def evaluate_stage_horizon_sensitivity(
    points: list[ConfluencePoint],
    *,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    cooldown_days: int = 90,
) -> list[AblationResult]:
    """Evaluate the same fixed staged rules at predeclared outcome horizons."""
    if not horizons:
        raise ValueError("at least one horizon is required")
    if any(horizon < 1 for horizon in horizons):
        raise ValueError("all horizons must be positive")

    rows: list[AblationResult] = []
    for horizon in horizons:
        rows.extend(
            evaluate_stage_ablation(
                points,
                horizon_days=horizon,
                cooldown_days=cooldown_days,
            )
        )
    return rows


def summarize_stage_horizon_sensitivity(
    rows: list[AblationResult],
) -> list[AblationSummary]:
    """Summarize each fixed allocation/ablation variant within each horizon."""
    return summarize_stage_ablation(rows)
