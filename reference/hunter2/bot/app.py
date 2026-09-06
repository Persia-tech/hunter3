"""Telegram DCA bot application construction and polling entry point."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from telegram import Update
from telegram.ext import Application, ContextTypes

from backend.app.config import ConfigurationError, load_settings
from bot.handlers import register_handlers
from bot.telegram_webapp import configure_menu_button, valid_mini_app_url

if TYPE_CHECKING:
    from bot.charts import ChartService
    from backend.app.services.comparison import DCAComparisonService
    from backend.app.services.current_prices import CurrentPricesService
    from backend.app.services.dca_calculator import DCACalculator
    from backend.app.services.lump_sum import DCAvsLumpSumService
    from backend.app.services.dca_market_data import MarketDataService
    from backend.app.services.rate_limit import PerUserRateLimiter

LOGGER = logging.getLogger(__name__)
GENERIC_ERROR_MESSAGE = "Something went wrong. Please try again or use /menu."


def build_application(
    token: str | None = None,
    dca_calculator: DCACalculator | None = None,
    comparison_service: DCAComparisonService | None = None,
    lump_sum_service: DCAvsLumpSumService | None = None,
    market_data: MarketDataService | None = None,
    current_prices_service: CurrentPricesService | None = None,
    chart_service: ChartService | None = None,
    rate_limiter: PerUserRateLimiter | None = None,
    mini_app_url: str | None = None,
) -> Application:
    """Build the Telegram application without starting polling.

    An injected token keeps construction tests offline. Normal startup always
    loads the token through the existing environment configuration.
    """

    telegram_token = token if token is not None else load_settings().telegram_bot_token
    if not telegram_token.strip():
        raise ConfigurationError("TELEGRAM_BOT_TOKEN is missing or blank.")
    resolved_mini_app_url = valid_mini_app_url(
        mini_app_url if mini_app_url is not None else os.getenv("MINI_APP_URL")
    )
    application = (
        Application.builder().token(telegram_token).post_init(configure_menu_button).build()
    )
    application.bot_data["mini_app_url"] = resolved_mini_app_url
    if dca_calculator is None:
        from backend.app.services.dca_calculator import DCACalculator
        from backend.app.services.dca_market_data import MarketDataService
        from backend.app.providers.dca_yfinance_provider import YFinanceProvider

        market_data = MarketDataService(YFinanceProvider())
        dca_calculator = DCACalculator(market_data)
    from bot.handlers.compare import COMPARISON_SERVICE_KEY
    from bot.handlers.current_prices import CURRENT_PRICES_SERVICE_KEY
    from bot.handlers.dca import DCA_CALCULATOR_KEY
    from bot.handlers.guardrails import RATE_LIMITER_KEY
    from bot.handlers.lump_sum import LUMP_SERVICE_KEY
    from bot.charts import CHART_SERVICE_KEY, ChartService
    from backend.app.services.comparison import DCAComparisonService
    from backend.app.services.current_prices import CurrentPricesService
    from backend.app.services.lump_sum import DCAvsLumpSumService
    from backend.app.services.rate_limit import PerUserRateLimiter

    application.bot_data[DCA_CALCULATOR_KEY] = dca_calculator
    application.bot_data[COMPARISON_SERVICE_KEY] = comparison_service or DCAComparisonService(
        dca_calculator
    )
    resolved_market_data = market_data or getattr(dca_calculator, "_market_data", None)
    application.bot_data[LUMP_SERVICE_KEY] = lump_sum_service or DCAvsLumpSumService(
        dca_calculator, resolved_market_data
    )
    application.bot_data[CURRENT_PRICES_SERVICE_KEY] = (
        current_prices_service or CurrentPricesService(resolved_market_data)
    )
    application.bot_data[CHART_SERVICE_KEY] = chart_service or ChartService()
    application.bot_data[RATE_LIMITER_KEY] = rate_limiter or PerUserRateLimiter()
    register_handlers(application)
    application.add_error_handler(handle_error)
    return application


async def handle_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log an unexpected handler failure and give the user a safe response."""

    error = context.error
    error_info = None
    if error is not None:
        error_info = (type(error), error, error.__traceback__)
    LOGGER.error("Unexpected Telegram handler error", exc_info=error_info)

    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(GENERIC_ERROR_MESSAGE)
        except Exception:
            LOGGER.exception("Could not send the generic Telegram error response")


def main() -> None:
    """Load configuration and run the bot until polling is stopped."""

    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        level=logging.INFO,
    )
    application = build_application()
    LOGGER.info("Starting Telegram DCA bot polling")
    try:
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    finally:
        LOGGER.info("Telegram DCA bot stopped")


if __name__ == "__main__":
    main()
