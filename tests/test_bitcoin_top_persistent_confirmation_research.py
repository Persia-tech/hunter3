from __future__ import annotations

from datetime import date, timedelta

from backend.app.services.bitcoin_top_confluence_research import TopConfluencePoint
from backend.app.services.bitcoin_top_persistent_confirmation_research import (
    evaluate_persistent_top_confirmations,
    summarize_persistent_top_confirmations,
)


def _point(day: date, price: float, heat: float, mvrv: float) -> TopConfluencePoint:
    return TopConfluencePoint(
        date=day,
        price=price,
        overheat_score=heat,
        quantile_percentile=50.0,
        mvrv_percentile=mvrv,
        future_return_365d_pct=None,
        future_max_drawdown_365d_pct=None,
    )


def test_persistence_delays_immediate_any2_confirmation() -> None:
    start = date(2020, 1, 1)
    points: list[TopConfluencePoint] = []
    for i in range(800):
        day = start + timedelta(days=i)
        price = 100.0 + i * 0.2
        heat = 80.0
        mvrv = 50.0
        if i == 220:
            mvrv = 95.0
        if 230 <= i <= 232:
            price = 120.0
            heat = 50.0
        if 250 <= i <= 270:
            price = 105.0
            heat = 50.0
        points.append(_point(day, price, heat, mvrv))

    rows = evaluate_persistent_top_confirmations(points)
    selected = {row.rule: row for row in rows if row.warning_date == start + timedelta(days=220)}

    assert selected["Any 2 immediate"].confirmation_date is not None
    assert selected["Any 2 sustained 7d"].confirmation_date is not None
    assert selected["Any 2 sustained 7d"].confirmation_date > selected["Any 2 immediate"].confirmation_date
    assert selected["Any 2 sustained 14d"].confirmation_date is not None
    assert selected["Any 2 sustained 14d"].confirmation_date > selected["Any 2 sustained 7d"].confirmation_date


def test_200d_sma_break_is_structural_and_point_in_time() -> None:
    start = date(2021, 1, 1)
    points: list[TopConfluencePoint] = []
    for i in range(800):
        day = start + timedelta(days=i)
        price = 200.0 if i < 260 else 150.0
        heat = 70.0
        mvrv = 95.0 if i == 220 else 50.0
        points.append(_point(day, price, heat, mvrv))

    rows = evaluate_persistent_top_confirmations(points)
    selected = {row.rule: row for row in rows if row.warning_date == start + timedelta(days=220)}

    structural = selected["Below 200d SMA"]
    assert structural.confirmation_date == start + timedelta(days=260)
    assert structural.days_to_confirmation == 40


def test_summary_contains_all_fixed_rules() -> None:
    start = date(2022, 1, 1)
    points = [
        _point(
            start + timedelta(days=i),
            100.0 + i * 0.05,
            70.0,
            95.0 if i == 220 else 50.0,
        )
        for i in range(800)
    ]
    rows = evaluate_persistent_top_confirmations(points)
    summaries = summarize_persistent_top_confirmations(rows)

    assert len(summaries) == 6
    assert {row.rule for row in summaries} == {
        "Any 2 immediate",
        "Any 2 sustained 7d",
        "Any 2 sustained 14d",
        "20% drawdown + one other weakness",
        "Below 50d SMA sustained 7d",
        "Below 200d SMA",
    }
