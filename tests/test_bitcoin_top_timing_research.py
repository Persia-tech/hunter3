from __future__ import annotations

from datetime import date, timedelta

from backend.app.services.bitcoin_top_confluence_research import TopConfluencePoint, TopSpec
from backend.app.services.bitcoin_top_timing_research import (
    evaluate_top_timing,
    summarize_top_timing,
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


def test_top_timing_measures_upside_then_running_peak_drawdown() -> None:
    start = date(2020, 1, 1)
    points: list[TopConfluencePoint] = []
    for i in range(401):
        day = start + timedelta(days=i)
        heat = 65.0 if i == 0 else 20.0
        q = 50.0
        m = 50.0
        if i <= 30:
            price = 100.0 + i
        else:
            price = max(60.0, 130.0 - (i - 30) * 2.0)
        points.append(_point(day, price, heat, q, m))

    spec = TopSpec("Heat", require_overheat=True)
    rows = evaluate_top_timing(points, specs=(spec,))
    assert len(rows) == 1
    row = rows[0]
    assert row.days_to_peak_365d == 30
    assert round(row.additional_upside_365d_pct or 0.0, 1) == 30.0
    assert row.days_to_20pct_running_peak_dd is not None
    assert row.days_to_30pct_running_peak_dd is not None
    assert row.days_to_40pct_running_peak_dd is not None
    assert (row.max_peak_to_trough_dd_365d_pct or 0.0) <= -50.0


def test_recent_episode_is_right_censored() -> None:
    start = date(2024, 1, 1)
    points = [
        _point(start + timedelta(days=i), 100.0 + i * 0.1, 65.0 if i == 100 else 20.0, 50.0, 50.0)
        for i in range(300)
    ]
    spec = TopSpec("Heat", require_overheat=True)
    rows = evaluate_top_timing(points, specs=(spec,))
    assert len(rows) == 1
    row = rows[0]
    assert row.max_peak_to_trough_dd_180d_pct is not None
    assert row.max_peak_to_trough_dd_365d_pct is None
    assert row.peak_date_365d is None


def test_summary_keeps_fixed_signal_separate() -> None:
    start = date(2021, 1, 1)
    points: list[TopConfluencePoint] = []
    for i in range(401):
        day = start + timedelta(days=i)
        heat = 65.0 if i == 0 else 20.0
        m = 95.0 if i == 100 else 50.0
        points.append(_point(day, 100.0 + i * 0.05, heat, 50.0, m))

    specs = (
        TopSpec("Heat", require_overheat=True),
        TopSpec("MVRV", require_mvrv=True),
    )
    rows = evaluate_top_timing(points, specs=specs)
    summaries = summarize_top_timing(rows, specs=specs)
    assert [row.signal for row in summaries] == ["Heat", "MVRV"]
    assert summaries[0].episodes == 1
    assert summaries[1].episodes == 1
