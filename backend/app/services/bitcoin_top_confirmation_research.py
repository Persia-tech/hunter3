"""Research-only confirmation study after Bitcoin top-risk warnings.

A top valuation warning is not treated as a sell signal. This module asks
whether simple, point-in-time market-weakness confirmations after an MVRV-high
warning improve timing.

All confirmation rules are fixed in advance and use only data available on or
before the confirmation date:
- close below trailing 50-day SMA,
- 30-day price momentum below zero,
- 10% drawdown from the running peak since the warning,
- Overheat score rollover of at least 20 points from its running post-warning max.

No threshold is optimized from future outcomes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from statistics import median

from backend.app.services.bitcoin_top_confluence_research import (
    MVRV_HIGH_THRESHOLD,
    TopConfluencePoint,
    TopSpec,
    independent_top_episodes,
)


MVRV_WARNING_SPEC = TopSpec("MVRV pct >= 90", require_mvrv=True)
CONFIRMATION_WINDOW_DAYS = 180
SMA_DAYS = 50
MOMENTUM_DAYS = 30
DRAWDOWN_CONFIRM_PCT = -10.0
OVERHEAT_ROLLOVER_POINTS = 20.0

CONFIRMATION_RULES = (
    "Below 50d SMA",
    "30d momentum < 0",
    "10% drawdown from post-warning peak",
    "Overheat rollover >=20",
    "Any 2 confirmations",
)


@dataclass(frozen=True, slots=True)
class TopConfirmationResult:
    warning_date: date
    warning_price: float
    rule: str
    confirmation_date: date | None
    confirmation_price: float | None
    days_to_confirmation: int | None
    upside_warning_to_confirmation_pct: float | None
    future_return_180d_from_confirmation_pct: float | None
    future_return_365d_from_confirmation_pct: float | None
    future_max_drawdown_180d_from_confirmation_pct: float | None
    future_max_drawdown_365d_from_confirmation_pct: float | None


@dataclass(frozen=True, slots=True)
class TopConfirmationSummary:
    rule: str
    warnings: int
    confirmed: int
    confirmation_rate_pct: float | None
    median_days_to_confirmation: float | None
    median_upside_to_confirmation_pct: float | None
    median_return_180d_pct: float | None
    median_return_365d_pct: float | None
    negative_365d_rate_pct: float | None
    median_drawdown_180d_pct: float | None
    median_drawdown_365d_pct: float | None


def _trailing_sma(points: list[TopConfluencePoint], index: int, days: int) -> float | None:
    if index + 1 < days:
        return None
    window = points[index - days + 1 : index + 1]
    return sum(point.price for point in window) / len(window)


def _future_outcomes(
    points: list[TopConfluencePoint],
    index: int,
    horizon_days: int,
) -> tuple[float | None, float | None]:
    start = points[index]
    end_date = start.date + timedelta(days=horizon_days)
    by_date = {point.date: point for point in points}
    end = by_date.get(end_date)
    if end is None:
        return None, None
    window = [point.price for point in points if start.date <= point.date <= end_date]
    if not window or start.price <= 0:
        return None, None
    ret = (end.price / start.price - 1.0) * 100.0
    peak = window[0]
    max_dd = 0.0
    for price in window:
        peak = max(peak, price)
        max_dd = min(max_dd, (price / peak - 1.0) * 100.0)
    return ret, max_dd


def evaluate_top_confirmations(
    points: list[TopConfluencePoint],
    *,
    cooldown_days: int = 90,
    confirmation_window_days: int = CONFIRMATION_WINDOW_DAYS,
) -> list[TopConfirmationResult]:
    """Evaluate fixed weakness confirmations after independent MVRV-high warnings."""
    ordered = sorted(points, key=lambda item: item.date)
    index_by_date = {point.date: index for index, point in enumerate(ordered)}
    warnings = independent_top_episodes(
        ordered,
        MVRV_WARNING_SPEC,
        cooldown_days=cooldown_days,
        mvrv_threshold=MVRV_HIGH_THRESHOLD,
    )

    results: list[TopConfirmationResult] = []
    for warning in warnings:
        start_index = index_by_date[warning.date]
        deadline = warning.date + timedelta(days=confirmation_window_days)
        running_peak_price = warning.price
        running_peak_overheat = warning.overheat_score
        first_hits: dict[str, int] = {}

        for index in range(start_index, len(ordered)):
            point = ordered[index]
            if point.date > deadline:
                break
            running_peak_price = max(running_peak_price, point.price)
            running_peak_overheat = max(running_peak_overheat, point.overheat_score)

            sma50 = _trailing_sma(ordered, index, SMA_DAYS)
            if sma50 is not None and point.price < sma50:
                first_hits.setdefault("Below 50d SMA", index)

            if index - MOMENTUM_DAYS >= 0:
                prior = ordered[index - MOMENTUM_DAYS]
                if prior.price > 0 and point.price / prior.price - 1.0 < 0:
                    first_hits.setdefault("30d momentum < 0", index)

            if running_peak_price > 0:
                drawdown = (point.price / running_peak_price - 1.0) * 100.0
                if drawdown <= DRAWDOWN_CONFIRM_PCT:
                    first_hits.setdefault("10% drawdown from post-warning peak", index)

            if running_peak_overheat - point.overheat_score >= OVERHEAT_ROLLOVER_POINTS:
                first_hits.setdefault("Overheat rollover >=20", index)

            primitive_hits = [
                hit_index
                for rule, hit_index in first_hits.items()
                if rule != "Any 2 confirmations" and hit_index <= index
            ]
            if len(primitive_hits) >= 2:
                first_hits.setdefault("Any 2 confirmations", index)

        for rule in CONFIRMATION_RULES:
            confirmation_index = first_hits.get(rule)
            if confirmation_index is None:
                results.append(
                    TopConfirmationResult(
                        warning_date=warning.date,
                        warning_price=warning.price,
                        rule=rule,
                        confirmation_date=None,
                        confirmation_price=None,
                        days_to_confirmation=None,
                        upside_warning_to_confirmation_pct=None,
                        future_return_180d_from_confirmation_pct=None,
                        future_return_365d_from_confirmation_pct=None,
                        future_max_drawdown_180d_from_confirmation_pct=None,
                        future_max_drawdown_365d_from_confirmation_pct=None,
                    )
                )
                continue

            confirmation = ordered[confirmation_index]
            path = [
                point.price
                for point in ordered
                if warning.date <= point.date <= confirmation.date
            ]
            max_price = max(path) if path else confirmation.price
            upside = (max_price / warning.price - 1.0) * 100.0
            ret180, dd180 = _future_outcomes(ordered, confirmation_index, 180)
            ret365, dd365 = _future_outcomes(ordered, confirmation_index, 365)
            results.append(
                TopConfirmationResult(
                    warning_date=warning.date,
                    warning_price=warning.price,
                    rule=rule,
                    confirmation_date=confirmation.date,
                    confirmation_price=confirmation.price,
                    days_to_confirmation=(confirmation.date - warning.date).days,
                    upside_warning_to_confirmation_pct=upside,
                    future_return_180d_from_confirmation_pct=ret180,
                    future_return_365d_from_confirmation_pct=ret365,
                    future_max_drawdown_180d_from_confirmation_pct=dd180,
                    future_max_drawdown_365d_from_confirmation_pct=dd365,
                )
            )
    return results


def _median(values: list[float | int | None]) -> float | None:
    clean = [float(value) for value in values if value is not None]
    return median(clean) if clean else None


def summarize_top_confirmations(rows: list[TopConfirmationResult]) -> list[TopConfirmationSummary]:
    summaries: list[TopConfirmationSummary] = []
    for rule in CONFIRMATION_RULES:
        selected = [row for row in rows if row.rule == rule]
        confirmed = [row for row in selected if row.confirmation_date is not None]
        valid365 = [
            row.future_return_365d_from_confirmation_pct
            for row in confirmed
            if row.future_return_365d_from_confirmation_pct is not None
        ]
        summaries.append(
            TopConfirmationSummary(
                rule=rule,
                warnings=len(selected),
                confirmed=len(confirmed),
                confirmation_rate_pct=(100.0 * len(confirmed) / len(selected) if selected else None),
                median_days_to_confirmation=_median([row.days_to_confirmation for row in confirmed]),
                median_upside_to_confirmation_pct=_median([row.upside_warning_to_confirmation_pct for row in confirmed]),
                median_return_180d_pct=_median([row.future_return_180d_from_confirmation_pct for row in confirmed]),
                median_return_365d_pct=_median(valid365),
                negative_365d_rate_pct=(
                    100.0 * sum(value < 0 for value in valid365) / len(valid365)
                    if valid365
                    else None
                ),
                median_drawdown_180d_pct=_median([row.future_max_drawdown_180d_from_confirmation_pct for row in confirmed]),
                median_drawdown_365d_pct=_median([row.future_max_drawdown_365d_from_confirmation_pct for row in confirmed]),
            )
        )
    return summaries
