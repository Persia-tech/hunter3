"""Shared validation for Telegram investment flows."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation


def parse_date_input(text: str, *, current_date: date, allow_today: bool = True) -> date:
    """Parse an ISO date or the case-insensitive word ``today``."""

    normalized = text.strip()
    if allow_today and normalized.casefold() == "today":
        return current_date
    try:
        return date.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("invalid date") from exc


def validate_date_not_future(value: date, *, current_date: date) -> None:
    if value > current_date:
        raise ValueError("future date")


def validate_date_range(start_date: date, end_date: date) -> None:
    if end_date < start_date:
        raise ValueError("end date before start date")


def parse_positive_decimal(text: str) -> Decimal:
    """Parse a finite positive Decimal, accepting one optional USD prefix."""

    normalized = text.strip()
    if normalized.startswith("$"):
        normalized = normalized[1:].strip()
    try:
        value = Decimal(normalized)
    except InvalidOperation as exc:
        raise ValueError("invalid amount") from exc
    if not value.is_finite() or value <= 0:
        raise ValueError("invalid amount")
    return value
