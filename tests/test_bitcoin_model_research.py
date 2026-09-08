from datetime import date, timedelta
from decimal import Decimal
import math

from backend.app.models.price import PriceRecord
from backend.app.services.bitcoin_cycle import calculate_bitcoin_cycle
from backend.app.services.bitcoin_model_research import (
    Candidate,
    OPPORTUNITY_BASE_WEIGHTS,
    OVERHEAT_BASE_WEIGHTS,
    ResearchRow,
    candidate_scores,
    factors_from_cycle,
    independent_episode_metrics,
    score_factors,
)


def _records(days: int = 2200) -> list[PriceRecord]:
    start = date(2020, 1, 1)
    rows: list[PriceRecord] = []
    for index in range(days):
        trend = 9000 + index * 18
        wave = 6000 * math.sin(index / 180)
        price = max(1000, trend + wave)
        rows.append(
            PriceRecord(
                date=start + timedelta(days=index),
                price=Decimal(str(round(price, 2))),
            )
        )
    return rows


def test_research_factor_scoring_reproduces_production_baseline() -> None:
    result = calculate_bitcoin_cycle(_records())
    opportunity, overheat = factors_from_cycle(result)

    opp_score = score_factors(
        opportunity,
        OPPORTUNITY_BASE_WEIGHTS,
        {name: 1.0 for name in OPPORTUNITY_BASE_WEIGHTS},
    )
    heat_score = score_factors(
        overheat,
        OVERHEAT_BASE_WEIGHTS,
        {name: 1.0 for name in OVERHEAT_BASE_WEIGHTS},
    )

    assert opp_score == result.opportunity_score
    assert heat_score == result.overheat_score


def test_candidate_scores_remain_bounded_after_feature_removal() -> None:
    factors = {name: 1.0 for name in OPPORTUNITY_BASE_WEIGHTS}
    rows = [
        ResearchRow(
            as_of=date(2020, 1, 1),
            price=100.0,
            opportunity_factors=factors,
            overheat_factors={name: 0.0 for name in OVERHEAT_BASE_WEIGHTS},
            future_return_365d_pct=50.0,
            future_max_drawdown_365d_pct=-10.0,
        )
    ]
    multipliers = {name: 1.0 for name in OPPORTUNITY_BASE_WEIGHTS}
    multipliers["weekly_rsi"] = 0.0
    scores = candidate_scores(rows, "opportunity", Candidate(multipliers, 60))
    assert scores == [100]


def test_independent_episode_metrics_counts_crossings_not_consecutive_days() -> None:
    start = date(2020, 1, 1)
    rows = [
        ResearchRow(
            as_of=start + timedelta(days=index),
            price=100.0,
            opportunity_factors={},
            overheat_factors={},
            future_return_365d_pct=50.0,
            future_max_drawdown_365d_pct=-10.0,
        )
        for index in range(8)
    ]
    scores = [50, 61, 70, 65, 40, 62, 63, 30]
    metrics = independent_episode_metrics(rows, scores, 60, cooldown_days=1)
    assert metrics.count == 2
    assert metrics.valid_365d == 2
    assert metrics.positive_365d_rate_pct == 100.0
