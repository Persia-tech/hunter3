"""Run a no-look-ahead daily backtest of the Bitcoin cycle score."""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from statistics import median

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
ERAS = (
    ("2015-2018", date(2015, 1, 1), date(2018, 12, 31)),
    ("2019-2022", date(2019, 1, 1), date(2022, 12, 31)),
    ("2023-2026", date(2023, 1, 1), date(2026, 12, 31)),
)


def _fmt(value: float | None) -> str:
    return "N/A" if value is None else f"{value:,.1f}%"


def _rate(values: list[bool]) -> float | None:
    if not values:
        return None
    return 100.0 * sum(values) / len(values)


def _median(values: list[float | None]) -> float | None:
    clean = [value for value in values if value is not None]
    return median(clean) if clean else None


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


def _signal_episodes(points, score_name: str, threshold: int, cooldown_days: int = 90):  # type: ignore[no-untyped-def]
    """Return distinct upward threshold crossings, suppressing clustered re-entries."""
    episodes = []
    was_above = False
    last_selected = None
    for point in points:
        above = getattr(point, score_name) >= threshold
        crossed = above and not was_above
        if crossed:
            far_enough = last_selected is None or (point.as_of - last_selected).days >= cooldown_days
            if far_enough:
                episodes.append(point)
                last_selected = point.as_of
        was_above = above
    return episodes


def _print_episode_table(title: str, episodes, score_name: str) -> None:  # type: ignore[no-untyped-def]
    print()
    print(title)
    print("-" * 104)
    print(f"{'Date':12} {'BTC':>12} {'Score':>7} {'180d':>10} {'365d':>10} {'365d max':>10} {'365d min':>10}")
    for point in episodes:
        print(
            f"{point.as_of.isoformat():12} ${point.price:>10,.0f} {getattr(point, score_name):>7} "
            f"{_fmt(point.future_return_180d_pct):>10} {_fmt(point.future_return_365d_pct):>10} "
            f"{_fmt(point.future_max_gain_365d_pct):>10} {_fmt(point.future_max_drawdown_365d_pct):>10}"
        )

    valid_365 = [point for point in episodes if point.future_return_365d_pct is not None]
    print("-" * 104)
    print(
        f"Episodes={len(episodes)}  Valid365={len(valid_365)}  "
        f"Median365={_fmt(_median([point.future_return_365d_pct for point in valid_365]))}  "
        f"Positive365={_fmt(_rate([point.future_return_365d_pct > 0 for point in valid_365]))}  "
        f"DD<=-30={_fmt(_rate([point.future_max_drawdown_365d_pct is not None and point.future_max_drawdown_365d_pct <= -30 for point in valid_365]))}"
    )


def _print_era_stability(points) -> None:  # type: ignore[no-untyped-def]
    print()
    print("ERA STABILITY OF EXTREME SIGNALS")
    print("-" * 112)
    print(
        f"{'Era':12} {'Opp>=60':>8} {'Opp med365':>12} {'Heat>=60':>9} {'Heat med365':>13} "
        f"{'Opp>=80':>8} {'Heat>=80':>9}"
    )
    for label, start, end in ERAS:
        era_points = [point for point in points if start <= point.as_of <= end]
        opp60 = _signal_episodes(era_points, "opportunity_score", 60)
        heat60 = _signal_episodes(era_points, "overheat_score", 60)
        opp80 = _signal_episodes(era_points, "opportunity_score", 80)
        heat80 = _signal_episodes(era_points, "overheat_score", 80)
        print(
            f"{label:12} {len(opp60):>8} "
            f"{_fmt(_median([point.future_return_365d_pct for point in opp60])):>12} "
            f"{len(heat60):>9} {_fmt(_median([point.future_return_365d_pct for point in heat60])):>13} "
            f"{len(opp80):>8} {len(heat80):>9}"
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
            f"{_fmt(point.future_return_180d_pct):>10} {_fmt(point.future_return_365d_pct):>10} "
            f"{_fmt(point.future_max_gain_365d_pct):>10} {_fmt(point.future_max_drawdown_365d_pct):>10}"
        )

    ath_record = max(records, key=lambda record: record.price)
    ath_point = nearest_backtest_point(points, ath_record.date)
    if ath_point is not None:
        print(
            f"{'Record ATH in dataset':24} {ath_point.as_of.isoformat():12} "
            f"${ath_point.price:>10,.0f} {ath_point.opportunity_score:>5} "
            f"{ath_point.overheat_score:>5} {_fmt(ath_point.future_return_180d_pct):>10} "
            f"{_fmt(ath_point.future_return_365d_pct):>10} {_fmt(ath_point.future_max_gain_365d_pct):>10} "
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
            f"{year:<6} {best_opp.opportunity_score:>3}/100 on {best_opp.as_of} ${best_opp.price:>9,.0f}   "
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

    valid_all = [point for point in points if point.future_return_365d_pct is not None]
    print()
    print("ALL-DAYS BASELINE")
    print("-" * 100)
    print(
        f"Valid days={len(valid_all)}  Median365={_fmt(_median([point.future_return_365d_pct for point in valid_all]))}  "
        f"Positive365={_fmt(_rate([point.future_return_365d_pct > 0 for point in valid_all]))}  "
        f"Gain>=50={_fmt(_rate([point.future_return_365d_pct >= 50 for point in valid_all]))}  "
        f"DD<=-30={_fmt(_rate([point.future_max_drawdown_365d_pct is not None and point.future_max_drawdown_365d_pct <= -30 for point in valid_all]))}"
    )

    for score_name, label in (("opportunity_score", "OPPORTUNITY"), ("overheat_score", "OVERHEAT")):
        for threshold in (60, 80):
            episodes = _signal_episodes(points, score_name, threshold)
            _print_episode_table(
                f"INDEPENDENT {label} >= {threshold} EPISODES (upward crossings, 90-day cooldown)",
                episodes,
                score_name,
            )

    _print_era_stability(points)

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
    print("Episode statistics count threshold crossings rather than every day above a threshold.")


if __name__ == "__main__":
    main()
