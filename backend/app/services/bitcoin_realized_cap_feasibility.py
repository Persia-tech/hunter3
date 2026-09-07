"""Estimate the raw-chain work needed to maintain Bitcoin realized cap.

This is deliberately a feasibility scanner, not a realized-cap implementation.
It samples recent blocks from an Esplora-compatible provider and measures how
many transactions, inputs, outputs, and unique previous transactions would need
to be resolved. That tells us whether public REST APIs are practical for live
incremental maintenance before attempting a historical bootstrap.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.providers.bitcoin_raw_chain_provider import BitcoinRawChainProvider


@dataclass(frozen=True, slots=True)
class BlockFeasibility:
    height: int
    block_hash: str
    tx_count: int
    sampled_transactions: int
    sampled_inputs: int
    sampled_outputs: int
    unique_prev_txids: int
    intra_sample_prev_txids: int
    external_prev_txids: int


@dataclass(frozen=True, slots=True)
class RealizedCapFeasibility:
    tip_height: int
    blocks_requested: int
    blocks_scanned: int
    sampled_transactions: int
    sampled_inputs: int
    sampled_outputs: int
    unique_prev_txids: int
    intra_sample_prev_txids: int
    external_prev_txids: int
    estimated_external_prev_tx_fetches_per_full_block: float
    blocks: tuple[BlockFeasibility, ...]


def _non_coinbase_prev_txids(tx: dict) -> list[str]:
    values: list[str] = []
    for vin in tx.get("vin", []) or []:
        if vin.get("is_coinbase"):
            continue
        txid = vin.get("txid")
        if txid:
            values.append(str(txid))
    return values


def scan_recent_blocks(
    provider: BitcoinRawChainProvider,
    *,
    blocks: int = 10,
    max_transactions_per_block: int = 250,
) -> RealizedCapFeasibility:
    """Sample recent blocks and estimate realized-cap state-resolution cost.

    Esplora block transaction pages contain 25 transactions. We intentionally
    cap each block sample so this research probe does not hammer public APIs.
    """
    if blocks <= 0:
        raise ValueError("blocks must be positive")
    if max_transactions_per_block <= 0:
        raise ValueError("max_transactions_per_block must be positive")

    tip_height, _ = provider.get_tip_height()
    block_results: list[BlockFeasibility] = []

    total_sampled_tx = 0
    total_inputs = 0
    total_outputs = 0
    all_prev_txids: set[str] = set()
    all_sample_txids: set[str] = set()

    start_height = max(0, tip_height - blocks + 1)
    for height in range(start_height, tip_height + 1):
        block_hash, _ = provider.get_block_hash(height)
        block, _ = provider.get_block(block_hash)
        tx_count = int(block.get("tx_count", 0))

        transactions: list[dict] = []
        for start_index in range(0, min(tx_count, max_transactions_per_block), 25):
            page, _ = provider.get_block_transactions(block_hash, start_index=start_index)
            if not page:
                break
            remaining = max_transactions_per_block - len(transactions)
            transactions.extend(page[:remaining])
            if len(transactions) >= max_transactions_per_block:
                break

        sample_txids = {str(tx.get("txid")) for tx in transactions if tx.get("txid")}
        prev_txids: list[str] = []
        input_count = 0
        output_count = 0
        for tx in transactions:
            vins = tx.get("vin", []) or []
            vouts = tx.get("vout", []) or []
            input_count += sum(1 for vin in vins if not vin.get("is_coinbase"))
            output_count += len(vouts)
            prev_txids.extend(_non_coinbase_prev_txids(tx))

        unique_prev = set(prev_txids)
        intra = unique_prev.intersection(sample_txids)
        external = unique_prev.difference(sample_txids)

        total_sampled_tx += len(transactions)
        total_inputs += input_count
        total_outputs += output_count
        all_prev_txids.update(unique_prev)
        all_sample_txids.update(sample_txids)

        block_results.append(
            BlockFeasibility(
                height=height,
                block_hash=block_hash,
                tx_count=tx_count,
                sampled_transactions=len(transactions),
                sampled_inputs=input_count,
                sampled_outputs=output_count,
                unique_prev_txids=len(unique_prev),
                intra_sample_prev_txids=len(intra),
                external_prev_txids=len(external),
            )
        )

    intra_all = all_prev_txids.intersection(all_sample_txids)
    external_all = all_prev_txids.difference(all_sample_txids)

    ratios: list[float] = []
    for item in block_results:
        if item.sampled_transactions > 0:
            ratios.append(item.external_prev_txids / item.sampled_transactions)
    external_per_tx = sum(ratios) / len(ratios) if ratios else 0.0

    average_full_tx_count = (
        sum(item.tx_count for item in block_results) / len(block_results)
        if block_results
        else 0.0
    )
    estimated_fetches = external_per_tx * average_full_tx_count

    return RealizedCapFeasibility(
        tip_height=tip_height,
        blocks_requested=blocks,
        blocks_scanned=len(block_results),
        sampled_transactions=total_sampled_tx,
        sampled_inputs=total_inputs,
        sampled_outputs=total_outputs,
        unique_prev_txids=len(all_prev_txids),
        intra_sample_prev_txids=len(intra_all),
        external_prev_txids=len(external_all),
        estimated_external_prev_tx_fetches_per_full_block=estimated_fetches,
        blocks=tuple(block_results),
    )
