"""Fetch, validate, and visualize free Bitcoin on-chain valuation metrics."""

from __future__ import annotations

import csv
import sys
from datetime import date
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.providers.coinmetrics_community_provider import CoinMetricsCommunityProvider
from backend.app.services.bitcoin_onchain_research import (
    build_onchain_research_rows,
    summarize_metric_quantile_bands,
)


START_DATE = date(2010, 7, 18)
REPORTS_DIR = ROOT / "reports"


def _fmt(value: float | None) -> str:
    return "N/A" if value is None else f"{value:,.2f}"


def _save(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(path, dpi=160, bbox_inches="tight")
    plt.close()


def _plot_metric(rows, *, key: str, title: str, ylabel: str, output: Path, log_y: bool = False) -> None:  # type: ignore[no-untyped-def]
    selected = [row for row in rows if getattr(row, key) is not None]
    dates = [row.date for row in selected]
    values = [getattr(row, key) for row in selected]

    plt.figure(figsize=(14, 6))
    plt.plot(dates, values, linewidth=1.3)
    if log_y:
        plt.yscale("log")
    plt.title(title)
    plt.xlabel("Date")
    plt.ylabel(ylabel)
    plt.grid(True, alpha=0.3)
    ax = plt.gca()
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    _save(output)


def _plot_band_returns(summaries_by_metric, output: Path) -> None:  # type: ignore[no-untyped-def]
    labels = ["Q1 low", "Q2", "Q3", "Q4", "Q5 high"]
    metrics = ("mvrv", "mvrv_z", "nupl")
    x = list(range(len(labels)))
    width = 0.25

    plt.figure(figsize=(11, 6))
    for idx, metric in enumerate(metrics):
        summaries = summaries_by_metric[metric]
        values = [
            0.0 if item.median_future_return_365d_pct is None else item.median_future_return_365d_pct
            for item in summaries
        ]
        offsets = [value + (idx - 1) * width for value in x]
        plt.bar(offsets, values, width=width, label=metric.upper())

    plt.axhline(0, linewidth=1, linestyle="--")
    plt.xticks(x, labels)
    plt.title("Bitcoin On-Chain Metric Quintiles vs Median Future 365-Day Return")
    plt.xlabel("Empirical metric quintile (descriptive full-sample bands)")
    plt.ylabel("Median future 365-day return (%)")
    plt.grid(True, axis="y", alpha=0.3)
    plt.legend()
    _save(output)


def _write_csv(rows, output: Path) -> None:  # type: ignore[no-untyped-def]
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            (
                "date",
                "price_usd",
                "mvrv",
                "mvrv_z",
                "realized_cap_usd",
                "nupl",
                "future_return_180d_pct",
                "future_return_365d_pct",
                "future_max_drawdown_365d_pct",
            )
        )
        for row in rows:
            writer.writerow(
                (
                    row.date.isoformat(),
                    row.price_usd,
                    row.mvrv,
                    row.mvrv_z,
                    row.realized_cap_usd,
                    row.nupl,
                    row.future_return_180d_pct,
                    row.future_return_365d_pct,
                    row.future_max_drawdown_365d_pct,
                )
            )


def _latest_usable_row(rows):  # type: ignore[no-untyped-def]
    for row in reversed(rows):
        if any(
            value is not None
            for value in (row.price_usd, row.mvrv, row.mvrv_z, row.realized_cap_usd, row.nupl)
        ):
            return row
    raise RuntimeError("No usable on-chain metric values were found in the downloaded history")


