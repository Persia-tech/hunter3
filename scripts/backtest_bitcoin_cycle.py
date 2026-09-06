"""Run a no-look-ahead daily backtest of the Bitcoin cycle score."""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.models.asset import get_asset
from backend.app.providers.dca_yfinance_provider import YFinanceProvider
from backend.app.services.bitcoin_backtest import (
    build_bitcoin_backtest,
    nearest_backtest_point,
    summarize_score_bands,
)
from backend.app.services.dca_market_data import MarketDataService


BTC_HISTORY_START = date(2014, 9, 17)
CHECKPOINTS = (
    ("2017 cycle top", date(2017, 12, 17)),
    ("2018 cycle bottom", date(2018, 12, 15)),
    ("2020 crash", date(2020, 3, 13)),
    ("2021 spring top", date(2021, 4, 14)),
    ("2021 cycle top", date(2021, 11, 10)),
    ("2022 cycle bottom", date(2022, 11, 21)),
)


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
                "opportunity_score",
                "overheat_score",
                "future_return_180d_pct",
                "future_return_365d_pct",
                "future_return_730d_pct",
                "future_max_gain_365d_pct",
                "future_max_drawdown_365d_pct",
            )
        )
        for point in points:
            writer.writerow(
                (
                    point.as_of.isoformat(),
                    f"{point.price:.8f}",
                    point.opportunity_score,
                    point.overheat_score,
                    point.future_return_180d_pct,
                    point.future_return_365d_pct,
                    point.future_return_730d_pct,
                    point.future_max_gain_365d_pct,
                    point.future_max_drawdown_365d_pct,
                )
            )


def _print_band_table(title: str, summaries) -> None:  # type: ignore[no-untyped-def]
    print()
    print(title)
    print("-" * 116)
    print(
        f"{'Score':8} {'Days':>6} {'Med 180d':>10} {'Med 365d':>10} {'Med 730d':>10} "
        f"{'365d >0':>9} {'365d >=50':>11} {'DD <=-30':>10} {'Med max+':>10} {'Med max-':>10}"
    )
    for row in summaries:
        print(
            f"{row.band:8} {row.count:>6} {_fmt(row.median_return_180d_pct):>10} "
            f"{_fmt(row.median_return_365d_pct):>10} {_fmt(row.median_return_730d_pct):>10} "
            f"{_fmt(row.positive_365d_rate_pct):>9} {_fmt(row.gain_50pct_365d_rate_pct):>11} "
            f"{_fmt(row.drawdown_30pct_365d_rate_pct):>10} {_fmt(row.median_max_gain_365d_pct):>10} "
            f"{_fmt(row.median_max_drawdown_365d_pct):>10}"
        )


def main() -> None:
    print("Fetching full available BTC-USD daily history...")
    market = MarketDataService(YFinanceProvider())
    records = market.get_historical_prices(
        get_asset("BTC"),
        BTC_HISTORY_START,
        date.today(),
    )

    print(f"Loaded {len(records):,} daily observations: {records[0].date} -> {records[-1].date}")
    print("Running point-in-time DAILY backtest (no future data in indicators)...")
    points = build_bitcoin_backtest(records, step_days=1)

    destination = ROOT / "reports" / "bitcoin_cycle_backtest.csv"
    _write_csv(points, destination)

    print()
    print("=" * 100)
    print("BITCOIN CYCLE HISTORICAL CHECKPOINTS")
    print("=" * 100)
    print(
        f"{'Checkpoint':24} {'Date':12} {'BTC':>12} {'Opp':>5} {'Heat':>5} "
        f"{'180d':>10} {'365d':>10} {'365d max':>10} {'365d min':>10}"
    )

    for label, target in CHECKPOINTS:
        point = nearest_backtest_point(points, target)
        if point is None:
            continue
        print(
            f"{label:24} {point.as_of.isoformat():12} ${point.price:>10,.0f} "
            f"{point.opportunity_score:>5} {point.overheat_score:>5} "
            f"{_fmt(point.future_return_180d_pct):>10} "
            f"{_fmt(point.future_return_365d_pct):>10} "
            f"{_fmt(point.future_max_gain_365d_pct):>10} "
            f"{_fmt(point.future_max_drawdown_365d_pct):>10}"
        )

    ath_record = max(records, key=lambda record: record.price)
    ath_point = nearest_backtest_point(points, ath_record.date)
    if ath_point is not None:
        print(
            f"{'Record ATH in dataset':24} {ath_point.as_of.isoformat():12} "
            f"${ath_point.price:>10,.0f} {ath_point.opportunity_score:>5} "
            f"{ath_point.overheat_score:>5} {_fmt(ath_point.future_return_180d_pct):>10} "
            f"{_fmt(ath_point.future_return_365d_pct):>10} "
            f"{_fmt(ath_point.future_max_gain_365d_pct):>10} "
            f"{_fmt(ath_point.future_max_drawdown_365d_pct):>10}"
        )

    print()
    print("YEARLY SCORE EXTREMES")
    print("-" * 100)
    by_year = defaultdict(list)
    for point in points:
        by_year[point.as_of.year].append(point)

    print(f"{'Year':6} {'Max opportunity':30} {'Max overheat':30}")
    for year in sorted(by_year):
        year_points = by_year[year]
        best_opp = max(year_points, key=lambda point: point.opportunity_score)
        best_heat = max(year_points, key=lambda point: point.overheat_score)
        print(
            f"{year:<6} "
            f"{best_opp.opportunity_score:>3}/100 on {best_opp.as_of} ${best_opp.price:>9,.0f}   "
            f"{best_heat.overheat_score:>3}/100 on {best_heat.as_of} ${best_heat.price:>9,.0f}"
        )

    _print_band_table(
        "OPPORTUNITY SCORE -> REALIZED FUTURE OUTCOMES",
        summarize_score_bands(points, score_name="opportunity_score"),
    )
    _print_band_table(
        "OVERHEAT SCORE -> REALIZED FUTURE OUTCOMES",
        summarize_score_bands(points, score_name="overheat_score"),
    )

    latest = points[-1]
    print()
    print("LATEST DAILY SCORE")
    print("-" * 100)
    print(
        f"{latest.as_of}  BTC ${latest.price:,.2f}  "
        f"Opportunity {latest.opportunity_score}/100  Overheat {latest.overheat_score}/100"
    )
    print()
    print(f"Full daily results saved to: {destination}")
    print("Future-return columns are validation labels only; they are never used to calculate the scores.")
    print("Band statistics use overlapping daily observations, so treat them as descriptive evidence, not independent trials.")


if __name__ == "__main__":
    main()
