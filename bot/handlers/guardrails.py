"""Shared Telegram-facing operational guardrails."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from backend.app.services.rate_limit import PerUserRateLimiter

LOGGER = logging.getLogger(__name__)
RATE_LIMITER_KEY = "rate_limiter"


async def enforce_cooldown(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    action: str,
    cooldown_seconds: float,
) -> bool:
    """Return false with a safe response when this user is cooling down."""

    user_id = getattr(getattr(update, "effective_user", None), "id", None)
    if user_id is None:
        return True
    limiter: PerUserRateLimiter = context.bot_data[RATE_LIMITER_KEY]
    if limiter.allow(user_id, action, cooldown_seconds):
        return True
    LOGGER.warning("Rate limit applied action=%s", action)
    if update.effective_message:
        await update.effective_message.reply_text(
            "Please wait a few seconds before running another calculation."
        )
    return False
