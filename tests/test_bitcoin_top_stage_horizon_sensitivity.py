from __future__ import annotations

from datetime import date, timedelta

from backend.app.services.bitcoin_top_confluence_research import TopConfluencePoint
from backend.app.services.bitcoin_top_stage_horizon_sensitivity import (
    evaluate_top_stage_horizon_sensitivity,
    summarize_top_stage_horizon_sensitivity,
)


def _point(day: date, price: float, mvrv: float) -> TopConfluencePoint:
    return TopConfluencePoint(
        date=day,
        price=price,
        overheat_score=80.0 if mvrv >= 90.0 else 20.0,
        quantile_percentile=95.0 if mvrv >= 90.0 else 50.0,
        mvrv_percentile=mvrv,
        future_return_365d_pct=None,
        future_max_drawdown_365d_pct=None,
    )


def _synthetic_points() -> list[TopConfluencePoint]:
    start = date(2020, 1, 1)
    warning_index = 250
    points: list[TopConfluencePoint] = []
    for i in range(1101):
        if i < warning_index:
            price = 100.0
        elif i <= warning_index + 20:
            price = 100.0 + (i - warning_index)
        else:
            price = max(55.0, 120.0 - 0.7 * (i - warning_index - 20))
        mvrv = 95.0 if i == warning_index else 50.0
        points.append(_point(start + timedelta(days=i), price, mvrv))
    return points


def test_top_horizon_sensitivity_keeps_signal_definitions_fixed() -> None:
    rows = evaluate_top_stage_horizon_sensitivity(_synthetic_points())
    focus = [
        row
        for row in rows
        if row.allocation == "Staged 50/25/25"
        and row.variant == "Stage 1 + Stage 2 + Stage 3"
    ]

    assert [row.horizon_days for row in focus] == [180, 365, 730]
    assert len({row.warning_date for row in focus}) == 1
    assert len({row.stage2_date for row in focus}) == 1
    assert len({row.stage3_date for row in focus}) == 1
    assert all(row.sold_pct == 100.0 for row in focus)


def test_top_horizon_summary_keeps_horizons_separate() -> None:
    rows = evaluate_top_stage_horizon_sensitivity(_synthetic_points())
    summaries = summarize_top_stage_horizon_sensitivity(rows)

    assert len(summaries) == 36
    assert {row.horizon_days for row in summaries} == {180, 365, 730}
    assert all(row.episodes == 1 for row in summaries)


def test_top_horizon_rejects_nonpositive_horizon() -> None:
    try:
        evaluate_top_stage_horizon_sensitivity(_synthetic_points(), horizons=(180, 0, 730))
    except ValueError as exc:
        assert "positive" in str(exc)
    else:
        raise AssertionError("expected ValueError")
