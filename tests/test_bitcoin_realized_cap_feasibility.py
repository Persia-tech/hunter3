from __future__ import annotations

from backend.app.services.bitcoin_realized_cap_feasibility import scan_recent_blocks


class FakeProvider:
    def __init__(self) -> None:
        self.tip = 101

    def get_tip_height(self):
        return self.tip, "fake"

    def get_block_hash(self, height: int):
        return f"hash-{height}", "fake"

    def get_block(self, block_hash: str):
        return {"id": block_hash, "tx_count": 3}, "fake"

    def get_block_transactions(self, block_hash: str, *, start_index: int = 0):
        height = int(block_hash.split("-")[1])
        if start_index > 0:
            return [], "fake"
        return [
            {
                "txid": f"coinbase-{height}",
                "vin": [{"is_coinbase": True}],
                "vout": [{"value": 50}],
            },
            {
                "txid": f"tx-a-{height}",
                "vin": [{"txid": "old-1", "is_coinbase": False}],
                "vout": [{"value": 10}, {"value": 20}],
            },
            {
                "txid": f"tx-b-{height}",
                "vin": [
                    {"txid": f"tx-a-{height}", "is_coinbase": False},
                    {"txid": "old-2", "is_coinbase": False},
                ],
                "vout": [{"value": 5}],
            },
        ], "fake"


def test_scan_counts_inputs_outputs_and_external_prev_transactions() -> None:
    result = scan_recent_blocks(FakeProvider(), blocks=2, max_transactions_per_block=25)  # type: ignore[arg-type]

    assert result.blocks_scanned == 2
    assert result.sampled_transactions == 6
    assert result.sampled_inputs == 6
    assert result.sampled_outputs == 8
    assert result.unique_prev_txids == 4
    assert result.intra_sample_prev_txids == 2
    assert result.external_prev_txids == 2


def test_scan_rejects_invalid_arguments() -> None:
    provider = FakeProvider()

    try:
        scan_recent_blocks(provider, blocks=0)  # type: ignore[arg-type]
    except ValueError as exc:
        assert "blocks must be positive" in str(exc)
    else:
        raise AssertionError("Expected ValueError")

    try:
        scan_recent_blocks(provider, max_transactions_per_block=0)  # type: ignore[arg-type]
    except ValueError as exc:
        assert "max_transactions_per_block must be positive" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
