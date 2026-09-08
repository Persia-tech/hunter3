"""Coin Metrics Community API provider for Bitcoin on-chain research data."""

from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta
from math import sqrt
from typing import Callable
from urllib.parse import urlencode

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from backend.app.models.onchain import BitcoinOnChainRecord


COMMUNITY_BASE_URL = "https://community-api.coinmetrics.io/v4"
ARCHIVE_BTC_CSV_URL = "https://raw.githubusercontent.com/coinmetrics/data/refs/heads/master/csv/btc.csv"

# These two metrics were verified against anonymous Community access on 2026-09-06.
# Keep the live request deliberately narrow so an unavailable derived metric cannot
# make the whole current-data request fail.
LIVE_COMMUNITY_METRICS = ("PriceUSD", "CapMVRVCur")


def _parse_optional_float(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return float(text)


class CoinMetricsCommunityProvider:
    """Fetch free Bitcoin MVRV plus historical reconstructed valuation metrics.

    Current/live source:
      Coin Metrics Community API, requesting only PriceUSD and CapMVRVCur (MVRV),
      which are confirmed available anonymously.

    Historical source:
      Coin Metrics' public BTC GitHub CSV archive. It includes PriceUSD,
      CapMrktCurUSD and CapMVRVCur. Realized Cap and NUPL are reconstructed from
      MVRV identities, while MVRV Z-Score is reconstructed with an expanding
      historical market-cap standard deviation so it remains no-look-ahead.

    The two sources are merged by date. Fresh Community PriceUSD/MVRV values
    override archive values when present, while archive-only reconstructed fields
    are preserved. This keeps historical research intact while allowing a fresh
    daily MVRV signal without pretending reconstructed metrics are live API data.
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
                "The Community endpoint does not require an API key for the verified live "
                "PriceUSD/CapMVRVCur request, but access may have changed."
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
            "metrics": ",".join(LIVE_COMMUNITY_METRICS),
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
                        mvrv_z=None,
                        realized_cap_usd=None,
                        nupl=None,
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
                "The public Coin Metrics GitHub BTC archive could not be downloaded."
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
                realized_cap = market_cap / mvrv
                if market_cap > 0:
                    nupl = (market_cap - realized_cap) / market_cap

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

    @staticmethod
    def _merge_rows(
        archive_rows: list[BitcoinOnChainRecord],
        live_rows: list[BitcoinOnChainRecord],
    ) -> list[BitcoinOnChainRecord]:
        merged = {row.date: row for row in archive_rows}
        for live in live_rows:
            historical = merged.get(live.date)
            merged[live.date] = BitcoinOnChainRecord(
                date=live.date,
                price_usd=(
                    live.price_usd
                    if live.price_usd is not None
                    else (historical.price_usd if historical is not None else None)
                ),
                mvrv=(
                    live.mvrv
                    if live.mvrv is not None
                    else (historical.mvrv if historical is not None else None)
                ),
                mvrv_z=historical.mvrv_z if historical is not None else None,
                realized_cap_usd=(
                    historical.realized_cap_usd if historical is not None else None
                ),
                nupl=historical.nupl if historical is not None else None,
            )
        return sorted(merged.values(), key=lambda item: item.date)

    def get_bitcoin_daily_metrics(
        self,
        *,
        start_date: date,
        end_date: date,
    ) -> list[BitcoinOnChainRecord]:
        if end_date < start_date:
            raise ValueError("end_date must be on or after start_date")

        # Test/injected callers intentionally exercise the API parser alone.
        if self._fetch_json_override is not None:
            return self._get_from_api(start_date=start_date, end_date=end_date)

        archive_rows: list[BitcoinOnChainRecord] = []
        archive_error: RuntimeError | None = None
        try:
            archive_rows = self._get_from_archive(start_date=start_date, end_date=end_date)
        except RuntimeError as exc:
            archive_error = exc

        # If the archive is available, request only the overlap/latest gap from
        # Community rather than re-downloading the entire BTC history via API.
        if archive_rows:
            latest_archive_day = archive_rows[-1].date
            live_start = max(start_date, latest_archive_day - timedelta(days=2))
        else:
            live_start = start_date

        try:
            live_rows = self._get_from_api(start_date=live_start, end_date=end_date)
        except RuntimeError:
            if archive_rows and self.allow_archive_fallback:
                return archive_rows
            if archive_error is not None:
                raise archive_error
            raise

        if not archive_rows:
            return live_rows
        return self._merge_rows(archive_rows, live_rows)
