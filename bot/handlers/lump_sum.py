"""Telegram conversation for equal-capital DCA versus lump sum."""

from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import Any

from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler

from backend.app.config import HEAVY_ACTION_COOLDOWN_SECONDS
from bot.handlers.calendar import begin_calendar, clear_calendar
from bot.handlers.dca import (
    FREQUENCY_LABELS,
    _asset_keyboard,
    _extract_symbol,
)
from bot.handlers.guardrails import enforce_cooldown
from bot.handlers.menu import build_main_menu
from backend.app.models.asset import UnsupportedAssetError, get_asset
from bot.charts import CHART_SERVICE_KEY, ChartGenerationError, ChartService
from backend.app.services.limits import RequestLimitError, validate_dca_workload
from backend.app.services.lump_sum import DCAvsLumpSumError, DCAvsLumpSumService
from bot.utils.calendar_keyboard import (
    CALENDAR_DATA_KEY,
    CUSTOM_DATES,
    PERIOD_PRESETS,
    build_period_keyboard,
    build_year_picker,
    preset_date_range,
)
from bot.utils.formatting import format_currency, format_dca_vs_lump_sum_result
from bot.utils.validation import (
    parse_date_input,
    parse_positive_decimal,
    validate_date_not_future,
    validate_date_range,
)

LOGGER = logging.getLogger(__name__)

(
    LUMP_SELECT_ASSET,
    LUMP_PERIOD,
    LUMP_START_DATE,
    LUMP_END_DATE,
    LUMP_FREQUENCY,
    LUMP_AMOUNT,
    LUMP_CONFIRM,
) = range(30, 37)
LUMP_DATA_KEY = "lump_sum"
LUMP_SERVICE_KEY = "dca_vs_lump_sum_service"
COMPARE = "âœ… Compare"
CANCEL = "âŒ Cancel"


def _flow(context: ContextTypes.DEFAULT_TYPE) -> dict[str, Any]:
    return context.user_data.setdefault(LUMP_DATA_KEY, {})


