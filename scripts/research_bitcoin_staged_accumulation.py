"""Compare fixed staged Bitcoin accumulation with all-in Stage 1 and fixed DCA."""

from __future__ import annotations

import csv
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.services.bitcoin_confluence_research import ConfluencePoint
from backend.app.services.bitcoin_staged_accumulation import (
    STAGED_ALLOCATIONS,
    evaluate_staged_accumulation,
    summarize_strategies,
)

REPORTS_DIR = ROOT / "reports"
INPUT_CSV = REPORTS_DIR / "bitcoin_confluence_research.csv"
OUTPUT_CSV = REPORTS_DIR / "bitcoin_staged_accumulation.csv"


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
            "episode_date", "strategy", "stage2_date", "stage3_date", "invested_pct",
            "average_entry_price", "final_value", "return_365d_pct", "max_drawdown_pct",
        ))
        for row in rows:
            writer.writerow((
                row.episode_date.isoformat(),
                row.strategy,
                row.stage2_date.isoformat() if row.stage2_date else "",
                row.stage3_date.isoformat() if row.stage3_date else "",
                row.invested_pct,
                row.average_entry_price,
                row.final_value,
                row.return_365d_pct,
                row.max_drawdown_pct,
            ))


def main() -> None:
    print("BITCOIN STAGED ACCUMULATION RESEARCH")
    print("-" * 118)
    print("Each experiment starts at an independent Quantile <=10 episode.")
    print("Stage 2: Quantile <=10 + MVRV pct <=20.")
    print("Stage 3: next globally independent Opportunity >=60 episode using the same 90-day cooldown as lead-time research.")
    print("Fixed allocation sensitivity only; no allocation is selected from future outcomes.")
    print("Staged allocations: " + ", ".join(name.replace("Staged ", "") for name, _ in STAGED_ALLOCATIONS) + ".")
    print("Untriggered staged capital remains cash.")
    print("Benchmarks: 100% all-in at Stage 1 and twelve equal 30-day DCA tranches.")

    points = _load_points()
    rows = evaluate_staged_accumulation(points)
    if not rows:
        raise RuntimeError("No completed 365-day Stage-1 episodes were available")

    print()
    print("STRATEGY SUMMARY — COMPLETED 365-DAY STAGE-1 EPISODES")
    print("-" * 118)
    print(f"{'Strategy':24} {'Ep':>4} {'Med365':>11} {'Positive':>10} {'Med DD':>10} {'Worst DD':>10} {'Med invested':>13}")
    for row in summarize_strategies(rows):
        print(
            f"{row.strategy:24} {row.episodes:>4} {_fmt(row.median_return_365d_pct):>11} "
            f"{_fmt(row.positive_rate_pct):>10} {_fmt(row.median_max_drawdown_pct):>10} "
            f"{_fmt(row.worst_max_drawdown_pct):>10} {_fmt(row.median_invested_pct):>13}"
        )

    print()
    print("EPISODE DETAILS")
    print("-" * 118)
    grouped: dict[date, list] = {}
    for row in rows:
        grouped.setdefault(row.episode_date, []).append(row)
    for episode_date in sorted(grouped):
        episode_rows = grouped[episode_date]
        staged = next(row for row in episode_rows if row.strategy == "Staged 25/25/50")
        print(
            f"{episode_date} Stage2={staged.stage2_date or 'NONE'} Stage3={staged.stage3_date or 'NONE'}"
        )
        for row in episode_rows:
            avg = "N/A" if row.average_entry_price is None else f"${row.average_entry_price:,.0f}"
            print(
                f"  {row.strategy:24} invested={row.invested_pct:>5.1f}% avg={avg:>10} "
                f"365d={_fmt(row.return_365d_pct):>10} maxDD={_fmt(row.max_drawdown_pct):>10}"
            )

    _write(rows)
    print()
    print(f"Saved: {OUTPUT_CSV}")
    print("Stage-3 semantics now match the lead-time study exactly: independent Opportunity episodes, not daily threshold recrossings.")
    print("Allocation rows are sensitivity analysis only; do not choose the best-looking historical split as an optimized rule.")
    print("This is an event-study comparison, not a claim that any strategy will repeat historically observed returns.")
    print("Recent Stage-1 episodes without a full 365-day horizon are excluded rather than backfilled with future assumptions.")
    print("Done.")


if __name__ == "__main__":
    main()
