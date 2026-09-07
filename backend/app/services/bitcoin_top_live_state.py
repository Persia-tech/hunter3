"""Point-in-time live evaluator for the researched Bitcoin top Stage 2 rule.

The de-risking research defines:
- Stage 1 warning: first entry into MVRV historical percentile >= 90,
- Stage 2 confirmation: at least two primitive weakness conditions sustained
  for 14 consecutive daily observations within 180 days of that warning.

This module reproduces that fixed rule for a current snapshot. It does not fit
or optimize thresholds and it does not create a composite score.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right, insort
from dataclasses import dataclass
from datetime import date, timedelta

from backend.app.models.onchain import BitcoinOnChainRecord
from backend.app.models.price import PriceRecord
from backend.app.services.bitcoin_cycle import calculate_bitcoin_cycle


MVRV_WARNING_PERCENTILE = 90.0
WARNING_COOLDOWN_DAYS = 90
CONFIRMATION_WINDOW_DAYS = 180
SUSTAINED_DAYS = 14
SMA50_DAYS = 50
MOMENTUM_DAYS = 30
DRAWDOWN_PCT = -10.0
OVERHEAT_ROLLOVER_POINTS = 20.0


@dataclass(frozen=True, slots=True)
class LiveTopStage2State:
    active: bool
    warning_date: date | None
    confirmation_date: date | None
    warning_age_days: int | None
    current_any2_streak_days: int
    primitive_count: int
    below_50d_sma: bool
    momentum_30d_negative: bool
    drawdown_10pct: bool
    overheat_rollover_20: bool
    reason: str


def _mvrv_percentile_series(
    rows: list[BitcoinOnChainRecord],
) -> list[tuple[date, float]]:
    """Return expanding mid-rank percentiles with no future leakage."""
    seen: list[float] = []
    output: list[tuple[date, float]] = []
    for row in sorted(rows, key=lambda item: item.date):
        if row.mvrv is None:
            continue
        value = float(row.mvrv)
        left = bisect_left(seen, value)
        right = bisect_right(seen, value)
        equal_after = (right - left) + 1
        total_after = len(seen) + 1
        percentile = 100.0 * (left + 0.5 * equal_after) / total_after
        output.append((row.date, percentile))
        insort(seen, value)
    return output


def _independent_warning_dates(
    percentile_rows: list[tuple[date, float]],
    *,
    threshold: float = MVRV_WARNING_PERCENTILE,
    cooldown_days: int = WARNING_COOLDOWN_DAYS,
) -> list[date]:
    warnings: list[date] = []
    was_inside = False
    last_selected: date | None = None
    for day, percentile in percentile_rows:
        inside = percentile >= threshold
        entered = inside and not was_inside
        if entered:
            far_enough = last_selected is None or (day - last_selected).days >= cooldown_days
            if far_enough:
                warnings.append(day)
                last_selected = day
        was_inside = inside
    return warnings


def evaluate_live_top_stage2(
    price_records: list[PriceRecord],
    onchain_rows: list[BitcoinOnChainRecord],
    *,
    as_of: date,
) -> LiveTopStage2State:
    """Evaluate the fixed Any-2-sustained-14d rule for the newest warning window."""
    prices = sorted(
        [record for record in price_records if record.date <= as_of],
        key=lambda item: item.date,
    )
    percentile_rows = _mvrv_percentile_series(
        [row for row in onchain_rows if row.date <= as_of]
    )
    warnings = _independent_warning_dates(percentile_rows)
    if not warnings:
        return LiveTopStage2State(
            active=False,
            warning_date=None,
            confirmation_date=None,
            warning_age_days=None,
            current_any2_streak_days=0,
            primitive_count=0,
            below_50d_sma=False,
            momentum_30d_negative=False,
            drawdown_10pct=False,
            overheat_rollover_20=False,
            reason="No MVRV >=90 historical-percentile warning has occurred in the available history.",
        )

    warning_date = warnings[-1]
    warning_age = (as_of - warning_date).days
    if warning_age > CONFIRMATION_WINDOW_DAYS:
        return LiveTopStage2State(
            active=False,
            warning_date=warning_date,
            confirmation_date=None,
            warning_age_days=warning_age,
            current_any2_streak_days=0,
            primitive_count=0,
            below_50d_sma=False,
            momentum_30d_negative=False,
            drawdown_10pct=False,
            overheat_rollover_20=False,
            reason="The latest independent MVRV warning is outside the fixed 180-day confirmation window.",
        )

    if len(prices) < 400:
        return LiveTopStage2State(
            active=False,
            warning_date=warning_date,
            confirmation_date=None,
            warning_age_days=warning_age,
            current_any2_streak_days=0,
            primitive_count=0,
            below_50d_sma=False,
            momentum_30d_negative=False,
            drawdown_10pct=False,
            overheat_rollover_20=False,
            reason="Insufficient BTC price history to evaluate persistent weakness.",
        )

    index_by_date = {record.date: index for index, record in enumerate(prices)}
    candidate_dates = [day for day in index_by_date if day >= warning_date]
    if not candidate_dates:
        return LiveTopStage2State(
            active=False,
            warning_date=warning_date,
            confirmation_date=None,
            warning_age_days=warning_age,
            current_any2_streak_days=0,
            primitive_count=0,
            below_50d_sma=False,
            momentum_30d_negative=False,
            drawdown_10pct=False,
            overheat_rollover_20=False,
            reason="No BTC price observations are available after the latest MVRV warning.",
        )

    start_date = min(candidate_dates)
    start_index = index_by_date[start_date]
    deadline = warning_date + timedelta(days=CONFIRMATION_WINDOW_DAYS)

    running_peak_price = float(prices[start_index].price)
    running_peak_overheat = 0.0
    streak = 0
    confirmation_date: date | None = None
    latest_flags = (False, False, False, False)

    daily_prices = [float(record.price) for record in prices]
    for index in range(start_index, len(prices)):
        point = prices[index]
        if point.date > min(as_of, deadline):
            break

        cycle = calculate_bitcoin_cycle(prices[: index + 1])
        overheat = float(cycle.overheat_score)
        price = float(point.price)
        running_peak_price = max(running_peak_price, price)
        running_peak_overheat = max(running_peak_overheat, overheat)

        sma50 = None
        if index + 1 >= SMA50_DAYS:
            window = daily_prices[index - SMA50_DAYS + 1 : index + 1]
            sma50 = sum(window) / len(window)
        below50 = sma50 is not None and price < sma50

        momentum_negative = False
        if index - MOMENTUM_DAYS >= 0:
            prior = daily_prices[index - MOMENTUM_DAYS]
            momentum_negative = prior > 0 and price < prior

        drawdown = (price / running_peak_price - 1.0) * 100.0 if running_peak_price > 0 else 0.0
        drawdown10 = drawdown <= DRAWDOWN_PCT
        rollover = running_peak_overheat - overheat >= OVERHEAT_ROLLOVER_POINTS
        latest_flags = (below50, momentum_negative, drawdown10, rollover)

        any2 = sum(latest_flags) >= 2
        streak = streak + 1 if any2 else 0
        if confirmation_date is None and streak >= SUSTAINED_DAYS:
            confirmation_date = point.date

    below50, momentum_negative, drawdown10, rollover = latest_flags
    primitive_count = sum(latest_flags)
    active = confirmation_date is not None
    if active:
        reason = f"Persistent weakness confirmed on {confirmation_date.isoformat()} after the latest MVRV warning."
    elif primitive_count >= 2:
        reason = f"Two or more weakness conditions are present, but the current streak is only {streak} of 14 days."
    else:
        reason = "The fixed persistent-weakness confirmation has not triggered in the current warning window."

    return LiveTopStage2State(
        active=active,
        warning_date=warning_date,
        confirmation_date=confirmation_date,
        warning_age_days=warning_age,
        current_any2_streak_days=streak,
        primitive_count=primitive_count,
        below_50d_sma=below50,
        momentum_30d_negative=momentum_negative,
        drawdown_10pct=drawdown10,
        overheat_rollover_20=rollover,
        reason=reason,
    )
