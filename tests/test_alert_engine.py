from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from backend.app.services.alert_engine import apply_evaluation_to_state, evaluate_rule


def rule(operator="above", numeric=50, text=None, **values):
    defaults = dict(id=1, metric="opportunity_score", numeric_value=numeric, text_value=text,
                    operator=operator, enabled=True, notify_on_enter=True, notify_on_exit=True,
                    cooldown_minutes=0)
    defaults.update(values)
    return SimpleNamespace(**defaults)


def state(**values):
    defaults = dict(is_active=False, last_numeric_value=None, previous_numeric_value=None,
                    last_text_value=None, previous_text_value=None, last_notified_at=None,
                    last_triggered_at=None, last_cleared_at=None, trigger_count=0, updated_at=None)
    defaults.update(values)
    return SimpleNamespace(**defaults)


@pytest.mark.parametrize(("operator", "current", "expected"), [
    ("above", 51, True), ("above_or_equal", 50, True), ("below", 49, True),
    ("below_or_equal", 50, True), ("equal", 50, True),
])
def test_numeric_operators(operator, current, expected):
    assert evaluate_rule(rule(operator), state(), current).matched is expected


def test_crossing_transition_cooldown_and_state_update():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    current_state = state(last_numeric_value=50, last_notified_at=now - timedelta(minutes=2))
    evaluation = evaluate_rule(rule("crossed_above", cooldown_minutes=5), current_state, 51, now=now)
    assert evaluation.matched and evaluation.entered and not evaluation.should_notify
    apply_evaluation_to_state(current_state, evaluation, now=now)
    assert current_state.is_active and current_state.last_numeric_value == 51


@pytest.mark.parametrize(("operator", "previous", "current", "target", "matched"), [
    ("equal", None, "Warm", "Warm", True), ("not_equal", None, "Neutral", "Warm", True),
    ("changed_to", "Neutral", "Warm", "Warm", True), ("changed_from", "Warm", "Neutral", "Warm", True),
])
def test_text_operators(operator, previous, current, target, matched):
    assert evaluate_rule(rule(operator, numeric=None, text=target), state(last_text_value=previous), current).matched is matched

@pytest.mark.parametrize(("metric", "operator", "threshold", "outside", "inside"), [
    ("bitcoin_quantile_percentile", "below_or_equal", 10, 11, 10),
    ("bitcoin_mvrv_percentile", "below_or_equal", 20, 21, 20),
    ("opportunity_score", "above_or_equal", 60, 59, 60),
    ("bitcoin_mvrv_percentile", "above_or_equal", 90, 89, 90),
    ("bitcoin_top_stage2_active", "equal", 1, False, True),
    ("bitcoin_below_200d_ma", "equal", 1, False, True),
    ("bitcoin_below_200w_ma", "equal", 1, False, True),
])
def test_bitcoin_alert_conditions_notify_once_on_entry(metric, operator, threshold, outside, inside):
    current_rule = rule(operator, numeric=threshold, metric=metric, notify_on_exit=False)
    current_state = state()

    initial = evaluate_rule(current_rule, current_state, outside)
    apply_evaluation_to_state(current_state, initial)
    assert not initial.should_notify

    entered = evaluate_rule(current_rule, current_state, inside)
    apply_evaluation_to_state(current_state, entered, notified=entered.should_notify)
    assert entered.entered and entered.should_notify

    duplicate = evaluate_rule(current_rule, current_state, inside)
    assert duplicate.matched and not duplicate.entered and not duplicate.should_notify
