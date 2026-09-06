"""Telegram conversation for fair multi-asset DCA comparisons."""

from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler

from backend.app.config import HEAVY_ACTION_COOLDOWN_SECONDS, MAX_COMPARE_ASSETS
from bot.handlers.calendar import begin_calendar, clear_calendar
from bot.handlers.dca import FREQUENCY_LABELS
from bot.handlers.guardrails import enforce_cooldown
from bot.handlers.menu import build_main_menu
from backend.app.models.asset import SUPPORTED_ASSETS
from bot.charts import CHART_SERVICE_KEY, ChartGenerationError, ChartService
from backend.app.services.comparison import DCAComparisonError, DCAComparisonService
from backend.app.services.limits import RequestLimitError
from bot.utils.calendar_keyboard import (
    CALENDAR_DATA_KEY,
    CUSTOM_DATES,
    PERIOD_PRESETS,
    build_period_keyboard,
    build_year_picker,
    preset_date_range,
)
from bot.utils.formatting import format_comparison_result, format_currency
from bot.utils.validation import (
    parse_date_input,
    parse_positive_decimal,
    validate_date_not_future,
    validate_date_range,
)

LOGGER = logging.getLogger(__name__)

(
    COMPARE_SELECT_ASSETS,
    COMPARE_PERIOD,
    COMPARE_START_DATE,
    COMPARE_END_DATE,
    COMPARE_FREQUENCY,
    COMPARE_AMOUNT,
    COMPARE_CONFIRM,
) = range(20, 27)
COMPARE_DATA_KEY = "compare"
COMPARISON_SERVICE_KEY = "dca_comparison_service"
COMPARE = "âœ… Compare"
CANCEL = "âŒ Cancel"


def _flow(context: ContextTypes.DEFAULT_TYPE) -> dict[str, Any]:
    return context.user_data.setdefault(COMPARE_DATA_KEY, {"assets": []})


def _clear(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop(COMPARE_DATA_KEY, None)
    context.user_data.pop(CALENDAR_DATA_KEY, None)


def _text(update: Update) -> str:
    return (update.effective_message.text or "").strip() if update.effective_message else ""


def _asset_keyboard(selected: list[str]) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(
            f"{'âœ…' if symbol in selected else 'â¬œ'} {symbol}",
            callback_data=f"compare:asset:{symbol}",
        )
        for symbol in SUPPORTED_ASSETS
    ]
    rows = [buttons[index : index + 3] for index in range(0, len(buttons), 3)]
    rows.append(
        [
            InlineKeyboardButton("âœ… Done", callback_data="compare:done"),
            InlineKeyboardButton("âŒ Cancel", callback_data="compare:cancel"),
        ]
    )
    return InlineKeyboardMarkup(rows)


