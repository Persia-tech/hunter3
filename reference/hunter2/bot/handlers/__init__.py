"""Deterministic registration for commands, feature flows, and menu routing."""

from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot.handlers.calendar import handle_calendar
from bot.handlers.compare import (
    CANCEL as COMPARE_CANCEL,
)
from bot.handlers.compare import (
    COMPARE,
    COMPARE_AMOUNT,
    COMPARE_CONFIRM,
    COMPARE_END_DATE,
    COMPARE_FREQUENCY,
    COMPARE_PERIOD,
    COMPARE_SELECT_ASSETS,
    COMPARE_START_DATE,
    cancel_compare,
    compare_amount,
    compare_end_date,
    compare_frequency,
    compare_period,
    compare_start_date,
    leave_compare_for_navigation,
    run_comparison,
    select_compare_asset,
    start_compare,
)
from bot.handlers.constants import (
    CALCULATE_DCA,
    COMPARE_ASSETS,
    CURRENT_PRICES,
    DCA_VS_LUMP_SUM,
    HELP,
    MAIN_MENU_BUTTONS,
)
from bot.handlers.current_prices import MAIN_MENU, REFRESH_PRICES, show_current_prices
from bot.handlers.dca import (
    CALCULATE,
    CANCEL,
    CONFIRM,
    ENTER_AMOUNT,
    ENTER_END_DATE,
    ENTER_START_DATE,
    SELECT_ASSET,
    SELECT_FREQUENCY,
    SELECT_PERIOD,
    calculate_dca,
    cancel_dca,
    enter_amount,
    enter_end_date,
    enter_start_date,
    leave_dca_for_navigation,
    select_asset,
    select_frequency,
    select_period,
    start_dca,
)
from bot.handlers.help import help_command
from bot.handlers.lump_sum import (
    CANCEL as LUMP_CANCEL,
)
from bot.handlers.lump_sum import (
    COMPARE as LUMP_COMPARE,
)
from bot.handlers.lump_sum import (
    LUMP_AMOUNT,
    LUMP_CONFIRM,
    LUMP_END_DATE,
    LUMP_FREQUENCY,
    LUMP_PERIOD,
    LUMP_SELECT_ASSET,
    LUMP_START_DATE,
    cancel_lump_sum,
    leave_lump_sum_for_navigation,
    lump_amount,
    lump_end_date,
    lump_frequency,
    lump_period,
    lump_select_asset,
    lump_start_date,
    run_lump_sum,
    start_lump_sum,
)
from bot.handlers.menu import cancel, show_menu, unknown_text
from bot.handlers.start import start


