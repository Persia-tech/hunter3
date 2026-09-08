from datetime import date, timedelta
from decimal import Decimal

from backend.app.models.price import PriceRecord
from backend.app.services.bitcoin_backtest import build_bitcoin_backtest


def test_daily_backtest_produces_one_point_per_day_after_warmup() -> None:
    start = date(2020, 1, 1)
    records = [
        PriceRecord(start + timedelta(days=i), Decimal(str(10000 + i)))
        for i in range(405)
    ]

    points = build_bitcoin_backtest(records, minimum_history_days=400, step_days=1)

    assert len(points) == 6
    assert points[0].as_of == records[399].date
    assert points[-1].as_of == records[-1].date
