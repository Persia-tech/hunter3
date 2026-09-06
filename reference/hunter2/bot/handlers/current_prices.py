"""Telegram handlers for on-demand current-price snapshots."""

from __future__ import annotations

import asyncio
import logging

from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from backend.app.config import CURRENT_PRICES_COOLDOWN_SECONDS
from bot.handlers.guardrails import enforce_cooldown
from bot.handlers.menu import build_main_menu
from backend.app.services.current_prices import CurrentPricesError, CurrentPricesService
from bot.utils.formatting import format_current_prices

LOGGER = logging.getLogger(__name__)
CURRENT_PRICES_SERVICE_KEY = "current_prices_service"
REFRESH_PRICES = "ðŸ”„ Refresh Prices"
MAIN_MENU = "ðŸ  Main Menu"


def build_prices_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        ((REFRESH_PRICES, MAIN_MENU),), resize_keyboard=True, is_persistent=True
    )


async def show_current_prices(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fetch without blocking the event loop and show a complete snapshot."""

    if not await enforce_cooldown(
        update,
        context,
        action="current_prices",
        cooldown_seconds=CURRENT_PRICES_COOLDOWN_SECONDS,
    ):
        return
    service: CurrentPricesService = context.bot_data[CURRENT_PRICES_SERVICE_KEY]
    if update.effective_message:
        await update.effective_message.reply_text("Fetching current prices...")
    try:
        result = await asyncio.to_thread(service.get_all)
    except CurrentPricesError:
        LOGGER.exception("All current-price lookups failed")
        if update.effective_message:
            await update.effective_message.reply_text(
                "Current prices are temporarily unavailable. Please try again.",
                reply_markup=build_main_menu(),
            )
        return
    if update.effective_message:
        await update.effective_message.reply_text(
            format_current_prices(result), reply_markup=build_prices_keyboard()
        )
