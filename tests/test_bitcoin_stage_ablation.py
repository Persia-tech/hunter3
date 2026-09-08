from __future__ import annotations

from datetime import date, timedelta

from backend.app.services.bitcoin_confluence_research import ConfluencePoint
from backend.app.services.bitcoin_stage_ablation import (
    evaluate_stage_ablation,
    summarize_stage_ablation,
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


def test_ablation_keeps_omitted_tranches_as_cash() -> None:
    start = date(2020, 1, 1)
    points: list[ConfluencePoint] = []
    for i in range(420):
        day = start + timedelta(days=i)
        q = 8.0
        m = 15.0 if i >= 30 else 40.0
        opp = 65.0 if 60 <= i <= 70 else 20.0
        points.append(_point(day, 100.0 + i * 0.1, opp, q, m))

    rows = evaluate_stage_ablation(points)
    selected = {
        row.variant: row
        for row in rows
        if row.allocation == "Staged 50/25/25"
    }

    assert selected["Stage 1 only"].invested_pct == 50.0
    assert selected["Stage 1 + Stage 2"].invested_pct == 75.0
    assert selected["Stage 1 + Stage 3"].invested_pct == 75.0
    assert selected["Stage 1 + Stage 2 + Stage 3"].invested_pct == 100.0


def test_stage3_ablation_uses_independent_opportunity_entries() -> None:
    start = date(2023, 1, 1)
    points: list[ConfluencePoint] = []
    for i in range(500):
        day = start + timedelta(days=i)
        q = 50.0
        m = 50.0
        opp = 20.0

        if 17 <= i <= 30:
            opp = 65.0
        if i >= 54:
            q = 8.0
        if i >= 67:
            m = 15.0
        if 67 <= i <= 75:
            opp = 65.0
        if 120 <= i <= 130:
            opp = 65.0

        points.append(_point(day, 100.0 + i * 0.1, opp, q, m))

    rows = evaluate_stage_ablation(points, cooldown_days=90)
    selected = {
        row.variant: row
        for row in rows
        if row.allocation == "Staged 50/25/25"
    }

    assert selected["Stage 1 + Stage 2"].stage2_date == start + timedelta(days=67)
    assert selected["Stage 1 + Stage 3"].stage3_date == start + timedelta(days=120)
    assert selected["Stage 1 + Stage 2 + Stage 3"].stage3_date == start + timedelta(days=120)


def test_summary_contains_all_fixed_allocations_and_variants() -> None:
    start = date(2021, 1, 1)
    points = [
        _point(start + timedelta(days=i), 100.0 + i * 0.2, 20.0, 8.0, 40.0)
        for i in range(420)
    ]
    rows = evaluate_stage_ablation(points)
    summaries = summarize_stage_ablation(rows)

    assert len(summaries) == 12
    assert {row.variant for row in summaries} == {
        "Stage 1 only",
        "Stage 1 + Stage 2",
        "Stage 1 + Stage 3",
        "Stage 1 + Stage 2 + Stage 3",
    }
    assert {row.allocation for row in summaries} == {
        "Staged 25/25/50",
        "Staged 33/33/34",
        "Staged 50/25/25",
    }
