"""Run no-look-ahead MVRV / MVRV-Z research validation."""

from __future__ import annotations

import csv
import sys
from datetime import date
from pathlib import Path
from statistics import median

import matplotlib.dates as mdates
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.providers.coinmetrics_community_provider import CoinMetricsCommunityProvider
from backend.app.services.bitcoin_onchain_backtest import (
    build_onchain_point_in_time_backtest,
    default_threshold_summaries,
    independent_episodes,
)
from backend.app.services.bitcoin_onchain_research import build_onchain_research_rows


START_DATE = date(2010, 7, 18)
REPORTS_DIR = ROOT / "reports"


def _fmt(value: float | None) -> str:
    return "N/A" if value is None else f"{value:,.1f}%"


def _write_csv(points, output: Path) -> None:  # type: ignore[no-untyped-def]
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow((
            "date", "price_usd", "mvrv", "mvrv_z", "mvrv_percentile", "mvrv_z_percentile",
            "future_return_180d_pct", "future_return_365d_pct", "future_max_drawdown_365d_pct",
        ))
        for point in points:
            writer.writerow((
                point.date.isoformat(), point.price_usd, point.mvrv, point.mvrv_z,
                point.mvrv_percentile, point.mvrv_z_percentile,
                point.future_return_180d_pct, point.future_return_365d_pct,
                point.future_max_drawdown_365d_pct,
            ))


