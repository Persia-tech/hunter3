"""Coin Metrics Community API provider for Bitcoin on-chain research data."""

from __future__ import annotations

import csv
import io
from datetime import date, datetime
from math import sqrt
from typing import Callable
from urllib.parse import urlencode

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from backend.app.models.onchain import BitcoinOnChainRecord


COMMUNITY_BASE_URL = "https://community-api.coinmetrics.io/v4"
ARCHIVE_BTC_CSV_URL = "https://raw.githubusercontent.com/coinmetrics/data/refs/heads/master/csv/btc.csv"
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
    """Fetch free daily Bitcoin on-chain valuation metrics.

    Primary source: Coin Metrics Community API.
    Fallback source: Coin Metrics' public daily GitHub CSV archive. The archive
    currently includes PriceUSD, CapMrktCurUSD and CapMVRVCur for BTC. When the
    API host cannot be reached, Realized Cap and NUPL are reconstructed exactly
    from the documented MVRV identities, and MVRV Z-Score is reconstructed from
    the documented formula using an expanding historical standard deviation of
    market cap. The fallback remains transparent and research-only.
    """

    def __init__(
        self,
        *,
        base_url: str = COMMUNITY_BASE_URL,
        timeout_seconds: int = 30,
        fetch_json: Callable[[str], dict] | None = None,
        allow_archive_fallback: bool = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._fetch_json_override = fetch_json
        self.allow_archive_fallback = allow_archive_fallback

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
                "Accept": "application/json,text/csv;q=0.9,*/*;q=0.8",
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
                "or the remote service closing the connection."
            ) from exc

        if response.status_code in {401, 403}:
            raise RuntimeError(
                f"Coin Metrics returned HTTP {response.status_code}. "
                "The Community endpoint does not require an API key, but one or more requested "
                "metrics may not be available to anonymous Community access."
            )
        if not response.ok:
            body = response.text[:500].replace("\n", " ")
            raise RuntimeError(f"Coin Metrics returned HTTP {response.status_code}: {body}")

        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError("Coin Metrics returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("Coin Metrics returned an unexpected response shape")
        return payload

    def _get_from_api(
        self,
        *,
        start_date: date,
        end_date: date,
    ) -> list[BitcoinOnChainRecord]:
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

    def _get_from_archive(
        self,
        *,
        start_date: date,
        end_date: date,
    ) -> list[BitcoinOnChainRecord]:
        try:
            response = self._session.get(ARCHIVE_BTC_CSV_URL, timeout=max(self.timeout_seconds, 60))
            response.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(
                "Coin Metrics API failed and the public Coin Metrics GitHub CSV fallback could "
                "not be downloaded either."
            ) from exc

        reader = csv.DictReader(io.StringIO(response.text))
        required = {"time", "PriceUSD", "CapMrktCurUSD", "CapMVRVCur"}
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise RuntimeError(
                "Coin Metrics BTC archive is missing required columns: " + ", ".join(sorted(missing))
            )

        rows: list[BitcoinOnChainRecord] = []
        count = 0
        mean_market_cap = 0.0
        m2_market_cap = 0.0

        for item in reader:
            day = date.fromisoformat(str(item["time"]))
            market_cap = _parse_optional_float(item.get("CapMrktCurUSD"))

            # Update expanding market-cap volatility before calculating today's
            # Z-score, so the fallback uses information available through today
            # and never future observations.
            if market_cap is not None:
                count += 1
                delta = market_cap - mean_market_cap
                mean_market_cap += delta / count
                m2_market_cap += delta * (market_cap - mean_market_cap)

            if not (start_date <= day <= end_date):
                continue

            price = _parse_optional_float(item.get("PriceUSD"))
            mvrv = _parse_optional_float(item.get("CapMVRVCur"))
            realized_cap = None
            nupl = None
            mvrv_z = None

            if market_cap is not None and mvrv is not None and mvrv > 0:
                # Coin Metrics definition: MVRV = market cap / realized cap.
                realized_cap = market_cap / mvrv
                # Coin Metrics definition: NUPL = (market cap - realized cap) / market cap.
                if market_cap > 0:
                    nupl = (market_cap - realized_cap) / market_cap

                # Coin Metrics definition: MVRV Z =
                # (market cap - realized cap) / std(market cap).
                # The archive does not include CapMVRVZ, so use an expanding
                # population standard deviation to preserve no-look-ahead behavior.
                if count > 1:
                    std_market_cap = sqrt(m2_market_cap / count)
                    if std_market_cap > 0:
                        mvrv_z = (market_cap - realized_cap) / std_market_cap

            rows.append(
                BitcoinOnChainRecord(
                    date=day,
                    price_usd=price,
                    mvrv=mvrv,
                    mvrv_z=mvrv_z,
                    realized_cap_usd=realized_cap,
                    nupl=nupl,
                )
            )

        rows.sort(key=lambda item: item.date)
        return rows

    def get_bitcoin_daily_metrics(
        self,
        *,
        start_date: date,
        end_date: date,
    ) -> list[BitcoinOnChainRecord]:
        if end_date < start_date:
            raise ValueError("end_date must be on or after start_date")

        try:
            return self._get_from_api(start_date=start_date, end_date=end_date)
        except RuntimeError:
            if not self.allow_archive_fallback or self._fetch_json_override is not None:
                raise
            return self._get_from_archive(start_date=start_date, end_date=end_date)
