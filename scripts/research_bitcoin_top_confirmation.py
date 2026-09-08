"""Run Bitcoin top-risk warning + weakness-confirmation research."""

from __future__ import annotations

import csv
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.services.bitcoin_top_confirmation_research import (
    evaluate_top_confirmations,
    summarize_top_confirmations,
)
from backend.app.services.bitcoin_top_confluence_research import TopConfluencePoint

REPORTS_DIR = ROOT / "reports"
INPUT_CSV = REPORTS_DIR / "bitcoin_top_confluence_research.csv"
OUTPUT_CSV = REPORTS_DIR / "bitcoin_top_confirmation_research.csv"


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


def _fmt_days(value: float | None) -> str:
    return "N/A" if value is None else f"{value:,.0f}d"


def _write(rows) -> None:  # type: ignore[no-untyped-def]
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow((
            "warning_date", "warning_price", "rule", "confirmation_date", "confirmation_price",
            "days_to_confirmation", "upside_warning_to_confirmation_pct",
            "future_return_180d_from_confirmation_pct", "future_return_365d_from_confirmation_pct",
            "future_max_drawdown_180d_from_confirmation_pct", "future_max_drawdown_365d_from_confirmation_pct",
        ))
        for row in rows:
            writer.writerow((
                row.warning_date.isoformat(), row.warning_price, row.rule,
                row.confirmation_date.isoformat() if row.confirmation_date else "",
                row.confirmation_price, row.days_to_confirmation,
                row.upside_warning_to_confirmation_pct,
                row.future_return_180d_from_confirmation_pct,
                row.future_return_365d_from_confirmation_pct,
                row.future_max_drawdown_180d_from_confirmation_pct,
                row.future_max_drawdown_365d_from_confirmation_pct,
            ))


def main() -> None:
    print("BITCOIN TOP WARNING + WEAKNESS-CONFIRMATION RESEARCH")
    print("-" * 126)
    print("Warning = independent MVRV percentile >=90 episode under the same 90-day cooldown.")
    print("Fixed weakness confirmations use only point-in-time data after the warning:")
    print("  close below trailing 50d SMA; 30d momentum <0; 10% drawdown from post-warning peak; Overheat rollover >=20; any 2.")
    print("Confirmation search window = 180 days. No threshold is optimized from future outcomes.")

    points = _load_points()
    rows = evaluate_top_confirmations(points)
    if not rows:
        raise RuntimeError("No MVRV-high warning episodes were available")

    print()
    print("TOP-CONFIRMATION SUMMARY")
    print("-" * 126)
    print(
        f"{'Rule':39} {'Warn':>4} {'Conf':>4} {'Rate':>8} {'Med lag':>9} {'Upside':>9} "
        f"{'Ret180':>9} {'Ret365':>9} {'365<0':>8} {'DD180':>9} {'DD365':>9}"
    )
    for row in summarize_top_confirmations(rows):
        print(
            f"{row.rule:39} {row.warnings:>4} {row.confirmed:>4} {_fmt(row.confirmation_rate_pct):>8} "
            f"{_fmt_days(row.median_days_to_confirmation):>9} {_fmt(row.median_upside_to_confirmation_pct):>9} "
            f"{_fmt(row.median_return_180d_pct):>9} {_fmt(row.median_return_365d_pct):>9} "
            f"{_fmt(row.negative_365d_rate_pct):>8} {_fmt(row.median_drawdown_180d_pct):>9} "
            f"{_fmt(row.median_drawdown_365d_pct):>9}"
        )

    print()
    print("EPISODE DETAILS")
    print("-" * 126)
    grouped: dict[date, list] = {}
    for row in rows:
        grouped.setdefault(row.warning_date, []).append(row)
    for warning_date in sorted(grouped):
        episode_rows = grouped[warning_date]
        print(f"{warning_date} BTC ${episode_rows[0].warning_price:,.0f}")
        for row in episode_rows:
            if row.confirmation_date is None:
                print(f"  {row.rule:39} -> UNCONFIRMED within 180d")
                continue
            print(
                f"  {row.rule:39} -> {row.confirmation_date} BTC ${row.confirmation_price:,.0f} "
                f"lag={row.days_to_confirmation:>3}d upside-to-conf={_fmt(row.upside_warning_to_confirmation_pct):>8} "
                f"ret180={_fmt(row.future_return_180d_from_confirmation_pct):>8} "
                f"ret365={_fmt(row.future_return_365d_from_confirmation_pct):>8} "
                f"DD365={_fmt(row.future_max_drawdown_365d_from_confirmation_pct):>8}"
            )

    _write(rows)
    print()
    print(f"Saved: {OUTPUT_CSV}")
    print("Interpret this as confirmation research, not a validated sell/de-risking rule.")
    print("Done.")


if __name__ == "__main__":
    main()
