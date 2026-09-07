"""Run staged Bitcoin top de-risking event study."""

from __future__ import annotations

import csv
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.services.bitcoin_top_confluence_research import TopConfluencePoint
from backend.app.services.bitcoin_top_staged_derisking import (
    evaluate_staged_derisking,
    summarize_staged_derisking,
)

REPORTS_DIR = ROOT / "reports"
INPUT_CSV = REPORTS_DIR / "bitcoin_top_confluence_research.csv"
OUTPUT_CSV = REPORTS_DIR / "bitcoin_top_staged_derisking.csv"


def _float_or_none(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _load_points() -> list[TopConfluencePoint]:
    if not INPUT_CSV.exists():
        raise RuntimeError(f"Missing {INPUT_CSV}. Run research_bitcoin_top_confluence.py first.")
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
            "warning_date", "strategy", "stage2_date", "stage3_date", "sold_pct",
            "sold_before_30dd_pct", "return_365d_pct", "max_drawdown_pct",
            "peak_upside_forfeited_pct_points", "excess_return_vs_hold_pct_points",
        ))
        for row in rows:
            writer.writerow((
                row.warning_date.isoformat(), row.strategy,
                row.stage2_date.isoformat() if row.stage2_date else "",
                row.stage3_date.isoformat() if row.stage3_date else "",
                row.sold_pct, row.sold_before_30dd_pct, row.return_365d_pct,
                row.max_drawdown_pct, row.peak_upside_forfeited_pct_points,
                row.excess_return_vs_hold_pct_points,
            ))


def main() -> None:
    print("BITCOIN STAGED TOP DE-RISKING EVENT STUDY")
    print("-" * 132)
    print("Stage 1 = independent MVRV percentile >=90 warning.")
    print("Stage 2 = Any-2 weakness confirmations sustained for 14 days.")
    print("Stage 3 = price below trailing 200-day SMA.")
    print("Fixed de-risking schedules: 25/25/50, 33/33/34, 50/25/25.")
    print("Missing later stages leave that BTC tranche invested; no future outcome is used to trigger a sale.")
    print("Cash is held after sale. This is an event study, not a validated sell strategy.")

    points = _load_points()
    rows = evaluate_staged_derisking(points)
    if not rows:
        raise RuntimeError("No completed 365-day MVRV-high warning episodes were available")

    print()
    print("STRATEGY SUMMARY — COMPLETED 365-DAY WARNING EPISODES")
    print("-" * 132)
    print(
        f"{'Strategy':27} {'Ep':>3} {'Med365':>10} {'Positive':>10} {'Med DD':>10} {'Worst DD':>10} "
        f"{'Peak forgone':>13} {'Sold pre30':>11} {'Vs hold':>10}"
    )
    for row in summarize_staged_derisking(rows):
        print(
            f"{row.strategy:27} {row.episodes:>3} {_fmt(row.median_return_365d_pct):>10} "
            f"{_fmt(row.positive_rate_pct):>10} {_fmt(row.median_max_drawdown_pct):>10} "
            f"{_fmt(row.worst_max_drawdown_pct):>10} {_fmt(row.median_peak_upside_forfeited_pct_points):>13} "
            f"{_fmt(row.median_sold_before_30dd_pct):>11} {_fmt(row.median_excess_vs_hold_pct_points):>10}"
        )

    print()
    print("EPISODE DETAILS")
    print("-" * 132)
    grouped: dict[date, list] = {}
    for row in rows:
        grouped.setdefault(row.warning_date, []).append(row)
    for warning_date in sorted(grouped):
        episode_rows = grouped[warning_date]
        stage2 = episode_rows[0].stage2_date or "NONE"
        stage3 = episode_rows[0].stage3_date or "NONE"
        print(f"{warning_date} Stage2={stage2} Stage3={stage3}")
        for row in episode_rows:
            print(
                f"  {row.strategy:27} sold={row.sold_pct:>5.1f}% pre30={row.sold_before_30dd_pct:>5.1f}% "
                f"365d={_fmt(row.return_365d_pct):>10} DD={_fmt(row.max_drawdown_pct):>10} "
                f"peak-forgone={_fmt(row.peak_upside_forfeited_pct_points):>10} vs-hold={_fmt(row.excess_return_vs_hold_pct_points):>10}"
            )

    _write(rows)
    print()
    print(f"Saved: {OUTPUT_CSV}")
    print("Peak-forgone compares each strategy's maximum portfolio value with buy-and-hold's maximum value during the same 365 days.")
    print("Sold pre30 = percent of original BTC exposure sold before the first 30% running-peak drawdown in that episode.")
    print("Vs hold = final portfolio-value difference versus holding BTC for the full 365 days.")
    print("Do not choose an allocation from three historical warning episodes.")
    print("Done.")


if __name__ == "__main__":
    main()
