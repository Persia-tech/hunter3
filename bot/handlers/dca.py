"""Guided Telegram conversation for one-asset DCA calculations."""

from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import Any

from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler

from backend.app.config import HEAVY_ACTION_COOLDOWN_SECONDS
from bot.handlers.calendar import begin_calendar, clear_calendar
from bot.handlers.guardrails import enforce_cooldown
from bot.handlers.menu import build_main_menu
from backend.app.models.asset import SUPPORTED_ASSETS, UnsupportedAssetError, get_asset
from backend.app.models.dca import DCAFrequency
from bot.charts import CHART_SERVICE_KEY, ChartGenerationError, ChartService
from backend.app.services.dca_calculator import DCACalculationError, DCACalculator
from backend.app.services.limits import RequestLimitError
from backend.app.services.dca_market_data import MarketDataError
from bot.utils.calendar_keyboard import (
    CALENDAR_DATA_KEY,
    CUSTOM_DATES,
    PERIOD_PRESETS,
    build_period_keyboard,
    build_year_picker,
    preset_date_range,
)
from bot.utils.formatting import format_currency, format_dca_result
from bot.utils.validation import (
    parse_date_input,
    parse_positive_decimal,
    validate_date_not_future,
    validate_date_range,
)

LOGGER = logging.getLogger(__name__)

(
    SELECT_ASSET,
    SELECT_PERIOD,
    ENTER_START_DATE,
    ENTER_END_DATE,
    SELECT_FREQUENCY,
    ENTER_AMOUNT,
    CONFIRM,
) = range(7)
DCA_CALCULATOR_KEY = "dca_calculator"
DCA_DATA_KEY = "dca_flow"
CALCULATE = "âœ… Calculate"
CANCEL = "âŒ Cancel"

FREQUENCY_LABELS = {
    "Daily": DCAFrequency.DAILY,
    "Weekly": DCAFrequency.WEEKLY,
    "Monthly": DCAFrequency.MONTHLY,
}


def _flow(context: ContextTypes.DEFAULT_TYPE) -> dict[str, Any]:
    return context.user_data.setdefault(DCA_DATA_KEY, {})


def _clear_flow(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop(DCA_DATA_KEY, None)
    context.user_data.pop(CALENDAR_DATA_KEY, None)


def _message_text(update: Update) -> str:
    if not update.effective_message or update.effective_message.text is None:
        return ""
    return update.effective_message.text.strip()


def _asset_keyboard() -> ReplyKeyboardMarkup:
    labels = [
        f"{asset.display_name} ({asset.symbol})" for asset in SUPPORTED_ASSETS.values()
    ]
    rows = tuple(tuple(labels[index : index + 2]) for index in range(0, len(labels), 2))
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, one_time_keyboard=True)


def _frequency_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        (tuple(FREQUENCY_LABELS),), resize_keyboard=True, one_time_keyboard=True
    )


def _confirmation_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(((CALCULATE, CANCEL),), resize_keyboard=True)


def _extract_symbol(text: str) -> str:
    if text.endswith(")") and "(" in text:
        return text.rsplit("(", 1)[1][:-1]
    return text


