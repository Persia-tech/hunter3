"""Telegram Web App init-data verification without trusting browser identity."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl


def _parse_init_data(init_data: str) -> dict[str, str]:
    return dict(parse_qsl(init_data, keep_blank_values=True))


def validate_init_data(
    init_data: str,
    bot_token: str,
    max_age_seconds: int = 3600,
) -> bool:
    """Validate Telegram's signed query string and reject stale payloads."""

    values = _parse_init_data(init_data)

    supplied_hash = values.pop("hash", "")

    if not supplied_hash or not values.get("auth_date", "").isdigit():
        return False

    if abs(time.time() - int(values["auth_date"])) > max_age_seconds:
        return False

    check_string = "\n".join(
        f"{key}={values[key]}"
        for key in sorted(values)
    )

    secret = hmac.new(
        b"WebAppData",
        bot_token.encode(),
        hashlib.sha256,
    ).digest()

    expected = hmac.new(
        secret,
        check_string.encode(),
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(
        expected,
        supplied_hash,
    )


def get_telegram_user_id(
    init_data: str,
    bot_token: str,
    max_age_seconds: int = 3600,
) -> str | None:
    """Return the authenticated Telegram user ID from signed init data."""

    if not validate_init_data(
        init_data,
        bot_token,
        max_age_seconds=max_age_seconds,
    ):
        return None

    values = _parse_init_data(init_data)
    raw_user = values.get("user")

    if not raw_user:
        return None

    try:
        user = json.loads(raw_user)
    except (json.JSONDecodeError, TypeError):
        return None

    user_id = user.get("id")

    if not isinstance(user_id, int):
        return None

    return str(user_id)