"""Refresh Market Temperature data, evaluate alerts, and deliver notifications."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date

from backend.app.db.database import SessionLocal
from backend.app.db.repository import MarketRepository
from backend.app.models.market import Asset, AssetClass
from backend.app.providers.yfinance_provider import YFinanceProvider
from backend.app.services.alert_processor import (
    AlertNotification,
    AlertProcessor,
)
from backend.app.services.market_temperature import calculate_temperature
from bot.alert_sender import send_alert_notification


MARKET_ASSETS = [
    Asset("BTC-USD", "Bitcoin", AssetClass.CRYPTO),
    Asset("ETH-USD", "Ethereum", AssetClass.CRYPTO),
    Asset("SPY", "SPDR S&P 500 ETF Trust", AssetClass.BROAD_MARKET_ETF),
    Asset("VOO", "Vanguard S&P 500 ETF", AssetClass.BROAD_MARKET_ETF),
    Asset("VTI", "Vanguard Total Stock Market ETF", AssetClass.BROAD_MARKET_ETF),
    Asset("QQQ", "Invesco QQQ Trust", AssetClass.TECHNOLOGY),
    Asset("SCHD", "Schwab U.S. Dividend Equity ETF", AssetClass.BROAD_MARKET_ETF),
    Asset("AAPL", "Apple", AssetClass.INDIVIDUAL_STOCK),
    Asset("MSFT", "Microsoft", AssetClass.INDIVIDUAL_STOCK),
    Asset("GOOGL", "Alphabet", AssetClass.INDIVIDUAL_STOCK),
    Asset("AMZN", "Amazon", AssetClass.INDIVIDUAL_STOCK),
    Asset("NVDA", "NVIDIA", AssetClass.INDIVIDUAL_STOCK),
    Asset("META", "Meta Platforms", AssetClass.INDIVIDUAL_STOCK),
    Asset("TSLA", "Tesla", AssetClass.INDIVIDUAL_STOCK),
    Asset("GLD", "SPDR Gold Shares", AssetClass.COMMODITY),
    Asset("SLV", "iShares Silver Trust", AssetClass.COMMODITY),
    Asset("PPLT", "abrdn Physical Platinum Shares ETF", AssetClass.COMMODITY),
    Asset("XLE", "Energy Select Sector SPDR Fund", AssetClass.SECTOR_ETF),
    Asset("VDE", "Vanguard Energy ETF", AssetClass.SECTOR_ETF),
    Asset("XLB", "Materials Select Sector SPDR Fund", AssetClass.SECTOR_ETF),
]


def _bitcoin_alert_metrics(temperature) -> dict[str, float | bool | None]:
    """Build independent, point-in-time BTC alert inputs for the current run."""
    # Keep the research stack lazy so non-Bitcoin refresh tooling stays light.
    from backend.app.api.bitcoin_research_state import _research_state_for_day

    research = _research_state_for_day(date.today())
    quantile = research.get("quantile")
    mvrv = research.get("mvrv")
    top_stage2 = research.get("top_stage2")
    return {
        "bitcoin_quantile_percentile": (
            quantile.get("percentile") if isinstance(quantile, dict) else None
        ),
        "bitcoin_mvrv_percentile": (
            mvrv.get("percentile") if isinstance(mvrv, dict) else None
        ),
        "bitcoin_top_stage2_active": (
            top_stage2.get("active") if isinstance(top_stage2, dict) else None
        ),
        "bitcoin_below_200d_ma": (
            temperature.current_price < temperature.sma_200d
            if temperature.sma_200d is not None else None
        ),
        "bitcoin_below_200w_ma": (
            temperature.current_price < temperature.sma_200w
            if temperature.sma_200w is not None else None
        ),
    }


@dataclass
class RefreshResult:
    processed: int
    failed: int
    notifications: list[AlertNotification]


async def refresh_market_temperature() -> RefreshResult:
    provider = YFinanceProvider()

    processed = 0
    failed = 0
    notifications: list[AlertNotification] = []

    with SessionLocal() as session:
        repository = MarketRepository(session)
        processor = AlertProcessor(repository)

        for asset in MARKET_ASSETS:
            try:
                weekly = provider.completed_weekly_history(
                    asset.symbol,
                    years=5,
                )

                daily = provider.daily_history(
                    asset.symbol,
                    years=2,
                )

                full_history = provider.full_history(
                    asset.symbol,
                )

                temperature = calculate_temperature(
                    asset,
                    weekly=weekly,
                    daily=daily,
                    full_history=full_history,
                )

                extra_metrics = (
                    _bitcoin_alert_metrics(temperature)
                    if asset.symbol == "BTC-USD"
                    else None
                )
                asset_notifications = processor.process_temperature(
                    temperature,
                    extra_metrics=extra_metrics,
                )

                for notification in asset_notifications:
                    state = repository.get_alert_state(
                        notification.rule_id
                    )

                    if state is None:
                        raise RuntimeError(
                            f"Alert state missing for rule "
                            f"{notification.rule_id}"
                        )

                    await send_alert_notification(
                        notification,
                        state,
                    )

                repository.commit()

                notifications.extend(asset_notifications)
                processed += 1

            except Exception as exc:
                repository.rollback()
                failed += 1

                print(
                    f"[WARN] {asset.symbol} refresh failed: "
                    f"{type(exc).__name__}: {exc}"
                )

    return RefreshResult(
        processed=processed,
        failed=failed,
        notifications=notifications,
    )


async def main() -> None:
    result = await refresh_market_temperature()

    print(
        f"Processed: {result.processed}, "
        f"Failed: {result.failed}, "
        f"Notifications: {len(result.notifications)}"
    )

    for notification in result.notifications:
        print(
            "[DELIVERED] "
            f"user={notification.telegram_user_id} "
            f"symbol={notification.symbol} "
            f"metric={notification.metric} "
            f"value={notification.current_value}"
        )


if __name__ == "__main__":
    asyncio.run(main())
