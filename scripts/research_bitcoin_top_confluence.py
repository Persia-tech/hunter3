"""Run fixed Bitcoin top/overheating confluence research."""

from __future__ import annotations

import csv
import sys
from datetime import date
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.services.bitcoin_top_confluence_research import (
    DEFAULT_TOP_SPECS,
    TopConfluencePoint,
    independent_top_episodes,
    summarize_default_top_confluence,
)

REPORTS_DIR = ROOT / "reports"
CYCLE_CSV = REPORTS_DIR / "bitcoin_cycle_backtest.csv"
QUANTILE_CSV = REPORTS_DIR / "bitcoin_quantile_backtest.csv"
ONCHAIN_CSV = REPORTS_DIR / "bitcoin_onchain_backtest.csv"
OUTPUT_CSV = REPORTS_DIR / "bitcoin_top_confluence_research.csv"


def _float_or_none(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _load_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise RuntimeError(f"Missing required research file: {path}")
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _join_points() -> list[TopConfluencePoint]:
    cycle = {row["date"]: row for row in _load_csv(CYCLE_CSV)}
    quantile = {row["date"]: row for row in _load_csv(QUANTILE_CSV)}
    onchain = {row["date"]: row for row in _load_csv(ONCHAIN_CSV)}
    common_dates = sorted(set(cycle).intersection(quantile, onchain))

    points: list[TopConfluencePoint] = []
    for day_text in common_dates:
        c = cycle[day_text]
        q = quantile[day_text]
        o = onchain[day_text]
        mvrv_pct = _float_or_none(o.get("mvrv_percentile"))
        if mvrv_pct is None:
            continue
        points.append(
            TopConfluencePoint(
                date=date.fromisoformat(day_text),
                price=float(c["price"]),
                overheat_score=float(c["overheat_score"]),
                quantile_percentile=float(q["quantile_percentile"]),
                mvrv_percentile=mvrv_pct,
                future_return_365d_pct=_float_or_none(c.get("future_return_365d_pct")),
                future_max_drawdown_365d_pct=_float_or_none(c.get("future_max_drawdown_365d_pct")),
            )
        )
    return points


def _fmt(value: float | None) -> str:
    return "N/A" if value is None else f"{value:,.1f}%"


def _write(points: list[TopConfluencePoint]) -> None:
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow((
            "date", "price", "overheat_score", "quantile_percentile", "mvrv_percentile",
            "future_return_365d_pct", "future_max_drawdown_365d_pct",
        ))
        for point in points:
            writer.writerow((
                point.date.isoformat(), point.price, point.overheat_score,
                point.quantile_percentile, point.mvrv_percentile,
                point.future_return_365d_pct, point.future_max_drawdown_365d_pct,
            ))


def main() -> None:
    print("BITCOIN TOP / OVERHEATING CONFLUENCE RESEARCH")
    print("-" * 118)
    print("Fixed research thresholds: Overheat >=60, Quantile >=90, MVRV percentile >=90.")
    print("No weights are fitted and no production score is changed.")
    print("The three families remain separate so we can test whether they add distinct top-risk information.")

    points = _join_points()
    if not points:
        raise RuntimeError("No common point-in-time observations were found")

    print(f"Common joined range: {points[0].date} -> {points[-1].date} ({len(points):,} daily observations)")

    print()
    print("DAILY TOP-RISK CONDITION OUTCOMES")
    print("-" * 118)
    print(f"{'Condition':58} {'Days':>7} {'Valid365':>9} {'Med365':>11} {'365d <0':>10} {'365d <=-30':>12} {'DD<=-30':>10}")
    for row in summarize_default_top_confluence(points):
        print(
            f"{row.label:58} {row.count:>7} {row.valid_365d:>9} {_fmt(row.median_return_365d_pct):>11} "
            f"{_fmt(row.negative_365d_rate_pct):>10} {_fmt(row.loss_30pct_365d_rate_pct):>12} "
            f"{_fmt(row.drawdown_30pct_rate_pct):>10}"
        )

    print()
    print("INDEPENDENT TOP-RISK CONDITION-ENTRY EPISODES (90-DAY COOLDOWN)")
    print("-" * 118)
    for spec in DEFAULT_TOP_SPECS:
        episodes = independent_top_episodes(points, spec, cooldown_days=90)
        valid = [p for p in episodes if p.future_return_365d_pct is not None]
        med = median([p.future_return_365d_pct for p in valid]) if valid else None
        neg = 100.0 * sum((p.future_return_365d_pct or 0) < 0 for p in valid) / len(valid) if valid else None
        dd = [p.future_max_drawdown_365d_pct for p in episodes if p.future_max_drawdown_365d_pct is not None]
        dd30 = 100.0 * sum(value <= -30 for value in dd) / len(dd) if dd else None
        print(
            f"{spec.label}: episodes={len(episodes)} valid365={len(valid)} median365={_fmt(med)} "
            f"negative365={_fmt(neg)} DD<=-30={_fmt(dd30)}"
        )
        for point in episodes:
            print(
                f"  {point.date} BTC ${point.price:>10,.0f} Heat={point.overheat_score:>5.1f} "
                f"Q={point.quantile_percentile:>5.1f} MVRV-pct={point.mvrv_percentile:>5.1f} "
                f"365d={_fmt(point.future_return_365d_pct):>10} min={_fmt(point.future_max_drawdown_365d_pct):>10}"
            )

    latest = points[-1]
    print()
    print("LATEST COMMON HISTORICAL OBSERVATION")
    print("-" * 118)
    print(
        f"{latest.date} BTC ${latest.price:,.2f} Heat={latest.overheat_score:.0f} "
        f"Quantile={latest.quantile_percentile:.1f} MVRV-pct={latest.mvrv_percentile:.1f}"
    )

    _write(points)
    print()
    print(f"Saved: {OUTPUT_CSV}")
    print("Interpret daily counts cautiously because neighboring days are autocorrelated.")
    print("Independent episodes are the primary comparison.")
    print("High Quantile is treated as a hypothesis here, not assumed to be a valid sell signal.")
    print("Done.")


if __name__ == "__main__":
    main()
