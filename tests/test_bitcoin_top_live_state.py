from datetime import date, timedelta
from decimal import Decimal

from backend.app.models.onchain import BitcoinOnChainRecord
from backend.app.models.price import PriceRecord
from backend.app.services.bitcoin_top_live_state import (
    _independent_warning_dates,
    _mvrv_percentile_series,
    evaluate_live_top_stage2,
)


def _onchain(day: date, value: float) -> BitcoinOnChainRecord:
    return BitcoinOnChainRecord(
        date=day,
        price_usd=None,
        mvrv=value,
        mvrv_z=None,
        realized_cap_usd=None,
        nupl=None,
    )


def test_expanding_mvrv_percentile_uses_midrank_without_future_values() -> None:
    start = date(2020, 1, 1)
    rows = [_onchain(start + timedelta(days=i), value) for i, value in enumerate((1.0, 2.0, 2.0, 4.0))]
    series = _mvrv_percentile_series(rows)

    assert [round(value, 2) for _, value in series] == [50.0, 75.0, 66.67, 87.5]


def test_warning_dates_require_entry_and_respect_cooldown() -> None:
    start = date(2020, 1, 1)
    rows = [
        (start, 89.0),
        (start + timedelta(days=1), 91.0),
        (start + timedelta(days=2), 95.0),
        (start + timedelta(days=3), 80.0),
        (start + timedelta(days=30), 92.0),
        (start + timedelta(days=31), 70.0),
        (start + timedelta(days=100), 93.0),
    ]
    warnings = _independent_warning_dates(rows, cooldown_days=90)

    assert warnings == [start + timedelta(days=1), start + timedelta(days=100)]


def test_live_stage_is_inactive_when_no_mvrv_warning_exists() -> None:
    start = date(2024, 1, 1)
    prices = [PriceRecord(date=start + timedelta(days=i), price=Decimal("50000")) for i in range(420)]

    # Keep MVRV genuinely neutral. A monotonically rising synthetic series is
    # always near the top of its own expanding history and therefore correctly
    # creates a >=90th-percentile warning even when the absolute values look low.
    onchain = [_onchain(start + timedelta(days=i), 1.2) for i in range(420)]

    state = evaluate_live_top_stage2(prices, onchain, as_of=start + timedelta(days=419))

    assert state.active is False
    assert state.warning_date is None
    assert state.confirmation_date is None
    assert state.current_any2_streak_days == 0
