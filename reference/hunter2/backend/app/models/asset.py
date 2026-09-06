"""Supported asset definitions and the central asset registry."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Final


class AssetType(str, Enum):
    """Broad asset categories used by the application."""

    CRYPTO = "crypto"
    STOCK = "stock"
    ETF = "etf"
    PRECIOUS_METAL_ETF = "precious_metal_etf"


class UnsupportedAssetError(ValueError):
    """Raised when a symbol is not present in the supported asset registry."""


@dataclass(frozen=True, slots=True)
class Asset:
    """Provider-independent metadata for an investable asset."""

    symbol: str
    display_name: str
    provider_ticker: str
    asset_type: AssetType
    trades_24_7: bool = False


def _asset(
    symbol: str,
    display_name: str,
    asset_type: AssetType,
    *,
    provider_ticker: str | None = None,
    trades_24_7: bool = False,
) -> Asset:
    return Asset(
        symbol=symbol,
        display_name=display_name,
        provider_ticker=provider_ticker or symbol,
        asset_type=asset_type,
        trades_24_7=trades_24_7,
    )


_ASSETS: Final[dict[str, Asset]] = {
    asset.symbol: asset
    for asset in (
        _asset(
            "BTC",
            "Bitcoin",
            AssetType.CRYPTO,
            provider_ticker="BTC-USD",
            trades_24_7=True,
        ),
        _asset("AAPL", "Apple", AssetType.STOCK),
        _asset("MSFT", "Microsoft", AssetType.STOCK),
        _asset("GOOGL", "Alphabet / Google", AssetType.STOCK),
        _asset("AMZN", "Amazon", AssetType.STOCK),
        _asset("NVDA", "Nvidia", AssetType.STOCK),
        _asset("META", "Meta", AssetType.STOCK),
        _asset("TSLA", "Tesla", AssetType.STOCK),
        _asset("QQQ", "Nasdaq-100", AssetType.ETF),
        _asset("SPY", "S&P 500", AssetType.ETF),
        _asset("GLD", "Gold", AssetType.PRECIOUS_METAL_ETF),
        _asset("SLV", "Silver", AssetType.PRECIOUS_METAL_ETF),
        _asset("PPLT", "Platinum", AssetType.PRECIOUS_METAL_ETF),
    )
}

# Read-only so callers cannot accidentally change the application's source of truth.
SUPPORTED_ASSETS: Final[Mapping[str, Asset]] = MappingProxyType(_ASSETS)


def get_asset(symbol: str) -> Asset:
    """Return a supported asset using a case-insensitive, whitespace-safe symbol."""

    normalized_symbol = symbol.strip().upper()
    try:
        return SUPPORTED_ASSETS[normalized_symbol]
    except KeyError as exc:
        raise UnsupportedAssetError(f"Unsupported asset symbol: {symbol!r}") from exc


