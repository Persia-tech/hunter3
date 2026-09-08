"""Research helpers for tuning Bitcoin cycle scores without changing production weights.

This module intentionally sits beside the production cycle engine.  It converts
point-in-time indicator snapshots into normalized factor values, searches
candidate weight multipliers/thresholds on historical training data, and
supports embargoed walk-forward evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from itertools import product
from statistics import median
from typing import Iterable, Literal

from backend.app.models.market import Divergence
from backend.app.services.bitcoin_backtest import BitcoinBacktestPoint
from backend.app.services.bitcoin_cycle import BitcoinCycleResult

ModelKind = Literal["opportunity", "overheat"]

OPPORTUNITY_BASE_WEIGHTS: dict[str, float] = {
    "distance_200w": 30.0,
    "mayer": 20.0,
    "weekly_rsi": 15.0,
    "drawdown": 15.0,
    "momentum_1y": 10.0,
    "divergence": 10.0,
}

OVERHEAT_BASE_WEIGHTS: dict[str, float] = {
    "pi_cycle": 25.0,
    "mayer": 20.0,
    "distance_200w": 20.0,
    "weekly_rsi": 15.0,
    "momentum_1y": 10.0,
    "divergence": 10.0,
}


@dataclass(frozen=True, slots=True)
class ResearchRow:
    as_of: date
    price: float
    opportunity_factors: dict[str, float]
    overheat_factors: dict[str, float]
    future_return_365d_pct: float | None
    future_max_drawdown_365d_pct: float | None


@dataclass(frozen=True, slots=True)
class Candidate:
    multipliers: dict[str, float]
    threshold: int


@dataclass(frozen=True, slots=True)
class CandidateMetrics:
    count: int
    median_return_365d_pct: float | None
    positive_365d_rate_pct: float | None
    drawdown_30pct_365d_rate_pct: float | None
    objective: float | None


@dataclass(frozen=True, slots=True)
class EpisodeMetrics:
    count: int
    valid_365d: int
    median_return_365d_pct: float | None
    positive_365d_rate_pct: float | None
    drawdown_30pct_365d_rate_pct: float | None


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def factors_from_cycle(result: BitcoinCycleResult) -> tuple[dict[str, float], dict[str, float]]:
    """Return the exact normalized factor shapes used by the baseline scorer."""

    momentum = result.momentum_1y_pct / 100.0 if result.momentum_1y_pct is not None else None

    opportunity = {
        "distance_200w": (
            _clamp((20.0 - result.distance_200w_pct) / 50.0)
            if result.distance_200w_pct is not None
            else 0.0
        ),
        "mayer": (
            _clamp((1.8 - result.mayer_multiple) / 1.0)
            if result.mayer_multiple is not None
            else 0.0
        ),
        "weekly_rsi": (
            _clamp((55.0 - result.weekly_rsi) / 25.0)
            if result.weekly_rsi is not None
            else 0.0
        ),
        "drawdown": _clamp((-result.ath_drawdown_pct - 20.0) / 60.0),
        "momentum_1y": _clamp((0.15 - momentum) / 0.8) if momentum is not None else 0.0,
        "divergence": 1.0 if result.divergence == Divergence.BULLISH else 0.0,
    }

    overheat = {
        "pi_cycle": (
            _clamp((result.pi_ratio - 0.75) / 0.25)
            if result.pi_ratio is not None
            else 0.0
        ),
        "mayer": (
            _clamp((result.mayer_multiple - 1.5) / 1.0)
            if result.mayer_multiple is not None
            else 0.0
        ),
        "distance_200w": (
            _clamp((result.distance_200w_pct - 100.0) / 250.0)
            if result.distance_200w_pct is not None
            else 0.0
        ),
        "weekly_rsi": (
            _clamp((result.weekly_rsi - 60.0) / 25.0)
            if result.weekly_rsi is not None
            else 0.0
        ),
        "momentum_1y": _clamp((momentum - 0.5) / 1.5) if momentum is not None else 0.0,
        "divergence": 1.0 if result.divergence == Divergence.BEARISH else 0.0,
    }
    return opportunity, overheat


def score_factors(
    factors: dict[str, float],
    base_weights: dict[str, float],
    multipliers: dict[str, float],
) -> int:
    """Score factors on 0-100 after re-normalizing candidate weights."""

    weighted_total = 0.0
    active_weight = 0.0
    for name, base_weight in base_weights.items():
        multiplier = multipliers.get(name, 1.0)
        weight = base_weight * multiplier
        if weight <= 0:
            continue
        active_weight += weight
        weighted_total += weight * factors.get(name, 0.0)
    if active_weight <= 0:
        return 0
    return round(100.0 * weighted_total / active_weight)


def candidate_scores(rows: list[ResearchRow], kind: ModelKind, candidate: Candidate) -> list[int]:
    base_weights = OPPORTUNITY_BASE_WEIGHTS if kind == "opportunity" else OVERHEAT_BASE_WEIGHTS
    return [
        score_factors(
            row.opportunity_factors if kind == "opportunity" else row.overheat_factors,
            base_weights,
            candidate.multipliers,
        )
        for row in rows
    ]


def _rates(rows: list[ResearchRow]) -> tuple[float, float, float]:
    returns = [row.future_return_365d_pct for row in rows if row.future_return_365d_pct is not None]
    drawdowns = [
        row.future_max_drawdown_365d_pct
        for row in rows
        if row.future_max_drawdown_365d_pct is not None
    ]
    if not returns:
        return 0.0, 0.0, 0.0
    med = median(returns)
    positive = 100.0 * sum(value > 0 for value in returns) / len(returns)
    dd30 = 100.0 * sum(value <= -30.0 for value in drawdowns) / len(drawdowns) if drawdowns else 0.0
    return med, positive, dd30


def evaluate_candidate(
    rows: list[ResearchRow],
    scores: list[int],
    candidate: Candidate,
    kind: ModelKind,
    *,
    start: date | None = None,
    end: date | None = None,
    minimum_days: int = 30,
) -> CandidateMetrics:
    eligible = [
        row
        for row, score in zip(rows, scores)
        if score >= candidate.threshold
        and row.future_return_365d_pct is not None
        and (start is None or row.as_of >= start)
        and (end is None or row.as_of <= end)
    ]
    if len(eligible) < minimum_days:
        return CandidateMetrics(len(eligible), None, None, None, None)

    comparison = [
        row
        for row in rows
        if row.future_return_365d_pct is not None
        and (start is None or row.as_of >= start)
        and (end is None or row.as_of <= end)
    ]
    med, positive, dd30 = _rates(eligible)
    base_med, base_positive, base_dd30 = _rates(comparison)

    if kind == "opportunity":
        objective = (med - base_med) + 0.5 * (positive - base_positive) - (dd30 - base_dd30)
    else:
        objective = (base_med - med) + 0.5 * (base_positive - positive) + (dd30 - base_dd30)

    return CandidateMetrics(len(eligible), med, positive, dd30, objective)


def independent_episode_metrics(
    rows: list[ResearchRow],
    scores: list[int],
    threshold: int,
    *,
    start: date | None = None,
    end: date | None = None,
    cooldown_days: int = 90,
) -> EpisodeMetrics:
    selected: list[ResearchRow] = []
    last_selected: date | None = None

    previous = scores[0] if scores else 0
    for index, (row, score) in enumerate(zip(rows, scores)):
        crossed = score >= threshold and (index == 0 or previous < threshold)
        previous = score
        if not crossed:
            continue
        if start is not None and row.as_of < start:
            continue
        if end is not None and row.as_of > end:
            continue
        if last_selected is not None and (row.as_of - last_selected).days < cooldown_days:
            continue
        selected.append(row)
        last_selected = row.as_of

    valid = [row for row in selected if row.future_return_365d_pct is not None]
    if not valid:
        return EpisodeMetrics(len(selected), 0, None, None, None)
    med, positive, dd30 = _rates(valid)
    return EpisodeMetrics(len(selected), len(valid), med, positive, dd30)


def generate_candidates(
    factor_names: Iterable[str],
    *,
    multipliers: tuple[float, ...] = (0.0, 0.5, 1.0, 1.5),
    thresholds: tuple[int, ...] = (50, 60, 70, 80),
) -> Iterable[Candidate]:
    names = tuple(factor_names)
    seen: set[tuple[float, ...]] = set()
    for values in product(multipliers, repeat=len(names)):
        if not any(values):
            continue
        maximum = max(values)
        normalized = tuple(round(value / maximum, 6) for value in values)
        if normalized in seen:
            continue
        seen.add(normalized)
        weights = dict(zip(names, values))
        for threshold in thresholds:
            yield Candidate(weights, threshold)


def find_best_candidate(
    rows: list[ResearchRow],
    kind: ModelKind,
    *,
    train_end: date,
    minimum_days: int = 30,
) -> tuple[Candidate, CandidateMetrics]:
    base_weights = OPPORTUNITY_BASE_WEIGHTS if kind == "opportunity" else OVERHEAT_BASE_WEIGHTS
    best_candidate: Candidate | None = None
    best_metrics: CandidateMetrics | None = None

    for candidate in generate_candidates(base_weights.keys()):
        scores = candidate_scores(rows, kind, candidate)
        metrics = evaluate_candidate(
            rows,
            scores,
            candidate,
            kind,
            end=train_end,
            minimum_days=minimum_days,
        )
        if metrics.objective is None:
            continue
        if best_metrics is None or metrics.objective > (best_metrics.objective or float("-inf")):
            best_candidate = candidate
            best_metrics = metrics

    if best_candidate is None or best_metrics is None:
        raise ValueError("No candidate had enough valid training observations")
    return best_candidate, best_metrics


def research_row_from_results(
    cycle: BitcoinCycleResult,
    backtest: BitcoinBacktestPoint,
) -> ResearchRow:
    opportunity, overheat = factors_from_cycle(cycle)
    return ResearchRow(
        as_of=cycle.as_of,
        price=cycle.price,
        opportunity_factors=opportunity,
        overheat_factors=overheat,
        future_return_365d_pct=backtest.future_return_365d_pct,
        future_max_drawdown_365d_pct=backtest.future_max_drawdown_365d_pct,
    )