def register_handlers(application: Application) -> None:
    """Use separate groups so one menu update can close an old flow and open another."""

    menu_buttons = filters.Text(MAIN_MENU_BUTTONS)
    conversation_text = filters.TEXT & ~filters.COMMAND & ~menu_buttons

    dca_conversation = ConversationHandler(
        entry_points=[MessageHandler(filters.Text([CALCULATE_DCA]), start_dca)],
        states={
            SELECT_ASSET: [MessageHandler(conversation_text, select_asset)],
            SELECT_PERIOD: [
                MessageHandler(filters.Text([CANCEL]), cancel_dca),
                MessageHandler(conversation_text, select_period),
            ],
            ENTER_START_DATE: [
                MessageHandler(conversation_text, enter_start_date),
                CallbackQueryHandler(handle_calendar, pattern=r"^cal:"),
            ],
            ENTER_END_DATE: [
                MessageHandler(conversation_text, enter_end_date),
                CallbackQueryHandler(handle_calendar, pattern=r"^cal:"),
            ],
            SELECT_FREQUENCY: [MessageHandler(conversation_text, select_frequency)],
            ENTER_AMOUNT: [MessageHandler(conversation_text, enter_amount)],
            CONFIRM: [
                MessageHandler(filters.Text([CALCULATE]), calculate_dca),
                MessageHandler(filters.Text([CANCEL]), cancel_dca),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", leave_dca_for_navigation),
            CommandHandler("menu", leave_dca_for_navigation),
            MessageHandler(menu_buttons, leave_dca_for_navigation),
        ],
        name="single_asset_dca",
        persistent=False,
        allow_reentry=True,
    )
    application.add_handler(dca_conversation, group=0)

    compare_conversation = ConversationHandler(
        entry_points=[MessageHandler(filters.Text([COMPARE_ASSETS]), start_compare)],
        states={
            COMPARE_SELECT_ASSETS: [
                CallbackQueryHandler(select_compare_asset, pattern=r"^compare:")
            ],
            COMPARE_PERIOD: [
                MessageHandler(filters.Text([COMPARE_CANCEL]), cancel_compare),
                MessageHandler(conversation_text, compare_period),
            ],
            COMPARE_START_DATE: [
                MessageHandler(conversation_text, compare_start_date),
                CallbackQueryHandler(handle_calendar, pattern=r"^cal:"),
            ],
            COMPARE_END_DATE: [
                MessageHandler(conversation_text, compare_end_date),
                CallbackQueryHandler(handle_calendar, pattern=r"^cal:"),
            ],
            COMPARE_FREQUENCY: [MessageHandler(conversation_text, compare_frequency)],
            COMPARE_AMOUNT: [MessageHandler(conversation_text, compare_amount)],
            COMPARE_CONFIRM: [
                MessageHandler(filters.Text([COMPARE]), run_comparison),
                MessageHandler(filters.Text([COMPARE_CANCEL]), cancel_compare),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", leave_compare_for_navigation),
            CommandHandler("menu", leave_compare_for_navigation),
            MessageHandler(menu_buttons, leave_compare_for_navigation),
        ],
        name="multi_asset_comparison",
        persistent=False,
        allow_reentry=True,
    )
    application.add_handler(compare_conversation, group=1)

    lump_conversation = ConversationHandler(
        entry_points=[MessageHandler(filters.Text([DCA_VS_LUMP_SUM]), start_lump_sum)],
        states={
            LUMP_SELECT_ASSET: [MessageHandler(conversation_text, lump_select_asset)],
            LUMP_PERIOD: [
                MessageHandler(filters.Text([LUMP_CANCEL]), cancel_lump_sum),
                MessageHandler(conversation_text, lump_period),
            ],
            LUMP_START_DATE: [
                MessageHandler(conversation_text, lump_start_date),
                CallbackQueryHandler(handle_calendar, pattern=r"^cal:"),
            ],
            LUMP_END_DATE: [
                MessageHandler(conversation_text, lump_end_date),
                CallbackQueryHandler(handle_calendar, pattern=r"^cal:"),
            ],
            LUMP_FREQUENCY: [MessageHandler(conversation_text, lump_frequency)],
            LUMP_AMOUNT: [MessageHandler(conversation_text, lump_amount)],
            LUMP_CONFIRM: [
                MessageHandler(filters.Text([LUMP_COMPARE]), run_lump_sum),
                MessageHandler(filters.Text([LUMP_CANCEL]), cancel_lump_sum),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", leave_lump_sum_for_navigation),
            CommandHandler("menu", leave_lump_sum_for_navigation),
            MessageHandler(menu_buttons, leave_lump_sum_for_navigation),
        ],
        name="dca_vs_lump_sum",
        persistent=False,
        allow_reentry=True,
    )
    application.add_handler(lump_conversation, group=2)

    # Non-conversation menu routing runs after all active flows have had a chance
    # to end silently for the same update.
    application.add_handler(
        MessageHandler(filters.Text([CURRENT_PRICES, REFRESH_PRICES]), show_current_prices),
        group=3,
    )
    application.add_handler(MessageHandler(filters.Text([MAIN_MENU]), show_menu), group=3)
    application.add_handler(CommandHandler("start", start), group=3)
    application.add_handler(CommandHandler("menu", show_menu), group=3)
    application.add_handler(CommandHandler("help", help_command), group=3)
    application.add_handler(CommandHandler("cancel", cancel), group=3)
    application.add_handler(MessageHandler(filters.Text([HELP]), help_command), group=3)
    application.add_handler(MessageHandler(conversation_text, unknown_text), group=3)


__all__ = ["register_handlers"]
