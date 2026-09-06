from datetime import date, timedelta
from decimal import Decimal

from backend.app.models.price import PriceRecord
from backend.app.services.bitcoin_backtest import build_bitcoin_backtest
from backend.app.services.bitcoin_cycle import calculate_bitcoin_cycle


def _records(days: int = 1700) -> list[PriceRecord]:
    start = date(2018, 1, 1)
    return [
        PriceRecord(
            date=start + timedelta(days=index),
            price=Decimal(str(5000 + index * 7 + (index % 31) * 3)),
        )
        for index in range(days)
    ]


def test_unfinished_week_does_not_change_weekly_indicators() -> None:
    records = _records()
    sunday_index = next(
        index for index in range(len(records) - 2, 399, -1)
        if records[index].date.weekday() == 6
    )

    through_sunday = records[: sunday_index + 1]
    sunday_result = calculate_bitcoin_cycle(through_sunday)

    monday = records[sunday_index + 1]
    extreme_monday = PriceRecord(monday.date, Decimal("1000000"))
    monday_result = calculate_bitcoin_cycle(through_sunday + [extreme_monday])

    assert monday_result.weekly_rsi == sunday_result.weekly_rsi
    assert monday_result.sma_200w == sunday_result.sma_200w


def test_future_prices_do_not_change_historical_score() -> None:
    records = _records(900)
    baseline = build_bitcoin_backtest(records, minimum_history_days=400)

    changed = list(records)
    for index in range(500, len(changed)):
        changed[index] = PriceRecord(
            changed[index].date,
            changed[index].price * Decimal("10"),
        )

    altered = build_bitcoin_backtest(changed, minimum_history_days=400)

    # Index 99 corresponds to day 499, before any modified future observation.
    assert baseline[99].as_of == altered[99].as_of
    assert baseline[99].opportunity_score == altered[99].opportunity_score
    assert baseline[99].overheat_score == altered[99].overheat_score


def test_backtest_attaches_future_validation_without_using_it_as_input() -> None:
    points = build_bitcoin_backtest(_records(800), minimum_history_days=400)

    assert points
    assert points[0].future_return_180d_pct is not None
    assert points[0].future_return_365d_pct is not None
    assert points[-1].future_return_180d_pct is None
    assert 0 <= points[0].opportunity_score <= 100
    assert 0 <= points[0].overheat_score <= 100
