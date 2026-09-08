"""Run persistent Bitcoin top weakness-confirmation research."""

from __future__ import annotations

import csv
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.services.bitcoin_top_confluence_research import TopConfluencePoint
from backend.app.services.bitcoin_top_persistent_confirmation_research import (
    evaluate_persistent_top_confirmations,
    summarize_persistent_top_confirmations,
)

REPORTS_DIR = ROOT / "reports"
INPUT_CSV = REPORTS_DIR / "bitcoin_top_confluence_research.csv"
OUTPUT_CSV = REPORTS_DIR / "bitcoin_top_persistent_confirmation_research.csv"


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
            "warning_date", "warning_price", "rule", "confirmation_date", "confirmation_price",
            "days_to_confirmation", "upside_before_confirmation_pct",
            "max_upside_365d_after_confirmation_pct", "future_return_180d_pct",
            "future_return_365d_pct", "max_drawdown_365d_pct",
        ))
        for row in rows:
            writer.writerow((
                row.warning_date.isoformat(), row.warning_price, row.rule,
                row.confirmation_date.isoformat() if row.confirmation_date else "",
                row.confirmation_price if row.confirmation_price is not None else "",
                row.days_to_confirmation if row.days_to_confirmation is not None else "",
                row.upside_before_confirmation_pct if row.upside_before_confirmation_pct is not None else "",
                row.max_upside_365d_after_confirmation_pct if row.max_upside_365d_after_confirmation_pct is not None else "",
                row.future_return_180d_pct if row.future_return_180d_pct is not None else "",
                row.future_return_365d_pct if row.future_return_365d_pct is not None else "",
                row.max_drawdown_365d_pct if row.max_drawdown_365d_pct is not None else "",
            ))


def main() -> None:
    print("BITCOIN PERSISTENT TOP-WEAKNESS CONFIRMATION RESEARCH")
    print("-" * 134)
    print("Warning = independent MVRV percentile >=90 episode under the same 90-day cooldown.")
    print("Confirmation window = 180 days. All confirmation rules are fixed and point-in-time.")
    print("Rules: Any-2 immediate; Any-2 sustained 7d/14d; 20% drawdown + one other weakness; 50d SMA break sustained 7d; 200d SMA break.")
    print("Early-confirmation proxy = BTC later gains >=25% above the confirmation price within the completed next 365 days.")
    print("This proxy is descriptive; it is not a definition of a failed signal.")

    points = _load_points()
    rows = evaluate_persistent_top_confirmations(points)
    summaries = summarize_persistent_top_confirmations(rows)

    print()
    print("PERSISTENT CONFIRMATION SUMMARY")
    print("-" * 134)
    print(
        f"{'Rule':36} {'Warn':>4} {'Conf':>4} {'Rate':>9} {'Lag':>8} {'Pre-up':>10} "
        f"{'Post-up':>10} {'Post>=25':>10} {'Ret365':>10} {'365<0':>9} {'DD365':>10}"
    )
    for row in summaries:
        lag = "N/A" if row.median_days_to_confirmation is None else f"{row.median_days_to_confirmation:.0f}d"
        print(
            f"{row.rule:36} {row.warnings:>4} {row.confirmed:>4} {_fmt(row.confirmation_rate_pct):>9} "
            f"{lag:>8} {_fmt(row.median_upside_before_confirmation_pct):>10} "
            f"{_fmt(row.median_max_upside_after_confirmation_pct):>10} {_fmt(row.early_25pct_upside_rate_pct):>10} "
            f"{_fmt(row.median_return_365d_pct):>10} {_fmt(row.negative_365d_rate_pct):>9} "
            f"{_fmt(row.median_drawdown_365d_pct):>10}"
        )

    print()
    print("EPISODE DETAILS")
    print("-" * 134)
    warning_dates = sorted({row.warning_date for row in rows})
    for warning_date in warning_dates:
        selected = [row for row in rows if row.warning_date == warning_date]
        first = selected[0]
        print(f"{warning_date} BTC ${first.warning_price:,.0f}")
        for row in selected:
            if row.confirmation_date is None:
                print(f"  {row.rule:36} -> NONE")
                continue
            print(
                f"  {row.rule:36} -> {row.confirmation_date} BTC ${row.confirmation_price:,.0f} "
                f"lag={row.days_to_confirmation:>3}d pre-up={_fmt(row.upside_before_confirmation_pct):>9} "
                f"post-up={_fmt(row.max_upside_365d_after_confirmation_pct):>9} "
                f"ret180={_fmt(row.future_return_180d_pct):>9} ret365={_fmt(row.future_return_365d_pct):>9} "
                f"DD365={_fmt(row.max_drawdown_365d_pct):>9}"
            )

    _write(rows)
    print()
    print(f"Saved: {OUTPUT_CSV}")
    print("Compare persistence and structural-break rules against the immediate Any-2 baseline; do not optimize from three historical warnings.")
    print("Done.")


if __name__ == "__main__":
    main()
