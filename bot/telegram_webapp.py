"""Shared Telegram Mini App URL validation and menu-button setup."""

from __future__ import annotations

from urllib.parse import urlparse

from telegram import MenuButtonWebApp, WebAppInfo
from telegram.ext import Application


def valid_mini_app_url(value: str | None) -> str | None:
    """Return a usable HTTP(S) Mini App URL, otherwise ``None``."""

    candidate = (value or "").strip()
    parsed = urlparse(candidate)
    if parsed.scheme != "https" or not parsed.netloc:
        return None
    return candidate


async def configure_menu_button(application: Application) -> None:
    """Configure Telegram's persistent menu only when a valid URL is available."""

    mini_app_url = application.bot_data.get("mini_app_url")
    if mini_app_url:
        await application.bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="Open DCA App", web_app=WebAppInfo(url=mini_app_url)
            )
        )
