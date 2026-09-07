"""Research helpers for validating Bitcoin on-chain valuation metrics."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from backend.app.models.onchain import BitcoinOnChainRecord


@dataclass(frozen=True, slots=True)
class OnChainResearchRow:
    date: object
    price_usd: float | None
    mvrv: float | None
    mvrv_z: float | None
    realized_cap_usd: float | None
    nupl: float | None
    future_return_180d_pct: float | None
    future_return_365d_pct: float | None
    future_max_drawdown_365d_pct: float | None


@dataclass(frozen=True, slots=True)
class MetricBandSummary:
    metric: str
    band: str
    count: int
    median_future_return_365d_pct: float | None
    positive_365d_rate_pct: float | None
    drawdown_30pct_rate_pct: float | None


def _future_return(prices: list[float | None], index: int, days: int) -> float | None:
    target = index + days
    if target >= len(prices):
        return None
    base = prices[index]
    future = prices[target]
    if base is None or future is None or base <= 0:
        return None
    return (future / base - 1.0) * 100.0


def _future_drawdown(prices: list[float | None], index: int, days: int) -> float | None:
    base = prices[index]
    if base is None or base <= 0 or index + 1 >= len(prices):
        return None
    end = min(len(prices), index + days + 1)
    window = [value for value in prices[index + 1 : end] if value is not None]
    if not window:
        return None
    return (min(window) / base - 1.0) * 100.0


def build_onchain_research_rows(records: list[BitcoinOnChainRecord]) -> list[OnChainResearchRow]:
    """Attach future price outcomes to already-historical raw on-chain metrics.

    The metrics themselves come directly from dated Coin Metrics observations.
    Future returns and drawdowns are validation labels only and never transform
    the on-chain inputs.
    """
    ordered = sorted(records, key=lambda item: item.date)
    prices = [item.price_usd for item in ordered]
    rows: list[OnChainResearchRow] = []
    for index, item in enumerate(ordered):
        rows.append(
            OnChainResearchRow(
                date=item.date,
                price_usd=item.price_usd,
                mvrv=item.mvrv,
                mvrv_z=item.mvrv_z,
                realized_cap_usd=item.realized_cap_usd,
                nupl=item.nupl,
                future_return_180d_pct=_future_return(prices, index, 180),
                future_return_365d_pct=_future_return(prices, index, 365),
                future_max_drawdown_365d_pct=_future_drawdown(prices, index, 365),
            )
        )
    return rows


def _rate(values: list[float], predicate) -> float | None:  # type: ignore[no-untyped-def]
    if not values:
        return None
    return 100.0 * sum(1 for value in values if predicate(value)) / len(values)


def summarize_metric_quantile_bands(
    rows: list[OnChainResearchRow],
    *,
    metric: str,
) -> list[MetricBandSummary]:
    """Summarize fixed empirical quintiles for one raw on-chain metric.

    Quintile cutoffs are descriptive full-sample research only. They are not a
    no-look-ahead trading rule and are intentionally not used in production.
    """
    if metric not in {"mvrv", "mvrv_z", "nupl"}:
        raise ValueError("metric must be one of: mvrv, mvrv_z, nupl")

    clean_values = sorted(
        float(getattr(row, metric))
        for row in rows
        if getattr(row, metric) is not None
    )
    if len(clean_values) < 5:
        return []

    def q(p: float) -> float:
        idx = int(round(p * (len(clean_values) - 1)))
        return clean_values[max(0, min(len(clean_values) - 1, idx))]

    cutoffs = [q(0.2), q(0.4), q(0.6), q(0.8)]
    labels = ("Q1 low", "Q2", "Q3", "Q4", "Q5 high")
    buckets: list[list[OnChainResearchRow]] = [[] for _ in range(5)]

    for row in rows:
        raw = getattr(row, metric)
        if raw is None:
            continue
        value = float(raw)
        bucket = 0
        while bucket < 4 and value > cutoffs[bucket]:
            bucket += 1
        buckets[bucket].append(row)

    summaries: list[MetricBandSummary] = []
    for label, bucket_rows in zip(labels, buckets):
        returns = [
            row.future_return_365d_pct
            for row in bucket_rows
            if row.future_return_365d_pct is not None
        ]
        drawdowns = [
            row.future_max_drawdown_365d_pct
            for row in bucket_rows
            if row.future_max_drawdown_365d_pct is not None
        ]
        summaries.append(
            MetricBandSummary(
                metric=metric,
                band=label,
                count=len(bucket_rows),
                median_future_return_365d_pct=median(returns) if returns else None,
                positive_365d_rate_pct=_rate(returns, lambda value: value > 0),
                drawdown_30pct_rate_pct=_rate(drawdowns, lambda value: value <= -30),
            )
        )
    return summaries
