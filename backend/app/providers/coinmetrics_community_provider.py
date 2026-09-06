"""Coin Metrics Community API provider for Bitcoin on-chain research data."""

from __future__ import annotations

from datetime import date, datetime
from typing import Callable
from urllib.parse import urlencode

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from backend.app.models.onchain import BitcoinOnChainRecord


COMMUNITY_BASE_URL = "https://community-api.coinmetrics.io/v4"
DEFAULT_METRICS = (
    "PriceUSD",
    "CapMVRVCur",
    "CapMVRVZ",
    "CapRealUSD",
    "NUPL",
)


def _parse_optional_float(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return float(text)


class CoinMetricsCommunityProvider:
    """Fetch free daily Bitcoin asset metrics from Coin Metrics Community API.

    The provider intentionally requests raw metrics only. Research services decide
    later how, or whether, to combine them.
    """

    def __init__(
        self,
        *,
        base_url: str = COMMUNITY_BASE_URL,
        timeout_seconds: int = 30,
        fetch_json: Callable[[str], dict] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._fetch_json_override = fetch_json

        retry = Retry(
            total=4,
            connect=4,
            read=4,
            status=4,
            backoff_factor=1.0,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self._session = requests.Session()
        self._session.mount("https://", adapter)
        self._session.headers.update(
            {
                "User-Agent": "hunter3-bitcoin-research/1.0",
                "Accept": "application/json",
                "Connection": "close",
            }
        )

    def _fetch_json(self, url: str) -> dict:
        if self._fetch_json_override is not None:
            return self._fetch_json_override(url)

        try:
            response = self._session.get(url, timeout=self.timeout_seconds)
        except requests.RequestException as exc:
            raise RuntimeError(
                "Could not connect to Coin Metrics Community API. "
                "This can be caused by a transient TLS/network reset, VPN/firewall filtering, "
                "or the remote service closing the connection. Try again once; if it persists, "
                "test the community-api.coinmetrics.io host from your browser/curl."
            ) from exc

        if response.status_code in {401, 403}:
            raise RuntimeError(
                f"Coin Metrics returned HTTP {response.status_code}. "
                "The Community endpoint does not require an API key, but one or more requested "
                "metrics may not be available to anonymous Community access."
            )
        if not response.ok:
            body = response.text[:500].replace("\n", " ")
            raise RuntimeError(
                f"Coin Metrics returned HTTP {response.status_code}: {body}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError("Coin Metrics returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("Coin Metrics returned an unexpected response shape")
        return payload

    def get_bitcoin_daily_metrics(
        self,
        *,
        start_date: date,
        end_date: date,
    ) -> list[BitcoinOnChainRecord]:
        if end_date < start_date:
            raise ValueError("end_date must be on or after start_date")

        params = {
            "assets": "btc",
            "metrics": ",".join(DEFAULT_METRICS),
            "frequency": "1d",
            "start_time": start_date.isoformat(),
            "end_time": end_date.isoformat(),
            "page_size": "10000",
        }
        url = f"{self.base_url}/timeseries/asset-metrics?{urlencode(params)}"

        rows: list[BitcoinOnChainRecord] = []
        while url:
            payload = self._fetch_json(url)
            if "data" not in payload:
                raise RuntimeError("Coin Metrics response did not contain a data field")

            for item in payload["data"]:
                day = datetime.fromisoformat(str(item["time"]).replace("Z", "+00:00")).date()
                rows.append(
                    BitcoinOnChainRecord(
                        date=day,
                        price_usd=_parse_optional_float(item.get("PriceUSD")),
                        mvrv=_parse_optional_float(item.get("CapMVRVCur")),
                        mvrv_z=_parse_optional_float(item.get("CapMVRVZ")),
                        realized_cap_usd=_parse_optional_float(item.get("CapRealUSD")),
                        nupl=_parse_optional_float(item.get("NUPL")),
                    )
                )

            next_url = payload.get("next_page_url")
            url = str(next_url) if next_url else ""

        rows.sort(key=lambda item: item.date)
        return rows
