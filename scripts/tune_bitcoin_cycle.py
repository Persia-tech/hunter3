"""Research Bitcoin cycle weights with embargoed walk-forward validation.

This is a research script only.  It never changes production model weights.
Run from the repository root with:

    python scripts/tune_bitcoin_cycle.py
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.models.asset import get_asset
from backend.app.providers.dca_yfinance_provider import YFinanceProvider
from backend.app.services.bitcoin_backtest import build_bitcoin_backtest
from backend.app.services.bitcoin_cycle import calculate_bitcoin_cycle
from backend.app.services.bitcoin_model_research import (
    Candidate,
    OPPORTUNITY_BASE_WEIGHTS,
    OVERHEAT_BASE_WEIGHTS,
    ResearchRow,
    candidate_scores,
    evaluate_candidate,
    find_best_candidate,
    independent_episode_metrics,
    research_row_from_results,
)
from backend.app.services.dca_market_data import MarketDataService

BTC_HISTORY_START = date(2014, 9, 17)

# A full 365-day embargo separates each training period from its unseen test.
FOLDS = (
    ("Fold A", date(2019, 12, 31), date(2021, 1, 1), date(2022, 12, 31)),
    ("Fold B", date(2022, 12, 31), date(2024, 1, 1), None),
)


def _fmt(value: float | None) -> str:
    return "N/A" if value is None else f"{value:,.1f}%"


def _candidate_text(candidate: Candidate) -> str:
    active = [f"{name}={value:g}x" for name, value in candidate.multipliers.items() if value > 0]
    return f"threshold={candidate.threshold}; " + ", ".join(active)


def _baseline_candidate(kind: str) -> Candidate:
    names = OPPORTUNITY_BASE_WEIGHTS if kind == "opportunity" else OVERHEAT_BASE_WEIGHTS
    return Candidate({name: 1.0 for name in names}, 60)


def _build_rows(records) -> list[ResearchRow]:  # type: ignore[no-untyped-def]
    points = build_bitcoin_backtest(records, step_days=1)
    point_by_date = {point.as_of: point for point in points}
    ordered = sorted(records, key=lambda item: item.date)

    rows: list[ResearchRow] = []
    for index in range(399, len(ordered)):
        cycle = calculate_bitcoin_cycle(ordered[: index + 1])
        backtest = point_by_date.get(cycle.as_of)
        if backtest is None:
            continue
        rows.append(research_row_from_results(cycle, backtest))
    return rows


def _print_test_result(label: str, rows: list[ResearchRow], kind: str, candidate: Candidate, start: date, end: date) -> float | None:
    scores = candidate_scores(rows, kind, candidate)  # type: ignore[arg-type]
    daily = evaluate_candidate(
        rows,
        scores,
        candidate,
        kind,  # type: ignore[arg-type]
        start=start,
        end=end,
        minimum_days=10,
    )
    episodes = independent_episode_metrics(
        rows,
        scores,
        candidate.threshold,
        start=start,
        end=end,
        cooldown_days=90,
    )
    print(
        f"{label:12} days={daily.count:4} med365={_fmt(daily.median_return_365d_pct):>9} "
        f"positive={_fmt(daily.positive_365d_rate_pct):>8} dd<=-30={_fmt(daily.drawdown_30pct_365d_rate_pct):>8} "
        f"episodes={episodes.valid_365d}/{episodes.count} ep_med365={_fmt(episodes.median_return_365d_pct):>9}"
    )
    return daily.objective


def _ablation_candidates(kind: str) -> list[tuple[str, Candidate]]:
    weights = OPPORTUNITY_BASE_WEIGHTS if kind == "opportunity" else OVERHEAT_BASE_WEIGHTS
    baseline = {name: 1.0 for name in weights}
    result = [("baseline", Candidate(dict(baseline), 60))]
    for omitted in weights:
        multipliers = dict(baseline)
        multipliers[omitted] = 0.0
        result.append((f"without {omitted}", Candidate(multipliers, 60)))
    return result


def main() -> None:
    print("Fetching full BTC daily history...")
    market = MarketDataService(YFinanceProvider())
    records = market.get_historical_prices(get_asset("BTC"), BTC_HISTORY_START, date.today())
    print(f"Loaded {len(records):,} observations: {records[0].date} -> {records[-1].date}")
    print("Building point-in-time research rows. No future values are used as model inputs...")
    rows = _build_rows(records)
    valid_dates = [row.as_of for row in rows if row.future_return_365d_pct is not None]
    latest_valid = max(valid_dates)
    print(f"Research rows: {len(rows):,}; latest date with complete 365d label: {latest_valid}")

    selected_by_fold: dict[tuple[str, str], Candidate] = {}

    for kind in ("opportunity", "overheat"):
        print()
        print("=" * 120)
        print(f"{kind.upper()} WALK-FORWARD TUNING")
        print("=" * 120)

        for fold_name, train_end, test_start, configured_test_end in FOLDS:
            test_end = min(configured_test_end or latest_valid, latest_valid)
            print()
            print(f"{fold_name}: train through {train_end}; 365d embargo; unseen test {test_start} -> {test_end}")
            print("Searching candidate factor weights and thresholds...")
            best, train_metrics = find_best_candidate(rows, kind, train_end=train_end, minimum_days=30)  # type: ignore[arg-type]
            selected_by_fold[(kind, fold_name)] = best
            print(f"Selected: {_candidate_text(best)}")
            print(
                f"Training objective={train_metrics.objective:.1f}  days={train_metrics.count}  "
                f"med365={_fmt(train_metrics.median_return_365d_pct)}  "
                f"positive={_fmt(train_metrics.positive_365d_rate_pct)}  "
                f"dd<=-30={_fmt(train_metrics.drawdown_30pct_365d_rate_pct)}"
            )
            _print_test_result("TUNED", rows, kind, best, test_start, test_end)
            _print_test_result("BASELINE", rows, kind, _baseline_candidate(kind), test_start, test_end)

    print()
    print("=" * 120)
    print("FEATURE ABLATION ON UNSEEN TEST FOLDS")
    print("Higher objective is better for that model kind. This section tests removals; it does not select production weights.")
    print("=" * 120)

    for kind in ("opportunity", "overheat"):
        print()
        print(kind.upper())
        print(f"{'Variant':28} {'Mean unseen objective':>22}")
        for label, candidate in _ablation_candidates(kind):
            objectives: list[float] = []
            scores = candidate_scores(rows, kind, candidate)  # type: ignore[arg-type]
            for _, _, test_start, configured_test_end in FOLDS:
                test_end = min(configured_test_end or latest_valid, latest_valid)
                metrics = evaluate_candidate(
                    rows,
                    scores,
                    candidate,
                    kind,  # type: ignore[arg-type]
                    start=test_start,
                    end=test_end,
                    minimum_days=10,
                )
                if metrics.objective is not None:
                    objectives.append(metrics.objective)
            value = mean(objectives) if objectives else None
            text = "N/A" if value is None else f"{value:,.1f}"
            print(f"{label:28} {text:>22}")

    print()
    print("Research only: no production score weights or API behavior were changed.")
    print("Use unseen-fold performance and ablation stability before accepting any tuned model.")


if __name__ == "__main__":
    main()
