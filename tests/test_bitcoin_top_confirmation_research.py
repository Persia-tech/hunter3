from __future__ import annotations

from datetime import date, timedelta

from backend.app.services.bitcoin_top_confirmation_research import (
    evaluate_top_confirmations,
    summarize_top_confirmations,
)
from backend.app.services.bitcoin_top_confluence_research import TopConfluencePoint


def _point(day: date, price: float, heat: float, mvrv_pct: float) -> TopConfluencePoint:
    return TopConfluencePoint(
        date=day,
        price=price,
        overheat_score=heat,
        quantile_percentile=50.0,
        mvrv_percentile=mvrv_pct,
        future_return_365d_pct=None,
        future_max_drawdown_365d_pct=None,
    )


def test_confirmations_are_point_in_time_after_mvrv_warning() -> None:
    start = date(2020, 1, 1)
    points: list[TopConfluencePoint] = []
    for i in range(500):
        day = start + timedelta(days=i)
        price = 100.0 + min(i, 100) * 1.0
        if i > 100:
            price = 200.0 - (i - 100) * 1.0
        heat = 80.0 if i <= 100 else 50.0
        mvrv = 95.0 if i == 50 else 50.0
        points.append(_point(day, max(price, 20.0), heat, mvrv))

    rows = evaluate_top_confirmations(points)
    selected = {row.rule: row for row in rows if row.warning_date == start + timedelta(days=50)}

    assert selected["Below 50d SMA"].confirmation_date is not None
    assert selected["30d momentum < 0"].confirmation_date is not None
    assert selected["10% drawdown from post-warning peak"].confirmation_date is not None
    assert selected["Overheat rollover >=20"].confirmation_date is not None
    assert selected["Any 2 confirmations"].confirmation_date is not None
    assert all(
        row.confirmation_date is None or row.confirmation_date >= row.warning_date
        for row in selected.values()
    )


def test_unconfirmed_warning_stays_explicit() -> None:
    start = date(2021, 1, 1)
    points = [
        _point(
            start + timedelta(days=i),
            100.0 + i * 0.5,
            70.0,
            95.0 if i == 60 else 50.0,
        )
        for i in range(500)
    ]
    rows = evaluate_top_confirmations(points)
    selected = [row for row in rows if row.warning_date == start + timedelta(days=60)]
    assert len(selected) == 5
    assert all(row.confirmation_date is None for row in selected)


def test_summary_contains_each_fixed_rule() -> None:
    start = date(2022, 1, 1)
    points: list[TopConfluencePoint] = []
    for i in range(500):
        price = 100.0 + i * 0.2 if i < 100 else 120.0 - (i - 100) * 0.2
        heat = 75.0 if i < 110 else 45.0
        mvrv = 95.0 if i == 50 else 50.0
        points.append(_point(start + timedelta(days=i), max(price, 20.0), heat, mvrv))
    rows = evaluate_top_confirmations(points)
    summaries = summarize_top_confirmations(rows)
    assert len(summaries) == 5
    assert {row.rule for row in summaries} == {
        "Below 50d SMA",
        "30d momentum < 0",
        "10% drawdown from post-warning peak",
        "Overheat rollover >=20",
        "Any 2 confirmations",
    }
