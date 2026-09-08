"""Run a no-look-ahead expanding-window backtest of the research quantile model."""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date
from pathlib import Path
from statistics import median

import matplotlib.dates as mdates
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.models.asset import get_asset
from backend.app.providers.dca_yfinance_provider import YFinanceProvider
from backend.app.services.bitcoin_quantile_backtest import (
    build_quantile_backtest,
    independent_threshold_episodes,
    summarize_percentile_bands,
    summarize_threshold,
)
from backend.app.services.dca_market_data import MarketDataService


BTC_HISTORY_START = date(2014, 9, 17)
REPORTS_DIR = ROOT / "reports"


def _fmt(value: float | None) -> str:
    return "N/A" if value is None else f"{value:,.1f}%"


def _write_csv(points, destination: Path) -> None:  # type: ignore[no-untyped-def]
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            (
                "date",
                "price",
                "quantile_percentile",
                "model_fit_date",
                "future_return_180d_pct",
                "future_return_365d_pct",
                "future_max_gain_365d_pct",
                "future_max_drawdown_365d_pct",
            )
        )
        for point in points:
            writer.writerow(
                (
                    point.as_of.isoformat(),
                    f"{point.price:.8f}",
                    f"{point.quantile_percentile:.6f}",
                    point.model_fit_date.isoformat(),
                    point.future_return_180d_pct,
                    point.future_return_365d_pct,
                    point.future_max_gain_365d_pct,
                    point.future_max_drawdown_365d_pct,
                )
            )


def _plot_percentile(points, output_path: Path) -> None:  # type: ignore[no-untyped-def]
    dates = [point.as_of for point in points]
    values = [point.quantile_percentile for point in points]
    plt.figure(figsize=(14, 6))
    plt.plot(dates, values, linewidth=1.4, label="Point-in-time quantile percentile")
    for threshold, style in ((10, "--"), (25, ":"), (75, ":"), (90, "--"), (95, "-.")):
        plt.axhline(threshold, linewidth=1, linestyle=style, label=f"{threshold}th percentile")
    plt.ylim(0, 100)
    plt.title("Bitcoin Quantile Percentile Over Time (No-Look-Ahead Expanding Fit)")
    plt.xlabel("Date")
    plt.ylabel("Model percentile")
    plt.grid(True, alpha=0.3)
    plt.legend(ncol=3)
    ax = plt.gca()
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close()


def _plot_episodes(points, output_path: Path) -> None:  # type: ignore[no-untyped-def]
    dates = [point.as_of for point in points]
    prices = [point.price for point in points]
    plt.figure(figsize=(14, 7))
    plt.plot(dates, prices, linewidth=1.3, label="BTC price")
    plt.yscale("log")

    specs = (
        (10, "low", "Percentile <= 10"),
        (25, "low", "Percentile <= 25"),
        (90, "high", "Percentile >= 90"),
        (95, "high", "Percentile >= 95"),
    )
    for threshold, direction, label in specs:
        episodes = independent_threshold_episodes(
            points,
            threshold=threshold,
            direction=direction,
            cooldown_days=90,
        )
        if episodes:
            plt.scatter(
                [point.as_of for point in episodes],
                [point.price for point in episodes],
                s=34,
                label=label,
            )

    plt.title("Bitcoin Price with Independent Point-in-Time Quantile Episodes")
    plt.xlabel("Date")
    plt.ylabel("BTC price (log scale)")
    plt.grid(True, alpha=0.3)
    plt.legend(ncol=2)
    ax = plt.gca()
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close()


def _plot_band_returns(points, output_path: Path) -> None:  # type: ignore[no-untyped-def]
    rows = summarize_percentile_bands(points)
    labels = [row[0] for row in rows]
    medians = [0.0 if row[2] is None else row[2] for row in rows]
    plt.figure(figsize=(10, 6))
    plt.bar(labels, medians)
    plt.axhline(0, linewidth=1, linestyle="--")
    plt.title("Point-in-Time Quantile Band vs Median Future 365-Day Return")
    plt.xlabel("Quantile percentile band")
    plt.ylabel("Median future 365-day return (%)")
    plt.grid(True, axis="y", alpha=0.3)
    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close()


