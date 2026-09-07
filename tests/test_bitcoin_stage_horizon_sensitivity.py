from __future__ import annotations

from datetime import date, timedelta

from backend.app.services.bitcoin_confluence_research import ConfluencePoint
from backend.app.services.bitcoin_stage_horizon_sensitivity import (
    evaluate_stage_horizon_sensitivity,
    summarize_stage_horizon_sensitivity,
)


def _point(day: date, price: float, opp: float, q: float, m: float) -> ConfluencePoint:
    return ConfluencePoint(
        date=day,
        price=price,
        opportunity_score=opp,
        quantile_percentile=q,
        mvrv_percentile=m,
        future_return_365d_pct=None,
        future_max_drawdown_365d_pct=None,
    )


def test_horizon_sensitivity_changes_only_evaluation_window() -> None:
    start = date(2020, 1, 1)
    points: list[ConfluencePoint] = []
    for i in range(901):
        day = start + timedelta(days=i)
        q = 8.0
        m = 15.0 if i >= 30 else 40.0
        opp = 65.0 if 60 <= i <= 70 else 20.0
        points.append(_point(day, 100.0 + i * 0.2, opp, q, m))

    rows = evaluate_stage_horizon_sensitivity(points)
    focus = [
        row
        for row in rows
        if row.allocation == "Staged 50/25/25"
        and row.variant == "Stage 1 + Stage 2 + Stage 3"
    ]

    assert [row.horizon_days for row in focus] == [180, 365, 730]
    assert {row.stage2_date for row in focus} == {start + timedelta(days=30)}
    assert {row.stage3_date for row in focus} == {start + timedelta(days=60)}
    assert all(row.invested_pct == 100.0 for row in focus)
    assert focus[0].return_pct < focus[1].return_pct < focus[2].return_pct


def test_horizon_summary_keeps_horizons_separate() -> None:
    start = date(2021, 1, 1)
    points = [
        _point(start + timedelta(days=i), 100.0 + i * 0.1, 20.0, 8.0, 40.0)
        for i in range(901)
    ]

    rows = evaluate_stage_horizon_sensitivity(points)
    summaries = summarize_stage_horizon_sensitivity(rows)

    assert len(summaries) == 36
    assert {row.horizon_days for row in summaries} == {180, 365, 730}
    assert all(row.episodes == 1 for row in summaries)
