"""Fit and visualize the research-only Bitcoin quantile model."""

from __future__ import annotations

import csv
import sys
from datetime import date
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.models.asset import get_asset
from backend.app.providers.dca_yfinance_provider import YFinanceProvider
from backend.app.services.bitcoin_quantile import (
    DEFAULT_QUANTILES,
    fit_bitcoin_quantile_model,
    predict_quantile_bands,
    snapshot_bitcoin_quantile,
)
from backend.app.services.dca_market_data import MarketDataService


BTC_HISTORY_START = date(2014, 9, 17)
REPORTS_DIR = ROOT / "reports"


def _plot_quantile_bands(records, model, output_path: Path) -> None:  # type: ignore[no-untyped-def]
    dates = [item.date for item in records]
    prices = [float(item.price) for item in records]
    band_series = {quantile: [] for quantile in DEFAULT_QUANTILES}

    for day in dates:
        for quantile, predicted in predict_quantile_bands(model, day):
            band_series[quantile].append(predicted)

    plt.figure(figsize=(14, 8))
    plt.plot(dates, prices, linewidth=1.5, label="BTC price")
    for quantile in DEFAULT_QUANTILES:
        plt.plot(
            dates,
            band_series[quantile],
            linewidth=1.0,
            label=f"Q{int(round(quantile * 100)):02d}",
        )

    plt.yscale("log")
    plt.title("Bitcoin Plan C v2-Style Quantile Research Model")
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


def _build_percentile_rows(records, model):  # type: ignore[no-untyped-def]
    rows = []
    for item in records:
        snapshot = snapshot_bitcoin_quantile(
            model,
            day=item.date,
            price=float(item.price),
        )
        rows.append((item.date, float(item.price), snapshot.percentile))
    return rows


def _plot_percentile(rows, output_path: Path) -> None:  # type: ignore[no-untyped-def]
    dates = [row[0] for row in rows]
    percentiles = [row[2] for row in rows]

    plt.figure(figsize=(14, 6))
    plt.plot(dates, percentiles, linewidth=1.4, label="Quantile percentile")
    plt.axhline(10, linewidth=1, linestyle="--", label="10th percentile")
    plt.axhline(25, linewidth=1, linestyle=":", label="25th percentile")
    plt.axhline(75, linewidth=1, linestyle=":", label="75th percentile")
    plt.axhline(95, linewidth=1, linestyle="--", label="95th percentile")
    plt.ylim(0, 100)
    plt.title("Bitcoin Quantile Percentile Over Time (Descriptive Full-Sample Fit)")
    plt.xlabel("Date")
    plt.ylabel("Model percentile")
    plt.grid(True, alpha=0.3)
    plt.legend(ncol=2)
    ax = plt.gca()
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close()


def _write_csv(rows, output_path: Path) -> None:  # type: ignore[no-untyped-def]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("date", "price", "quantile_percentile"))
        for day, price, percentile in rows:
            writer.writerow((day.isoformat(), f"{price:.8f}", f"{percentile:.6f}"))


def main() -> None:
    print("Fetching BTC-USD daily history...")
    market = MarketDataService(YFinanceProvider())
    records = market.get_historical_prices(
        get_asset("BTC"),
        BTC_HISTORY_START,
        date.today(),
    )
    print(f"Loaded {len(records):,} observations: {records[0].date} -> {records[-1].date}")
    print("Fitting Plan C v2-style stretched-exponential quantile research model...")
    print("NOTE: this is an independent functional-form reproduction, not the official Plan C v2 model.")
    print("NOTE: current provider history begins in 2014, so this is not yet a full 2010-present reproduction.")

    model = fit_bitcoin_quantile_model(records)
    latest = records[-1]
    snapshot = snapshot_bitcoin_quantile(
        model,
        day=latest.date,
        price=float(latest.price),
    )

    print()
    print(f"Latest: {snapshot.as_of} BTC ${snapshot.price:,.2f}")
    print(f"Quantile percentile: {snapshot.percentile:.1f}/100")
    print("Latest fitted bands:")
    for quantile, price in snapshot.bands:
        print(f"  Q{quantile * 100:>5.1f}: ${price:,.2f}")

    rows = _build_percentile_rows(records, model)
    chart_path = REPORTS_DIR / "bitcoin_quantile_model.png"
    percentile_path = REPORTS_DIR / "bitcoin_quantile_percentile.png"
    csv_path = REPORTS_DIR / "bitcoin_quantile_research.csv"

    _plot_quantile_bands(records, model, chart_path)
    _plot_percentile(rows, percentile_path)
    _write_csv(rows, csv_path)

    print()
    print(f"Saved: {chart_path}")
    print(f"Saved: {percentile_path}")
    print(f"Saved: {csv_path}")
    print("Research only: do not treat the full-sample historical percentile series as a no-look-ahead backtest.")
    print("Done.")


if __name__ == "__main__":
    main()
