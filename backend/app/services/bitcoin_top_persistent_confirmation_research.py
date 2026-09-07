"""Research-only persistent weakness confirmation after Bitcoin MVRV-high warnings.

This second-generation study tests whether persistence or slower trend breaks
reduce the early-confirmation problem observed with one-day weakness signals.
All thresholds are fixed in advance and all calculations are point-in-time.
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
SMA50_DAYS = 50
SMA200_DAYS = 200
MOMENTUM_DAYS = 30
DRAWDOWN_PRIMITIVE_PCT = -10.0
DEEP_DRAWDOWN_PCT = -20.0
OVERHEAT_ROLLOVER_POINTS = 20.0
EARLY_UPSIDE_PROXY_PCT = 25.0

RULES = (
    "Any 2 immediate",
    "Any 2 sustained 7d",
    "Any 2 sustained 14d",
    "20% drawdown + one other weakness",
    "Below 50d SMA sustained 7d",
    "Below 200d SMA",
)


@dataclass(frozen=True, slots=True)
class PersistentTopConfirmationResult:
    warning_date: date
    warning_price: float
    rule: str
    confirmation_date: date | None
    confirmation_price: float | None
    days_to_confirmation: int | None
    upside_before_confirmation_pct: float | None
    max_upside_365d_after_confirmation_pct: float | None
    future_return_180d_pct: float | None
    future_return_365d_pct: float | None
    max_drawdown_365d_pct: float | None


@dataclass(frozen=True, slots=True)
class PersistentTopConfirmationSummary:
    rule: str
    warnings: int
    confirmed: int
    confirmation_rate_pct: float | None
    median_days_to_confirmation: float | None
    median_upside_before_confirmation_pct: float | None
    median_max_upside_after_confirmation_pct: float | None
    early_25pct_upside_rate_pct: float | None
    median_return_365d_pct: float | None
    negative_365d_rate_pct: float | None
    median_drawdown_365d_pct: float | None


def _sma(points: list[TopConfluencePoint], index: int, days: int) -> float | None:
    if index + 1 < days:
        return None
    window = points[index - days + 1 : index + 1]
    return sum(point.price for point in window) / len(window)


def _future_metrics(
    points: list[TopConfluencePoint], index: int, horizon_days: int
) -> tuple[float | None, float | None, float | None]:
    start = points[index]
    end_date = start.date + timedelta(days=horizon_days)
    by_date = {point.date: point for point in points}
    end = by_date.get(end_date)
    if end is None or start.price <= 0:
        return None, None, None
    window = [point.price for point in points if start.date <= point.date <= end_date]
    if not window:
        return None, None, None
    ret = (end.price / start.price - 1.0) * 100.0
    max_upside = (max(window) / start.price - 1.0) * 100.0
    peak = window[0]
    max_dd = 0.0
    for price in window:
        peak = max(peak, price)
        max_dd = min(max_dd, (price / peak - 1.0) * 100.0)
    return ret, max_upside, max_dd


def _consecutive_true(flags: list[bool], index: int, days: int) -> bool:
    if index + 1 < days:
        return False
    return all(flags[index - days + 1 : index + 1])


def evaluate_persistent_top_confirmations(
    points: list[TopConfluencePoint],
    *,
    cooldown_days: int = 90,
    confirmation_window_days: int = CONFIRMATION_WINDOW_DAYS,
) -> list[PersistentTopConfirmationResult]:
    ordered = sorted(points, key=lambda item: item.date)
    index_by_date = {point.date: index for index, point in enumerate(ordered)}
    warnings = independent_top_episodes(
        ordered,
        MVRV_WARNING_SPEC,
        cooldown_days=cooldown_days,
        mvrv_threshold=MVRV_HIGH_THRESHOLD,
    )

    rows: list[PersistentTopConfirmationResult] = []
    for warning in warnings:
        start_index = index_by_date[warning.date]
        deadline = warning.date + timedelta(days=confirmation_window_days)
        running_peak_price = warning.price
        running_peak_overheat = warning.overheat_score
        any2_flags: list[bool] = []
        below50_flags: list[bool] = []
        first_hits: dict[str, int] = {}

        for index in range(start_index, len(ordered)):
            point = ordered[index]
            if point.date > deadline:
                break

            running_peak_price = max(running_peak_price, point.price)
            running_peak_overheat = max(running_peak_overheat, point.overheat_score)
            sma50 = _sma(ordered, index, SMA50_DAYS)
            sma200 = _sma(ordered, index, SMA200_DAYS)

            below50 = sma50 is not None and point.price < sma50
            momentum_negative = False
            if index - MOMENTUM_DAYS >= 0:
                prior = ordered[index - MOMENTUM_DAYS]
                momentum_negative = prior.price > 0 and point.price < prior.price

            drawdown = (
                (point.price / running_peak_price - 1.0) * 100.0
                if running_peak_price > 0
                else 0.0
            )
            drawdown10 = drawdown <= DRAWDOWN_PRIMITIVE_PCT
            drawdown20 = drawdown <= DEEP_DRAWDOWN_PCT
            rollover = running_peak_overheat - point.overheat_score >= OVERHEAT_ROLLOVER_POINTS

            primitive_count = sum((below50, momentum_negative, drawdown10, rollover))
            any2 = primitive_count >= 2
            any2_flags.append(any2)
            below50_flags.append(below50)
            local_index = len(any2_flags) - 1

            if any2:
                first_hits.setdefault("Any 2 immediate", index)
            if _consecutive_true(any2_flags, local_index, 7):
                first_hits.setdefault("Any 2 sustained 7d", index)
            if _consecutive_true(any2_flags, local_index, 14):
                first_hits.setdefault("Any 2 sustained 14d", index)
            if drawdown20 and sum((below50, momentum_negative, rollover)) >= 1:
                first_hits.setdefault("20% drawdown + one other weakness", index)
            if _consecutive_true(below50_flags, local_index, 7):
                first_hits.setdefault("Below 50d SMA sustained 7d", index)
            if sma200 is not None and point.price < sma200:
                first_hits.setdefault("Below 200d SMA", index)

        for rule in RULES:
            confirmation_index = first_hits.get(rule)
            if confirmation_index is None:
                rows.append(
                    PersistentTopConfirmationResult(
                        warning_date=warning.date,
                        warning_price=warning.price,
                        rule=rule,
                        confirmation_date=None,
                        confirmation_price=None,
                        days_to_confirmation=None,
                        upside_before_confirmation_pct=None,
                        max_upside_365d_after_confirmation_pct=None,
                        future_return_180d_pct=None,
                        future_return_365d_pct=None,
                        max_drawdown_365d_pct=None,
                    )
                )
                continue

            confirmation = ordered[confirmation_index]
            path_before = [
                point.price
                for point in ordered
                if warning.date <= point.date <= confirmation.date
            ]
            upside_before = (
                (max(path_before) / warning.price - 1.0) * 100.0 if path_before else 0.0
            )
            ret180, _, _ = _future_metrics(ordered, confirmation_index, 180)
            ret365, max_upside365, dd365 = _future_metrics(ordered, confirmation_index, 365)
            rows.append(
                PersistentTopConfirmationResult(
                    warning_date=warning.date,
                    warning_price=warning.price,
                    rule=rule,
                    confirmation_date=confirmation.date,
                    confirmation_price=confirmation.price,
                    days_to_confirmation=(confirmation.date - warning.date).days,
                    upside_before_confirmation_pct=upside_before,
                    max_upside_365d_after_confirmation_pct=max_upside365,
                    future_return_180d_pct=ret180,
                    future_return_365d_pct=ret365,
                    max_drawdown_365d_pct=dd365,
                )
            )
    return rows


def _median(values: list[float | int | None]) -> float | None:
    clean = [float(value) for value in values if value is not None]
    return median(clean) if clean else None


def summarize_persistent_top_confirmations(
    rows: list[PersistentTopConfirmationResult],
) -> list[PersistentTopConfirmationSummary]:
    summaries: list[PersistentTopConfirmationSummary] = []
    for rule in RULES:
        selected = [row for row in rows if row.rule == rule]
        confirmed = [row for row in selected if row.confirmation_date is not None]
        valid365 = [row for row in confirmed if row.future_return_365d_pct is not None]
        returns365 = [row.future_return_365d_pct for row in valid365 if row.future_return_365d_pct is not None]
        upsides365 = [
            row.max_upside_365d_after_confirmation_pct
            for row in valid365
            if row.max_upside_365d_after_confirmation_pct is not None
        ]
        summaries.append(
            PersistentTopConfirmationSummary(
                rule=rule,
                warnings=len(selected),
                confirmed=len(confirmed),
                confirmation_rate_pct=(100.0 * len(confirmed) / len(selected) if selected else None),
                median_days_to_confirmation=_median([row.days_to_confirmation for row in confirmed]),
                median_upside_before_confirmation_pct=_median([row.upside_before_confirmation_pct for row in confirmed]),
                median_max_upside_after_confirmation_pct=_median(upsides365),
                early_25pct_upside_rate_pct=(
                    100.0 * sum(value >= EARLY_UPSIDE_PROXY_PCT for value in upsides365) / len(upsides365)
                    if upsides365
                    else None
                ),
                median_return_365d_pct=_median(returns365),
                negative_365d_rate_pct=(
                    100.0 * sum(value < 0 for value in returns365) / len(returns365)
                    if returns365
                    else None
                ),
                median_drawdown_365d_pct=_median([row.max_drawdown_365d_pct for row in valid365]),
            )
        )
    return summaries
