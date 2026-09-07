"""Compare predeclared Bitcoin signal combinations without fitting weights."""

from __future__ import annotations

import csv
import sys
from datetime import date
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.services.bitcoin_confluence_research import (
    DEFAULT_SPECS,
    ConfluencePoint,
    evaluate_era_stability,
    evaluate_threshold_sensitivity,
    independent_confluence_episodes,
    summarize_default_confluence,
)

REPORTS_DIR = ROOT / "reports"
CYCLE_CSV = REPORTS_DIR / "bitcoin_cycle_backtest.csv"
QUANTILE_CSV = REPORTS_DIR / "bitcoin_quantile_backtest.csv"
ONCHAIN_CSV = REPORTS_DIR / "bitcoin_onchain_backtest.csv"
OUTPUT_CSV = REPORTS_DIR / "bitcoin_confluence_research.csv"
SENSITIVITY_CSV = REPORTS_DIR / "bitcoin_confluence_threshold_sensitivity.csv"
ERA_CSV = REPORTS_DIR / "bitcoin_confluence_era_stability.csv"


def _float_or_none(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _load_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise RuntimeError(
            f"Missing required research file: {path}. Run the corresponding backtest script first."
        )
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _join_points() -> list[ConfluencePoint]:
    cycle = {row["date"]: row for row in _load_csv(CYCLE_CSV)}
    quantile = {row["date"]: row for row in _load_csv(QUANTILE_CSV)}
    onchain = {row["date"]: row for row in _load_csv(ONCHAIN_CSV)}

    common_dates = sorted(set(cycle).intersection(quantile, onchain))
    points: list[ConfluencePoint] = []
    for day_text in common_dates:
        c = cycle[day_text]
        q = quantile[day_text]
        o = onchain[day_text]
        mvrv_pct = _float_or_none(o.get("mvrv_percentile"))
        if mvrv_pct is None:
            continue

        points.append(
            ConfluencePoint(
                date=date.fromisoformat(day_text),
                price=float(c["price"]),
                opportunity_score=float(c["opportunity_score"]),
                quantile_percentile=float(q["quantile_percentile"]),
                mvrv_percentile=mvrv_pct,
                future_return_365d_pct=_float_or_none(c.get("future_return_365d_pct")),
                future_max_drawdown_365d_pct=_float_or_none(c.get("future_max_drawdown_365d_pct")),
            )
        )
    return points


def _fmt(value: float | None) -> str:
    return "N/A" if value is None else f"{value:,.1f}%"


def _write_csv(points: list[ConfluencePoint]) -> None:
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("date", "price", "opportunity_score", "quantile_percentile", "mvrv_percentile", "future_return_365d_pct", "future_max_drawdown_365d_pct"))
        for point in points:
            writer.writerow((point.date.isoformat(), point.price, point.opportunity_score, point.quantile_percentile, point.mvrv_percentile, point.future_return_365d_pct, point.future_max_drawdown_365d_pct))


def _write_sensitivity_csv(rows) -> None:  # type: ignore[no-untyped-def]
    SENSITIVITY_CSV.parent.mkdir(parents=True, exist_ok=True)
    with SENSITIVITY_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("opportunity_threshold", "quantile_threshold", "mvrv_percentile_threshold", "daily_count", "valid_365d", "median_return_365d_pct", "positive_365d_rate_pct", "gain_50pct_365d_rate_pct", "drawdown_30pct_rate_pct", "episode_count", "episode_valid_365d", "episode_median_return_365d_pct", "episode_drawdown_30pct_rate_pct"))
        for row in rows:
            writer.writerow((row.opportunity_threshold, row.quantile_threshold, row.mvrv_percentile_threshold, row.daily_count, row.valid_365d, row.median_return_365d_pct, row.positive_365d_rate_pct, row.gain_50pct_365d_rate_pct, row.drawdown_30pct_rate_pct, row.episode_count, row.episode_valid_365d, row.episode_median_return_365d_pct, row.episode_drawdown_30pct_rate_pct))


