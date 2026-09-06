"""Telegram delivery for Hunter2 market alerts."""

from __future__ import annotations

from datetime import datetime, timezone

from telegram import Bot

from backend.app.config import ConfigurationError, load_settings
from backend.app.db.models import AlertState
from backend.app.services.alert_processor import AlertNotification


def _format_alert_message(notification: AlertNotification) -> str:
    evaluation = notification.evaluation

    if evaluation.entered:
        event = "Triggered"
    elif evaluation.exited:
        event = "Cleared"
    else:
        event = "Updated"

    return (
        "Hunter2 Market Alert\n\n"
        f"{event}: {notification.symbol}\n"
        f"Metric: {notification.metric}\n"
        f"Condition: {notification.operator}\n"
        f"Current value: {notification.current_value}"
    )


async def send_alert_notification(
    notification: AlertNotification,
    state: AlertState,
    *,
    token: str | None = None,
) -> None:
    """Send one Telegram alert and mark it delivered only on success."""

    telegram_token = (
        token
        if token is not None
        else load_settings().telegram_bot_token
    )

    if not telegram_token.strip():
        raise ConfigurationError(
            "TELEGRAM_BOT_TOKEN is missing or blank."
        )

    if notification.delivery_channel != "telegram":
        raise ValueError(
            f"Unsupported delivery channel: "
            f"{notification.delivery_channel}"
        )

    bot = Bot(token=telegram_token)

    await bot.send_message(
        chat_id=notification.telegram_user_id,
        text=_format_alert_message(notification),
    )

    state.last_notified_at = datetime.now(timezone.utc)
    state.updated_at = state.last_notified_at