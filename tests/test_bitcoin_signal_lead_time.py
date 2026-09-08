from __future__ import annotations

from datetime import date, timedelta

from backend.app.services.bitcoin_confluence_research import ConfluencePoint
from backend.app.services.bitcoin_signal_lead_time import (
    evaluate_lead_time_episodes,
    summarize_lead_time,
)


def _point(day: date, *, price: float, opp: float, quantile: float, mvrv_pct: float) -> ConfluencePoint:
    return ConfluencePoint(
        date=day,
        price=price,
        opportunity_score=opp,
        quantile_percentile=quantile,
        mvrv_percentile=mvrv_pct,
        future_return_365d_pct=None,
        future_max_drawdown_365d_pct=None,
    )


def test_lead_time_matches_next_opportunity_entry_and_gap_drawdown() -> None:
    start = date(2022, 1, 1)
    points = [
        _point(start, price=100, opp=20, quantile=50, mvrv_pct=50),
        _point(start + timedelta(days=1), price=90, opp=40, quantile=8, mvrv_pct=15),
        _point(start + timedelta(days=2), price=80, opp=45, quantile=7, mvrv_pct=14),
        _point(start + timedelta(days=3), price=70, opp=61, quantile=5, mvrv_pct=10),
        _point(start + timedelta(days=4), price=75, opp=65, quantile=4, mvrv_pct=9),
    ]

    rows = evaluate_lead_time_episodes(points, max_confirmation_days=365, cooldown_days=90)
    quantile = next(row for row in rows if row.signal == "Quantile <= 10")
    assert quantile.early_date == start + timedelta(days=1)
    assert quantile.confirmation_date == start + timedelta(days=3)
    assert quantile.lead_days == 2
    assert round(float(quantile.max_drawdown_to_confirmation_pct), 6) == round((70 / 90 - 1) * 100, 6)


def test_unconfirmed_episode_stays_explicit() -> None:
    start = date(2025, 1, 1)
    points = [
        _point(start, price=100, opp=20, quantile=8, mvrv_pct=15),
        _point(start + timedelta(days=1), price=95, opp=30, quantile=7, mvrv_pct=14),
        _point(start + timedelta(days=2), price=90, opp=40, quantile=6, mvrv_pct=13),
    ]

    rows = evaluate_lead_time_episodes(points, max_confirmation_days=30, cooldown_days=90)
    quantile = next(row for row in rows if row.signal == "Quantile <= 10")
    assert quantile.confirmation_date is None
    assert quantile.lead_days is None
    assert quantile.max_drawdown_to_confirmation_pct is None

    summary = next(row for row in summarize_lead_time(rows) if row.signal == "Quantile <= 10")
    assert summary.early_episode_count == 1
    assert summary.confirmed_count == 0
    assert summary.confirmation_rate_pct == 0.0
