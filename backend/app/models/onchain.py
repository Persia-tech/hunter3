"""Provider-independent Bitcoin on-chain research models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class BitcoinOnChainRecord:
    """Daily Bitcoin on-chain valuation metrics used for research.

    All fields remain separate on purpose. No composite score is calculated here;
    each metric can be validated independently before any weighting is considered.
    """

    date: date
    price_usd: float | None
    mvrv: float | None
    mvrv_z: float | None
    realized_cap_usd: float | None
    nupl: float | None