def _print_threshold_table(points) -> None:  # type: ignore[no-untyped-def]
    print()
    print("POINT-IN-TIME QUANTILE THRESHOLD OUTCOMES")
    print("-" * 92)
    print(f"{'Threshold':16} {'Days':>7} {'Med365':>12} {'365d >0':>10} {'365d >=50':>11} {'DD <=-30':>10}")
    for threshold, direction in ((10, "low"), (25, "low"), (75, "high"), (90, "high"), (95, "high")):
        row = summarize_threshold(points, threshold=threshold, direction=direction)
        print(
            f"{row.label:16} {row.count:>7} {_fmt(row.median_return_365d_pct):>12} "
            f"{_fmt(row.positive_365d_rate_pct):>10} {_fmt(row.gain_50pct_365d_rate_pct):>11} "
            f"{_fmt(row.drawdown_30pct_365d_rate_pct):>10}"
        )


def _print_episode_table(points) -> None:  # type: ignore[no-untyped-def]
    print()
    print("INDEPENDENT QUANTILE THRESHOLD EPISODES (90-DAY COOLDOWN)")
    print("-" * 104)
    for threshold, direction in ((10, "low"), (25, "low"), (90, "high"), (95, "high")):
        episodes = independent_threshold_episodes(
            points,
            threshold=threshold,
            direction=direction,
            cooldown_days=90,
        )
        returns = [point.future_return_365d_pct for point in episodes if point.future_return_365d_pct is not None]
        median_return = median(returns) if returns else None
        symbol = "<=" if direction == "low" else ">="
        print(
            f"Percentile {symbol} {threshold:<2}: episodes={len(episodes):>2} "
            f"valid365={len(returns):>2} median365={_fmt(median_return)}"
        )
        for point in episodes:
            print(
                f"  {point.as_of} BTC ${point.price:>10,.0f} pct={point.quantile_percentile:>5.1f} "
                f"fit={point.model_fit_date} 365d={_fmt(point.future_return_365d_pct):>10} "
                f"min={_fmt(point.future_max_drawdown_365d_pct):>10}"
            )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--minimum-history-days", type=int, default=730)
    parser.add_argument("--refit-days", type=int, default=90)
    parser.add_argument("--initializations", type=int, default=2)
    parser.add_argument("--maxiter", type=int, default=900)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    print("Fetching BTC-USD daily history...")
    market = MarketDataService(YFinanceProvider())
    records = market.get_historical_prices(
        get_asset("BTC"),
        BTC_HISTORY_START,
        date.today(),
    )
    print(f"Loaded {len(records):,} observations: {records[0].date} -> {records[-1].date}")
    print("Running expanding-window point-in-time quantile backtest...")
    print(
        f"minimum_history_days={args.minimum_history_days}, refit_days={args.refit_days}, "
        f"initializations={args.initializations}, maxiter={args.maxiter}"
    )
    print("Each model fit sees only history available on its fit date. Future returns are labels only.")
    print("This can take several minutes because the quantile regression is intentionally refit through history.")

    points = build_quantile_backtest(
        records,
        minimum_history_days=args.minimum_history_days,
        refit_days=args.refit_days,
        fit_initializations=args.initializations,
        fit_maxiter=args.maxiter,
    )
    if not points:
        raise RuntimeError("No quantile backtest points were produced")

    csv_path = REPORTS_DIR / "bitcoin_quantile_backtest.csv"
    percentile_path = REPORTS_DIR / "bitcoin_quantile_backtest_percentile.png"
    episodes_path = REPORTS_DIR / "bitcoin_quantile_backtest_episodes.png"
    bands_path = REPORTS_DIR / "bitcoin_quantile_backtest_band_returns.png"

    _write_csv(points, csv_path)
    _plot_percentile(points, percentile_path)
    _plot_episodes(points, episodes_path)
    _plot_band_returns(points, bands_path)

    _print_threshold_table(points)
    _print_episode_table(points)

    latest = points[-1]
    print()
    print("LATEST POINT-IN-TIME QUANTILE")
    print("-" * 92)
    print(
        f"{latest.as_of} BTC ${latest.price:,.2f} percentile={latest.quantile_percentile:.1f}/100 "
        f"model_fit_date={latest.model_fit_date}"
    )
    print()
    for path in (csv_path, percentile_path, episodes_path, bands_path):
        print(f"Saved: {path}")
    print("Research only: percentile history above is now point-in-time, but provider history still begins in 2014.")
    print("Done.")


if __name__ == "__main__":
    main()
