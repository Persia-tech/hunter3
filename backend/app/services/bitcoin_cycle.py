"""Bitcoin-specific long-term cycle indicators and scores."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from backend.app.models.market import Divergence
from backend.app.models.price import PriceRecord
from backend.app.services.technical_indicators import (
    ath_drawdown,
    detect_rsi_divergence,
    momentum,
    rsi_series,
    simple_moving_average,
)


@dataclass(frozen=True, slots=True)
class BitcoinCycleResult:
    as_of: date
    price: float
    opportunity_score: int
    overheat_score: int
    weekly_rsi: float | None
    divergence: Divergence
    sma_200w: float | None
    distance_200w_pct: float | None
    sma_200d: float | None
    mayer_multiple: float | None
    pi_111dma: float | None
    pi_350dma_x2: float | None
    pi_ratio: float | None
    ath: float
    ath_drawdown_pct: float
    momentum_1y_pct: float | None


def _weekly_closes(records: list[PriceRecord]) -> list[float]:
    weeks: dict[tuple[int, int], float] = {}
    for record in records:
        iso = record.date.isocalendar()
        weeks[(iso.year, iso.week)] = float(record.price)
    return list(weeks.values())


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _opportunity_score(
    distance_200w: float | None,
    mayer: float | None,
    weekly_rsi: float | None,
    drawdown: float,
    momentum_1y: float | None,
    divergence: Divergence,
) -> int:
    score = 0.0
    if distance_200w is not None:
        score += 30 * _clamp((20 - distance_200w) / 50, 0, 1)
    if mayer is not None:
        score += 20 * _clamp((1.8 - mayer) / 1.0, 0, 1)
    if weekly_rsi is not None:
        score += 15 * _clamp((55 - weekly_rsi) / 25, 0, 1)
    score += 15 * _clamp((-drawdown - 20) / 60, 0, 1)
    if momentum_1y is not None:
        score += 10 * _clamp((0.15 - momentum_1y) / 0.8, 0, 1)
    if divergence == Divergence.BULLISH:
        score += 10
    return round(_clamp(score))


def _overheat_score(
    distance_200w: float | None,
    mayer: float | None,
    weekly_rsi: float | None,
    pi_ratio: float | None,
    momentum_1y: float | None,
    divergence: Divergence,
) -> int:
    score = 0.0
    if pi_ratio is not None:
        score += 25 * _clamp((pi_ratio - 0.75) / 0.25, 0, 1)
    if mayer is not None:
        score += 20 * _clamp((mayer - 1.5) / 1.0, 0, 1)
    if distance_200w is not None:
        score += 20 * _clamp((distance_200w - 100) / 250, 0, 1)
    if weekly_rsi is not None:
        score += 15 * _clamp((weekly_rsi - 60) / 25, 0, 1)
    if momentum_1y is not None:
        score += 10 * _clamp((momentum_1y - 0.5) / 1.5, 0, 1)
    if divergence == Divergence.BEARISH:
        score += 10
    return round(_clamp(score))


def calculate_bitcoin_cycle(records: list[PriceRecord]) -> BitcoinCycleResult:
    if len(records) < 400:
        raise ValueError("At least 400 daily Bitcoin price records are required")

    records = sorted(records, key=lambda item: item.date)
    daily = [float(item.price) for item in records]
    weekly = _weekly_closes(records)

    price = daily[-1]
    sma_200d = simple_moving_average(daily, 200)
    mayer = price / sma_200d if sma_200d else None

    sma_200w = simple_moving_average(weekly, 200)
    distance_200w = ((price / sma_200w) - 1) * 100 if sma_200w else None

    weekly_rsi_values = rsi_series(weekly, 14)
    weekly_rsi = weekly_rsi_values[-1] if weekly_rsi_values else None
    divergence = detect_rsi_divergence(weekly, weekly_rsi_values)

    pi_111 = simple_moving_average(daily, 111)
    pi_350 = simple_moving_average(daily, 350)
    pi_350_x2 = pi_350 * 2 if pi_350 else None
    pi_ratio = pi_111 / pi_350_x2 if pi_111 and pi_350_x2 else None

    ath, drawdown = ath_drawdown(daily)
    momentum_1y = momentum(daily, 365)

    opportunity = _opportunity_score(
        distance_200w, mayer, weekly_rsi, drawdown, momentum_1y, divergence
    )
    overheat = _overheat_score(
        distance_200w, mayer, weekly_rsi, pi_ratio, momentum_1y, divergence
    )

    return BitcoinCycleResult(
        as_of=records[-1].date,
        price=price,
        opportunity_score=opportunity,
        overheat_score=overheat,
        weekly_rsi=weekly_rsi,
        divergence=divergence,
        sma_200w=sma_200w,
        distance_200w_pct=distance_200w,
        sma_200d=sma_200d,
        mayer_multiple=mayer,
        pi_111dma=pi_111,
        pi_350dma_x2=pi_350_x2,
        pi_ratio=pi_ratio,
        ath=ath,
        ath_drawdown_pct=drawdown,
        momentum_1y_pct=(momentum_1y * 100 if momentum_1y is not None else None),
    )