def main() -> None:
    print("Fetching free Bitcoin on-chain metrics from Coin Metrics...")
    print("Primary source: Community API; automatic fallback: Coin Metrics public GitHub BTC archive.")
    print("Requested/derived research metrics: PriceUSD, MVRV, MVRV Z-Score, Realized Cap, NUPL")
    provider = CoinMetricsCommunityProvider()
    records = provider.get_bitcoin_daily_metrics(start_date=START_DATE, end_date=date.today())
    if not records:
        raise RuntimeError("Coin Metrics returned no Bitcoin on-chain records")

    print(f"Loaded {len(records):,} daily rows: {records[0].date} -> {records[-1].date}")
    rows = build_onchain_research_rows(records)

    latest = _latest_usable_row(rows)
    stale_days = (date.today() - latest.date).days
    print()
    print("LATEST USABLE RAW / RECONSTRUCTED ON-CHAIN METRICS")
    print("-" * 72)
    print(f"Date:          {latest.date}")
    print(f"BTC price:     ${_fmt(latest.price_usd)}")
    print(f"MVRV:          {_fmt(latest.mvrv)}")
    print(f"MVRV Z-score:  {_fmt(latest.mvrv_z)}")
    print(f"Realized cap:  ${_fmt(latest.realized_cap_usd)}")
    print(f"NUPL:          {_fmt(latest.nupl)}")
    if stale_days > 7:
        print(f"WARNING: latest usable on-chain row is {stale_days} days old; do not use it as a current signal.")

    summaries_by_metric = {}
    for metric in ("mvrv", "mvrv_z", "nupl"):
        summaries = summarize_metric_quantile_bands(rows, metric=metric)
        summaries_by_metric[metric] = summaries
        print()
        print(f"{metric.upper()} DESCRIPTIVE QUINTILE OUTCOMES")
        print("-" * 72)
        print(f"{'Band':12} {'Days':>7} {'Med365':>12} {'365d >0':>10} {'DD<=-30':>10}")
        for item in summaries:
            med = "N/A" if item.median_future_return_365d_pct is None else f"{item.median_future_return_365d_pct:,.1f}%"
            pos = "N/A" if item.positive_365d_rate_pct is None else f"{item.positive_365d_rate_pct:,.1f}%"
            dd = "N/A" if item.drawdown_30pct_rate_pct is None else f"{item.drawdown_30pct_rate_pct:,.1f}%"
            print(f"{item.band:12} {item.count:>7} {med:>12} {pos:>10} {dd:>10}")

    csv_path = REPORTS_DIR / "bitcoin_onchain_research.csv"
    mvrv_path = REPORTS_DIR / "bitcoin_mvrv.png"
    mvrvz_path = REPORTS_DIR / "bitcoin_mvrv_z.png"
    nupl_path = REPORTS_DIR / "bitcoin_nupl.png"
    realized_path = REPORTS_DIR / "bitcoin_realized_cap.png"
    band_path = REPORTS_DIR / "bitcoin_onchain_quintile_returns.png"

    _write_csv(rows, csv_path)
    _plot_metric(rows, key="mvrv", title="Bitcoin MVRV", ylabel="MVRV", output=mvrv_path)
    _plot_metric(rows, key="mvrv_z", title="Bitcoin MVRV Z-Score", ylabel="MVRV Z-score", output=mvrvz_path)
    _plot_metric(rows, key="nupl", title="Bitcoin NUPL", ylabel="NUPL", output=nupl_path)
    _plot_metric(
        rows,
        key="realized_cap_usd",
        title="Bitcoin Realized Market Cap",
        ylabel="Realized cap (USD, log scale)",
        output=realized_path,
        log_y=True,
    )
    _plot_band_returns(summaries_by_metric, band_path)

    print()
    for path in (csv_path, mvrv_path, mvrvz_path, nupl_path, realized_path, band_path):
        print(f"Saved: {path}")
    print("Research only: raw metrics remain separate; no composite weights were changed.")
    print("If the GitHub archive fallback was used, MVRV is archived directly; Realized Cap and NUPL are algebraically reconstructed; MVRV Z uses an expanding no-look-ahead market-cap standard deviation.")
    print("MVRV and reconstructed NUPL are monotonic transforms of the same underlying valuation ratio, so do not give them independent composite weights without additional justification.")
    print("Quintile summaries use full-sample cutoffs and are descriptive, not no-look-ahead signals.")
    print("Done.")


if __name__ == "__main__":
    main()
