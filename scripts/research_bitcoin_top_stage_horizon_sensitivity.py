"""Run Bitcoin top-stage ablation sensitivity across fixed outcome horizons."""

from __future__ import annotations

import csv
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.services.bitcoin_top_confluence_research import TopConfluencePoint
from backend.app.services.bitcoin_top_stage_horizon_sensitivity import (
    DEFAULT_HORIZONS,
    evaluate_top_stage_horizon_sensitivity,
    summarize_top_stage_horizon_sensitivity,
)

REPORTS_DIR = ROOT / "reports"
INPUT_CSV = REPORTS_DIR / "bitcoin_top_confluence_research.csv"
OUTPUT_CSV = REPORTS_DIR / "bitcoin_top_stage_horizon_sensitivity.csv"


def _float_or_none(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _load_points() -> list[TopConfluencePoint]:
    if not INPUT_CSV.exists():
        raise RuntimeError(f"Missing required research file: {INPUT_CSV}")
    points: list[TopConfluencePoint] = []
    with INPUT_CSV.open("r", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            points.append(
                TopConfluencePoint(
                    date=date.fromisoformat(row["date"]),
                    price=float(row["price"]),
                    overheat_score=float(row["overheat_score"]),
                    quantile_percentile=float(row["quantile_percentile"]),
                    mvrv_percentile=float(row["mvrv_percentile"]),
                    future_return_365d_pct=_float_or_none(row.get("future_return_365d_pct")),
                    future_max_drawdown_365d_pct=_float_or_none(
                        row.get("future_max_drawdown_365d_pct")
                    ),
                )
            )
    return points


def _fmt(value: float | None) -> str:
    return "N/A" if value is None else f"{value:,.1f}%"


def _write(rows) -> None:  # type: ignore[no-untyped-def]
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            (
                "warning_date",
                "horizon_days",
                "allocation",
                "variant",
                "stage2_date",
                "stage3_date",
                "sold_pct",
                "sold_before_30dd_pct",
                "return_pct",
                "max_drawdown_pct",
                "peak_upside_forfeited_pct_points",
                "excess_return_vs_hold_pct_points",
            )
        )
        for row in rows:
            writer.writerow(
                (
                    row.warning_date.isoformat(),
                    row.horizon_days,
                    row.allocation,
                    row.variant,
                    row.stage2_date.isoformat() if row.stage2_date else "",
                    row.stage3_date.isoformat() if row.stage3_date else "",
                    row.sold_pct,
                    row.sold_before_30dd_pct,
                    row.return_pct,
                    row.max_drawdown_pct,
                    row.peak_upside_forfeited_pct_points,
                    row.excess_return_vs_hold_pct_points,
                )
            )


def main() -> None:
    print("BITCOIN TOP-STAGE OUTCOME-HORIZON SENSITIVITY")
    print("-" * 138)
    print("Only the outcome horizon changes: 180, 365, and 730 days.")
    print("Stage 1 = MVRV percentile >=90; Stage 2 = Any-2 weakness sustained 14d; Stage 3 = below 200d SMA.")
    print("Stage-2/3 search remains fixed to the predeclared 180-day confirmation window for every horizon.")
    print("Allocations and 90-day warning cooldown remain fixed. No horizon or allocation is selected from future outcomes.")

    points = _load_points()
    rows = evaluate_top_stage_horizon_sensitivity(points)
    summaries = summarize_top_stage_horizon_sensitivity(rows)

    print()
    print("HORIZON SENSITIVITY SUMMARY")
    print("-" * 138)
    print(
        f"{'Days':>5} {'Allocation':20} {'Variant':29} {'Ep':>3} {'Med ret':>10} {'Positive':>10} "
        f"{'Med DD':>10} {'Worst DD':>10} {'Peak forgone':>13} {'Sold pre30':>11} {'Med sold':>10} {'Vs hold':>10}"
    )
    for row in summaries:
        print(
            f"{row.horizon_days:>5} {row.allocation:20} {row.variant:29} {row.episodes:>3} "
            f"{_fmt(row.median_return_pct):>10} {_fmt(row.positive_rate_pct):>10} "
            f"{_fmt(row.median_max_drawdown_pct):>10} {_fmt(row.worst_max_drawdown_pct):>10} "
            f"{_fmt(row.median_peak_upside_forfeited_pct_points):>13} "
            f"{_fmt(row.median_sold_before_30dd_pct):>11} {_fmt(row.median_sold_pct):>10} "
            f"{_fmt(row.median_excess_vs_hold_pct_points):>10}"
        )

    print()
    print("COMPARISON FOCUS — 50/25/25 ALLOCATION")
    print("-" * 138)
    for horizon in DEFAULT_HORIZONS:
        print(f"{horizon} days")
        for row in summaries:
            if row.horizon_days == horizon and row.allocation == "Staged 50/25/25":
                print(
                    f"  {row.variant:29} Ep={row.episodes:>2} med={_fmt(row.median_return_pct):>10} "
                    f"DD={_fmt(row.median_max_drawdown_pct):>9} sold={_fmt(row.median_sold_pct):>8} "
                    f"vs-hold={_fmt(row.median_excess_vs_hold_pct_points):>9}"
                )

    _write(rows)
    print()
    print(f"Saved: {OUTPUT_CSV}")
    counts = {
        horizon: len({row.warning_date for row in rows if row.horizon_days == horizon})
        for horizon in DEFAULT_HORIZONS
    }
    print("Completed warning episodes by horizon: " + ", ".join(f"{h}d={counts[h]}" for h in DEFAULT_HORIZONS))
    if len(set(counts.values())) > 1:
        print("Episode counts differ across horizons because of right-censoring; cross-horizon medians are not a pure same-cohort comparison.")
    else:
        print("Episode counts are identical across these horizons, so the same completed warning cohort is being compared here.")
    print("Compare Stage-2 and Stage-3 incremental patterns across horizons; do not choose the best-looking cell from three warnings.")
    print("Done.")


if __name__ == "__main__":
    main()
