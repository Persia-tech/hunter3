"""Raw Bitcoin chain provider using Esplora-compatible public APIs.

Primary: Blockstream Esplora at blockstream.info.
Fallback: mempool.space's compatible REST API.

This provider intentionally exposes raw chain data only. It does not calculate
MVRV, realized cap, or any production score.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


BLOCKSTREAM_BASE_URL = "https://blockstream.info/api"
MEMPOOL_BASE_URL = "https://mempool.space/api"


@dataclass(frozen=True, slots=True)
class BitcoinChainProbe:
    source: str
    base_url: str
    tip_height: int
    tip_hash: str
    block_timestamp: int
    block_time_utc: str
    block_tx_count: int
    txids_count: int
    first_batch_count: int
    first_txid: str
    first_tx_matches_txids: bool


class BitcoinRawChainProvider:
    """Read raw Bitcoin blocks/transactions with automatic provider fallback."""

    def __init__(
        self,
        *,
        primary_base_url: str = BLOCKSTREAM_BASE_URL,
        fallback_base_url: str = MEMPOOL_BASE_URL,
        timeout_seconds: int = 30,
        session: requests.Session | None = None,
    ) -> None:
        self.primary_base_url = primary_base_url.rstrip("/")
        self.fallback_base_url = fallback_base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._session = session or self._build_session()
        self._active_base_url: str | None = None

    @staticmethod
    def _build_session() -> requests.Session:
        retry = Retry(
            total=3,
            connect=3,
            read=3,
            status=3,
            backoff_factor=0.75,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        session = requests.Session()
        session.mount("https://", adapter)
        session.headers.update(
            {
                "User-Agent": "hunter3-bitcoin-research/1.0",
                "Accept": "application/json,text/plain;q=0.9,*/*;q=0.8",
                "Connection": "close",
            }
        )
        return session

    def _request(self, base_url: str, path: str, *, expect_json: bool) -> Any:
        url = f"{base_url}{path}"
        response = self._session.get(url, timeout=self.timeout_seconds)
        response.raise_for_status()
        if expect_json:
            return response.json()
        return response.text.strip()

    def _request_with_fallback(self, path: str, *, expect_json: bool) -> tuple[Any, str]:
        candidates: list[str]
        if self._active_base_url is not None:
            other = (
                self.fallback_base_url
                if self._active_base_url == self.primary_base_url
                else self.primary_base_url
            )
            candidates = [self._active_base_url, other]
        else:
            candidates = [self.primary_base_url, self.fallback_base_url]

        errors: list[str] = []
        for base_url in candidates:
            try:
                value = self._request(base_url, path, expect_json=expect_json)
                self._active_base_url = base_url
                return value, base_url
            except (requests.RequestException, ValueError) as exc:
                errors.append(f"{base_url}: {exc}")

        raise RuntimeError(
            "Both Blockstream Esplora and mempool.space failed for "
            f"{path}. " + " | ".join(errors)
        )

    @staticmethod
    def _source_name(base_url: str) -> str:
        if "blockstream.info" in base_url:
            return "Blockstream Esplora"
        if "mempool.space" in base_url:
            return "mempool.space"
        return base_url

    def get_tip_height(self) -> tuple[int, str]:
        text, source = self._request_with_fallback("/blocks/tip/height", expect_json=False)
        return int(text), source

    def get_tip_hash(self) -> tuple[str, str]:
        text, source = self._request_with_fallback("/blocks/tip/hash", expect_json=False)
        return str(text), source

    def get_block_hash(self, height: int) -> tuple[str, str]:
        if height < 0:
            raise ValueError("height must be non-negative")
        text, source = self._request_with_fallback(f"/block-height/{height}", expect_json=False)
        return str(text), source

    def get_block(self, block_hash: str) -> tuple[dict[str, Any], str]:
        payload, source = self._request_with_fallback(f"/block/{block_hash}", expect_json=True)
        if not isinstance(payload, dict):
            raise RuntimeError("Unexpected block response shape")
        return payload, source

    def get_block_txids(self, block_hash: str) -> tuple[list[str], str]:
        payload, source = self._request_with_fallback(f"/block/{block_hash}/txids", expect_json=True)
        if not isinstance(payload, list):
            raise RuntimeError("Unexpected block txids response shape")
        return [str(item) for item in payload], source

    def get_block_transactions(
        self,
        block_hash: str,
        *,
        start_index: int = 0,
    ) -> tuple[list[dict[str, Any]], str]:
        if start_index < 0 or start_index % 25 != 0:
            raise ValueError("start_index must be a non-negative multiple of 25")
        path = f"/block/{block_hash}/txs"
        if start_index:
            path += f"/{start_index}"
        payload, source = self._request_with_fallback(path, expect_json=True)
        if not isinstance(payload, list):
            raise RuntimeError("Unexpected block transactions response shape")
        return [dict(item) for item in payload], source

    def probe(self) -> BitcoinChainProbe:
        """Probe the current tip and verify basic block/transaction consistency."""
        tip_height, source_url = self.get_tip_height()
        tip_hash, _ = self.get_tip_hash()
        block_hash_by_height, _ = self.get_block_hash(tip_height)
        if block_hash_by_height != tip_hash:
            raise RuntimeError("Tip hash does not match block-height lookup")

        block, _ = self.get_block(tip_hash)
        txids, _ = self.get_block_txids(tip_hash)
        first_batch, _ = self.get_block_transactions(tip_hash, start_index=0)

        block_id = str(block.get("id", ""))
        if block_id and block_id != tip_hash:
            raise RuntimeError("Block response id does not match requested tip hash")

        tx_count = int(block.get("tx_count", len(txids)))
        if tx_count != len(txids):
            raise RuntimeError(
                f"Block tx_count={tx_count} but txids endpoint returned {len(txids)}"
            )
        if not txids:
            raise RuntimeError("Tip block returned no transaction ids")
        if not first_batch:
            raise RuntimeError("Tip block first transaction page was empty")

        first_txid = str(first_batch[0].get("txid", ""))
        matches = first_txid == txids[0]
        if not matches:
            raise RuntimeError("First transaction page does not match txids ordering")

        timestamp = int(block.get("timestamp", 0))
        block_time = datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()

        return BitcoinChainProbe(
            source=self._source_name(source_url),
            base_url=source_url,
            tip_height=tip_height,
            tip_hash=tip_hash,
            block_timestamp=timestamp,
            block_time_utc=block_time,
            block_tx_count=tx_count,
            txids_count=len(txids),
            first_batch_count=len(first_batch),
            first_txid=first_txid,
            first_tx_matches_txids=matches,
        )
