"""Measure lead time from early BTC valuation signals to Opportunity >=60 confirmation."""

from __future__ import annotations

import csv
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.services.bitcoin_confluence_research import ConfluencePoint
from backend.app.services.bitcoin_signal_lead_time import (
    evaluate_lead_time_episodes,
    summarize_lead_time,
)

REPORTS_DIR = ROOT / "reports"
INPUT_CSV = REPORTS_DIR / "bitcoin_confluence_research.csv"
OUTPUT_CSV = REPORTS_DIR / "bitcoin_signal_lead_time.csv"


def _float_or_none(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _load_points() -> list[ConfluencePoint]:
    if not INPUT_CSV.exists():
        raise RuntimeError(
            f"Missing {INPUT_CSV}. Run scripts\\research_bitcoin_confluence.py first."
        )
    with INPUT_CSV.open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    points: list[ConfluencePoint] = []
    for row in rows:
        points.append(
            ConfluencePoint(
                date=date.fromisoformat(row["date"]),
                price=float(row["price"]),
                opportunity_score=float(row["opportunity_score"]),
                quantile_percentile=float(row["quantile_percentile"]),
                mvrv_percentile=float(row["mvrv_percentile"]),
                future_return_365d_pct=_float_or_none(row.get("future_return_365d_pct")),
                future_max_drawdown_365d_pct=_float_or_none(row.get("future_max_drawdown_365d_pct")),
            )
        )
    return points


def _fmt_pct(value: float | None) -> str:
    return "N/A" if value is None else f"{value:,.1f}%"


def _fmt_days(value: float | None) -> str:
    return "N/A" if value is None else f"{value:,.1f}"


def _write_csv(rows) -> None:  # type: ignore[no-untyped-def]
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            (
                "signal",
                "early_date",
                "early_price",
                "confirmation_date",
                "confirmation_price",
                "lead_days",
                "max_drawdown_to_confirmation_pct",
            )
        )
        for row in rows:
            writer.writerow(
                (
                    row.signal,
                    row.early_date.isoformat(),
                    row.early_price,
                    "" if row.confirmation_date is None else row.confirmation_date.isoformat(),
                    "" if row.confirmation_price is None else row.confirmation_price,
                    "" if row.lead_days is None else row.lead_days,
                    "" if row.max_drawdown_to_confirmation_pct is None else row.max_drawdown_to_confirmation_pct,
                )
            )


def main() -> None:
    print("BITCOIN EARLY-SIGNAL LEAD-TIME RESEARCH")
    print("-" * 110)
    print("Early thresholds are fixed: Quantile <=10, MVRV pct <=20, and their intersection.")
    print("Confirmation is the next independent Opportunity >=60 entry within 365 days.")
    print("No thresholds or weights are fitted from future outcomes.")

    points = _load_points()
    if not points:
        raise RuntimeError("No confluence research points were loaded")

    rows = evaluate_lead_time_episodes(points, max_confirmation_days=365, cooldown_days=90)
    summaries = summarize_lead_time(rows)

    print(f"Research range: {points[0].date} -> {points[-1].date} ({len(points):,} daily observations)")
    print()
    print("LEAD-TIME SUMMARY")
    print("-" * 110)
    print(
        f"{'Early signal':38} {'Ep':>4} {'Confirmed':>9} {'Confirm%':>10} "
        f"{'Med lead d':>11} {'Med DD gap':>12} {'Worst DD gap':>13}"
    )
    for row in summaries:
        print(
            f"{row.signal:38} {row.early_episode_count:>4} {row.confirmed_count:>9} "
            f"{_fmt_pct(row.confirmation_rate_pct):>10} {_fmt_days(row.median_lead_days):>11} "
            f"{_fmt_pct(row.median_drawdown_to_confirmation_pct):>12} "
            f"{_fmt_pct(row.worst_drawdown_to_confirmation_pct):>13}"
        )

    print()
    print("EPISODE DETAILS")
    print("-" * 110)
    for row in rows:
        confirmation = "UNCONFIRMED"
        if row.confirmation_date is not None:
            confirmation = (
                f"{row.confirmation_date} ${row.confirmation_price:,.0f} "
                f"lead={row.lead_days}d gapDD={_fmt_pct(row.max_drawdown_to_confirmation_pct)}"
            )
        print(
            f"{row.signal:38} {row.early_date} ${row.early_price:>10,.0f} -> {confirmation}"
        )

    _write_csv(rows)
    print()
    print(f"Saved: {OUTPUT_CSV}")
    print("Interpret unconfirmed recent episodes cautiously because the 365-day confirmation window may be censored by the dataset endpoint.")
    print("Done.")


if __name__ == "__main__":
    main()
