"""Print the newest free Coin Metrics Community BTC MVRV observation."""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.providers.coinmetrics_community_provider import CoinMetricsCommunityProvider


def freshness_label(days_old: int) -> str:
    if days_old <= 0:
        return "LIVE"
    if days_old == 1:
        return "CURRENT"
    if days_old == 2:
        return "ACCEPTABLE"
    return "STALE"


def main() -> None:
    today = date.today()
    provider = CoinMetricsCommunityProvider()
    records = provider.get_bitcoin_daily_metrics(
        start_date=today - timedelta(days=14),
        end_date=today,
    )

    mvrv_rows = [row for row in records if row.mvrv is not None]
    if not mvrv_rows:
        raise RuntimeError("No non-null BTC MVRV value was returned")

    latest = mvrv_rows[-1]
    age_days = (today - latest.date).days

    print("CURRENT BITCOIN MVRV — COIN METRICS COMMUNITY")
    print("-" * 72)
    print(f"Date:         {latest.date}")
    print(f"BTC price:    ${latest.price_usd:,.2f}" if latest.price_usd is not None else "BTC price:    N/A")
    print(f"MVRV:         {latest.mvrv:.6f}")
    print(f"Age:          {age_days} day(s)")
    print(f"Freshness:    {freshness_label(age_days)}")
    print()
    print("Live request intentionally uses only Community-confirmed PriceUSD + CapMVRVCur.")
    print("MVRV Z, Realized Cap and NUPL are not claimed as live Community API metrics here.")


if __name__ == "__main__":
    main()
