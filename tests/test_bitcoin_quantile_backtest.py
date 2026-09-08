from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

from backend.app.models.price import PriceRecord
from backend.app.services.bitcoin_quantile_backtest import (
    QuantileBacktestPoint,
    build_quantile_backtest,
    independent_threshold_episodes,
)


def _records(count: int = 520) -> list[PriceRecord]:
    start = date(2020, 1, 1)
    return [
        PriceRecord(date=start + timedelta(days=index), price=Decimal(str(100 + index)))
        for index in range(count)
    ]


def _fake_fit(records, **kwargs):  # type: ignore[no-untyped-def]
    prices = [float(item.price) for item in records]
    return SimpleNamespace(mean=sum(prices) / len(prices), fit_date=records[-1].date)


def _fake_snapshot(model, *, day, price):  # type: ignore[no-untyped-def]
    percentile = max(0.0, min(100.0, 50.0 + (price / model.mean - 1.0) * 100.0))
    return SimpleNamespace(percentile=percentile)


def test_quantile_backtest_does_not_use_future_prices_for_historical_percentiles() -> None:
    original = _records()
    cutoff_index = 430
    cutoff = original[cutoff_index].date

    changed = list(original)
    for index in range(cutoff_index + 1, len(changed)):
        changed[index] = PriceRecord(
            date=changed[index].date,
            price=changed[index].price * Decimal("50"),
        )

    kwargs = dict(
        minimum_history_days=365,
        refit_days=30,
        fit_initializations=1,
        fit_maxiter=1,
        fit_model_func=_fake_fit,
        snapshot_func=_fake_snapshot,
    )
    first = build_quantile_backtest(original, **kwargs)
    second = build_quantile_backtest(changed, **kwargs)

    first_past = [point for point in first if point.as_of <= cutoff]
    second_past = [point for point in second if point.as_of <= cutoff]

    assert len(first_past) == len(second_past)
    assert [point.quantile_percentile for point in first_past] == [
        point.quantile_percentile for point in second_past
    ]
    assert [point.model_fit_date for point in first_past] == [point.model_fit_date for point in second_past]


def test_quantile_backtest_refits_on_configured_cadence() -> None:
    points = build_quantile_backtest(
        _records(430),
        minimum_history_days=365,
        refit_days=20,
        fit_initializations=1,
        fit_maxiter=1,
        fit_model_func=_fake_fit,
        snapshot_func=_fake_snapshot,
    )

    fit_dates = []
    for point in points:
        if not fit_dates or point.model_fit_date != fit_dates[-1]:
            fit_dates.append(point.model_fit_date)

    assert len(fit_dates) >= 3
    assert (fit_dates[1] - fit_dates[0]).days == 20
    assert (fit_dates[2] - fit_dates[1]).days == 20


def test_independent_quantile_episodes_count_entries_not_consecutive_days() -> None:
    start = date(2020, 1, 1)
    percentiles = [30, 9, 8, 7, 30, 9, 8, 30, 9]
    points = [
        QuantileBacktestPoint(
            as_of=start + timedelta(days=index * 50),
            price=100.0,
            quantile_percentile=value,
            model_fit_date=start,
            future_return_180d_pct=None,
            future_return_365d_pct=None,
            future_max_gain_365d_pct=None,
            future_max_drawdown_365d_pct=None,
        )
        for index, value in enumerate(percentiles)
    ]

    episodes = independent_threshold_episodes(
        points,
        threshold=10,
        direction="low",
        cooldown_days=90,
    )

    assert len(episodes) == 3
    assert [point.quantile_percentile for point in episodes] == [9, 9, 9]
