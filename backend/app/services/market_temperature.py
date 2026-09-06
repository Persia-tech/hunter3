"""Indicator orchestration for market temperature."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

from backend.app.models.market import Asset, Candle, MarketTemperature, Trend
from backend.app.services.scoring import (
    ScoreInputs,
    calculate_scores,
    classify,
)
from backend.app.services.technical_indicators import (
    ath_drawdown,
    detect_rsi_divergence,
    momentum,
    rsi_series,
    simple_moving_average,
    stochastic_rsi_series,
)


def _trend(
    price: float,
    sma_10m: float | None,
    momentum_12m: float | None,
    weekly_rsi: float | None,
    distance_200w: float | None,
) -> Trend:
    if (
        distance_200w is not None
        and distance_200w > 75
        and (weekly_rsi or 0) >= 70
    ):
        return Trend.EXTENDED

    if sma_10m is not None and price >= sma_10m:
        if momentum_12m is not None and momentum_12m > 0:
            return Trend.UPTREND

        return Trend.RECOVERING

    if weekly_rsi is not None and weekly_rsi < 35:
        return Trend.BOTTOMING

    return Trend.FALLING


def calculate_temperature(
    asset: Asset,
    weekly: Sequence[Candle],
    daily: Sequence[Candle],
    now: datetime | None = None,
    full_history: Sequence[Candle] | None = None,
) -> MarketTemperature:
    if not weekly:
        raise ValueError("weekly history must not be empty")

    weekly_values = [candle.close for candle in weekly]
    daily_values = [candle.close for candle in daily]

    # Weekly technical indicators use only completed weekly candles.
    current_weekly = weekly_values[-1]

    # Current displayed price uses the latest available daily close.
    current = (
        daily_values[-1]
        if daily_values
        else current_weekly
    )

    rsi_values = rsi_series(weekly_values)
    stochastic_values = stochastic_rsi_series(weekly_values)

    weekly_rsi = rsi_values[-1]

    previous_rsi = (
        rsi_values[-2]
        if len(rsi_values) > 1
        else None
    )

    stochastic = stochastic_values[-1]

    previous_stochastic = (
        stochastic_values[-2]
        if len(stochastic_values) > 1
        else None
    )

    # 200-week SMA uses completed weekly candles.
    sma_200w = simple_moving_average(
        weekly_values,
        200,
    )

    # Distance from 200-week SMA uses latest market price.
    distance = (
        (current - sma_200w)
        / sma_200w
        * 100
        if sma_200w
        else None
    )

    # True ATH uses maximum available historical data.
    if full_history:
        full_values = [
            candle.close
            for candle in full_history
        ]

        ath = (
            max(full_values)
            if full_values
            else current
        )

    else:
        ath, _ = ath_drawdown(weekly_values)

    # Protect against the latest price being a new ATH.
    ath = max(
        ath,
        current,
    )

    drawdown = (
        (current - ath)
        / ath
        * 100
        if ath
        else 0.0
    )

    # 200-day SMA uses daily prices.
    sma_200d = simple_moving_average(
        daily_values,
        200,
    )

    # Approximate 10-month SMA using 43 completed weeks.
    sma_10m = simple_moving_average(
        weekly_values,
        43,
    )

    # Approximate 12-month momentum using 52 weeks.
    momentum_12m = momentum(
        weekly_values,
        52,
    )

    divergence = detect_rsi_divergence(
        weekly_values,
        rsi_values,
    )

    # Weekly RSI recovery.
    rsi_recovery = (
        previous_rsi is not None
        and weekly_rsi is not None
        and previous_rsi < 30 <= weekly_rsi
    )

    # Weekly stochastic recovery.
    stochastic_recovery = (
        previous_stochastic is not None
        and stochastic is not None
        and previous_stochastic < 20 <= stochastic
    )

    # Moving-average recovery should use completed weekly candles.
    moving_average_recovery = (
        len(weekly_values) >= 44
        and sma_10m is not None
        and weekly_values[-2]
        < sum(weekly_values[-44:-1]) / 43
        and current_weekly >= sma_10m
    )

    recovery = (
        rsi_recovery
        or stochastic_recovery
        or moving_average_recovery
    )

    stochastic_signal = None

    if stochastic_recovery:
        stochastic_signal = "Bullish Cross"

    elif (
        previous_stochastic is not None
        and stochastic is not None
        and previous_stochastic > 80 >= stochastic
    ):
        stochastic_signal = "Bearish Cross"

    trend = _trend(
        current,
        sma_10m,
        momentum_12m,
        weekly_rsi,
        distance,
    )

    inputs = ScoreInputs(
        weekly_rsi=weekly_rsi,
        distance_200w=distance,
        drawdown=drawdown,
        stochastic_rsi=stochastic,
        divergence=divergence,
        recovery=recovery,
        momentum_12m=momentum_12m,
        trend=trend,
    )

    opportunity, overheat = calculate_scores(
        inputs,
        asset.asset_class,
    )

    return MarketTemperature(
        symbol=asset.symbol,
        name=asset.name,
        asset_class=asset.asset_class,
        as_of=now or datetime.now(timezone.utc),
        current_price=current,
        opportunity_score=opportunity,
        overheat_score=overheat,
        classification=classify(
            opportunity,
            overheat,
            recovery,
        ),
        weekly_rsi=weekly_rsi,
        previous_weekly_rsi=previous_rsi,
        stochastic_rsi=stochastic,
        previous_stochastic_rsi=previous_stochastic,
        stochastic_signal=stochastic_signal,
        sma_200w=sma_200w,
        distance_200w_percent=distance,
        ath=ath,
        drawdown_percent=drawdown,
        sma_200d=sma_200d,
        sma_10m=sma_10m,
        momentum_12m=momentum_12m,
        divergence=divergence,
        trend=trend,
        recovery_signal=recovery,
        history_status=(
            "Complete"
            if sma_200w is not None
            else "Insufficient History"
        ),
    )