def _write_era_csv(rows) -> None:  # type: ignore[no-untyped-def]
    ERA_CSV.parent.mkdir(parents=True, exist_ok=True)
    with ERA_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("era", "start_date", "end_date", "condition", "daily_count", "valid_365d", "median_return_365d_pct", "positive_365d_rate_pct", "drawdown_30pct_rate_pct", "episode_count", "episode_valid_365d", "episode_median_return_365d_pct", "episode_drawdown_30pct_rate_pct"))
        for row in rows:
            writer.writerow((row.era, row.start_date.isoformat(), row.end_date.isoformat(), row.condition, row.daily_count, row.valid_365d, row.median_return_365d_pct, row.positive_365d_rate_pct, row.drawdown_30pct_rate_pct, row.episode_count, row.episode_valid_365d, row.episode_median_return_365d_pct, row.episode_drawdown_30pct_rate_pct))


def _print_sensitivity(rows) -> None:  # type: ignore[no-untyped-def]
    print()
    print("ALL-THREE THRESHOLD SENSITIVITY (PREDECLARED GRID; NOT OPTIMIZATION)")
    print("-" * 120)
    print("Opportunity thresholds: 50 / 60 / 70")
    print("Quantile thresholds:     5 / 10 / 15 / 20")
    print("MVRV pct thresholds:     10 / 20 / 30")
    print("Primary view below is independent 90-day-cooldown episodes.")
    print()
    print(f"{'Opp':>5} {'Q<=':>5} {'MVRV<=':>7} {'Days':>7} {'Ep':>4} {'ValidEp':>7} {'Ep Med365':>11} {'Ep DD<=-30':>12} {'Daily Med365':>13}")
    for row in rows:
        print(f"{row.opportunity_threshold:>5.0f} {row.quantile_threshold:>5.0f} {row.mvrv_percentile_threshold:>7.0f} {row.daily_count:>7} {row.episode_count:>4} {row.episode_valid_365d:>7} {_fmt(row.episode_median_return_365d_pct):>11} {_fmt(row.episode_drawdown_30pct_rate_pct):>12} {_fmt(row.median_return_365d_pct):>13}")

    usable = [row for row in rows if row.episode_valid_365d >= 3]
    positive = [row for row in usable if row.episode_median_return_365d_pct is not None and row.episode_median_return_365d_pct > 0]
    low_drawdown = [row for row in usable if row.episode_drawdown_30pct_rate_pct is not None and row.episode_drawdown_30pct_rate_pct <= 25]
    print()
    print("ROBUSTNESS COUNTS (descriptive, not model selection)")
    print("-" * 120)
    print(f"Grid cells:                                      {len(rows)}")
    print(f"Cells with >=3 valid independent 365d episodes: {len(usable)}")
    print(f"Of those, cells with positive median 365d:      {len(positive)}")
    print(f"Of those, cells with DD<=-30 rate <=25%:        {len(low_drawdown)}")


def _print_era_stability(rows) -> None:  # type: ignore[no-untyped-def]
    print()
    print("ERA STABILITY / WALK-FORWARD-STYLE VALIDATION (FIXED THRESHOLDS)")
    print("-" * 128)
    print("Thresholds are unchanged in every era: Opportunity >=60, Quantile <=10, MVRV pct <=20.")
    print("Era boundaries partition validation only; they do not refit or optimize the signals.")
    print()
    print(f"{'Era':11} {'Condition':24} {'Days':>6} {'Valid':>6} {'DailyMed':>10} {'Daily>0':>9} {'DailyDD':>9} {'Ep':>4} {'ValidEp':>7} {'EpMed365':>10} {'EpDD':>9}")
    for row in rows:
        print(f"{row.era:11} {row.condition:24} {row.daily_count:>6} {row.valid_365d:>6} {_fmt(row.median_return_365d_pct):>10} {_fmt(row.positive_365d_rate_pct):>9} {_fmt(row.drawdown_30pct_rate_pct):>9} {row.episode_count:>4} {row.episode_valid_365d:>7} {_fmt(row.episode_median_return_365d_pct):>10} {_fmt(row.episode_drawdown_30pct_rate_pct):>9}")


