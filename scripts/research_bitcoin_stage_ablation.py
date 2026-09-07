"""Run fixed Bitcoin staged-accumulation ablation research."""

from __future__ import annotations

import csv
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.services.bitcoin_confluence_research import ConfluencePoint
from backend.app.services.bitcoin_stage_ablation import (
    evaluate_stage_ablation,
    summarize_stage_ablation,
)

REPORTS_DIR = ROOT / "reports"
INPUT_CSV = REPORTS_DIR / "bitcoin_confluence_research.csv"
OUTPUT_CSV = REPORTS_DIR / "bitcoin_stage_ablation.csv"


def _float_or_none(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _load_points() -> list[ConfluencePoint]:
    if not INPUT_CSV.exists():
        raise RuntimeError(f"Missing {INPUT_CSV}. Run research_bitcoin_confluence.py first.")
    with INPUT_CSV.open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return [
        ConfluencePoint(
            date=date.fromisoformat(row["date"]),
            price=float(row["price"]),
            opportunity_score=float(row["opportunity_score"]),
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
            "episode_date", "allocation", "variant", "stage2_date", "stage3_date",
            "invested_pct", "average_entry_price", "return_365d_pct", "max_drawdown_pct",
        ))
        for row in rows:
            writer.writerow((
                row.episode_date.isoformat(),
                row.allocation,
                row.variant,
                row.stage2_date.isoformat() if row.stage2_date else "",
                row.stage3_date.isoformat() if row.stage3_date else "",
                row.invested_pct,
                row.average_entry_price,
                row.return_365d_pct,
                row.max_drawdown_pct,
            ))


def main() -> None:
    print("BITCOIN STAGE CONTRIBUTION / ABLATION RESEARCH")
    print("-" * 118)
    print("Each experiment begins at an independent Quantile <=10 Stage-1 episode.")
    print("Stage 2 = Quantile <=10 + MVRV pct <=20.")
    print("Stage 3 = globally independent Opportunity >=60 under the same 90-day cooldown.")
    print("Omitted or untriggered tranches remain cash; they are not reassigned.")
    print("Fixed allocations: 25/25/50, 33/33/34, 50/25/25. No outcome-based selection.")

    points = _load_points()
    rows = evaluate_stage_ablation(points)
    if not rows:
        raise RuntimeError("No completed 365-day Stage-1 episodes were available")

    print()
    print("ABLATION SUMMARY")
    print("-" * 118)
    print(
        f"{'Allocation':18} {'Variant':30} {'Ep':>3} {'Med365':>10} {'Positive':>10} "
        f"{'Med DD':>10} {'Worst DD':>10} {'Med invested':>13}"
    )
    for row in summarize_stage_ablation(rows):
        print(
            f"{row.allocation:18} {row.variant:30} {row.episodes:>3} "
            f"{_fmt(row.median_return_365d_pct):>10} {_fmt(row.positive_rate_pct):>10} "
            f"{_fmt(row.median_max_drawdown_pct):>10} {_fmt(row.worst_max_drawdown_pct):>10} "
            f"{_fmt(row.median_invested_pct):>13}"
        )

    print()
    print("EPISODE DETAILS — 50/25/25 ALLOCATION")
    print("-" * 118)
    selected = [row for row in rows if row.allocation == "Staged 50/25/25"]
    grouped: dict[date, list] = {}
    for row in selected:
        grouped.setdefault(row.episode_date, []).append(row)
    for episode_date in sorted(grouped):
        print(episode_date)
        for row in grouped[episode_date]:
            avg = "N/A" if row.average_entry_price is None else f"${row.average_entry_price:,.0f}"
            print(
                f"  {row.variant:30} invested={row.invested_pct:>5.1f}% avg={avg:>10} "
                f"365d={_fmt(row.return_365d_pct):>10} DD={_fmt(row.max_drawdown_pct):>10} "
                f"S2={row.stage2_date or 'NONE'} S3={row.stage3_date or 'NONE'}"
            )

    _write(rows)
    print()
    print(f"Saved: {OUTPUT_CSV}")
    print("This is ablation/sensitivity analysis only. It does not choose a preferred allocation or stage from future outcomes.")
    print("Done.")


if __name__ == "__main__":
    main()
