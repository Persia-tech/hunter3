"""Research-only timing analysis for independent Bitcoin top-risk episodes.

For each fixed top-risk condition, this module asks how much upside remained
after the signal, when the highest subsequent price occurred, how severe the
following peak-to-trough drawdown became, and how quickly 20/30/40% running-peak
drawdowns were first observed. Thresholds are predeclared and unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from statistics import median

from backend.app.services.bitcoin_top_confluence_research import (
    DEFAULT_TOP_SPECS,
    TopConfluencePoint,
    TopSpec,
    independent_top_episodes,
)


@dataclass(frozen=True, slots=True)
class TopTimingEpisode:
    signal: str
    signal_date: date
    signal_price: float
    peak_date_365d: date | None
    peak_price_365d: float | None
    days_to_peak_365d: int | None
    additional_upside_365d_pct: float | None
    max_peak_to_trough_dd_180d_pct: float | None
    max_peak_to_trough_dd_365d_pct: float | None
    days_to_20pct_running_peak_dd: int | None
    days_to_30pct_running_peak_dd: int | None
    days_to_40pct_running_peak_dd: int | None


@dataclass(frozen=True, slots=True)
class TopTimingSummary:
    signal: str
    episodes: int
    valid_180d: int
    valid_365d: int
    median_days_to_peak_365d: float | None
    median_additional_upside_365d_pct: float | None
    median_max_peak_to_trough_dd_180d_pct: float | None
    median_max_peak_to_trough_dd_365d_pct: float | None
    hit_20pct_dd_rate_pct: float | None
    hit_30pct_dd_rate_pct: float | None
    hit_40pct_dd_rate_pct: float | None
    median_days_to_20pct_dd: float | None
    median_days_to_30pct_dd: float | None
    median_days_to_40pct_dd: float | None


def _window(
    ordered: list[TopConfluencePoint],
    *,
    start: date,
    days: int,
) -> list[TopConfluencePoint]:
    end = start + timedelta(days=days)
    return [point for point in ordered if start <= point.date <= end]


def _max_peak_to_trough_drawdown(window: list[TopConfluencePoint]) -> float | None:
    if not window:
        return None
    running_peak = window[0].price
    worst = 0.0
    for point in window:
        running_peak = max(running_peak, point.price)
        if running_peak > 0:
            worst = min(worst, (point.price / running_peak - 1.0) * 100.0)
    return worst


def _first_running_peak_drawdown_days(
    window: list[TopConfluencePoint],
    *,
    threshold_pct: float,
) -> int | None:
    if not window:
        return None
    running_peak = window[0].price
    start = window[0].date
    for point in window:
        running_peak = max(running_peak, point.price)
        drawdown = (point.price / running_peak - 1.0) * 100.0 if running_peak > 0 else 0.0
        if drawdown <= -abs(threshold_pct):
            return (point.date - start).days
    return None


def evaluate_top_timing(
    points: list[TopConfluencePoint],
    *,
    specs: tuple[TopSpec, ...] = DEFAULT_TOP_SPECS,
    cooldown_days: int = 90,
) -> list[TopTimingEpisode]:
    """Evaluate timing/risk after independent entries into fixed top conditions.

    The 365-day peak is the highest observed BTC price from the signal date
    through day 365, inclusive. Additional upside is measured from signal price
    to that peak. Drawdowns are running-peak-to-trough drawdowns inside the
    stated horizon. Threshold-hit timing is also measured from a running peak,
    so a signal may first rise and still later register a 20/30/40% drawdown.

    A metric is left None when the dataset does not contain the full required
    horizon, preventing right-censored recent episodes from being treated as
    completed observations.
    """
    ordered = sorted(points, key=lambda item: item.date)
    if not ordered:
        return []
    last_date = ordered[-1].date
    rows: list[TopTimingEpisode] = []

    for spec in specs:
        episodes = independent_top_episodes(ordered, spec, cooldown_days=cooldown_days)
        for episode in episodes:
            has_180 = episode.date + timedelta(days=180) <= last_date
            has_365 = episode.date + timedelta(days=365) <= last_date
            window_180 = _window(ordered, start=episode.date, days=180) if has_180 else []
            window_365 = _window(ordered, start=episode.date, days=365) if has_365 else []

            peak = max(window_365, key=lambda point: point.price) if window_365 else None
            days_to_peak = (peak.date - episode.date).days if peak is not None else None
            upside = (
                (peak.price / episode.price - 1.0) * 100.0
                if peak is not None and episode.price > 0
                else None
            )

            rows.append(
                TopTimingEpisode(
                    signal=spec.label,
                    signal_date=episode.date,
                    signal_price=episode.price,
                    peak_date_365d=peak.date if peak else None,
                    peak_price_365d=peak.price if peak else None,
                    days_to_peak_365d=days_to_peak,
                    additional_upside_365d_pct=upside,
                    max_peak_to_trough_dd_180d_pct=_max_peak_to_trough_drawdown(window_180),
                    max_peak_to_trough_dd_365d_pct=_max_peak_to_trough_drawdown(window_365),
                    days_to_20pct_running_peak_dd=_first_running_peak_drawdown_days(
                        window_365, threshold_pct=20.0
                    ),
                    days_to_30pct_running_peak_dd=_first_running_peak_drawdown_days(
                        window_365, threshold_pct=30.0
                    ),
                    days_to_40pct_running_peak_dd=_first_running_peak_drawdown_days(
                        window_365, threshold_pct=40.0
                    ),
                )
            )
    return rows


def _median(values: list[float]) -> float | None:
    return median(values) if values else None


def _hit_rate(values: list[int | None]) -> float | None:
    if not values:
        return None
    return 100.0 * sum(value is not None for value in values) / len(values)


def summarize_top_timing(
    rows: list[TopTimingEpisode],
    *,
    specs: tuple[TopSpec, ...] = DEFAULT_TOP_SPECS,
) -> list[TopTimingSummary]:
    summaries: list[TopTimingSummary] = []
    for spec in specs:
        selected = [row for row in rows if row.signal == spec.label]
        valid_180 = [row for row in selected if row.max_peak_to_trough_dd_180d_pct is not None]
        valid_365 = [row for row in selected if row.max_peak_to_trough_dd_365d_pct is not None]
        d20 = [row.days_to_20pct_running_peak_dd for row in valid_365]
        d30 = [row.days_to_30pct_running_peak_dd for row in valid_365]
        d40 = [row.days_to_40pct_running_peak_dd for row in valid_365]
        summaries.append(
            TopTimingSummary(
                signal=spec.label,
                episodes=len(selected),
                valid_180d=len(valid_180),
                valid_365d=len(valid_365),
                median_days_to_peak_365d=_median([
                    float(row.days_to_peak_365d)
                    for row in valid_365
                    if row.days_to_peak_365d is not None
                ]),
                median_additional_upside_365d_pct=_median([
                    float(row.additional_upside_365d_pct)
                    for row in valid_365
                    if row.additional_upside_365d_pct is not None
                ]),
                median_max_peak_to_trough_dd_180d_pct=_median([
                    float(row.max_peak_to_trough_dd_180d_pct)
                    for row in valid_180
                    if row.max_peak_to_trough_dd_180d_pct is not None
                ]),
                median_max_peak_to_trough_dd_365d_pct=_median([
                    float(row.max_peak_to_trough_dd_365d_pct)
                    for row in valid_365
                    if row.max_peak_to_trough_dd_365d_pct is not None
                ]),
                hit_20pct_dd_rate_pct=_hit_rate(d20),
                hit_30pct_dd_rate_pct=_hit_rate(d30),
                hit_40pct_dd_rate_pct=_hit_rate(d40),
                median_days_to_20pct_dd=_median([float(value) for value in d20 if value is not None]),
                median_days_to_30pct_dd=_median([float(value) for value in d30 if value is not None]),
                median_days_to_40pct_dd=_median([float(value) for value in d40 if value is not None]),
            )
        )
    return summaries