async def start_dca(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start a fresh DCA flow and ask for one supported asset."""

    _clear_flow(context)
    _flow(context)
    if update.effective_message:
        await update.effective_message.reply_text(
            "Choose one asset:", reply_markup=_asset_keyboard()
        )
    return SELECT_ASSET


async def select_asset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Validate a registry symbol and ask for the start date."""

    try:
        asset = get_asset(_extract_symbol(_message_text(update)))
    except UnsupportedAssetError:
        if update.effective_message:
            await update.effective_message.reply_text(
                "Please choose a supported asset from the buttons.",
                reply_markup=_asset_keyboard(),
            )
        return SELECT_ASSET

    _flow(context)["asset"] = asset
    if update.effective_message:
        await update.effective_message.reply_text(
            "Choose a period:", reply_markup=build_period_keyboard()
        )
    return SELECT_PERIOD


async def select_period(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    label = _message_text(update)
    if label == CUSTOM_DATES:
        begin_calendar(
            context,
            flow="dca",
            data_key=DCA_DATA_KEY,
            target="start",
            states={
                "period": SELECT_PERIOD,
                "start": ENTER_START_DATE,
                "end": ENTER_END_DATE,
                "frequency": SELECT_FREQUENCY,
            },
        )
        today = date.today()
        await update.effective_message.reply_text(
            "Choose start date\n\nYou can also type a date as YYYY-MM-DD.",
            reply_markup=build_year_picker(today.year, max_date=today),
        )
        return ENTER_START_DATE
    if label not in PERIOD_PRESETS:
        await update.effective_message.reply_text(
            "Please choose one of the period buttons.", reply_markup=build_period_keyboard()
        )
        return SELECT_PERIOD
    start, end = preset_date_range(label, today=date.today())
    flow = _flow(context)
    flow["start_date"], flow["end_date"] = start, end
    await update.effective_message.reply_text(
        f"Period: {start.isoformat()} â†’ {end.isoformat()}\n\nChoose an investment frequency:",
        reply_markup=_frequency_keyboard(),
    )
    return SELECT_FREQUENCY


async def enter_start_date(
    update: Update, context: ContextTypes.DEFAULT_TYPE, *, current_date: date | None = None
) -> int:
    """Store a valid, non-future start date."""

    today = current_date or date.today()
    try:
        entered_date = parse_date_input(
            _message_text(update), allow_today=False, current_date=today
        )
    except ValueError:
        return await _date_error(update, ENTER_START_DATE)
    try:
        validate_date_not_future(entered_date, current_date=today)
    except ValueError:
        return await _future_date_error(update, ENTER_START_DATE)

    _flow(context)["start_date"] = entered_date
    if update.effective_message:
        calendar = context.user_data.get(CALENDAR_DATA_KEY)
        if calendar:
            calendar["target"] = "end"
            await update.effective_message.reply_text(
                f"âœ… Start date: {entered_date.isoformat()}\n\nChoose end date. "
                "You can also type YYYY-MM-DD.",
                reply_markup=build_year_picker(today.year, max_date=today),
            )
        else:
            await update.effective_message.reply_text(
                "Enter the end date in YYYY-MM-DD format, or type today."
            )
    return ENTER_END_DATE


async def enter_end_date(
    update: Update, context: ContextTypes.DEFAULT_TYPE, *, current_date: date | None = None
) -> int:
    """Store a valid end date on or after the selected start date."""

    today = current_date or date.today()
    try:
        entered_date = parse_date_input(_message_text(update), current_date=today)
    except ValueError:
        return await _date_error(update, ENTER_END_DATE)
    try:
        validate_date_not_future(entered_date, current_date=today)
    except ValueError:
        return await _future_date_error(update, ENTER_END_DATE)
    try:
        validate_date_range(_flow(context)["start_date"], entered_date)
    except ValueError:
        if update.effective_message:
            await update.effective_message.reply_text(
                "End date cannot be before the start date. Please try again."
            )
        return ENTER_END_DATE

    _flow(context)["end_date"] = entered_date
    clear_calendar(context)
    if update.effective_message:
        await update.effective_message.reply_text(
            "Choose an investment frequency:", reply_markup=_frequency_keyboard()
        )
    return SELECT_FREQUENCY


async def select_frequency(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Map a button label to the calculation engine's frequency enum."""

    frequency = FREQUENCY_LABELS.get(_message_text(update).title())
    if frequency is None:
        if update.effective_message:
            await update.effective_message.reply_text(
                "Please choose Daily, Weekly, or Monthly.",
                reply_markup=_frequency_keyboard(),
            )
        return SELECT_FREQUENCY
    _flow(context)["frequency"] = frequency
    if update.effective_message:
        await update.effective_message.reply_text(
            "How much would you like to invest each period?\n\n"
            "Enter an amount in USD. Example: 500"
        )
    return ENTER_AMOUNT


async def enter_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Parse a finite, positive USD amount and show confirmation."""

    try:
        amount = parse_positive_decimal(_message_text(update))
    except ValueError:
        return await _amount_error(update)

    flow = _flow(context)
    flow["investment_amount"] = amount
    asset = flow["asset"]
    confirmation = (
        "Please confirm:\n\n"
        f"Asset: {asset.display_name} ({asset.symbol})\n"
        f"Period: {flow['start_date'].isoformat()} â†’ {flow['end_date'].isoformat()}\n"
        f"Frequency: {flow['frequency'].value.title()}\n"
        f"Investment: {format_currency(amount)} per period"
    )
    if update.effective_message:
        await update.effective_message.reply_text(
            confirmation, reply_markup=_confirmation_keyboard()
        )
    return CONFIRM


async def calculate_dca(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Run the blocking calculator in a worker thread and display its result."""

    flow = _flow(context)
    if not await enforce_cooldown(
        update,
        context,
        action="heavy_calculation",
        cooldown_seconds=HEAVY_ACTION_COOLDOWN_SECONDS,
    ):
        return CONFIRM
    if flow.get("calculating"):
        return CONFIRM
    flow["calculating"] = True
    if update.effective_message:
        await update.effective_message.reply_text("Calculating your DCA result...")

    calculator: DCACalculator = context.bot_data[DCA_CALCULATOR_KEY]
    asset = flow["asset"]
    LOGGER.info(
        "DCA calculation started asset=%s start=%s end=%s frequency=%s",
        asset.symbol,
        flow["start_date"],
        flow["end_date"],
        flow["frequency"].value,
    )
    try:
        result = await asyncio.to_thread(
            calculator.calculate,
            asset,
            flow["start_date"],
            flow["end_date"],
            flow["frequency"],
            flow["investment_amount"],
        )
    except RequestLimitError as exc:
        LOGGER.warning("DCA request rejected by workload limit asset=%s", asset.symbol)
        if update.effective_message:
            await update.effective_message.reply_text(
                str(exc), reply_markup=build_main_menu()
            )
        _clear_flow(context)
        return ConversationHandler.END
    except (DCACalculationError, MarketDataError):
        LOGGER.exception("DCA calculation failed for %s", asset.symbol)
        if update.effective_message:
            await update.effective_message.reply_text(
                "I couldn't retrieve enough market data for that calculation. "
                "Please try a different date range or try again later.",
                reply_markup=build_main_menu(),
            )
        _clear_flow(context)
        return ConversationHandler.END

    LOGGER.info(
        "DCA calculation completed asset=%s requested_end=%s effective_end=%s purchases=%s",
        asset.symbol,
        result.requested_end_date or result.end_date,
        result.end_date,
        result.number_of_purchases,
    )
    if update.effective_message:
        await update.effective_message.reply_text(
            format_dca_result(result), reply_markup=build_main_menu()
        )
        chart_service: ChartService | None = context.bot_data.get(CHART_SERVICE_KEY)
        if chart_service is not None:
            try:
                chart = await asyncio.to_thread(chart_service.build_dca_chart, result)
            except ChartGenerationError:
                LOGGER.exception("DCA chart generation failed for %s", asset.symbol)
                await update.effective_message.reply_text(
                    "The calculation succeeded, but the chart could not be generated."
                )
            else:
                await update.effective_message.reply_photo(photo=chart)
    _clear_flow(context)
    return ConversationHandler.END


async def cancel_dca(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Clear the active flow and return to the persistent main menu."""

    _clear_flow(context)
    if update.effective_message:
        await update.effective_message.reply_text(
            "Cancelled. Back to the main menu.", reply_markup=build_main_menu()
        )
    return ConversationHandler.END


async def menu_from_dca(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Clear the active flow when the user invokes ``/menu``."""

    _clear_flow(context)
    if update.effective_message:
        await update.effective_message.reply_text(
            "Main menu â€” choose an option:", reply_markup=build_main_menu()
        )
    return ConversationHandler.END


async def leave_dca_for_navigation(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """End silently so another handler group can route the same update."""

    del update
    _clear_flow(context)
    return ConversationHandler.END


async def _date_error(update: Update, state: int) -> int:
    if update.effective_message:
        await update.effective_message.reply_text(
            "Invalid date. Please use YYYY-MM-DD, for example 2020-01-01."
        )
    return state


async def _future_date_error(update: Update, state: int) -> int:
    if update.effective_message:
        await update.effective_message.reply_text(
            "Future dates are not supported. Please try again."
        )
    return state


async def _amount_error(update: Update) -> int:
    if update.effective_message:
        await update.effective_message.reply_text(
            "Invalid amount. Enter a number greater than zero, for example 500."
        )
    return ENTER_AMOUNT
