"""Run staged top de-risking ablation research."""

from __future__ import annotations

import csv
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.services.bitcoin_top_confluence_research import TopConfluencePoint
from backend.app.services.bitcoin_top_stage_ablation import (
    evaluate_top_stage_ablation,
    summarize_top_stage_ablation,
)

REPORTS_DIR = ROOT / "reports"
INPUT_CSV = REPORTS_DIR / "bitcoin_top_confluence_research.csv"
OUTPUT_CSV = REPORTS_DIR / "bitcoin_top_stage_ablation.csv"


def _float_or_none(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _load_points() -> list[TopConfluencePoint]:
    if not INPUT_CSV.exists():
        raise RuntimeError(f"Missing required research file: {INPUT_CSV}")
    with INPUT_CSV.open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return [
        TopConfluencePoint(
            date=date.fromisoformat(row["date"]),
            price=float(row["price"]),
            overheat_score=float(row["overheat_score"]),
            quantile_percentile=float(row["quantile_percentile"]),
            mvrv_percentile=float(row["mvrv_percentile"]),
            future_return_365d_pct=_float_or_none(row.get("future_return_365d_pct")),
            future_max_drawdown_365d_pct=_float_or_none(row.get("future_max_drawdown_365d_pct")),
        )
        for row in rows
    ]


def _fmt(value: float | None) -> str:
    return "N/A" if value is None else f"{value:,.1f}%"


def _write(rows) -> None:  # type: ignore[no-untyped-def]
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow((
            "warning_date", "allocation", "variant", "stage2_date", "stage3_date",
            "sold_pct", "sold_before_30dd_pct", "return_365d_pct", "max_drawdown_pct",
            "peak_upside_forfeited_pct_points", "excess_return_vs_hold_pct_points",
        ))
        for row in rows:
            writer.writerow((
                row.warning_date.isoformat(), row.allocation, row.variant,
                row.stage2_date.isoformat() if row.stage2_date else "",
                row.stage3_date.isoformat() if row.stage3_date else "",
                row.sold_pct, row.sold_before_30dd_pct, row.return_365d_pct,
                row.max_drawdown_pct, row.peak_upside_forfeited_pct_points,
                row.excess_return_vs_hold_pct_points,
            ))


def main() -> None:
    print("BITCOIN TOP DE-RISKING STAGE ABLATION")
    print("-" * 132)
    print("Stage 1 = independent MVRV percentile >=90 warning.")
    print("Stage 2 = Any-2 weakness sustained 14 days.")
    print("Stage 3 = price below trailing 200-day SMA.")
    print("Variants remove Stage 2 and/or Stage 3 while keeping the same fixed allocations.")
    print("Omitted tranches remain invested in BTC; they are not reassigned or sold later.")

    points = _load_points()
    rows = evaluate_top_stage_ablation(points)
    summaries = summarize_top_stage_ablation(rows)

    print()
    print("ABLATION SUMMARY — COMPLETED 365-DAY WARNING EPISODES")
    print("-" * 132)
    print(
        f"{'Allocation':20} {'Variant':28} {'Ep':>3} {'Med365':>10} {'Positive':>10} "
        f"{'Med DD':>10} {'Worst DD':>10} {'Peak forgone':>13} {'Sold pre30':>11} "
        f"{'Med sold':>10} {'Vs hold':>10}"
    )
    for row in summaries:
        print(
            f"{row.allocation:20} {row.variant:28} {row.episodes:>3} "
            f"{_fmt(row.median_return_365d_pct):>10} {_fmt(row.positive_rate_pct):>10} "
            f"{_fmt(row.median_max_drawdown_pct):>10} {_fmt(row.worst_max_drawdown_pct):>10} "
            f"{_fmt(row.median_peak_upside_forfeited_pct_points):>13} "
            f"{_fmt(row.median_sold_before_30dd_pct):>11} {_fmt(row.median_sold_pct):>10} "
            f"{_fmt(row.median_excess_vs_hold_pct_points):>10}"
        )

    print()
    print("EPISODE DETAILS — 50/25/25")
    print("-" * 132)
    focus = [row for row in rows if row.allocation == "Staged 50/25/25"]
    for warning_date in sorted({row.warning_date for row in focus}):
        selected = [row for row in focus if row.warning_date == warning_date]
        stage2 = next((row.stage2_date for row in selected if row.stage2_date is not None), None)
        stage3 = next((row.stage3_date for row in selected if row.stage3_date is not None), None)
        print(f"{warning_date} Stage2={stage2 or 'N/A'} Stage3={stage3 or 'N/A'}")
        for row in selected:
            print(
                f"  {row.variant:28} sold={row.sold_pct:>5.1f}% pre30={row.sold_before_30dd_pct:>5.1f}% "
                f"365d={_fmt(row.return_365d_pct):>10} DD={_fmt(row.max_drawdown_pct):>10} "
                f"peak-forgone={_fmt(row.peak_upside_forfeited_pct_points):>10} "
                f"vs-hold={_fmt(row.excess_return_vs_hold_pct_points):>10}"
            )

    _write(rows)
    print()
    print(f"Saved: {OUTPUT_CSV}")
    print("Compare incremental stage contributions, not the best-looking allocation cell.")
    print("Episode count is only three completed independent warnings, so this is descriptive evidence only.")
    print("Done.")


if __name__ == "__main__":
    main()
