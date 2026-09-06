"""Main-menu keyboard and navigation handlers."""

from __future__ import annotations

from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.handlers.constants import (
    ACTIVE_FLOW_DATA_KEYS,
    CALCULATE_DCA,
    COMPARE_ASSETS,
    CURRENT_PRICES,
    DCA_VS_LUMP_SUM,
    HELP,
)


def build_main_menu() -> ReplyKeyboardMarkup:
    """Build the persistent, mobile-friendly main navigation keyboard."""

    return ReplyKeyboardMarkup(
        (
            (CALCULATE_DCA,),
            (COMPARE_ASSETS, DCA_VS_LUMP_SUM),
            (CURRENT_PRICES, HELP),
        ),
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Choose an option",
    )


async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display the main menu for the ``/menu`` command."""

    del context
    if update.effective_message:
        await update.effective_message.reply_text(
            "Main menu â€” choose an option:", reply_markup=build_main_menu()
        )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reset the current interaction and return to the main menu."""

    del context
    if update.effective_message:
        await update.effective_message.reply_text(
            "Cancelled. Back to the main menu.", reply_markup=build_main_menu()
        )


async def unknown_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Recover gracefully when text does not match a main-menu action."""

    user_data = getattr(context, "user_data", {})
    if any(key in user_data for key in ACTIVE_FLOW_DATA_KEYS):
        return
    if update.effective_message:
        await update.effective_message.reply_text(
            "I didn't recognize that option. Please choose a menu button.",
            reply_markup=build_main_menu(),
        )
