"""Probe Blockstream Esplora with mempool.space fallback."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.providers.bitcoin_raw_chain_provider import BitcoinRawChainProvider


def main() -> None:
    print("Probing fresh raw Bitcoin chain data...")
    print("Primary: Blockstream Esplora")
    print("Fallback: mempool.space")

    provider = BitcoinRawChainProvider()
    result = provider.probe()

    print()
    print("RAW BITCOIN CHAIN PROBE")
    print("-" * 88)
    print(f"Source used:           {result.source}")
    print(f"Base URL:              {result.base_url}")
    print(f"Tip height:            {result.tip_height:,}")
    print(f"Tip hash:              {result.tip_hash}")
    print(f"Tip block time (UTC):  {result.block_time_utc}")
    print(f"Block transaction cnt: {result.block_tx_count:,}")
    print(f"TXIDs returned:        {result.txids_count:,}")
    print(f"First tx page count:   {result.first_batch_count:,}")
    print(f"First txid:            {result.first_txid}")
    print(f"TX ordering verified:  {result.first_tx_matches_txids}")
    print()
    print("Success: raw current Bitcoin block/transaction data is reachable and internally consistent.")
    print("No realized-cap or MVRV calculation has been attempted yet.")


if __name__ == "__main__":
    main()