def _save(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(path, dpi=160, bbox_inches="tight")
    plt.close()


def _plot_percentiles(points, output: Path) -> None:  # type: ignore[no-untyped-def]
    dates = [p.date for p in points]
    plt.figure(figsize=(14, 6))
    plt.plot(dates, [p.mvrv_percentile for p in points], linewidth=1.2, label="MVRV expanding percentile")
    plt.plot(dates, [p.mvrv_z_percentile for p in points], linewidth=1.2, label="MVRV-Z expanding percentile")
    for level, style in ((10, "--"), (20, ":"), (80, ":"), (90, "--")):
        plt.axhline(level, linewidth=0.9, linestyle=style)
    plt.ylim(0, 100)
    plt.title("Bitcoin On-Chain Expanding Percentiles (No Look-Ahead)")
    plt.xlabel("Date")
    plt.ylabel("Historical percentile")
    plt.grid(True, alpha=0.3)
    plt.legend()
    ax = plt.gca()
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    _save(output)


def _plot_episode_prices(points, output: Path) -> None:  # type: ignore[no-untyped-def]
    dates = [p.date for p in points]
    prices = [p.price_usd for p in points]
    plt.figure(figsize=(14, 7))
    plt.plot(dates, prices, linewidth=1.4, label="BTC price")
    plt.yscale("log")

    specs = (
        ("MVRV pct <= 10", lambda p: p.mvrv_percentile is not None and p.mvrv_percentile <= 10),
        ("MVRV-Z pct <= 10", lambda p: p.mvrv_z_percentile is not None and p.mvrv_z_percentile <= 10),
        ("MVRV pct >= 90", lambda p: p.mvrv_percentile is not None and p.mvrv_percentile >= 90),
        ("MVRV-Z pct >= 90", lambda p: p.mvrv_z_percentile is not None and p.mvrv_z_percentile >= 90),
    )
    for label, predicate in specs:
        episodes = independent_episodes(points, predicate=predicate)
        if episodes:
            plt.scatter([p.date for p in episodes], [p.price_usd for p in episodes], s=34, label=label)

    plt.title("Bitcoin Price with Independent On-Chain Percentile Episodes")
    plt.xlabel("Date")
    plt.ylabel("BTC price (log scale)")
    plt.grid(True, alpha=0.3)
    plt.legend(ncol=2)
    ax = plt.gca()
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    _save(output)


def _print_episodes(points) -> None:  # type: ignore[no-untyped-def]
    specs = (
        ("MVRV pct <= 10", lambda p: p.mvrv_percentile is not None and p.mvrv_percentile <= 10),
        ("MVRV-Z pct <= 10", lambda p: p.mvrv_z_percentile is not None and p.mvrv_z_percentile <= 10),
        ("MVRV pct >= 90", lambda p: p.mvrv_percentile is not None and p.mvrv_percentile >= 90),
        ("MVRV-Z pct >= 90", lambda p: p.mvrv_z_percentile is not None and p.mvrv_z_percentile >= 90),
    )
    print()
    print("INDEPENDENT ON-CHAIN PERCENTILE EPISODES (90-DAY COOLDOWN)")
    print("-" * 108)
    for label, predicate in specs:
        episodes = independent_episodes(points, predicate=predicate)
        valid = [p for p in episodes if p.future_return_365d_pct is not None]
        med = median([p.future_return_365d_pct for p in valid]) if valid else None
        print(f"{label}: episodes={len(episodes):>2} valid365={len(valid):>2} median365={_fmt(med)}")
        for point in episodes:
            pct = point.mvrv_percentile if label.startswith("MVRV pct") else point.mvrv_z_percentile
            print(
                f"  {point.date} BTC ${point.price_usd:>10,.0f} pct={pct:>5.1f} "
                f"365d={_fmt(point.future_return_365d_pct):>10} min={_fmt(point.future_max_drawdown_365d_pct):>10}"
            )


def main() -> None:
    print("Fetching Bitcoin on-chain history...")
    provider = CoinMetricsCommunityProvider()
    records = provider.get_bitcoin_daily_metrics(start_date=START_DATE, end_date=date.today())
    print(f"Loaded {len(records):,} rows: {records[0].date} -> {records[-1].date}")
    research_rows = build_onchain_research_rows(records)
    points = build_onchain_point_in_time_backtest(research_rows, minimum_history_days=730)
    print(f"Built {len(points):,} point-in-time observations using expanding historical percentiles.")
    print("Future returns are validation labels only; percentile thresholds use no future metric values.")

    print()
    print("POINT-IN-TIME ON-CHAIN THRESHOLD OUTCOMES")
    print("-" * 96)
    print(f"{'Threshold':22} {'Days':>7} {'Med365':>12} {'365d >0':>10} {'DD<=-30':>10}")
    for row in default_threshold_summaries(points):
        print(
            f"{row.label:22} {row.count:>7} {_fmt(row.median_return_365d_pct):>12} "
            f"{_fmt(row.positive_365d_rate_pct):>10} {_fmt(row.drawdown_30pct_rate_pct):>10}"
        )

    _print_episodes(points)

    latest = points[-1]
    print()
    print("LATEST USABLE POINT-IN-TIME ON-CHAIN STATE")
    print("-" * 96)
    print(
        f"{latest.date} BTC ${latest.price_usd:,.2f} MVRV={latest.mvrv if latest.mvrv is not None else 'N/A'} "
        f"MVRV-pct={latest.mvrv_percentile if latest.mvrv_percentile is not None else 'N/A'} "
        f"MVRV-Z={latest.mvrv_z if latest.mvrv_z is not None else 'N/A'} "
        f"MVRV-Z-pct={latest.mvrv_z_percentile if latest.mvrv_z_percentile is not None else 'N/A'}"
    )

    csv_path = REPORTS_DIR / "bitcoin_onchain_backtest.csv"
    pct_path = REPORTS_DIR / "bitcoin_onchain_backtest_percentiles.png"
    episode_path = REPORTS_DIR / "bitcoin_onchain_backtest_episodes.png"
    _write_csv(points, csv_path)
    _plot_percentiles(points, pct_path)
    _plot_episode_prices(points, episode_path)

    print()
    for path in (csv_path, pct_path, episode_path):
        print(f"Saved: {path}")
    print("Research only: archive fallback is stale for live use, but historical validation remains usable.")
    print("MVRV and reconstructed NUPL are not treated as independent signals.")
    print("Done.")


if __name__ == "__main__":
    main()
