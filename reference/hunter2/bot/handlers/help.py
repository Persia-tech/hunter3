"""Telegram help command and Help-button behavior."""

from telegram import Update
from telegram.ext import ContextTypes

from bot.handlers.constants import HELP_TEXT
from bot.handlers.menu import build_main_menu


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Explain current and planned bot capabilities."""

    del context
    if update.effective_message:
        await update.effective_message.reply_text(
            HELP_TEXT, reply_markup=build_main_menu()
        )
