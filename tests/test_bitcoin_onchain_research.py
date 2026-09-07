from __future__ import annotations

from datetime import date, timedelta

from backend.app.models.onchain import BitcoinOnChainRecord
from backend.app.providers.coinmetrics_community_provider import CoinMetricsCommunityProvider
from backend.app.services.bitcoin_onchain_research import (
    build_onchain_research_rows,
    summarize_metric_quantile_bands,
)


def test_coinmetrics_provider_parses_live_mvrv_and_pagination() -> None:
    payloads = [
        {
            "data": [
                {
                    "asset": "btc",
                    "time": "2026-09-04T00:00:00Z",
                    "PriceUSD": "79681.55",
                    "CapMVRVCur": "1.4994",
                }
            ],
            "next_page_url": "https://example.test/page2",
        },
        {
            "data": [
                {
                    "asset": "btc",
                    "time": "2026-09-05T00:00:00Z",
                    "PriceUSD": "79817.32",
                    "CapMVRVCur": "1.5014",
                },
                {
                    "asset": "btc",
                    "time": "2026-09-06T00:00:00Z",
                    "PriceUSD": "80319.97",
                    "CapMVRVCur": None,
                },
            ]
        },
    ]
    called: list[str] = []

    def fake_fetch(url: str) -> dict:
        called.append(url)
        return payloads[len(called) - 1]

    provider = CoinMetricsCommunityProvider(fetch_json=fake_fetch)
    rows = provider.get_bitcoin_daily_metrics(
        start_date=date(2026, 9, 4),
        end_date=date(2026, 9, 6),
    )

    assert len(rows) == 3
    assert rows[0].mvrv == 1.4994
    assert rows[1].mvrv == 1.5014
    assert rows[2].mvrv is None
    assert rows[0].mvrv_z is None
    assert rows[0].realized_cap_usd is None
    assert rows[0].nupl is None
    assert called[1] == "https://example.test/page2"
    assert "CapMVRVCur" in called[0]
    assert "PriceUSD" in called[0]
    assert "CapMVRVZ" not in called[0]
    assert "CapRealUSD" not in called[0]
    assert "NUPL" not in called[0]


def test_merge_live_rows_preserves_archive_reconstructed_fields() -> None:
    archive = [
        BitcoinOnChainRecord(
            date=date(2026, 5, 23),
            price_usd=76000.0,
            mvrv=1.41,
            mvrv_z=0.74,
            realized_cap_usd=1.08e12,
            nupl=0.29,
        )
    ]
    live = [
        BitcoinOnChainRecord(
            date=date(2026, 5, 23),
            price_usd=76100.0,
            mvrv=1.42,
            mvrv_z=None,
            realized_cap_usd=None,
            nupl=None,
        ),
        BitcoinOnChainRecord(
            date=date(2026, 5, 24),
            price_usd=77000.0,
            mvrv=1.45,
            mvrv_z=None,
            realized_cap_usd=None,
            nupl=None,
        ),
    ]

    merged = CoinMetricsCommunityProvider._merge_rows(archive, live)

    assert len(merged) == 2
    assert merged[0].price_usd == 76100.0
    assert merged[0].mvrv == 1.42
    assert merged[0].mvrv_z == 0.74
    assert merged[0].realized_cap_usd == 1.08e12
    assert merged[0].nupl == 0.29
    assert merged[1].mvrv == 1.45
    assert merged[1].mvrv_z is None


def test_future_labels_do_not_change_raw_onchain_metrics() -> None:
    start = date(2020, 1, 1)
    records = [
        BitcoinOnChainRecord(
            date=start + timedelta(days=index),
            price_usd=100.0 + index,
            mvrv=1.0 + index / 1000,
            mvrv_z=index / 500,
            realized_cap_usd=1e11 + index * 1e8,
            nupl=index / 1000,
        )
        for index in range(500)
    ]

    rows = build_onchain_research_rows(records)

    assert rows[0].mvrv == records[0].mvrv
    assert rows[0].mvrv_z == records[0].mvrv_z
    assert rows[0].nupl == records[0].nupl
    assert rows[0].future_return_365d_pct is not None
    assert rows[-1].future_return_365d_pct is None


def test_metric_quintile_summary_keeps_metrics_separate() -> None:
    start = date(2020, 1, 1)
    records = [
        BitcoinOnChainRecord(
            date=start + timedelta(days=index),
            price_usd=100.0 + index,
            mvrv=float(index + 1),
            mvrv_z=float(index + 1) / 2,
            realized_cap_usd=1e11,
            nupl=float(index + 1) / 100,
        )
        for index in range(800)
    ]
    rows = build_onchain_research_rows(records)

    mvrv = summarize_metric_quantile_bands(rows, metric="mvrv")
    mvrv_z = summarize_metric_quantile_bands(rows, metric="mvrv_z")

    assert len(mvrv) == 5
    assert len(mvrv_z) == 5
    assert all(item.metric == "mvrv" for item in mvrv)
    assert all(item.metric == "mvrv_z" for item in mvrv_z)
