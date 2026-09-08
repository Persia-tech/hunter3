"""Research-only ablation of staged Bitcoin top de-risking components.

The experiment keeps the same fixed top-warning and confirmation definitions as
the staged de-risking event study, but removes Stage 2 and/or Stage 3 to measure
whether later stages add incremental value beyond the Stage 1 MVRV warning.
Omitted tranches remain invested in BTC; they are not reassigned.
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
from backend.app.services.bitcoin_top_staged_derisking import (
    DRAWDOWN_EVENT_PCT,
    HORIZON_DAYS,
    STAGE2_RULE,
    STAGE3_RULE,
    STAGED_DERISK_ALLOCATIONS,
)


WARNING_SPEC = TopSpec("MVRV pct >= 90", require_mvrv=True)

VARIANTS = (
    "Stage 1 only",
    "Stage 1 + Stage 2",
    "Stage 1 + Stage 3",
    "Stage 1 + Stage 2 + Stage 3",
)


@dataclass(frozen=True, slots=True)
class TopAblationResult:
    warning_date: date
    allocation: str
    variant: str
    stage2_date: date | None
    stage3_date: date | None
    sold_pct: float
    sold_before_30dd_pct: float
    return_365d_pct: float
    max_drawdown_pct: float
    peak_upside_forfeited_pct_points: float
    excess_return_vs_hold_pct_points: float


@dataclass(frozen=True, slots=True)
class TopAblationSummary:
    allocation: str
    variant: str
    episodes: int
    median_return_365d_pct: float | None
    positive_rate_pct: float | None
    median_max_drawdown_pct: float | None
    worst_max_drawdown_pct: float | None
    median_peak_upside_forfeited_pct_points: float | None
    median_sold_before_30dd_pct: float | None
    median_sold_pct: float | None
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
    warning_date: date,
    allocation: str,
    variant: str,
    stage2_date: date | None,
    stage3_date: date | None,
    hold_final_value: float,
    hold_peak_value: float,
    first_30dd_date: date | None,
) -> TopAblationResult:
    start_price = window[0].price
    initial_btc = 100.0 / start_price
    btc = initial_btc
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
            btc_to_sell = min((amount_pct / 100.0) * initial_btc, btc)
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
    return TopAblationResult(
        warning_date=warning_date,
        allocation=allocation,
        variant=variant,
        stage2_date=stage2_date,
        stage3_date=stage3_date,
        sold_pct=sold_pct,
        sold_before_30dd_pct=sold_before_30dd_pct,
        return_365d_pct=final_value - 100.0,
        max_drawdown_pct=max_dd,
        peak_upside_forfeited_pct_points=hold_peak_value - strategy_peak,
        excess_return_vs_hold_pct_points=final_value - hold_final_value,
    )


def evaluate_top_stage_ablation(
    points: list[TopConfluencePoint],
    *,
    cooldown_days: int = 90,
    horizon_days: int = HORIZON_DAYS,
) -> list[TopAblationResult]:
    """Evaluate fixed Stage-1/2/3 de-risking ablations.

    Stage 1 is the independent MVRV percentile >=90 warning. Stage 2 is the
    predeclared Any-2 sustained-14d weakness confirmation. Stage 3 is the
    predeclared below-200d-SMA structural break. Omitted tranches remain BTC.
    """
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

    rows: list[TopAblationResult] = []
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

        for allocation_name, (a1, a2, a3) in STAGED_DERISK_ALLOCATIONS:
            sales_by_variant: dict[str, list[tuple[date, float]]] = {
                "Stage 1 only": [(warning.date, a1)],
                "Stage 1 + Stage 2": [(warning.date, a1)],
                "Stage 1 + Stage 3": [(warning.date, a1)],
                "Stage 1 + Stage 2 + Stage 3": [(warning.date, a1)],
            }
            if stage2_date is not None:
                sales_by_variant["Stage 1 + Stage 2"].append((stage2_date, a2))
                sales_by_variant["Stage 1 + Stage 2 + Stage 3"].append((stage2_date, a2))
            if stage3_date is not None:
                sales_by_variant["Stage 1 + Stage 3"].append((stage3_date, a3))
                sales_by_variant["Stage 1 + Stage 2 + Stage 3"].append((stage3_date, a3))

            for variant in VARIANTS:
                rows.append(
                    _simulate(
                        window,
                        sales=sales_by_variant[variant],
                        warning_date=warning.date,
                        allocation=allocation_name,
                        variant=variant,
                        stage2_date=stage2_date if "Stage 2" in variant else None,
                        stage3_date=stage3_date if "Stage 3" in variant else None,
                        hold_final_value=hold_final,
                        hold_peak_value=hold_peak,
                        first_30dd_date=dd30_date,
                    )
                )
    return rows


def _median(values: list[float]) -> float | None:
    return median(values) if values else None


def summarize_top_stage_ablation(rows: list[TopAblationResult]) -> list[TopAblationSummary]:
    summaries: list[TopAblationSummary] = []
    for allocation_name, _ in STAGED_DERISK_ALLOCATIONS:
        for variant in VARIANTS:
            selected = [
                row for row in rows
                if row.allocation == allocation_name and row.variant == variant
            ]
            returns = [row.return_365d_pct for row in selected]
            drawdowns = [row.max_drawdown_pct for row in selected]
            summaries.append(
                TopAblationSummary(
                    allocation=allocation_name,
                    variant=variant,
                    episodes=len(selected),
                    median_return_365d_pct=_median(returns),
                    positive_rate_pct=(
                        100.0 * sum(value > 0 for value in returns) / len(returns)
                        if returns else None
                    ),
                    median_max_drawdown_pct=_median(drawdowns),
                    worst_max_drawdown_pct=min(drawdowns) if drawdowns else None,
                    median_peak_upside_forfeited_pct_points=_median(
                        [row.peak_upside_forfeited_pct_points for row in selected]
                    ),
                    median_sold_before_30dd_pct=_median(
                        [row.sold_before_30dd_pct for row in selected]
                    ),
                    median_sold_pct=_median([row.sold_pct for row in selected]),
                    median_excess_vs_hold_pct_points=_median(
                        [row.excess_return_vs_hold_pct_points for row in selected]
                    ),
                )
            )
    return summaries
