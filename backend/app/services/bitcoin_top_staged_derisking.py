"""Research-only staged Bitcoin de-risking event study.

Each completed experiment begins at an independent MVRV percentile >= 90
warning. The study compares holding BTC, full exits at fixed confirmation
stages, and fixed staged de-risking schedules. Rules and allocations are fixed
in advance; missing later stages leave the corresponding BTC exposure intact.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from statistics import median

from backend.app.services.bitcoin_top_confluence_research import (
    MVRV_HIGH_THRESHOLD,
    TopConfluencePoint,
    TopSpec,
    independent_top_episodes,
)
from backend.app.services.bitcoin_top_persistent_confirmation_research import (
    evaluate_persistent_top_confirmations,
)


WARNING_SPEC = TopSpec("MVRV pct >= 90", require_mvrv=True)
STAGE2_RULE = "Any 2 sustained 14d"
STAGE3_RULE = "Below 200d SMA"
HORIZON_DAYS = 365
DRAWDOWN_EVENT_PCT = -30.0

STAGED_DERISK_ALLOCATIONS: tuple[tuple[str, tuple[float, float, float]], ...] = (
    ("Staged 25/25/50", (25.0, 25.0, 50.0)),
    ("Staged 33/33/34", (33.0, 33.0, 34.0)),
    ("Staged 50/25/25", (50.0, 25.0, 25.0)),
)


@dataclass(frozen=True, slots=True)
class DeriskingResult:
    warning_date: date
    strategy: str
    stage2_date: date | None
    stage3_date: date | None
    sold_pct: float
    sold_before_30dd_pct: float
    return_365d_pct: float
    max_drawdown_pct: float
    peak_upside_forfeited_pct_points: float
    excess_return_vs_hold_pct_points: float


@dataclass(frozen=True, slots=True)
class DeriskingSummary:
    strategy: str
    episodes: int
    median_return_365d_pct: float | None
    positive_rate_pct: float | None
    median_max_drawdown_pct: float | None
    worst_max_drawdown_pct: float | None
    median_peak_upside_forfeited_pct_points: float | None
    median_sold_before_30dd_pct: float | None
    median_excess_vs_hold_pct_points: float | None


def _first_30dd_date(window: list[TopConfluencePoint]) -> date | None:
    peak = window[0].price
    for point in window:
        peak = max(peak, point.price)
        if peak > 0 and (point.price / peak - 1.0) * 100.0 <= DRAWDOWN_EVENT_PCT:
            return point.date
    return None


def _simulate(
    window: list[TopConfluencePoint],
    *,
    sales: list[tuple[date, float]],
    strategy: str,
    warning_date: date,
    stage2_date: date | None,
    stage3_date: date | None,
    hold_final_value: float,
    hold_peak_value: float,
    first_30dd_date: date | None,
) -> DeriskingResult:
    start_price = window[0].price
    btc = 100.0 / start_price
    cash = 0.0
    sold_pct = 0.0
    sold_before_30dd_pct = 0.0
    sale_map: dict[date, float] = {}
    for day, amount_pct in sales:
        sale_map[day] = sale_map.get(day, 0.0) + amount_pct

    values: list[float] = []
    for point in window:
        amount_pct = min(sale_map.get(point.date, 0.0), 100.0 - sold_pct)
        if amount_pct > 0:
            btc_to_sell = (amount_pct / 100.0) * (100.0 / start_price)
            btc_to_sell = min(btc_to_sell, btc)
            cash += btc_to_sell * point.price
            btc -= btc_to_sell
            sold_pct += amount_pct
            if first_30dd_date is not None and point.date <= first_30dd_date:
                sold_before_30dd_pct += amount_pct
        values.append(cash + btc * point.price)

    peak = values[0]
    max_dd = 0.0
    for value in values:
        peak = max(peak, value)
        if peak > 0:
            max_dd = min(max_dd, (value / peak - 1.0) * 100.0)

    final_value = values[-1]
    strategy_peak = max(values)
    return DeriskingResult(
        warning_date=warning_date,
        strategy=strategy,
        stage2_date=stage2_date,
        stage3_date=stage3_date,
        sold_pct=sold_pct,
        sold_before_30dd_pct=sold_before_30dd_pct,
        return_365d_pct=final_value - 100.0,
        max_drawdown_pct=max_dd,
        peak_upside_forfeited_pct_points=hold_peak_value - strategy_peak,
        excess_return_vs_hold_pct_points=final_value - hold_final_value,
    )


def evaluate_staged_derisking(
    points: list[TopConfluencePoint],
    *,
    cooldown_days: int = 90,
    horizon_days: int = HORIZON_DAYS,
) -> list[DeriskingResult]:
    if horizon_days < 1:
        raise ValueError("horizon_days must be positive")

    ordered = sorted(points, key=lambda item: item.date)
    by_date = {point.date: point for point in ordered}
    warnings = independent_top_episodes(
        ordered,
        WARNING_SPEC,
        cooldown_days=cooldown_days,
        mvrv_threshold=MVRV_HIGH_THRESHOLD,
    )
    confirmations = evaluate_persistent_top_confirmations(
        ordered,
        cooldown_days=cooldown_days,
    )
    conf_by_warning_rule = {
        (row.warning_date, row.rule): row
        for row in confirmations
        if row.confirmation_date is not None
    }

    rows: list[DeriskingResult] = []
    for warning in warnings:
        end_date = warning.date + timedelta(days=horizon_days)
        if end_date not in by_date:
            continue
        window = [point for point in ordered if warning.date <= point.date <= end_date]
        stage2_row = conf_by_warning_rule.get((warning.date, STAGE2_RULE))
        stage3_row = conf_by_warning_rule.get((warning.date, STAGE3_RULE))
        stage2_date = stage2_row.confirmation_date if stage2_row else None
        stage3_date = stage3_row.confirmation_date if stage3_row else None

        hold_values = [100.0 * point.price / warning.price for point in window]
        hold_final = hold_values[-1]
        hold_peak = max(hold_values)
        dd30_date = _first_30dd_date(window)

        strategies: list[tuple[str, list[tuple[date, float]]]] = [
            ("Hold BTC", []),
            ("Sell 100% at Stage 1", [(warning.date, 100.0)]),
        ]
        if stage2_date is not None:
            strategies.append(("Sell 100% at Stage 2", [(stage2_date, 100.0)]))
        else:
            strategies.append(("Sell 100% at Stage 2", []))
        if stage3_date is not None:
            strategies.append(("Sell 100% at Stage 3", [(stage3_date, 100.0)]))
        else:
            strategies.append(("Sell 100% at Stage 3", []))

        for name, (a1, a2, a3) in STAGED_DERISK_ALLOCATIONS:
            sales = [(warning.date, a1)]
            if stage2_date is not None:
                sales.append((stage2_date, a2))
            if stage3_date is not None:
                sales.append((stage3_date, a3))
            strategies.append((name, sales))

        for strategy, sales in strategies:
            rows.append(
                _simulate(
                    window,
                    sales=sales,
                    strategy=strategy,
                    warning_date=warning.date,
                    stage2_date=stage2_date,
                    stage3_date=stage3_date,
                    hold_final_value=hold_final,
                    hold_peak_value=hold_peak,
                    first_30dd_date=dd30_date,
                )
            )
    return rows


def _median(values: list[float]) -> float | None:
    return median(values) if values else None


def summarize_staged_derisking(rows: list[DeriskingResult]) -> list[DeriskingSummary]:
    order = (
        "Hold BTC",
        "Sell 100% at Stage 1",
        "Sell 100% at Stage 2",
        "Sell 100% at Stage 3",
        *(name for name, _ in STAGED_DERISK_ALLOCATIONS),
    )
    summaries: list[DeriskingSummary] = []
    for strategy in order:
        selected = [row for row in rows if row.strategy == strategy]
        returns = [row.return_365d_pct for row in selected]
        drawdowns = [row.max_drawdown_pct for row in selected]
        summaries.append(
            DeriskingSummary(
                strategy=strategy,
                episodes=len(selected),
                median_return_365d_pct=_median(returns),
                positive_rate_pct=(100.0 * sum(value > 0 for value in returns) / len(returns) if returns else None),
                median_max_drawdown_pct=_median(drawdowns),
                worst_max_drawdown_pct=min(drawdowns) if drawdowns else None,
                median_peak_upside_forfeited_pct_points=_median([row.peak_upside_forfeited_pct_points for row in selected]),
                median_sold_before_30dd_pct=_median([row.sold_before_30dd_pct for row in selected]),
                median_excess_vs_hold_pct_points=_median([row.excess_return_vs_hold_pct_points for row in selected]),
            )
        )
    return summaries
