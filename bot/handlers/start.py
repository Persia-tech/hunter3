"""Telegram welcome command."""

from telegram import KeyboardButton, ReplyKeyboardMarkup, Update, WebAppInfo
from telegram.ext import ContextTypes

from bot.handlers.constants import WELCOME_TEXT
from bot.handlers.menu import build_main_menu
from bot.telegram_webapp import valid_mini_app_url


def build_start_menu(app_url: str | None) -> ReplyKeyboardMarkup:
    """Add the Mini App to the existing chat keyboard without a second message."""

    menu = build_main_menu()
    valid_url = valid_mini_app_url(app_url)
    if not valid_url:
        return menu
    return ReplyKeyboardMarkup(
        [[KeyboardButton("Open DCA App", web_app=WebAppInfo(url=valid_url))], *menu.keyboard],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Choose an option",
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Welcome a user and show the reusable main menu."""

    if update.effective_message:
        await update.effective_message.reply_text(
            WELCOME_TEXT,
            reply_markup=build_start_menu(context.application.bot_data.get("mini_app_url")),
        )
