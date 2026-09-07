"""Research-only staged Bitcoin accumulation comparison.

The strategy rules are fixed in advance and are not optimized from future
returns. Each experiment begins at an independent Quantile <= 10 episode and
compares three ways to deploy the same initial $100 of cash over the following
365 days.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from statistics import median

from backend.app.services.bitcoin_confluence_research import (
    ConfluencePoint,
    ConfluenceSpec,
    condition_matches,
    independent_confluence_episodes,
)


STAGE1_SPEC = ConfluenceSpec("Stage 1: Quantile <= 10", require_quantile=True)
STAGE2_SPEC = ConfluenceSpec(
    "Stage 2: Quantile <= 10 + MVRV pct <= 20",
    require_quantile=True,
    require_mvrv=True,
)
STAGE3_SPEC = ConfluenceSpec("Stage 3: Opportunity >= 60", require_opportunity=True)


@dataclass(frozen=True, slots=True)
class StrategyResult:
    episode_date: date
    strategy: str
    stage2_date: date | None
    stage3_date: date | None
    invested_pct: float
    average_entry_price: float | None
    final_value: float
    return_365d_pct: float
    max_drawdown_pct: float


@dataclass(frozen=True, slots=True)
class StrategySummary:
    strategy: str
    episodes: int
    median_return_365d_pct: float | None
    positive_rate_pct: float | None
    median_max_drawdown_pct: float | None
    worst_max_drawdown_pct: float | None
    median_invested_pct: float | None


def _find_first(
    points: list[ConfluencePoint],
    *,
    start: date,
    end: date,
    spec: ConfluenceSpec,
) -> ConfluencePoint | None:
    return next(
        (point for point in points if start <= point.date <= end and condition_matches(point, spec)),
        None,
    )


def _simulate(
    window: list[ConfluencePoint],
    *,
    purchases: list[tuple[date, float]],
    strategy: str,
    episode_date: date,
    stage2_date: date | None,
    stage3_date: date | None,
) -> StrategyResult:
    cash = 100.0
    btc = 0.0
    total_spent = 0.0
    purchase_map: dict[date, float] = {}
    for day, amount in purchases:
        purchase_map[day] = purchase_map.get(day, 0.0) + amount

    values: list[float] = []
    for point in window:
        amount = purchase_map.get(point.date, 0.0)
        if amount > 0:
            amount = min(amount, cash)
            btc += amount / point.price
            cash -= amount
            total_spent += amount
        values.append(cash + btc * point.price)

    peak = values[0]
    max_drawdown = 0.0
    for value in values:
        peak = max(peak, value)
        if peak > 0:
            max_drawdown = min(max_drawdown, (value / peak - 1.0) * 100.0)

    final_value = values[-1]
    average_entry = total_spent / btc if btc > 0 else None
    return StrategyResult(
        episode_date=episode_date,
        strategy=strategy,
        stage2_date=stage2_date,
        stage3_date=stage3_date,
        invested_pct=total_spent,
        average_entry_price=average_entry,
        final_value=final_value,
        return_365d_pct=final_value - 100.0,
        max_drawdown_pct=max_drawdown,
    )


def evaluate_staged_accumulation(
    points: list[ConfluencePoint],
    *,
    horizon_days: int = 365,
    cooldown_days: int = 90,
) -> list[StrategyResult]:
    """Compare fixed staged deployment against all-in Stage 1 and fixed DCA.

    Staged rule: 25% at Quantile <=10, 25% when MVRV also <=20, and 50%
    when Opportunity >=60. Untriggered capital remains cash. Benchmark DCA uses
    twelve equal tranches every 30 days beginning at the Stage-1 date.
    """
    if horizon_days < 330:
        raise ValueError("horizon_days must be at least 330")

    ordered = sorted(points, key=lambda item: item.date)
    by_date = {point.date: point for point in ordered}
    stage1_episodes = independent_confluence_episodes(
        ordered,
        STAGE1_SPEC,
        cooldown_days=cooldown_days,
    )

    results: list[StrategyResult] = []
    for entry in stage1_episodes:
        end_date = entry.date + timedelta(days=horizon_days)
        if end_date not in by_date:
            continue
        window = [point for point in ordered if entry.date <= point.date <= end_date]

        stage2 = _find_first(window, start=entry.date, end=end_date, spec=STAGE2_SPEC)
        stage3 = None
        if stage2 is not None:
            stage3 = _find_first(window, start=stage2.date, end=end_date, spec=STAGE3_SPEC)

        staged_purchases = [(entry.date, 25.0)]
        if stage2 is not None:
            staged_purchases.append((stage2.date, 25.0))
        if stage3 is not None:
            staged_purchases.append((stage3.date, 50.0))

        results.append(
            _simulate(
                window,
                purchases=[(entry.date, 100.0)],
                strategy="All-in at Stage 1",
                episode_date=entry.date,
                stage2_date=stage2.date if stage2 else None,
                stage3_date=stage3.date if stage3 else None,
            )
        )
        results.append(
            _simulate(
                window,
                purchases=staged_purchases,
                strategy="Staged 25/25/50",
                episode_date=entry.date,
                stage2_date=stage2.date if stage2 else None,
                stage3_date=stage3.date if stage3 else None,
            )
        )

        dca_purchases: list[tuple[date, float]] = []
        tranche = 100.0 / 12.0
        for index in range(12):
            target = entry.date + timedelta(days=30 * index)
            point = next((item for item in window if item.date >= target), None)
            if point is not None:
                dca_purchases.append((point.date, tranche))
        results.append(
            _simulate(
                window,
                purchases=dca_purchases,
                strategy="12-tranche 30d DCA",
                episode_date=entry.date,
                stage2_date=stage2.date if stage2 else None,
                stage3_date=stage3.date if stage3 else None,
            )
        )

    return results


def summarize_strategies(rows: list[StrategyResult]) -> list[StrategySummary]:
    summaries: list[StrategySummary] = []
    for strategy in ("All-in at Stage 1", "Staged 25/25/50", "12-tranche 30d DCA"):
        selected = [row for row in rows if row.strategy == strategy]
        returns = [row.return_365d_pct for row in selected]
        drawdowns = [row.max_drawdown_pct for row in selected]
        invested = [row.invested_pct for row in selected]
        summaries.append(
            StrategySummary(
                strategy=strategy,
                episodes=len(selected),
                median_return_365d_pct=median(returns) if returns else None,
                positive_rate_pct=(100.0 * sum(value > 0 for value in returns) / len(returns) if returns else None),
                median_max_drawdown_pct=median(drawdowns) if drawdowns else None,
                worst_max_drawdown_pct=min(drawdowns) if drawdowns else None,
                median_invested_pct=median(invested) if invested else None,
            )
        )
    return summaries
