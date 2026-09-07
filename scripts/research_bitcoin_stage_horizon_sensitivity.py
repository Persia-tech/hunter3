"""Run fixed 180/365/730-day horizon sensitivity for Bitcoin staged ablation."""

from __future__ import annotations

import csv
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.services.bitcoin_confluence_research import ConfluencePoint
from backend.app.services.bitcoin_stage_horizon_sensitivity import (
    DEFAULT_HORIZONS,
    evaluate_stage_horizon_sensitivity,
    summarize_stage_horizon_sensitivity,
)

REPORTS_DIR = ROOT / "reports"
INPUT_CSV = REPORTS_DIR / "bitcoin_confluence_research.csv"
OUTPUT_CSV = REPORTS_DIR / "bitcoin_stage_horizon_sensitivity.csv"


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
            "horizon_days", "episode_date", "allocation", "variant", "stage2_date", "stage3_date",
            "invested_pct", "average_entry_price", "return_pct", "max_drawdown_pct",
        ))
        for row in rows:
            writer.writerow((
                row.horizon_days,
                row.episode_date.isoformat(),
                row.allocation,
                row.variant,
                row.stage2_date.isoformat() if row.stage2_date else "",
                row.stage3_date.isoformat() if row.stage3_date else "",
                row.invested_pct,
                row.average_entry_price,
                row.return_pct,
                row.max_drawdown_pct,
            ))


def main() -> None:
    print("BITCOIN STAGED-ABLATION OUTCOME-HORIZON SENSITIVITY")
    print("-" * 126)
    print("Only the evaluation horizon changes: 180, 365, and 730 days.")
    print("Stage thresholds, 90-day independent-signal cooldown, and allocations remain fixed.")
    print("Later horizons have fewer completed episodes because recent events are right-censored.")
    print("No horizon, allocation, or stage combination is selected from future outcomes.")

    points = _load_points()
    rows = evaluate_stage_horizon_sensitivity(points)
    if not rows:
        raise RuntimeError("No completed Stage-1 episodes were available for the requested horizons")

    summaries = summarize_stage_horizon_sensitivity(rows)
    print()
    print("HORIZON SENSITIVITY SUMMARY")
    print("-" * 126)
    print(
        f"{'Days':>5} {'Allocation':18} {'Variant':30} {'Ep':>3} {'Median ret':>11} "
        f"{'Positive':>10} {'Med DD':>10} {'Worst DD':>10} {'Med invested':>13}"
    )
    for row in summaries:
        print(
            f"{row.horizon_days:>5} {row.allocation:18} {row.variant:30} {row.episodes:>3} "
            f"{_fmt(row.median_return_pct):>11} {_fmt(row.positive_rate_pct):>10} "
            f"{_fmt(row.median_max_drawdown_pct):>10} {_fmt(row.worst_max_drawdown_pct):>10} "
            f"{_fmt(row.median_invested_pct):>13}"
        )

    print()
    print("COMPARISON FOCUS — 50/25/25 ALLOCATION")
    print("-" * 126)
    focus = [row for row in summaries if row.allocation == "Staged 50/25/25"]
    for horizon in DEFAULT_HORIZONS:
        print(f"{horizon} days")
        for row in focus:
            if row.horizon_days != horizon:
                continue
            print(
                f"  {row.variant:30} Ep={row.episodes:>2} median={_fmt(row.median_return_pct):>10} "
                f"positive={_fmt(row.positive_rate_pct):>8} medDD={_fmt(row.median_max_drawdown_pct):>8}"
            )

    _write(rows)
    print()
    print(f"Saved: {OUTPUT_CSV}")
    print("Compare patterns across horizons, not the single best-looking cell.")
    print("Episode counts are the primary limitation, especially at 730 days.")
    print("Done.")


if __name__ == "__main__":
    main()
