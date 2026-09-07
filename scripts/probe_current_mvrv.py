"""Print the newest free Coin Metrics Community BTC MVRV observation and percentile."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.providers.coinmetrics_community_provider import CoinMetricsCommunityProvider
from backend.app.services.bitcoin_onchain_backtest import expanding_percentile


START_DATE = date(2010, 7, 18)


def freshness_label(days_old: int) -> str:
    if days_old <= 0:
        return "LIVE"
    if days_old == 1:
        return "CURRENT"
    if days_old == 2:
        return "ACCEPTABLE"
    return "STALE"


def valuation_label(percentile: float) -> str:
    if percentile <= 10:
        return "EXTREME LOW"
    if percentile <= 20:
        return "LOW"
    if percentile < 80:
        return "NEUTRAL"
    if percentile < 90:
        return "HIGH"
    return "EXTREME HIGH"


def main() -> None:
    today = date.today()
    provider = CoinMetricsCommunityProvider()
    records = provider.get_bitcoin_daily_metrics(
        start_date=START_DATE,
        end_date=today,
    )

    mvrv_rows = [row for row in records if row.mvrv is not None]
    if not mvrv_rows:
        raise RuntimeError("No non-null BTC MVRV value was returned")

    latest = mvrv_rows[-1]
    age_days = (today - latest.date).days

    # Point-in-time convention: today's percentile is computed only from MVRV
    # observations available through the latest completed MVRV date, including
    # that observation itself. No future values participate.
    history = [float(row.mvrv) for row in mvrv_rows if row.date <= latest.date and row.mvrv is not None]
    percentile = expanding_percentile(float(latest.mvrv), history)
    if percentile is None:
        raise RuntimeError("Could not calculate MVRV historical percentile")

    print("CURRENT BITCOIN MVRV — COIN METRICS COMMUNITY")
    print("-" * 72)
    print(f"Date:                   {latest.date}")
    print(f"BTC price:              ${latest.price_usd:,.2f}" if latest.price_usd is not None else "BTC price:              N/A")
    print(f"MVRV:                   {latest.mvrv:.6f}")
    print(f"Historical percentile:  {percentile:.2f} / 100")
    print(f"Valuation state:        {valuation_label(percentile)}")
    print(f"History observations:   {len(history):,}")
    print(f"Age:                    {age_days} day(s)")
    print(f"Freshness:              {freshness_label(age_days)}")
    print()
    print("Percentile uses only MVRV observations available through the latest completed MVRV date.")
    print("Live request intentionally uses only Community-confirmed PriceUSD + CapMVRVCur.")
    print("MVRV Z, Realized Cap and NUPL are not claimed as live Community API metrics here.")


if __name__ == "__main__":
    main()
