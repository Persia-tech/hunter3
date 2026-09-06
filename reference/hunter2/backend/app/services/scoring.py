"""Configurable, asset-class-aware market-temperature scoring."""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.models.market import AssetClass, Divergence, Trend


@dataclass(frozen=True)
class ScoreWeights:
    weekly_rsi: float = 0.30
    distance_200w: float = 0.25
    drawdown: float = 0.25
    stochastic_recovery: float = 0.10
    divergence: float = 0.10


@dataclass(frozen=True)
class Thresholds:
    weights: ScoreWeights
    below_200w_full: float
    above_200w_full: float
    drawdown_full: float
    drawdown_strength: float = 1.0


DEFAULT_THRESHOLDS = Thresholds(
    ScoreWeights(),
    -30,
    100,
    -50,
)

THRESHOLDS: dict[AssetClass, Thresholds] = {
    AssetClass.CRYPTO: Thresholds(
        ScoreWeights(),
        -25,
        150,
        -50,
    ),
    AssetClass.BROAD_MARKET_ETF: Thresholds(
        ScoreWeights(),
        -20,
        60,
        -45,
    ),
    AssetClass.SECTOR_ETF: Thresholds(
        ScoreWeights(),
        -30,
        85,
        -55,
    ),
    AssetClass.TECHNOLOGY: Thresholds(
        ScoreWeights(),
        -30,
        100,
        -55,
    ),
    AssetClass.INDIVIDUAL_STOCK: Thresholds(
        ScoreWeights(),
        -35,
        120,
        -65,
        0.45,
    ),
    AssetClass.COMMODITY: Thresholds(
        ScoreWeights(),
        -25,
        70,
        -45,
    ),
    AssetClass.OTHER: DEFAULT_THRESHOLDS,
}


@dataclass(frozen=True)
class ScoreInputs:
    weekly_rsi: float | None
    distance_200w: float | None
    drawdown: float
    stochastic_rsi: float | None
    divergence: Divergence
    recovery: bool
    momentum_12m: float | None
    trend: Trend


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, value))


def calculate_scores(
    inputs: ScoreInputs,
    asset_class: AssetClass,
) -> tuple[int, int]:

    config = THRESHOLDS.get(
        asset_class,
        DEFAULT_THRESHOLDS,
    )

    weights = config.weights
    weekly_rsi = inputs.weekly_rsi

    opportunity_rsi = (
        _clamp((50 - weekly_rsi) / 30 * 100)
        if weekly_rsi is not None
        else 0
    )

    overheat_rsi = (
        _clamp((weekly_rsi - 50) / 30 * 100)
        if weekly_rsi is not None
        else 0
    )

    if inputs.distance_200w is None:
        opportunity_distance = 0
        overheat_distance = 0
    else:
        opportunity_distance = _clamp(
            inputs.distance_200w
            / config.below_200w_full
            * 100
        )

        overheat_distance = _clamp(
            inputs.distance_200w
            / config.above_200w_full
            * 100
        )

    opportunity_drawdown = _clamp(
        inputs.drawdown
        / config.drawdown_full
        * 100
    )

    opportunity_drawdown *= config.drawdown_strength

    # Near an ATH contributes to heat,
    # without making drawdown a direct inverse score.
    overheat_drawdown = _clamp(
        (inputs.drawdown + 20) * 5
    )

    stochastic = inputs.stochastic_rsi

    opportunity_stochastic = (
        _clamp((50 - stochastic) * 2)
        if stochastic is not None
        else 0
    )

    overheat_stochastic = (
        _clamp((stochastic - 50) * 2)
        if stochastic is not None
        else 0
    )

    if inputs.recovery:
        opportunity_stochastic = max(
            opportunity_stochastic,
            100,
        )

    opportunity_divergence = (
        100
        if inputs.divergence is Divergence.BULLISH
        else 0
    )

    overheat_divergence = (
        100
        if inputs.divergence is Divergence.BEARISH
        else 0
    )

    def weighted(
        a: float,
        b: float,
        c: float,
        d: float,
        e: float,
    ) -> float:
        return (
            a * weights.weekly_rsi
            + b * weights.distance_200w
            + c * weights.drawdown
            + d * weights.stochastic_recovery
            + e * weights.divergence
        )

    opportunity = weighted(
        opportunity_rsi,
        opportunity_distance,
        opportunity_drawdown,
        opportunity_stochastic,
        opportunity_divergence,
    )

    overheat = weighted(
        overheat_rsi,
        overheat_distance,
        overheat_drawdown,
        overheat_stochastic,
        overheat_divergence,
    )

    # Momentum and trend are modifiers,
    # not large weighted inputs.
    if (
        inputs.trend is Trend.RECOVERING
        and opportunity >= 35
    ):
        opportunity += 8

    elif inputs.trend is Trend.FALLING:
        opportunity -= (
            8
            if asset_class is AssetClass.INDIVIDUAL_STOCK
            else 4
        )

    if (
        inputs.momentum_12m is not None
        and inputs.momentum_12m > 0.5
    ):
        overheat += min(
            8,
            inputs.momentum_12m * 8,
        )

    return (
        round(_clamp(opportunity)),
        round(_clamp(overheat)),
    )


def classify(
    opportunity: int,
    overheat: int,
    recovery: bool = False,
) -> str:
    """Choose one display status while preserving both raw scores."""

    if recovery and opportunity >= 60:
        return "Oversold Recovery"

    if opportunity > overheat:

        if opportunity >= 90:
            return "Extreme Opportunity"

        if opportunity >= 75:
            return "Strong Opportunity"

        if opportunity >= 60:
            return "Technically Oversold"

    if overheat >= opportunity:

        if overheat >= 90:
            return "Extreme Overbought"

        if overheat >= 75:
            return "Overbought"

        if overheat >= 60:
            return "Warm"

    return "Neutral"