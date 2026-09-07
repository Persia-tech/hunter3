"""Research-only lead-time analysis between early BTC valuation signals and Opportunity confirmation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from statistics import median

from backend.app.services.bitcoin_confluence_research import (
    ConfluencePoint,
    ConfluenceSpec,
    independent_confluence_episodes,
)


@dataclass(frozen=True, slots=True)
class LeadTimeEpisode:
    signal: str
    early_date: date
    early_price: float
    confirmation_date: date | None
    confirmation_price: float | None
    lead_days: int | None
    max_drawdown_to_confirmation_pct: float | None


@dataclass(frozen=True, slots=True)
class LeadTimeSummary:
    signal: str
    early_episode_count: int
    confirmed_count: int
    confirmation_rate_pct: float | None
    median_lead_days: float | None
    median_drawdown_to_confirmation_pct: float | None
    worst_drawdown_to_confirmation_pct: float | None


OPPORTUNITY_SPEC = ConfluenceSpec("Opportunity >= 60", require_opportunity=True)
EARLY_SPECS = (
    ConfluenceSpec("Quantile <= 10", require_quantile=True),
    ConfluenceSpec("MVRV pct <= 20", require_mvrv=True),
    ConfluenceSpec("Quantile <= 10 + MVRV pct <= 20", require_quantile=True, require_mvrv=True),
)


def _drawdown_between(
    ordered: list[ConfluencePoint],
    *,
    start_date: date,
    end_date: date,
    start_price: float,
) -> float | None:
    prices = [point.price for point in ordered if start_date <= point.date <= end_date]
    if not prices or start_price <= 0:
        return None
    return (min(prices) / start_price - 1.0) * 100.0


def evaluate_lead_time_episodes(
    points: list[ConfluencePoint],
    *,
    max_confirmation_days: int = 365,
    cooldown_days: int = 90,
) -> list[LeadTimeEpisode]:
    """Measure how long early valuation episodes lead Opportunity >=60 confirmation.

    Early signals and Opportunity confirmation use fixed, predeclared thresholds.
    Each early episode is matched to the first independent Opportunity >=60 entry
    on or after the early date and no more than ``max_confirmation_days`` later.
    Drawdown is measured from the early-signal price to the minimum daily price
    through the confirmation date. Unconfirmed episodes remain explicit and do
    not receive an invented lead time or drawdown-to-confirmation value.
    """
    if max_confirmation_days < 1:
        raise ValueError("max_confirmation_days must be positive")
    if cooldown_days < 0:
        raise ValueError("cooldown_days must be non-negative")

    ordered = sorted(points, key=lambda item: item.date)
    opportunity_episodes = independent_confluence_episodes(
        ordered,
        OPPORTUNITY_SPEC,
        cooldown_days=cooldown_days,
    )

    rows: list[LeadTimeEpisode] = []
    for spec in EARLY_SPECS:
        early_episodes = independent_confluence_episodes(
            ordered,
            spec,
            cooldown_days=cooldown_days,
        )
        for early in early_episodes:
            deadline = early.date + timedelta(days=max_confirmation_days)
            confirmation = next(
                (
                    episode
                    for episode in opportunity_episodes
                    if early.date <= episode.date <= deadline
                ),
                None,
            )
            if confirmation is None:
                rows.append(
                    LeadTimeEpisode(
                        signal=spec.label,
                        early_date=early.date,
                        early_price=early.price,
                        confirmation_date=None,
                        confirmation_price=None,
                        lead_days=None,
                        max_drawdown_to_confirmation_pct=None,
                    )
                )
                continue

            rows.append(
                LeadTimeEpisode(
                    signal=spec.label,
                    early_date=early.date,
                    early_price=early.price,
                    confirmation_date=confirmation.date,
                    confirmation_price=confirmation.price,
                    lead_days=(confirmation.date - early.date).days,
                    max_drawdown_to_confirmation_pct=_drawdown_between(
                        ordered,
                        start_date=early.date,
                        end_date=confirmation.date,
                        start_price=early.price,
                    ),
                )
            )
    return rows


def summarize_lead_time(rows: list[LeadTimeEpisode]) -> list[LeadTimeSummary]:
    summaries: list[LeadTimeSummary] = []
    for signal in (spec.label for spec in EARLY_SPECS):
        selected = [row for row in rows if row.signal == signal]
        confirmed = [row for row in selected if row.confirmation_date is not None]
        leads = [float(row.lead_days) for row in confirmed if row.lead_days is not None]
        drawdowns = [
            float(row.max_drawdown_to_confirmation_pct)
            for row in confirmed
            if row.max_drawdown_to_confirmation_pct is not None
        ]
        summaries.append(
            LeadTimeSummary(
                signal=signal,
                early_episode_count=len(selected),
                confirmed_count=len(confirmed),
                confirmation_rate_pct=(
                    100.0 * len(confirmed) / len(selected) if selected else None
                ),
                median_lead_days=median(leads) if leads else None,
                median_drawdown_to_confirmation_pct=median(drawdowns) if drawdowns else None,
                worst_drawdown_to_confirmation_pct=min(drawdowns) if drawdowns else None,
            )
        )
    return summaries
