"""Shared callback handler connecting calendar UI to active investment flows."""

from __future__ import annotations

from datetime import date
from typing import Any

from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler

from bot.handlers.menu import build_main_menu
from bot.utils.calendar_keyboard import (
    CALENDAR_DATA_KEY,
    adjacent_month,
    build_month_calendar,
    build_month_picker,
    build_period_keyboard,
    build_year_picker,
    parse_calendar_callback,
)


def begin_calendar(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    flow: str,
    data_key: str,
    target: str,
    states: dict[str, int],
) -> None:
    context.user_data[CALENDAR_DATA_KEY] = {
        "flow": flow,
        "data_key": data_key,
        "target": target,
        "states": states,
    }


def clear_calendar(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop(CALENDAR_DATA_KEY, None)


async def handle_calendar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    action = parse_calendar_callback(query.data)
    calendar: dict[str, Any] | None = context.user_data.get(CALENDAR_DATA_KEY)
    if calendar is None:
        await query.answer("This calendar has expired. Please start again.", show_alert=True)
        return ConversationHandler.END
    today = date.today()
    states = calendar["states"]
    flow = context.user_data.setdefault(calendar["data_key"], {})

    if action.action == "noop":
        await query.answer()
        return states[calendar["target"]]
    if action.action == "cancel":
        await query.answer()
        context.user_data.pop(calendar["data_key"], None)
        clear_calendar(context)
        await query.message.reply_text(
            "Cancelled. Back to the main menu.", reply_markup=build_main_menu()
        )
        return ConversationHandler.END
    if action.action == "back":
        await query.answer()
        clear_calendar(context)
        await query.edit_message_text("Returning to period selection.")
        await query.message.reply_text("Choose a period:", reply_markup=build_period_keyboard())
        return states["period"]

    markup = _navigation_markup(action.action, action.values, today)
    if markup is not None:
        await query.answer()
        await query.edit_message_text(_navigation_prompt(action.action), reply_markup=markup)
        return states[calendar["target"]]

    selected = action.selected_date
    if selected is None or selected > today:
        await query.answer("Future dates are not supported.", show_alert=True)
        return states[calendar["target"]]
    if calendar["target"] == "end" and selected < flow["start_date"]:
        await query.answer("End date cannot be before the start date.", show_alert=True)
        return states["end"]

    await query.answer()
    target = calendar["target"]
    flow[f"{target}_date"] = selected
    await query.edit_message_text(f"âœ… {target.title()} date: {selected.isoformat()}")
    if target == "start":
        calendar["target"] = "end"
        await query.message.reply_text(
            "Choose end date\n\nYou can also type a date as YYYY-MM-DD.",
            reply_markup=build_year_picker(today.year, max_date=today),
        )
        return states["end"]

    clear_calendar(context)
    keyboard = ReplyKeyboardMarkup((("Daily", "Weekly", "Monthly"),), resize_keyboard=True)
    await query.message.reply_text("Choose a frequency:", reply_markup=keyboard)
    return states["frequency"]


def _navigation_markup(action: str, values: tuple[int, ...], today: date):
    if action in {"years", "older", "newer"}:
        return build_year_picker(values[0], max_date=today)
    if action in {"year", "months"}:
        return build_month_picker(values[0], max_date=today)
    if action == "month":
        return build_month_calendar(*values, max_date=today)
    if action in {"prev", "next"}:
        year, month = adjacent_month(*values, -1 if action == "prev" else 1)
        return build_month_calendar(year, month, max_date=today)
    return None


def _navigation_prompt(action: str) -> str:
    return "Choose year:" if action in {"years", "older", "newer"} else "Choose date:"
