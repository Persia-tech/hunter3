from __future__ import annotations

from typing import Any

import requests

from backend.app.providers.bitcoin_raw_chain_provider import BitcoinRawChainProvider


class FakeResponse:
    def __init__(self, *, text: str = "", json_data: Any = None, status_code: int = 200) -> None:
        self.text = text
        self._json_data = json_data
        self.status_code = status_code
        self.ok = 200 <= status_code < 400

    def raise_for_status(self) -> None:
        if not self.ok:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self) -> Any:
        return self._json_data


class FakeSession:
    def __init__(self, mapping: dict[str, FakeResponse | Exception]) -> None:
        self.mapping = mapping
        self.calls: list[str] = []

    def get(self, url: str, timeout: int) -> FakeResponse:  # noqa: ARG002
        self.calls.append(url)
        result = self.mapping[url]
        if isinstance(result, Exception):
            raise result
        return result


def _responses(base: str) -> dict[str, FakeResponse]:
    block_hash = "abc123"
    first_txid = "coinbase-tx"
    return {
        f"{base}/blocks/tip/height": FakeResponse(text="900000"),
        f"{base}/blocks/tip/hash": FakeResponse(text=block_hash),
        f"{base}/block-height/900000": FakeResponse(text=block_hash),
        f"{base}/block/{block_hash}": FakeResponse(
            json_data={
                "id": block_hash,
                "height": 900000,
                "timestamp": 1_700_000_000,
                "tx_count": 2,
            }
        ),
        f"{base}/block/{block_hash}/txids": FakeResponse(
            json_data=[first_txid, "second-tx"]
        ),
        f"{base}/block/{block_hash}/txs": FakeResponse(
            json_data=[{"txid": first_txid}, {"txid": "second-tx"}]
        ),
    }


def test_probe_uses_primary_when_blockstream_works() -> None:
    primary = "https://primary.example/api"
    fallback = "https://fallback.example/api"
    session = FakeSession(_responses(primary))
    provider = BitcoinRawChainProvider(
        primary_base_url=primary,
        fallback_base_url=fallback,
        session=session,  # type: ignore[arg-type]
    )

    result = provider.probe()

    assert result.tip_height == 900000
    assert result.tip_hash == "abc123"
    assert result.block_tx_count == 2
    assert result.txids_count == 2
    assert result.first_tx_matches_txids is True
    assert all(url.startswith(primary) for url in session.calls)


def test_provider_falls_back_when_primary_connection_fails() -> None:
    primary = "https://primary.example/api"
    fallback = "https://fallback.example/api"
    mapping: dict[str, FakeResponse | Exception] = {
        f"{primary}/blocks/tip/height": requests.ConnectionError("primary down"),
        **_responses(fallback),
    }
    session = FakeSession(mapping)
    provider = BitcoinRawChainProvider(
        primary_base_url=primary,
        fallback_base_url=fallback,
        session=session,  # type: ignore[arg-type]
    )

    result = provider.probe()

    assert result.tip_height == 900000
    assert result.tip_hash == "abc123"
    assert any(url.startswith(primary) for url in session.calls)
    assert any(url.startswith(fallback) for url in session.calls)


def test_block_transaction_start_index_must_match_esplora_paging() -> None:
    provider = BitcoinRawChainProvider(session=FakeSession({}))  # type: ignore[arg-type]

    try:
        provider.get_block_transactions("abc123", start_index=1)
    except ValueError as exc:
        assert "multiple of 25" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
