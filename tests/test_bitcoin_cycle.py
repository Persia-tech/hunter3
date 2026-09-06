from datetime import date, timedelta
from decimal import Decimal

from backend.app.models.price import PriceRecord
from backend.app.services.bitcoin_cycle import calculate_bitcoin_cycle


def _records(days: int = 2200) -> list[PriceRecord]:
    start = date(2020, 1, 1)
    result: list[PriceRecord] = []

    for index in range(days):
        # Smooth long-term uptrend with a full cycle-like wave so all indicators
        # have realistic, positive inputs without relying on network data.
        trend = 9000 + index * 18
        wave = 6000 * __import__("math").sin(index / 180)
        price = max(1000, trend + wave)
        result.append(
            PriceRecord(
                date=start + timedelta(days=index),
                price=Decimal(str(round(price, 2))),
            )
        )

    return result


def test_bitcoin_cycle_calculates_core_indicators() -> None:
    result = calculate_bitcoin_cycle(_records())

    assert result.price > 0
    assert result.sma_200d is not None
    assert result.sma_200w is not None
    assert result.mayer_multiple is not None
    assert result.pi_111dma is not None
    assert result.pi_350dma_x2 is not None
    assert result.pi_ratio is not None
    assert result.weekly_rsi is not None
    assert 0 <= result.opportunity_score <= 100
    assert 0 <= result.overheat_score <= 100


def test_bitcoin_cycle_requires_enough_history() -> None:
    try:
        calculate_bitcoin_cycle(_records(399))
    except ValueError as exc:
        assert "400" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
