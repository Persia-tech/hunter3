from __future__ import annotations

from datetime import date, timedelta

from backend.app.services.bitcoin_top_confluence_research import TopConfluencePoint
from backend.app.services.bitcoin_top_stage_ablation import (
    VARIANTS,
    evaluate_top_stage_ablation,
    summarize_top_stage_ablation,
)


def _point(day: date, price: float, heat: float, q: float, m: float) -> TopConfluencePoint:
    return TopConfluencePoint(
        date=day,
        price=price,
        overheat_score=heat,
        quantile_percentile=q,
        mvrv_percentile=m,
        future_return_365d_pct=None,
        future_max_drawdown_365d_pct=None,
    )


def test_top_ablation_keeps_omitted_tranches_in_btc() -> None:
    start = date(2020, 1, 1)
    points: list[TopConfluencePoint] = []
    for i in range(701):
        day = start + timedelta(days=i)
        price = 100.0
        if i >= 60:
            price = 80.0
        if i >= 120:
            price = 60.0
        mvrv = 95.0 if i == 0 else 50.0
        heat = 80.0 if i < 20 else 40.0
        points.append(_point(day, price, heat, 50.0, mvrv))

    rows = evaluate_top_stage_ablation(points)
    focus = [
        row for row in rows
        if row.allocation == "Staged 50/25/25" and row.warning_date == start
    ]
    assert {row.variant for row in focus} == set(VARIANTS)
    s1 = next(row for row in focus if row.variant == "Stage 1 only")
    all3 = next(row for row in focus if row.variant == "Stage 1 + Stage 2 + Stage 3")
    assert s1.sold_pct == 50.0
    assert all3.sold_pct >= s1.sold_pct


def test_top_ablation_summary_has_all_allocations_and_variants() -> None:
    start = date(2021, 1, 1)
    points = [
        _point(
            start + timedelta(days=i),
            100.0 + i * 0.05,
            20.0,
            50.0,
            95.0 if i == 0 else 40.0,
        )
        for i in range(701)
    ]
    rows = evaluate_top_stage_ablation(points)
    summaries = summarize_top_stage_ablation(rows)
    assert len(summaries) == 12
    assert all(row.episodes == 1 for row in summaries)


def test_top_ablation_rejects_nonpositive_horizon() -> None:
    try:
        evaluate_top_stage_ablation([], horizon_days=0)
    except ValueError as exc:
        assert "positive" in str(exc)
    else:
        raise AssertionError("expected ValueError")
