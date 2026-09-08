"""Estimate whether public Esplora APIs are practical for live realized-cap maintenance."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.providers.bitcoin_raw_chain_provider import BitcoinRawChainProvider
from backend.app.services.bitcoin_realized_cap_feasibility import scan_recent_blocks


def main() -> None:
    print("Scanning recent Bitcoin blocks for realized-cap feasibility...")
    print("Provider: Blockstream Esplora with mempool.space fallback")
    print("Sample: 10 recent blocks, capped at 250 transactions per block")
    print("This does NOT calculate realized cap yet.")
    print()

    provider = BitcoinRawChainProvider()
    result = scan_recent_blocks(provider, blocks=10, max_transactions_per_block=250)

    print("REALIZED CAP RAW-CHAIN FEASIBILITY")
    print("-" * 96)
    print(f"Tip height:                         {result.tip_height:,}")
    print(f"Blocks scanned:                     {result.blocks_scanned}")
    print(f"Transactions sampled:               {result.sampled_transactions:,}")
    print(f"Non-coinbase inputs sampled:        {result.sampled_inputs:,}")
    print(f"Outputs sampled:                    {result.sampled_outputs:,}")
    print(f"Unique previous txids referenced:   {result.unique_prev_txids:,}")
    print(f"Previous txids inside sample:       {result.intra_sample_prev_txids:,}")
    print(f"External previous txids to resolve: {result.external_prev_txids:,}")
    print(
        "Estimated external previous-tx lookups per full recent block: "
        f"{result.estimated_external_prev_tx_fetches_per_full_block:,.0f}"
    )
    print()

    print("PER-BLOCK SAMPLE")
    print("-" * 96)
    print(f"{'Height':>10} {'Tx total':>10} {'Sampled':>9} {'Inputs':>9} {'Outputs':>9} {'External prev tx':>17}")
    for item in result.blocks:
        print(
            f"{item.height:>10,} {item.tx_count:>10,} {item.sampled_transactions:>9,} "
            f"{item.sampled_inputs:>9,} {item.sampled_outputs:>9,} {item.external_prev_txids:>17,}"
        )

    print()
    print("Interpretation:")
    print("- A live incremental realized-cap engine is plausible if we keep our own UTXO state.")
    print("- Re-fetching old transactions for every input through public REST would be expensive.")
    print("- Historical bootstrap should therefore come from a bulk dataset or one-time local reconstruction.")


if __name__ == "__main__":
    main()
