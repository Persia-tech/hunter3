from __future__ import annotations

from datetime import date, timedelta

from backend.app.services.bitcoin_top_confluence_research import TopConfluencePoint
from backend.app.services.bitcoin_top_staged_derisking import (
    evaluate_staged_derisking,
    summarize_staged_derisking,
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


def test_staged_derisking_uses_fixed_stage_tranches() -> None:
    start = date(2020, 1, 1)
    points: list[TopConfluencePoint] = []
    for i in range(500):
        day = start + timedelta(days=i)
        price = 100.0
        if i >= 40:
            price = 80.0
        if i >= 80:
            price = 60.0
        mvrv = 95.0 if i == 0 else 50.0
        heat = 80.0 if i < 20 else 40.0
        points.append(_point(day, price, heat, 95.0, mvrv))

    rows = evaluate_staged_derisking(points)
    selected = {row.strategy: row for row in rows}

    assert selected["Sell 100% at Stage 1"].sold_pct == 100.0
    assert selected["Staged 25/25/50"].sold_pct <= 100.0
    assert selected["Staged 33/33/34"].sold_pct <= 100.0
    assert selected["Staged 50/25/25"].sold_pct <= 100.0


def test_hold_is_zero_excess_vs_itself_and_no_peak_forgone() -> None:
    start = date(2021, 1, 1)
    points = [
        _point(
            start + timedelta(days=i),
            100.0 + i * 0.05,
            70.0,
            95.0,
            95.0 if i == 0 else 50.0,
        )
        for i in range(500)
    ]
    rows = evaluate_staged_derisking(points)
    hold = next(row for row in rows if row.strategy == "Hold BTC")

    assert hold.excess_return_vs_hold_pct_points == 0.0
    assert hold.peak_upside_forfeited_pct_points == 0.0
    assert hold.sold_pct == 0.0


def test_summary_contains_benchmarks_and_three_staged_allocations() -> None:
    start = date(2022, 1, 1)
    points = [
        _point(
            start + timedelta(days=i),
            100.0 + i * 0.02,
            70.0,
            95.0,
            95.0 if i == 0 else 50.0,
        )
        for i in range(500)
    ]
    rows = evaluate_staged_derisking(points)
    summaries = summarize_staged_derisking(rows)

    assert len(summaries) == 7
    assert {row.strategy for row in summaries} == {
        "Hold BTC",
        "Sell 100% at Stage 1",
        "Sell 100% at Stage 2",
        "Sell 100% at Stage 3",
        "Staged 25/25/50",
        "Staged 33/33/34",
        "Staged 50/25/25",
    }