def _clear(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop(LUMP_DATA_KEY, None)
    context.user_data.pop(CALENDAR_DATA_KEY, None)


def _text(update: Update) -> str:
    return (update.effective_message.text or "").strip() if update.effective_message else ""


async def start_lump_sum(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    _clear(context)
    _flow(context)
    await update.effective_message.reply_text(
        "Choose one asset:", reply_markup=_asset_keyboard()
    )
    return LUMP_SELECT_ASSET


async def lump_select_asset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        asset = get_asset(_extract_symbol(_text(update)))
    except UnsupportedAssetError:
        await update.effective_message.reply_text(
            "Please choose a supported asset from the buttons.", reply_markup=_asset_keyboard()
        )
        return LUMP_SELECT_ASSET
    _flow(context)["asset"] = asset
    await update.effective_message.reply_text(
        "Choose a period:", reply_markup=build_period_keyboard()
    )
    return LUMP_PERIOD


async def lump_period(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    label = _text(update)
    if label == CUSTOM_DATES:
        begin_calendar(
            context,
            flow="lump_sum",
            data_key=LUMP_DATA_KEY,
            target="start",
            states={
                "period": LUMP_PERIOD,
                "start": LUMP_START_DATE,
                "end": LUMP_END_DATE,
                "frequency": LUMP_FREQUENCY,
            },
        )
        today = date.today()
        await update.effective_message.reply_text(
            "Choose start date\n\nYou can also type a date as YYYY-MM-DD.",
            reply_markup=build_year_picker(today.year, max_date=today),
        )
        return LUMP_START_DATE
    if label not in PERIOD_PRESETS:
        await update.effective_message.reply_text(
            "Please choose one of the period buttons.", reply_markup=build_period_keyboard()
        )
        return LUMP_PERIOD
    start, end = preset_date_range(label, today=date.today())
    flow = _flow(context)
    flow["start_date"], flow["end_date"] = start, end
    keyboard = ReplyKeyboardMarkup((tuple(FREQUENCY_LABELS),), resize_keyboard=True)
    await update.effective_message.reply_text(
        f"Period: {start.isoformat()} â†’ {end.isoformat()}\n\nChoose a frequency:",
        reply_markup=keyboard,
    )
    return LUMP_FREQUENCY


async def lump_start_date(
    update: Update, context: ContextTypes.DEFAULT_TYPE, *, current_date: date | None = None
) -> int:
    today = current_date or date.today()
    try:
        entered = parse_date_input(_text(update), current_date=today)
    except ValueError:
        await update.effective_message.reply_text("Invalid date. Please use YYYY-MM-DD or today.")
        return LUMP_START_DATE
    try:
        validate_date_not_future(entered, current_date=today)
    except ValueError:
        await update.effective_message.reply_text(
            "Future dates are not supported. Please try again."
        )
        return LUMP_START_DATE
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
    return LUMP_END_DATE


async def lump_end_date(
    update: Update, context: ContextTypes.DEFAULT_TYPE, *, current_date: date | None = None
) -> int:
    today = current_date or date.today()
    try:
        entered = parse_date_input(_text(update), current_date=today)
    except ValueError:
        await update.effective_message.reply_text("Invalid date. Please use YYYY-MM-DD or today.")
        return LUMP_END_DATE
    try:
        validate_date_not_future(entered, current_date=today)
    except ValueError:
        await update.effective_message.reply_text(
            "Future dates are not supported. Please try again."
        )
        return LUMP_END_DATE
    try:
        validate_date_range(_flow(context)["start_date"], entered)
    except ValueError:
        await update.effective_message.reply_text("End date cannot be before the start date.")
        return LUMP_END_DATE
    _flow(context)["end_date"] = entered
    clear_calendar(context)
    keyboard = ReplyKeyboardMarkup((tuple(FREQUENCY_LABELS),), resize_keyboard=True)
    await update.effective_message.reply_text("Choose a frequency:", reply_markup=keyboard)
    return LUMP_FREQUENCY


async def lump_frequency(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    frequency = FREQUENCY_LABELS.get(_text(update).title())
    if frequency is None:
        await update.effective_message.reply_text("Please choose Daily, Weekly, or Monthly.")
        return LUMP_FREQUENCY
    _flow(context)["frequency"] = frequency
    await update.effective_message.reply_text(
        "How much would you like to invest each period?\n\nExample: 500"
    )
    return LUMP_AMOUNT


async def lump_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        amount = parse_positive_decimal(_text(update))
    except ValueError:
        await update.effective_message.reply_text(
            "Invalid amount. Enter a number greater than zero, for example 500."
        )
        return LUMP_AMOUNT
    flow = _flow(context)
    flow["investment_amount"] = amount
    frequency = flow["frequency"].value
    period = {"daily": "day", "weekly": "week", "monthly": "month"}[frequency]
    try:
        estimated_purchases = validate_dca_workload(
            flow["start_date"], flow["end_date"], flow["frequency"]
        )
    except RequestLimitError as exc:
        await update.effective_message.reply_text(str(exc))
        return LUMP_AMOUNT
    estimated_capital = amount * estimated_purchases
    confirmation = (
        "Please confirm:\n\n"
        f"Asset:\n{flow['asset'].symbol}\n\n"
        f"Period:\n{flow['start_date'].isoformat()} â†’ {flow['end_date'].isoformat()}\n\n"
        f"Frequency:\n{frequency.title()}\n\n"
        f"DCA:\n{format_currency(amount)} per {period}\n\n"
        f"Estimated total capital:\n{format_currency(estimated_capital)}\n\n"
        "Comparison:\nDCA vs an equal-capital lump sum invested at the start.\n\n"
        "The lump-sum amount will equal the total capital contributed by the DCA strategy."
    )
    keyboard = ReplyKeyboardMarkup(((COMPARE, CANCEL),), resize_keyboard=True)
    await update.effective_message.reply_text(confirmation, reply_markup=keyboard)
    return LUMP_CONFIRM


async def run_lump_sum(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    flow = _flow(context)
    if not await enforce_cooldown(
        update,
        context,
        action="heavy_calculation",
        cooldown_seconds=HEAVY_ACTION_COOLDOWN_SECONDS,
    ):
        return LUMP_CONFIRM
    if flow.get("calculating"):
        return LUMP_CONFIRM
    flow["calculating"] = True
    await update.effective_message.reply_text("Comparing DCA with lump sum...")
    service: DCAvsLumpSumService = context.bot_data[LUMP_SERVICE_KEY]
    LOGGER.info(
        "DCA vs lump-sum started asset=%s start=%s end=%s frequency=%s",
        flow["asset"].symbol,
        flow["start_date"],
        flow["end_date"],
        flow["frequency"].value,
    )
    try:
        result = await asyncio.to_thread(
            service.compare,
            flow["asset"],
            flow["start_date"],
            flow["end_date"],
            flow["frequency"],
            flow["investment_amount"],
        )
    except RequestLimitError as exc:
        LOGGER.warning("Lump-sum request rejected by workload limit")
        await update.effective_message.reply_text(
            str(exc), reply_markup=build_main_menu()
        )
        _clear(context)
        return ConversationHandler.END
    except DCAvsLumpSumError:
        LOGGER.exception("DCA vs lump-sum comparison failed for %s", flow["asset"].symbol)
        await update.effective_message.reply_text(
            "I couldn't complete the DCA vs Lump Sum comparison because market data was "
            "unavailable. Please try again or use a different date range.",
            reply_markup=build_main_menu(),
        )
        _clear(context)
        return ConversationHandler.END
    LOGGER.info(
        "DCA vs lump-sum completed asset=%s requested_end=%s effective_end=%s",
        result.dca.asset.symbol,
        result.dca.requested_end_date or result.dca.end_date,
        result.dca.end_date,
    )
    await update.effective_message.reply_text(
        format_dca_vs_lump_sum_result(result), reply_markup=build_main_menu()
    )
    chart_service: ChartService | None = context.bot_data.get(CHART_SERVICE_KEY)
    if chart_service is not None:
        try:
            chart = await asyncio.to_thread(
                chart_service.build_dca_vs_lump_sum_chart, result
            )
        except ChartGenerationError:
            LOGGER.exception("DCA vs lump-sum chart generation failed")
            await update.effective_message.reply_text(
                "The comparison succeeded, but the chart could not be generated."
            )
        else:
            await update.effective_message.reply_photo(photo=chart)
    _clear(context)
    return ConversationHandler.END


async def cancel_lump_sum(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    _clear(context)
    await update.effective_message.reply_text(
        "Cancelled. Back to the main menu.", reply_markup=build_main_menu()
    )
    return ConversationHandler.END


async def menu_from_lump_sum(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    _clear(context)
    await update.effective_message.reply_text(
        "Main menu â€” choose an option:", reply_markup=build_main_menu()
    )
    return ConversationHandler.END


async def leave_lump_sum_for_navigation(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    del update
    _clear(context)
    return ConversationHandler.END
