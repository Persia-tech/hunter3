"""Flexible alert rule evaluation for Hunter2."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.app.db.models import AlertRule, AlertState


NUMERIC_OPERATORS = {
    "above",
    "above_or_equal",
    "below",
    "below_or_equal",
    "equal",
    "crossed_above",
    "crossed_below",
}

TEXT_OPERATORS = {
    "equal",
    "not_equal",
    "changed_to",
    "changed_from",
}


@dataclass(frozen=True)
class AlertEvaluation:
    """Result of evaluating one alert rule."""

    matched: bool
    entered: bool
    exited: bool
    should_notify: bool

    current_numeric_value: float | None = None
    previous_numeric_value: float | None = None

    current_text_value: str | None = None
    previous_text_value: str | None = None

    reason: str | None = None


class AlertEvaluationError(ValueError):
    """Raised when an alert rule cannot be evaluated safely."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def evaluate_rule(
    rule: AlertRule,
    state: AlertState | None,
    current_value: Any,
    *,
    now: datetime | None = None,
) -> AlertEvaluation:
    """Evaluate one alert rule against the current metric value."""

    evaluation_time = now or utc_now()

    if current_value is None:
        return AlertEvaluation(
            matched=False,
            entered=False,
            exited=False,
            should_notify=False,
            reason="Current value is unavailable.",
        )

    if rule.numeric_value is not None:
        return _evaluate_numeric(
            rule,
            state,
            current_value,
            evaluation_time,
        )

    if rule.text_value is not None:
        return _evaluate_text(
            rule,
            state,
            current_value,
            evaluation_time,
        )

    raise AlertEvaluationError(
        f"Alert rule {rule.id} has neither numeric_value nor text_value."
    )


def _evaluate_numeric(
    rule: AlertRule,
    state: AlertState | None,
    current_value: Any,
    now: datetime,
) -> AlertEvaluation:
    try:
        current = float(current_value)
    except (TypeError, ValueError) as exc:
        raise AlertEvaluationError(
            f"Metric {rule.metric!r} is not numeric."
        ) from exc

    threshold = rule.numeric_value
    if threshold is None:
        raise AlertEvaluationError("Numeric rule is missing numeric_value.")

    previous = state.last_numeric_value if state else None
    operator = rule.operator

    if operator not in NUMERIC_OPERATORS:
        raise AlertEvaluationError(
            f"Unsupported numeric operator: {operator}"
        )

    if operator == "above":
        matched = current > threshold

    elif operator == "above_or_equal":
        matched = current >= threshold

    elif operator == "below":
        matched = current < threshold

    elif operator == "below_or_equal":
        matched = current <= threshold

    elif operator == "equal":
        matched = current == threshold

    elif operator == "crossed_above":
        matched = (
            previous is not None
            and previous <= threshold
            and current > threshold
        )

    elif operator == "crossed_below":
        matched = (
            previous is not None
            and previous >= threshold
            and current < threshold
        )

    else:
        matched = False

    was_active = state.is_active if state else False

    entered = matched and not was_active
    exited = not matched and was_active

    should_notify = _should_notify(
        rule,
        state,
        entered=entered,
        exited=exited,
        now=now,
    )

    return AlertEvaluation(
        matched=matched,
        entered=entered,
        exited=exited,
        should_notify=should_notify,
        current_numeric_value=current,
        previous_numeric_value=previous,
    )


def _evaluate_text(
    rule: AlertRule,
    state: AlertState | None,
    current_value: Any,
    now: datetime,
) -> AlertEvaluation:
    current = str(current_value)
    target = rule.text_value

    if target is None:
        raise AlertEvaluationError("Text rule is missing text_value.")

    previous = state.last_text_value if state else None
    operator = rule.operator

    if operator not in TEXT_OPERATORS:
        raise AlertEvaluationError(
            f"Unsupported text operator: {operator}"
        )

    if operator == "equal":
        matched = current == target

    elif operator == "not_equal":
        matched = current != target

    elif operator == "changed_to":
        matched = (
            previous is not None
            and previous != target
            and current == target
        )

    elif operator == "changed_from":
        matched = (
            previous is not None
            and previous == target
            and current != target
        )

    else:
        matched = False

    was_active = state.is_active if state else False

    entered = matched and not was_active
    exited = not matched and was_active

    should_notify = _should_notify(
        rule,
        state,
        entered=entered,
        exited=exited,
        now=now,
    )

    return AlertEvaluation(
        matched=matched,
        entered=entered,
        exited=exited,
        should_notify=should_notify,
        current_text_value=current,
        previous_text_value=previous,
    )


def _should_notify(
    rule: AlertRule,
    state: AlertState | None,
    *,
    entered: bool,
    exited: bool,
    now: datetime,
) -> bool:
    if not rule.enabled:
        return False

    wants_notification = (
        entered and rule.notify_on_enter
    ) or (
        exited and rule.notify_on_exit
    )

    if not wants_notification:
        return False

    if state is None or state.last_notified_at is None:
        return True

    cooldown = max(rule.cooldown_minutes, 0)

    if cooldown == 0:
        return True

    next_allowed = state.last_notified_at + timedelta(
        minutes=cooldown
    )

    return now >= next_allowed


def apply_evaluation_to_state(
    state: AlertState,
    evaluation: AlertEvaluation,
    *,
    notified: bool = False,
    now: datetime | None = None,
) -> None:
    """Update persistent alert state after an evaluation."""

    update_time = now or utc_now()

    state.is_active = evaluation.matched

    if evaluation.current_numeric_value is not None:
        state.previous_numeric_value = state.last_numeric_value
        state.last_numeric_value = evaluation.current_numeric_value

    if evaluation.current_text_value is not None:
        state.previous_text_value = state.last_text_value
        state.last_text_value = evaluation.current_text_value

    if evaluation.entered:
        state.last_triggered_at = update_time
        state.trigger_count += 1

    if evaluation.exited:
        state.last_cleared_at = update_time

    if notified:
        state.last_notified_at = update_time

    state.updated_at = update_time