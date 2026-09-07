from __future__ import annotations

from datetime import date, timedelta

from backend.app.services.bitcoin_confluence_research import ConfluencePoint
from backend.app.services.bitcoin_staged_accumulation import (
    evaluate_staged_accumulation,
    summarize_strategies,
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


def test_staged_strategy_deploys_only_when_fixed_stages_trigger() -> None:
    start = date(2020, 1, 1)
    points = []
    for i in range(366):
        day = start + timedelta(days=i)
        price = 100.0 - min(i, 100) * 0.2 + max(i - 100, 0) * 0.4
        q = 8.0
        m = 15.0 if i >= 30 else 40.0
        opp = 65.0 if i >= 60 else 20.0
        points.append(_point(day, price, opp, q, m))

    rows = evaluate_staged_accumulation(points)
    staged = next(row for row in rows if row.strategy == "Staged 25/25/50")
    assert staged.stage2_date == start + timedelta(days=30)
    assert staged.stage3_date == start + timedelta(days=60)
    assert staged.invested_pct == 100.0


def test_untriggered_later_stages_leave_cash_uninvested() -> None:
    start = date(2021, 1, 1)
    points = [
        _point(start + timedelta(days=i), 100.0 + i * 0.1, 20.0, 8.0, 40.0)
        for i in range(366)
    ]
    rows = evaluate_staged_accumulation(points)
    staged = next(row for row in rows if row.strategy == "Staged 25/25/50")
    assert staged.stage2_date is None
    assert staged.stage3_date is None
    assert staged.invested_pct == 25.0

    summaries = summarize_strategies(rows)
    assert {row.strategy for row in summaries} == {
        "All-in at Stage 1",
        "Staged 25/25/50",
        "Staged 33/33/34",
        "Staged 50/25/25",
        "12-tranche 30d DCA",
    }


def test_stage3_uses_independent_opportunity_episode_not_daily_recrossing() -> None:
    start = date(2023, 1, 1)
    points: list[ConfluencePoint] = []
    for i in range(366):
        day = start + timedelta(days=i)
        q = 50.0
        m = 50.0
        opp = 20.0

        # First independent Opportunity episode begins before Stage 1.
        if 17 <= i <= 30:
            opp = 65.0

        # Stage 1 begins later and Stage 2 confirms after that.
        if i >= 54:
            q = 8.0
        if i >= 67:
            m = 15.0

        # Daily Opportunity recrossing inside 90 days of the January episode.
        # This must NOT count as a new independent Stage-3 confirmation.
        if 67 <= i <= 75:
            opp = 65.0

        # Genuine independent Opportunity entry after the cooldown.
        if 120 <= i <= 130:
            opp = 65.0

        points.append(_point(day, 100.0 + i * 0.1, opp, q, m))

    rows = evaluate_staged_accumulation(points, cooldown_days=90)
    staged = next(row for row in rows if row.strategy == "Staged 25/25/50")
    assert staged.episode_date == start + timedelta(days=54)
    assert staged.stage2_date == start + timedelta(days=67)
    assert staged.stage3_date == start + timedelta(days=120)


def test_fixed_allocation_sensitivity_changes_only_deployment_sizes() -> None:
    start = date(2020, 1, 1)
    points = []
    for i in range(366):
        day = start + timedelta(days=i)
        q = 8.0
        m = 15.0 if i >= 30 else 40.0
        opp = 65.0 if i >= 60 else 20.0
        points.append(_point(day, 100.0 + i * 0.1, opp, q, m))

    rows = evaluate_staged_accumulation(points)
    staged = {row.strategy: row for row in rows if row.strategy.startswith("Staged ")}

    assert staged["Staged 25/25/50"].invested_pct == 100.0
    assert staged["Staged 33/33/34"].invested_pct == 100.0
    assert staged["Staged 50/25/25"].invested_pct == 100.0

    stage2_dates = {row.stage2_date for row in staged.values()}
    stage3_dates = {row.stage3_date for row in staged.values()}
    assert stage2_dates == {start + timedelta(days=30)}
    assert stage3_dates == {start + timedelta(days=60)}
