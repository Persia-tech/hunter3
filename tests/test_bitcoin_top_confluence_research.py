from __future__ import annotations

from datetime import date, timedelta

from backend.app.services.bitcoin_top_confluence_research import (
    DEFAULT_TOP_SPECS,
    TopConfluencePoint,
    condition_matches,
    independent_top_episodes,
    summarize_top_spec,
)


def _point(
    day: date,
    *,
    heat: float,
    quantile: float,
    mvrv_pct: float,
    future: float | None = -20.0,
    drawdown: float | None = -40.0,
) -> TopConfluencePoint:
    return TopConfluencePoint(
        date=day,
        price=100.0,
        overheat_score=heat,
        quantile_percentile=quantile,
        mvrv_percentile=mvrv_pct,
        future_return_365d_pct=future,
        future_max_drawdown_365d_pct=drawdown,
    )


def test_top_conditions_keep_signal_families_separate() -> None:
    point = _point(date(2021, 1, 1), heat=70, quantile=95, mvrv_pct=92)
    assert condition_matches(point, DEFAULT_TOP_SPECS[0])
    assert condition_matches(point, DEFAULT_TOP_SPECS[1])
    assert condition_matches(point, DEFAULT_TOP_SPECS[2])
    assert condition_matches(point, DEFAULT_TOP_SPECS[-1])

    only_mvrv = _point(date(2021, 1, 2), heat=20, quantile=50, mvrv_pct=95)
    assert not condition_matches(only_mvrv, DEFAULT_TOP_SPECS[0])
    assert not condition_matches(only_mvrv, DEFAULT_TOP_SPECS[1])
    assert condition_matches(only_mvrv, DEFAULT_TOP_SPECS[2])


def test_top_summary_uses_selected_outcomes() -> None:
    spec = DEFAULT_TOP_SPECS[2]
    points = [
        _point(date(2020, 1, 1), heat=10, quantile=50, mvrv_pct=95, future=-40, drawdown=-50),
        _point(date(2020, 1, 2), heat=10, quantile=50, mvrv_pct=92, future=20, drawdown=-10),
        _point(date(2020, 1, 3), heat=90, quantile=99, mvrv_pct=50, future=-80, drawdown=-80),
    ]
    summary = summarize_top_spec(points, spec)
    assert summary.count == 2
    assert summary.valid_365d == 2
    assert summary.median_return_365d_pct == -10.0
    assert summary.negative_365d_rate_pct == 50.0
    assert summary.loss_30pct_365d_rate_pct == 50.0
    assert summary.drawdown_30pct_rate_pct == 50.0


def test_top_episode_detection_requires_exit_and_reentry() -> None:
    start = date(2021, 1, 1)
    spec = DEFAULT_TOP_SPECS[0]
    points: list[TopConfluencePoint] = []
    for i in range(140):
        active = 10 <= i <= 20 or i == 120
        points.append(
            _point(
                start + timedelta(days=i),
                heat=70 if active else 20,
                quantile=50,
                mvrv_pct=50,
            )
        )
    episodes = independent_top_episodes(points, spec, cooldown_days=90)
    assert [row.date for row in episodes] == [
        start + timedelta(days=10),
        start + timedelta(days=120),
    ]
