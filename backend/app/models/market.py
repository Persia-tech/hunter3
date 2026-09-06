"""Market-temperature domain objects with API-friendly serialization."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any


class AssetClass(str, Enum):
    CRYPTO = "crypto"
    BROAD_MARKET_ETF = "broad_market_etf"
    SECTOR_ETF = "sector_etf"
    TECHNOLOGY = "technology"
    INDIVIDUAL_STOCK = "individual_stock"
    COMMODITY = "commodity"
    OTHER = "other"


class Trend(str, Enum):
    FALLING = "Falling"
    BOTTOMING = "Bottoming"
    RECOVERING = "Recovering"
    UPTREND = "Uptrend"
    EXTENDED = "Extended"


class Divergence(str, Enum):
    BULLISH = "Bullish"
    BEARISH = "Bearish"
    NONE = "None"


@dataclass(frozen=True)
class Asset:
    symbol: str
    name: str
    asset_class: AssetClass


@dataclass(frozen=True)
class Candle:
    timestamp: date
    close: float


@dataclass
class MarketTemperature:
    symbol: str
    name: str
    asset_class: AssetClass
    as_of: datetime
    current_price: float
    opportunity_score: int
    overheat_score: int
    classification: str
    weekly_rsi: float | None
    previous_weekly_rsi: float | None
    stochastic_rsi: float | None
    previous_stochastic_rsi: float | None
    stochastic_signal: str | None
    sma_200w: float | None
    distance_200w_percent: float | None
    ath: float
    drawdown_percent: float
    sma_200d: float | None
    sma_10m: float | None
    momentum_12m: float | None
    divergence: Divergence
    trend: Trend
    recovery_signal: bool
    history_status: str = "Complete"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["asset_class"] = self.asset_class.value
        data["as_of"] = self.as_of.isoformat()
        data["divergence"] = self.divergence.value
        data["trend"] = self.trend.value
        return data