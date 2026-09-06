"""Environment-based application configuration.

Stage 1 deliberately keeps configuration small. Later stages can extend this
module without putting tokens or API keys in source control.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

# Central production guardrails. These are intentionally code constants so a
# deployment cannot accidentally disable them through an untrusted environment.
MAX_COMPARE_ASSETS = 10
MAX_DAILY_YEARS = 10
MAX_WEEKLY_YEARS = 20
MAX_DCA_PURCHASES = 5000
MAX_COMPARISON_WORK_UNITS = 20000
HEAVY_ACTION_COOLDOWN_SECONDS = 8.0
CURRENT_PRICES_COOLDOWN_SECONDS = 4.0
CURRENT_PRICE_CACHE_TTL_SECONDS = 20.0
MARKET_DATA_MAX_ATTEMPTS = 2
MARKET_DATA_RETRY_DELAY_SECONDS = 0.2
# A 24/7 market can still have an isolated delayed or omitted provider candle.
# Scheduled purchases may use the next real completed candle within this bound.
CRYPTO_LOOKUP_WINDOW_DAYS = 2


class ConfigurationError(RuntimeError):
    """Raised when a required setting is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    """Settings needed to start the Telegram bot."""

    telegram_bot_token: str
    market_data_api_key: str | None = None
    mini_app_url: str | None = None


def load_settings() -> Settings:
    """Load settings from ``.env`` and the process environment.

    Existing process environment values take priority over values in ``.env``.
    The token itself is never logged or included in an error message.
    """

    # Be explicit about precedence: shell/container variables must never be
    # replaced by values from a developer's local .env file.
    load_dotenv(override=False)
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token or token == "your_telegram_bot_token_here":
        raise ConfigurationError(
            "TELEGRAM_BOT_TOKEN is missing. Copy .env.example to .env and add "
            "the token supplied by BotFather."
        )

    api_key = os.getenv("MARKET_DATA_API_KEY", "").strip() or None
    mini_app_url = os.getenv("MINI_APP_URL", "").strip() or None
    return Settings(
        telegram_bot_token=token,
        market_data_api_key=api_key,
        mini_app_url=mini_app_url,
    )
