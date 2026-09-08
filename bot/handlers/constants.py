"""Shared Telegram button labels and user-facing Stage 4 messages."""

CALCULATE_DCA = "📊 Calculate DCA"
COMPARE_ASSETS = "⚖️ Compare Assets"
DCA_VS_LUMP_SUM = "💰 DCA vs Lump Sum"
CURRENT_PRICES = "📈 Current Prices"
HELP = "ℹ️ Help"

MAIN_MENU_BUTTONS = (
    CALCULATE_DCA,
    COMPARE_ASSETS,
    DCA_VS_LUMP_SUM,
    CURRENT_PRICES,
    HELP,
)

ACTIVE_FLOW_DATA_KEYS = ("dca_flow", "compare", "lump_sum", "calendar")

WELCOME_TEXT = (
    "Compare historical DCA strategies across crypto, stocks, and ETFs.\n\n"
    "Choose an option below:"
)

HELP_TEXT = (
    "ℹ️ Help\n\n"
    "📊 Calculate DCA — simulate recurring contributions.\n"
    "⚖️ Compare Assets — apply one strategy independently to several assets.\n"
    "💰 DCA vs Lump Sum — compare equal total capital.\n"
    "📈 Current Prices — view a provider snapshot, not a streaming quote.\n\n"
    "Choose a period preset or use Custom Dates. Historical data from yfinance "
    "can be delayed, incomplete, or provider-adjusted.\n\n"
    "GLD, SLV, and PPLT are tradable ETF proxies for gold, silver, and platinum.\n\n"
    "Use /menu at any time to return to the main menu.\n\n"
    "This bot provides historical simulations and market-data snapshots for "
    "educational purposes only. It is not financial advice."
)
