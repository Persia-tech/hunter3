from __future__ import annotations

from datetime import date, timedelta

from backend.app.services.bitcoin_confluence_research import (
    DEFAULT_SPECS,
    ConfluencePoint,
    ConfluenceSpec,
    condition_matches,
    evaluate_threshold_sensitivity,
    independent_confluence_episodes,
    summarize_spec,
)


def _point(
    day: date,
    *,
    opp: float,
    quantile: float,
    mvrv_pct: float,
    future: float | None = 50.0,
    drawdown: float | None = -10.0,
) -> ConfluencePoint:
    return ConfluencePoint(
        date=day,
        price=100.0,
        opportunity_score=opp,
        quantile_percentile=quantile,
        mvrv_percentile=mvrv_pct,
        future_return_365d_pct=future,
        future_max_drawdown_365d_pct=drawdown,
    )


def test_condition_matching_keeps_signals_separate() -> None:
    point = _point(date(2022, 1, 1), opp=65, quantile=8, mvrv_pct=15)
    assert condition_matches(point, DEFAULT_SPECS[0])
    assert condition_matches(point, DEFAULT_SPECS[1])
    assert condition_matches(point, DEFAULT_SPECS[2])
    assert condition_matches(point, DEFAULT_SPECS[-1])

    not_mvrv = _point(date(2022, 1, 2), opp=65, quantile=8, mvrv_pct=40)
    assert condition_matches(not_mvrv, DEFAULT_SPECS[0])
    assert condition_matches(not_mvrv, DEFAULT_SPECS[1])
    assert not condition_matches(not_mvrv, DEFAULT_SPECS[-1])


def test_summary_uses_only_selected_condition_outcomes() -> None:
    start = date(2020, 1, 1)
    spec = ConfluenceSpec("Q+M", require_quantile=True, require_mvrv=True)
    points = [
        _point(start, opp=10, quantile=5, mvrv_pct=10, future=100, drawdown=-5),
        _point(start + timedelta(days=1), opp=10, quantile=7, mvrv_pct=15, future=50, drawdown=-35),
        _point(start + timedelta(days=2), opp=80, quantile=50, mvrv_pct=10, future=-80, drawdown=-80),
    ]
    summary = summarize_spec(points, spec)
    assert summary.count == 2
    assert summary.valid_365d == 2
    assert summary.median_return_365d_pct == 75.0
    assert summary.positive_365d_rate_pct == 100.0
    assert summary.gain_50pct_365d_rate_pct == 100.0
    assert summary.drawdown_30pct_rate_pct == 50.0


def test_independent_episode_cooldown_counts_reentries() -> None:
    start = date(2022, 1, 1)
    spec = ConfluenceSpec("all", require_opportunity=True, require_quantile=True, require_mvrv=True)
    points: list[ConfluencePoint] = []
    for i in range(140):
        active = i in {10, 11, 12, 120}
        points.append(
            _point(
                start + timedelta(days=i),
                opp=70 if active else 20,
                quantile=5 if active else 50,
                mvrv_pct=10 if active else 50,
            )
        )
    episodes = independent_confluence_episodes(points, spec, cooldown_days=90)
    assert [item.date for item in episodes] == [start + timedelta(days=10), start + timedelta(days=120)]


def test_threshold_sensitivity_uses_predeclared_grid_without_fitting() -> None:
    start = date(2020, 1, 1)
    points = [
        _point(start, opp=55, quantile=12, mvrv_pct=25, future=50, drawdown=-10),
        _point(start + timedelta(days=1), opp=65, quantile=8, mvrv_pct=15, future=100, drawdown=-5),
        # Deliberately leave the loose all-three condition before the later
        # signal so episode counting tests a true threshold re-entry.
        _point(start + timedelta(days=50), opp=20, quantile=50, mvrv_pct=50, future=10, drawdown=-5),
        _point(start + timedelta(days=100), opp=75, quantile=4, mvrv_pct=8, future=-20, drawdown=-40),
    ]
    rows = evaluate_threshold_sensitivity(
        points,
        opportunity_thresholds=(50.0, 70.0),
        quantile_thresholds=(5.0, 15.0),
        mvrv_percentile_thresholds=(10.0, 30.0),
        cooldown_days=90,
    )
    assert len(rows) == 8

    loose = next(
        row
        for row in rows
        if row.opportunity_threshold == 50.0
        and row.quantile_threshold == 15.0
        and row.mvrv_percentile_threshold == 30.0
    )
    assert loose.daily_count == 3
    assert loose.episode_count == 2

    strict = next(
        row
        for row in rows
        if row.opportunity_threshold == 70.0
        and row.quantile_threshold == 5.0
        and row.mvrv_percentile_threshold == 10.0
    )
    assert strict.daily_count == 1
    assert strict.episode_count == 1
    assert strict.episode_median_return_365d_pct == -20.0
