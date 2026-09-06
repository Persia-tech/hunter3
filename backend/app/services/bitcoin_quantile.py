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
from math import exp, isfinite, log
from statistics import median

import numpy as np
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
    return a * log(t) + b * exp(-c * (ratio**d))


def _objective_numpy(
    raw_params: np.ndarray,
    *,
    times: np.ndarray,
    log_times: np.ndarray,
    log_prices: np.ndarray,
    t_scale: float,
    quantile: float,
) -> float:
    a, b, log_c, log_d = [float(value) for value in raw_params]
    if not all(isfinite(value) for value in (a, b, log_c, log_d)):
        return 1e30
    if abs(a) > 20 or abs(b) > 100 or not -9 <= log_c <= 5 or not -9 <= log_d <= 5:
        return 1e30

    c = exp(log_c)
    d = exp(log_d)
    try:
        ratio = np.maximum(times / t_scale, 1e-12)
        predicted = a * log_times + b * np.exp(-c * np.power(ratio, d))
        residual = log_prices - predicted
        losses = np.where(residual >= 0, quantile * residual, (quantile - 1.0) * residual)
        total = float(np.sum(losses))
    except (FloatingPointError, OverflowError, ValueError):
        return 1e30

    return total if isfinite(total) else 1e30


def _linear_seed(log_times: np.ndarray, log_prices: np.ndarray) -> tuple[float, float]:
    x_mean = float(np.mean(log_times))
    y_mean = float(np.mean(log_prices))
    denominator = float(np.sum((log_times - x_mean) ** 2))
    slope = 0.0 if denominator == 0 else float(
        np.sum((log_times - x_mean) * (log_prices - y_mean)) / denominator
    )
    intercept = y_mean - slope * x_mean
    return slope, intercept


def fit_bitcoin_quantile_model(
    records: list[PriceRecord],
    *,
    quantiles: tuple[float, ...] = DEFAULT_QUANTILES,
    anchor: date = GENESIS_ANCHOR,
    initializations: int = 4,
    maxiter: int = 1800,
) -> BitcoinQuantileModel:
    """Fit stretched-exponential quantile curves by pinball-loss minimization.

    Public research describes the Plan C v2 functional class as approximately:

        Q_tau(log10(P(t))) = a_tau * ln(t)
                           + b_tau * exp(-c_tau * (t / T) ** d_tau)

    with non-crossing quantile bands. Because the exact official v2 parameters
    and implementation are unpublished, this function independently fits that
    public functional class to the supplied Bitcoin history.
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
    times = np.array([_days_since_anchor(item.date, anchor) for item in ordered], dtype=float)
    prices = np.array([float(item.price) for item in ordered], dtype=float)
    if np.any(prices <= 0):
        raise ValueError("Bitcoin prices must be positive")

    log_times = np.log(times)
    log_prices = np.log10(prices)
    t_scale = float(median(times.tolist()))
    slope, intercept = _linear_seed(log_times, log_prices)

    c_seeds = (0.03, 0.10, 0.30, 1.0)
    d_seeds = (0.40, 0.75, 1.25, 2.0)
    fitted: list[QuantileParameters] = []

    baseline_residuals = np.sort(log_prices - (slope * log_times + intercept))

    for quantile in quantiles:
        residual_shift = float(np.quantile(baseline_residuals, quantile))
        b_seed = intercept + residual_shift
        starts = [
            np.array(
                [
                    slope,
                    b_seed,
                    log(c_seeds[idx % len(c_seeds)]),
                    log(d_seeds[idx % len(d_seeds)]),
                ],
                dtype=float,
            )
            for idx in range(initializations)
        ]

        best = None
        for start in starts:
            result = minimize(
                _objective_numpy,
                start,
                args=(),
                method="Nelder-Mead",
                options={"maxiter": maxiter, "xatol": 1e-7, "fatol": 1e-7},
                kwargs={
                    "times": times,
                    "log_times": log_times,
                    "log_prices": log_prices,
                    "t_scale": t_scale,
                    "quantile": quantile,
                },
            )
            if best is None or float(result.fun) < float(best.fun):
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