def main() -> None:
    print("BITCOIN SIGNAL CONFLUENCE RESEARCH")
    print("-" * 108)
    print("Using existing point-in-time/no-look-ahead research CSVs.")
    print("No weights are fitted and no production score is changed.")
    print("Baseline thresholds are predeclared: Opportunity >=60, Quantile <=10, MVRV percentile <=20.")

    points = _join_points()
    if not points:
        raise RuntimeError("No common point-in-time dates were found across the three research datasets")

    print(f"Common joined range: {points[0].date} -> {points[-1].date} ({len(points):,} daily observations)")

    print()
    print("DAILY CONDITION OUTCOMES")
    print("-" * 118)
    print(f"{'Condition':58} {'Days':>7} {'Valid365':>9} {'Med365':>11} {'365d >0':>10} {'365d >=50':>11} {'DD<=-30':>10}")
    for row in summarize_default_confluence(points):
        print(f"{row.label:58} {row.count:>7} {row.valid_365d:>9} {_fmt(row.median_return_365d_pct):>11} {_fmt(row.positive_365d_rate_pct):>10} {_fmt(row.gain_50pct_365d_rate_pct):>11} {_fmt(row.drawdown_30pct_rate_pct):>10}")

    print()
    print("INDEPENDENT CONDITION-ENTRY EPISODES (90-DAY COOLDOWN)")
    print("-" * 118)
    for spec in DEFAULT_SPECS:
        episodes = independent_confluence_episodes(points, spec, cooldown_days=90)
        valid = [p for p in episodes if p.future_return_365d_pct is not None]
        med = median([p.future_return_365d_pct for p in valid]) if valid else None
        print(f"{spec.label}: episodes={len(episodes)} valid365={len(valid)} median365={_fmt(med)}")
        for point in episodes:
            print(f"  {point.date} BTC ${point.price:>10,.0f} Opp={point.opportunity_score:>5.1f} Q={point.quantile_percentile:>5.1f} MVRV-pct={point.mvrv_percentile:>5.1f} 365d={_fmt(point.future_return_365d_pct):>10} min={_fmt(point.future_max_drawdown_365d_pct):>10}")

    sensitivity = evaluate_threshold_sensitivity(points)
    _print_sensitivity(sensitivity)

    era_rows = evaluate_era_stability(points)
    _print_era_stability(era_rows)

    latest = points[-1]
    print()
    print("LATEST DATE PRESENT IN ALL THREE HISTORICAL RESEARCH SERIES")
    print("-" * 108)
    print(f"{latest.date} BTC ${latest.price:,.2f} Opportunity={latest.opportunity_score:.0f} Quantile={latest.quantile_percentile:.1f} MVRV-pct={latest.mvrv_percentile:.1f}")
    print("Note: this common historical endpoint may lag the separately fetched live MVRV snapshot.")

    _write_csv(points)
    _write_sensitivity_csv(sensitivity)
    _write_era_csv(era_rows)
    print()
    print(f"Saved: {OUTPUT_CSV}")
    print(f"Saved: {SENSITIVITY_CSV}")
    print(f"Saved: {ERA_CSV}")
    print("Sensitivity grid is for robustness checking only; do not choose the best-looking cell as a fitted rule.")
    print("Era analysis uses fixed thresholds and point-in-time signals; future returns remain validation labels only.")
    print("Interpret daily counts cautiously because neighboring days are autocorrelated.")
    print("Independent episodes are the more important comparison for deciding whether confluence adds value.")
    print("Done.")


if __name__ == "__main__":
    main()
