"""Run timing analysis for independent Bitcoin top-risk signals."""

from __future__ import annotations

import csv
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.services.bitcoin_top_confluence_research import TopConfluencePoint
from backend.app.services.bitcoin_top_timing_research import (
    evaluate_top_timing,
    summarize_top_timing,
)

REPORTS_DIR = ROOT / "reports"
INPUT_CSV = REPORTS_DIR / "bitcoin_top_confluence_research.csv"
OUTPUT_CSV = REPORTS_DIR / "bitcoin_top_timing_research.csv"


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


def _fmt_pct(value: float | None) -> str:
    return "N/A" if value is None else f"{value:,.1f}%"


def _fmt_days(value: float | int | None) -> str:
    return "N/A" if value is None else f"{value:,.0f}d"


def _write(rows) -> None:  # type: ignore[no-untyped-def]
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow((
            "signal", "signal_date", "signal_price", "peak_date_365d", "peak_price_365d",
            "days_to_peak_365d", "additional_upside_365d_pct", "max_peak_to_trough_dd_180d_pct",
            "max_peak_to_trough_dd_365d_pct", "days_to_20pct_running_peak_dd",
            "days_to_30pct_running_peak_dd", "days_to_40pct_running_peak_dd",
        ))
        for row in rows:
            writer.writerow((
                row.signal,
                row.signal_date.isoformat(),
                row.signal_price,
                row.peak_date_365d.isoformat() if row.peak_date_365d else "",
                row.peak_price_365d,
                row.days_to_peak_365d,
                row.additional_upside_365d_pct,
                row.max_peak_to_trough_dd_180d_pct,
                row.max_peak_to_trough_dd_365d_pct,
                row.days_to_20pct_running_peak_dd,
                row.days_to_30pct_running_peak_dd,
                row.days_to_40pct_running_peak_dd,
            ))


def main() -> None:
    print("BITCOIN TOP-SIGNAL TIMING / EARLY-WARNING RESEARCH")
    print("-" * 126)
    print("Independent top-risk entries use the same fixed thresholds and 90-day cooldown as prior top-confluence research.")
    print("Peak = highest BTC price during the completed 365 days after signal.")
    print("Drawdown = running-peak-to-trough drawdown, not merely decline from the original signal price.")
    print("Recent episodes without a full required horizon are left censored rather than treated as completed.")

    points = _load_points()
    rows = evaluate_top_timing(points)
    summaries = summarize_top_timing(rows)

    print()
    print("TOP-SIGNAL TIMING SUMMARY")
    print("-" * 126)
    print(
        f"{'Signal':58} {'Ep':>3} {'V365':>5} {'Med peak':>9} {'Med upside':>11} "
        f"{'DD180':>9} {'DD365':>9} {'Hit20':>8} {'Hit30':>8} {'Hit40':>8}"
    )
    for row in summaries:
        print(
            f"{row.signal:58} {row.episodes:>3} {row.valid_365d:>5} "
            f"{_fmt_days(row.median_days_to_peak_365d):>9} {_fmt_pct(row.median_additional_upside_365d_pct):>11} "
            f"{_fmt_pct(row.median_max_peak_to_trough_dd_180d_pct):>9} "
            f"{_fmt_pct(row.median_max_peak_to_trough_dd_365d_pct):>9} "
            f"{_fmt_pct(row.hit_20pct_dd_rate_pct):>8} {_fmt_pct(row.hit_30pct_dd_rate_pct):>8} "
            f"{_fmt_pct(row.hit_40pct_dd_rate_pct):>8}"
        )
        print(
            f"{'':58} {'':>3} {'':>5} {'':>9} {'':>11} {'':>9} {'':>9} "
            f"days20={_fmt_days(row.median_days_to_20pct_dd)} "
            f"days30={_fmt_days(row.median_days_to_30pct_dd)} "
            f"days40={_fmt_days(row.median_days_to_40pct_dd)}"
        )

    print()
    print("EPISODE DETAILS")
    print("-" * 126)
    for row in rows:
        peak = "N/A" if row.peak_date_365d is None else f"{row.peak_date_365d} ${row.peak_price_365d:,.0f}"
        print(
            f"{row.signal} | {row.signal_date} BTC ${row.signal_price:,.0f} -> peak {peak} "
            f"({ _fmt_days(row.days_to_peak_365d) }, upside {_fmt_pct(row.additional_upside_365d_pct)})"
        )
        print(
            f"  DD180={_fmt_pct(row.max_peak_to_trough_dd_180d_pct)} "
            f"DD365={_fmt_pct(row.max_peak_to_trough_dd_365d_pct)} "
            f"to-20={_fmt_days(row.days_to_20pct_running_peak_dd)} "
            f"to-30={_fmt_days(row.days_to_30pct_running_peak_dd)} "
            f"to-40={_fmt_days(row.days_to_40pct_running_peak_dd)}"
        )

    _write(rows)
    print()
    print(f"Saved: {OUTPUT_CSV}")
    print("Interpret this as early-warning timing research, not as a validated sell rule.")
    print("Done.")


if __name__ == "__main__":
    main()