async def start_compare(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    _clear(context)
    selected = _flow(context)["assets"]
    await update.effective_message.reply_text(
        "Select at least two assets to compare:", reply_markup=_asset_keyboard(selected)
    )
    return COMPARE_SELECT_ASSETS


async def select_compare_asset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    action = query.data.removeprefix("compare:")
    if action == "cancel":
        await query.answer()
        return await _cancel_query(update, context)
    selected = _flow(context)["assets"]
    if action == "done":
        if len(selected) < 2:
            await query.answer("Please select at least two assets to compare.", show_alert=True)
            return COMPARE_SELECT_ASSETS
        await query.answer()
        await query.edit_message_text("Asset selection complete.")
        await query.message.reply_text("Choose a period:", reply_markup=build_period_keyboard())
        return COMPARE_PERIOD
    await query.answer()
    symbol = action.removeprefix("asset:")
    if symbol in SUPPORTED_ASSETS:
        if symbol in selected:
            selected.remove(symbol)
        else:
            if len(selected) >= MAX_COMPARE_ASSETS:
                await query.answer(
                    f"Please choose up to {MAX_COMPARE_ASSETS} assets.", show_alert=True
                )
                return COMPARE_SELECT_ASSETS
            selected.append(symbol)
        await query.edit_message_reply_markup(reply_markup=_asset_keyboard(selected))
    return COMPARE_SELECT_ASSETS


async def compare_period(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    label = _text(update)
    if label == CUSTOM_DATES:
        begin_calendar(
            context,
            flow="compare",
            data_key=COMPARE_DATA_KEY,
            target="start",
            states={
                "period": COMPARE_PERIOD,
                "start": COMPARE_START_DATE,
                "end": COMPARE_END_DATE,
                "frequency": COMPARE_FREQUENCY,
            },
        )
        today = date.today()
        await update.effective_message.reply_text(
            "Choose start date\n\nYou can also type a date as YYYY-MM-DD.",
            reply_markup=build_year_picker(today.year, max_date=today),
        )
        return COMPARE_START_DATE
    if label not in PERIOD_PRESETS:
        await update.effective_message.reply_text(
            "Please choose one of the period buttons.", reply_markup=build_period_keyboard()
        )
        return COMPARE_PERIOD
    start, end = preset_date_range(label, today=date.today())
    flow = _flow(context)
    flow["start_date"], flow["end_date"] = start, end
    keyboard = ReplyKeyboardMarkup((tuple(FREQUENCY_LABELS),), resize_keyboard=True)
    await update.effective_message.reply_text(
        f"Period: {start.isoformat()} â†’ {end.isoformat()}\n\nChoose a frequency:",
        reply_markup=keyboard,
    )
    return COMPARE_FREQUENCY


async def compare_start_date(
    update: Update, context: ContextTypes.DEFAULT_TYPE, *, current_date: date | None = None
) -> int:
    today = current_date or date.today()
    try:
        entered = parse_date_input(_text(update), current_date=today)
    except ValueError:
        await update.effective_message.reply_text("Invalid date. Please use YYYY-MM-DD or today.")
        return COMPARE_START_DATE
    try:
        validate_date_not_future(entered, current_date=today)
    except ValueError:
        await update.effective_message.reply_text(
            "Future dates are not supported. Please try again."
        )
        return COMPARE_START_DATE
    _flow(context)["start_date"] = entered
    calendar = context.user_data.get(CALENDAR_DATA_KEY)
    if calendar:
        calendar["target"] = "end"
        await update.effective_message.reply_text(
            f"âœ… Start date: {entered.isoformat()}\n\nChoose end date. "
            "You can also type YYYY-MM-DD.",
            reply_markup=build_year_picker(today.year, max_date=today),
        )
    else:
        await update.effective_message.reply_text(
            "Enter the end date in YYYY-MM-DD format, or type today."
        )
    return COMPARE_END_DATE


async def compare_end_date(
    update: Update, context: ContextTypes.DEFAULT_TYPE, *, current_date: date | None = None
) -> int:
    today = current_date or date.today()
    try:
        entered = parse_date_input(_text(update), current_date=today)
    except ValueError:
        await update.effective_message.reply_text("Invalid date. Please use YYYY-MM-DD or today.")
        return COMPARE_END_DATE
    try:
        validate_date_not_future(entered, current_date=today)
    except ValueError:
        await update.effective_message.reply_text(
            "Future dates are not supported. Please try again."
        )
        return COMPARE_END_DATE
    try:
        validate_date_range(_flow(context)["start_date"], entered)
    except ValueError:
        await update.effective_message.reply_text("End date cannot be before the start date.")
        return COMPARE_END_DATE
    _flow(context)["end_date"] = entered
    clear_calendar(context)
    keyboard = ReplyKeyboardMarkup((tuple(FREQUENCY_LABELS),), resize_keyboard=True)
    await update.effective_message.reply_text("Choose a frequency:", reply_markup=keyboard)
    return COMPARE_FREQUENCY


async def compare_frequency(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    frequency = FREQUENCY_LABELS.get(_text(update).title())
    if frequency is None:
        await update.effective_message.reply_text("Please choose Daily, Weekly, or Monthly.")
        return COMPARE_FREQUENCY
    _flow(context)["frequency"] = frequency
    await update.effective_message.reply_text("Enter the investment amount per asset per period.")
    return COMPARE_AMOUNT


async def compare_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        amount = parse_positive_decimal(_text(update))
    except ValueError:
        await update.effective_message.reply_text(
            "Invalid amount. Enter a number greater than zero."
        )
        return COMPARE_AMOUNT
    flow = _flow(context)
    flow["investment_amount"] = amount
    frequency = flow["frequency"].value
    period_label = {"daily": "day", "weekly": "week", "monthly": "month"}[frequency]
    confirmation = (
        "Please confirm:\n\n"
        f"Assets:\n{', '.join(flow['assets'])}\n\n"
        f"Period:\n{flow['start_date'].isoformat()} â†’ {flow['end_date'].isoformat()}\n\n"
        f"Frequency:\n{frequency.title()}\n\n"
        f"Investment:\n{format_currency(amount)} per asset per {period_label}\n\n"
        "Important:\nEach asset receives the full contribution independently."
    )
    keyboard = ReplyKeyboardMarkup(((COMPARE, CANCEL),), resize_keyboard=True)
    await update.effective_message.reply_text(confirmation, reply_markup=keyboard)
    return COMPARE_CONFIRM


async def run_comparison(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    flow = _flow(context)
    if not await enforce_cooldown(
        update,
        context,
        action="heavy_calculation",
        cooldown_seconds=HEAVY_ACTION_COOLDOWN_SECONDS,
    ):
        return COMPARE_CONFIRM
    if flow.get("calculating"):
        return COMPARE_CONFIRM
    flow["calculating"] = True
    await update.effective_message.reply_text("Comparing assets...")
    service: DCAComparisonService = context.bot_data[COMPARISON_SERVICE_KEY]
    assets = tuple(SUPPORTED_ASSETS[symbol] for symbol in flow["assets"])
    LOGGER.info(
        "Asset comparison started assets=%s start=%s end=%s frequency=%s",
        ",".join(flow["assets"]),
        flow["start_date"],
        flow["end_date"],
        flow["frequency"].value,
    )
    try:
        results = await asyncio.to_thread(
            service.compare,
            assets,
            flow["start_date"],
            flow["end_date"],
            flow["frequency"],
            flow["investment_amount"],
        )
    except RequestLimitError as exc:
        LOGGER.warning("Comparison request rejected by workload limit")
        await update.effective_message.reply_text(
            str(exc), reply_markup=build_main_menu()
        )
        _clear(context)
        return ConversationHandler.END
    except DCAComparisonError as exc:
        LOGGER.exception("Comparison failed for %s", exc.asset.symbol)
        await update.effective_message.reply_text(
            "I couldn't complete the comparison because market data for "
            f"{exc.asset.symbol} could not be retrieved. Please try again or choose a "
            "different date range.",
            reply_markup=build_main_menu(),
        )
        _clear(context)
        return ConversationHandler.END
    LOGGER.info(
        "Asset comparison completed assets=%s effective_end=%s",
        len(results),
        results[0].end_date,
    )
    await update.effective_message.reply_text(
        format_comparison_result(results), reply_markup=build_main_menu()
    )
    chart_service: ChartService | None = context.bot_data.get(CHART_SERVICE_KEY)
    if chart_service is not None:
        try:
            chart = await asyncio.to_thread(chart_service.build_comparison_chart, results)
        except ChartGenerationError:
            LOGGER.exception("Comparison chart generation failed")
            await update.effective_message.reply_text(
                "The comparison succeeded, but the chart could not be generated."
            )
        else:
            await update.effective_message.reply_photo(photo=chart)
    _clear(context)
    return ConversationHandler.END


async def cancel_compare(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    _clear(context)
    await update.effective_message.reply_text(
        "Cancelled. Back to the main menu.", reply_markup=build_main_menu()
    )
    return ConversationHandler.END


async def menu_from_compare(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    _clear(context)
    await update.effective_message.reply_text(
        "Main menu â€” choose an option:", reply_markup=build_main_menu()
    )
    return ConversationHandler.END


async def leave_compare_for_navigation(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    del update
    _clear(context)
    return ConversationHandler.END


async def _cancel_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    _clear(context)
    await update.callback_query.message.reply_text(
        "Cancelled. Back to the main menu.", reply_markup=build_main_menu()
    )
    return ConversationHandler.END
