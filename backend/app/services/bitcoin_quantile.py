"""Research-only Bitcoin long-term quantile model.

This module implements a transparent reproduction of the publicly described
Plan C v2 *functional form* using stretched-exponential quantile regression.
It is not the official Plan C implementation: the exact v2 fitted parameters,
piecewise details, and production code are not publicly available.

The model is intentionally kept separate from the production Opportunity and
Overheat scores. It is a research signal that can be validated independently
before any composite weighting is considered.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import exp, isfinite, log, log10
from statistics import median
from typing import Iterable

from scipy.optimize import minimize

from backend.app.models.price import PriceRecord


GENESIS_ANCHOR = date(2009, 1, 3)
DEFAULT_QUANTILES = (0.01, 0.10, 0.25, 0.50, 0.75, 0.95, 0.99)


@dataclass(frozen=True, slots=True)
class QuantileParameters:
    quantile: float
    a: float
    b: float
    c: float
    d: float
    check_loss: float


@dataclass(frozen=True, slots=True)
class BitcoinQuantileModel:
    anchor: date
    t_scale: float
    parameters: tuple[QuantileParameters, ...]


@dataclass(frozen=True, slots=True)
class BitcoinQuantileSnapshot:
    as_of: date
    price: float
    percentile: float
    bands: tuple[tuple[float, float], ...]
    method: str = "Plan C v2-style stretched-exponential quantile research reproduction"


def _days_since_anchor(day: date, anchor: date) -> float:
    days = (day - anchor).days
    if days <= 0:
        raise ValueError("Price observations must occur after the model anchor")
    return float(days)


def _pinball_loss(residual: float, quantile: float) -> float:
    return quantile * residual if residual >= 0 else (quantile - 1.0) * residual


def _predict_log_price_from_values(
    *,
    t: float,
    t_scale: float,
    a: float,
    b: float,
    c: float,
    d: float,
) -> float:
    ratio = max(t / t_scale, 1e-12)
    decay_power = ratio**d
    decay = exp(-c * decay_power)
    return a * log(t) + b * decay


def _objective(
    raw_params: Iterable[float],
    *,
    times: list[float],
    log_prices: list[float],
    t_scale: float,
    quantile: float,
) -> float:
    values = list(raw_params)
    if len(values) != 4:
        return 1e30

    a, b, log_c, log_d = values
    if not all(isfinite(value) for value in values):
        return 1e30
    if abs(a) > 20 or abs(b) > 100 or not -9 <= log_c <= 5 or not -9 <= log_d <= 5:
        return 1e30

    c = exp(log_c)
    d = exp(log_d)
    total = 0.0

    try:
        for t, observed in zip(times, log_prices):
            predicted = _predict_log_price_from_values(
                t=t,
                t_scale=t_scale,
                a=a,
                b=b,
                c=c,
                d=d,
            )
            if not isfinite(predicted):
                return 1e30
            total += _pinball_loss(observed - predicted, quantile)
    except (OverflowError, ValueError):
        return 1e30

    return total


def _linear_seed(times: list[float], log_prices: list[float]) -> tuple[float, float]:
    xs = [log(t) for t in times]
    x_mean = sum(xs) / len(xs)
    y_mean = sum(log_prices) / len(log_prices)
    denominator = sum((x - x_mean) ** 2 for x in xs)
    slope = 0.0 if denominator == 0 else sum(
        (x - x_mean) * (y - y_mean) for x, y in zip(xs, log_prices)
    ) / denominator
    intercept = y_mean - slope * x_mean
    return slope, intercept


def fit_bitcoin_quantile_model(
    records: list[PriceRecord],
    *,
    quantiles: tuple[float, ...] = DEFAULT_QUANTILES,
    anchor: date = GENESIS_ANCHOR,
    initializations: int = 6,
    maxiter: int = 2500,
) -> BitcoinQuantileModel:
    """Fit stretched-exponential quantile curves by pinball-loss minimization.

    Public research describes the Plan C v2 functional class as roughly:

        Q_tau(log(P(t))) = a_tau * ln(t)
                        + b_tau * exp(-c_tau * (t / T) ** d_tau)

    with non-crossing quantile bands. Because the exact official v2 parameters
    and implementation are unpublished, this function independently fits that
    public functional class to the supplied price history.
    """
    if len(records) < 365:
        raise ValueError("At least 365 daily price observations are required")
    if initializations < 1:
        raise ValueError("initializations must be at least 1")
    if any(not 0 < q < 1 for q in quantiles):
        raise ValueError("quantiles must be strictly between 0 and 1")
    if tuple(sorted(set(quantiles))) != quantiles:
        raise ValueError("quantiles must be unique and sorted ascending")

    ordered = sorted(records, key=lambda item: item.date)
    times = [_days_since_anchor(item.date, anchor) for item in ordered]
    prices = [float(item.price) for item in ordered]
    if any(price <= 0 for price in prices):
        raise ValueError("Bitcoin prices must be positive")
    log_prices = [log10(price) for price in prices]
    t_scale = float(median(times))

    slope, intercept = _linear_seed(times, log_prices)
    fitted: list[QuantileParameters] = []

    # Deterministic starting grid. This avoids random-search instability in tests
    # and makes local research runs reproducible.
    c_seeds = (0.03, 0.10, 0.30, 1.0, 3.0, 10.0)
    d_seeds = (0.35, 0.60, 1.0, 1.5, 2.0, 3.0)

    for quantile in quantiles:
        residuals = sorted(y - (slope * log(t) + intercept) for t, y in zip(times, log_prices))
        index = min(len(residuals) - 1, max(0, int(round(quantile * (len(residuals) - 1)))))
        residual_shift = residuals[index]
        b_seed = intercept + residual_shift

        starts: list[tuple[float, float, float, float]] = []
        for idx in range(initializations):
            c0 = c_seeds[idx % len(c_seeds)]
            d0 = d_seeds[(idx * 2) % len(d_seeds)]
            starts.append((slope, b_seed, log(c0), log(d0)))

        best = None
        for start in starts:
            objective = lambda values: _objective(  # noqa: E731
                values,
                times=times,
                log_prices=log_prices,
                t_scale=t_scale,
                quantile=quantile,
            )
            result = minimize(
                objective,
                start,
                method="Nelder-Mead",
                options={"maxiter": maxiter, "xatol": 1e-8, "fatol": 1e-8},
            )
            if best is None or result.fun < best.fun:
                best = result

        if best is None or not isfinite(float(best.fun)):
            raise RuntimeError(f"Quantile optimization failed for q={quantile}")

        a, b, log_c, log_d = [float(value) for value in best.x]
        fitted.append(
            QuantileParameters(
                quantile=quantile,
                a=a,
                b=b,
                c=exp(log_c),
                d=exp(log_d),
                check_loss=float(best.fun),
            )
        )

    return BitcoinQuantileModel(anchor=anchor, t_scale=t_scale, parameters=tuple(fitted))


def predict_quantile_bands(model: BitcoinQuantileModel, day: date) -> tuple[tuple[float, float], ...]:
    """Predict non-crossing price bands for one date using monotone rearrangement."""
    t = _days_since_anchor(day, model.anchor)
    raw: list[tuple[float, float]] = []
    for params in model.parameters:
        log_price = _predict_log_price_from_values(
            t=t,
            t_scale=model.t_scale,
            a=params.a,
            b=params.b,
            c=params.c,
            d=params.d,
        )
        raw.append((params.quantile, 10**log_price))

    quantiles = [item[0] for item in raw]
    sorted_prices = sorted(item[1] for item in raw)
    return tuple(zip(quantiles, sorted_prices))


def percentile_from_bands(price: float, bands: tuple[tuple[float, float], ...]) -> float:
    """Interpolate a 0-100 percentile location from fitted quantile bands."""
    if price <= 0:
        raise ValueError("price must be positive")
    if not bands:
        raise ValueError("bands must not be empty")

    ordered = sorted(bands, key=lambda item: item[0])
    if price <= ordered[0][1]:
        return 0.0
    if price >= ordered[-1][1]:
        return 100.0

    log_price = log(price)
    for (q0, p0), (q1, p1) in zip(ordered, ordered[1:]):
        if p0 <= price <= p1:
            if p1 <= p0:
                return q1 * 100.0
            fraction = (log_price - log(p0)) / (log(p1) - log(p0))
            return max(0.0, min(100.0, (q0 + fraction * (q1 - q0)) * 100.0))

    return 100.0


def snapshot_bitcoin_quantile(
    model: BitcoinQuantileModel,
    *,
    day: date,
    price: float,
) -> BitcoinQuantileSnapshot:
    bands = predict_quantile_bands(model, day)
    return BitcoinQuantileSnapshot(
        as_of=day,
        price=price,
        percentile=percentile_from_bands(price, bands),
        bands=bands,
    )
