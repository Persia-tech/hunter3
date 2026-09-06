from datetime import date, timedelta
from decimal import Decimal

from backend.app.models.price import PriceRecord
from backend.app.services.bitcoin_cycle import calculate_bitcoin_cycle


def test_partial_current_week_is_excluded_from_weekly_series() -> None:
    start = date(2020, 1, 5)  # Sunday
    records = [
        PriceRecord(
            date=start + timedelta(days=index),
            price=Decimal(str(10000 + index * 5)),
        )
        for index in range(1500)
    ]

    sunday_index = next(
        index for index in range(len(records) - 2, 400, -1)
        if records[index].date.weekday() == 6
    )
    sunday_records = records[: sunday_index + 1]
    sunday = calculate_bitcoin_cycle(sunday_records)

    monday_date = sunday_records[-1].date + timedelta(days=1)
    monday_records = sunday_records + [PriceRecord(monday_date, Decimal("999999"))]
    monday = calculate_bitcoin_cycle(monday_records)

    assert monday.weekly_rsi == sunday.weekly_rsi
    assert monday.sma_200w == sunday.sma_200w
