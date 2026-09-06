from __future__ import annotations

from datetime import date, timedelta

from backend.app.services.bitcoin_onchain_backtest import (
    build_onchain_point_in_time_backtest,
    default_threshold_summaries,
    independent_episodes,
)
from backend.app.services.bitcoin_onchain_research import OnChainResearchRow


def _row(day: date, *, price: float, mvrv: float, mvrv_z: float, future: float | None = 10.0) -> OnChainResearchRow:
    return OnChainResearchRow(
        date=day,
        price_usd=price,
        mvrv=mvrv,
        mvrv_z=mvrv_z,
        realized_cap_usd=None,
        nupl=None,
        future_return_180d_pct=None,
        future_return_365d_pct=future,
        future_max_drawdown_365d_pct=-5.0,
    )


def test_expanding_percentile_uses_only_history_through_today() -> None:
    start = date(2020, 1, 1)
    rows = [
        _row(start + timedelta(days=i), price=100 + i, mvrv=float(i + 1), mvrv_z=float(i + 1))
        for i in range(40)
    ]
    points = build_onchain_point_in_time_backtest(rows, minimum_history_days=30)

    first = points[0]
    assert first.date == start + timedelta(days=29)
    assert first.mvrv_percentile == 100.0 * 29.5 / 30.0

    # Appending an extreme future value must not change an earlier percentile.
    extended = rows + [_row(start + timedelta(days=40), price=140, mvrv=10_000.0, mvrv_z=10_000.0)]
    extended_points = build_onchain_point_in_time_backtest(extended, minimum_history_days=30)
    same_day = next(point for point in extended_points if point.date == first.date)
    assert same_day.mvrv_percentile == first.mvrv_percentile
    assert same_day.mvrv_z_percentile == first.mvrv_z_percentile


def test_future_labels_do_not_change_percentiles() -> None:
    start = date(2021, 1, 1)
    rows_a = [
        _row(start + timedelta(days=i), price=100 + i, mvrv=1.0 + i / 100.0, mvrv_z=i / 10.0, future=20.0)
        for i in range(35)
    ]
    rows_b = [
        _row(start + timedelta(days=i), price=100 + i, mvrv=1.0 + i / 100.0, mvrv_z=i / 10.0, future=-80.0)
        for i in range(35)
    ]

    points_a = build_onchain_point_in_time_backtest(rows_a, minimum_history_days=30)
    points_b = build_onchain_point_in_time_backtest(rows_b, minimum_history_days=30)
    assert [p.mvrv_percentile for p in points_a] == [p.mvrv_percentile for p in points_b]
    assert [p.mvrv_z_percentile for p in points_a] == [p.mvrv_z_percentile for p in points_b]


def test_default_summaries_and_episode_cooldown() -> None:
    start = date(2022, 1, 1)
    rows = []
    for i in range(140):
        mvrv = 0.9 if i in {30, 31, 32, 130} else 2.0
        rows.append(_row(start + timedelta(days=i), price=100 + i, mvrv=mvrv, mvrv_z=mvrv))
    points = build_onchain_point_in_time_backtest(rows, minimum_history_days=30)

    summaries = default_threshold_summaries(points)
    assert any(item.label == "MVRV <= 1.0" and item.count >= 4 for item in summaries)

    episodes = independent_episodes(points, predicate=lambda p: p.mvrv is not None and p.mvrv <= 1.0, cooldown_days=90)
    assert len(episodes) == 2
