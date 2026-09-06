"""Display formatting for Telegram messages; calculation values stay unrounded."""

from __future__ import annotations

from datetime import timezone
from decimal import Decimal

from backend.app.models.asset import Asset, AssetType
from backend.app.models.comparison import DCAComparisonResult
from backend.app.models.current_prices import CurrentPricesResult
from backend.app.models.dca import DCAResult
from backend.app.models.lump_sum import DCAvsLumpSumResult, StrategyWinner


def format_currency(value: Decimal, *, show_sign: bool = False) -> str:
    """Format a Decimal as USD, optionally showing a plus sign for gains."""

    if value == 0:
        return "$0.00"
    sign = "+" if show_sign and value > 0 else "-" if value < 0 else ""
    return f"{sign}${abs(value):,.2f}"


def format_units(value: Decimal, maximum_places: int = 8) -> str:
    """Show useful fractional precision while trimming trailing zeroes."""

    rendered = f"{value:,.{maximum_places}f}"
    return rendered.rstrip("0").rstrip(".")


def format_asset_quantity(asset: Asset, value: Decimal) -> str:
    """Format total quantity without changing its Decimal-backed value."""

    if asset.asset_type is AssetType.CRYPTO:
        return f"{format_units(value, maximum_places=8)} {asset.symbol}"
    return f"{format_units(value, maximum_places=6)} shares"


def format_percentage(value: Decimal) -> str:
    """Format a return percentage with an explicit positive sign."""

    if value == 0:
        return "0.00%"
    return f"{value:+.2f}%"


def format_dca_result(result: DCAResult) -> str:
    """Build a compact, mobile-friendly single-asset DCA result."""

    frequency = result.frequency.value
    lines = [
        "ðŸ“Š DCA Result",
        "",
        f"Asset: {result.asset.symbol}",
        f"Period: {result.start_date.isoformat()} â†’ {result.end_date.isoformat()}",
        f"Frequency: {frequency.title()}",
        f"Contribution: {format_currency(result.investment_per_period)}",
        f"Purchases: {result.number_of_purchases}",
        "",
        f"Total invested: {format_currency(result.total_invested)}",
        f"Final value: {format_currency(result.current_value)}",
        f"Profit: {format_currency(result.profit_loss, show_sign=True)}",
        f"Return: {format_percentage(result.total_return_percentage)}",
        "",
        f"Accumulated: {format_asset_quantity(result.asset, result.total_units)}",
        f"Average price: {format_currency(result.average_purchase_price)}",
        f"Ending price: {format_currency(result.latest_price)}",
        (
            f"First purchase: {result.first_execution_date.isoformat()} at "
            f"{format_currency(result.first_purchase_price)}"
        ),
        (
            f"Last purchase: {result.last_execution_date.isoformat()} at "
            f"{format_currency(result.last_purchase_price)}"
        ),
    ]
    if not result.asset.trades_24_7:
        lines.extend(
            (
                "",
                "Note: Contributions on non-trading days execute on the next available session.",
            )
        )
    requested_end = result.requested_end_date or result.end_date
    if requested_end != result.end_date:
        lines.extend(
            ("", f"Using completed market data through {result.end_date.isoformat()}.")
        )
    if result.asset.asset_type is AssetType.PRECIOUS_METAL_ETF:
        lines.extend(
            (
                "",
                f"{result.asset.display_name} uses {result.asset.provider_ticker}, "
                "a tradable ETF proxyâ€”not the physical-metal spot price.",
            )
        )
    return "\n".join(lines)


def format_comparison_result(
    results: tuple[DCAResult, ...] | DCAComparisonResult,
) -> str:
    """Build a ranked, narrow multi-asset result for Telegram."""

    if not results:
        raise ValueError("results cannot be empty")
    first = results[0]
    lines = [
        "âš–ï¸ Asset Comparison",
        "",
        f"Common period: {first.start_date.isoformat()} â†’ {first.end_date.isoformat()}",
        f"Frequency: {first.frequency.value.title()}",
        f"Contribution: {format_currency(first.investment_per_period)} per asset",
        f"Total invested per asset: {format_currency(first.total_invested)}",
    ]
    for rank, result in enumerate(results, start=1):
        lines.extend(
            (
                "",
                f"{'ðŸ† ' if rank == 1 else ''}{rank}. {result.asset.symbol}",
                f"Accumulated: {format_asset_quantity(result.asset, result.total_units)}",
                f"Final value: {format_currency(result.current_value)}",
                f"Profit: {format_currency(result.profit_loss, show_sign=True)}",
                f"Return: {format_percentage(result.total_return_percentage)}",
            )
        )
    unavailable = getattr(results, "unavailable_symbols", ())
    if unavailable:
        lines.extend(("", "âš ï¸ Unavailable:", ", ".join(unavailable)))
    requested_end = first.requested_end_date or first.end_date
    if requested_end != first.end_date:
        lines.extend(
            ("", f"Common market data period ends {first.end_date:%b %d, %Y}.")
        )
    if any(result.asset.asset_type is AssetType.PRECIOUS_METAL_ETF for result in results):
        lines.extend(
            (
                "",
                "GLD, SLV, and PPLT are tradable ETF proxies for gold, silver, and platinum.",
            )
        )
    return "\n".join(lines)


def format_dca_vs_lump_sum_result(result: DCAvsLumpSumResult) -> str:
    """Build a compact equal-capital strategy comparison."""

    dca = result.dca
    lump = result.lump_sum
    if dca.total_invested != lump.total_invested:
        raise ValueError("DCA and lump sum must use identical total capital")
    winner = {
        StrategyWinner.DCA: "DCA",
        StrategyWinner.LUMP_SUM: "Lump Sum",
        StrategyWinner.TIE: "Tie",
    }[result.winner]
    lines = [
        "âš–ï¸ DCA vs Lump Sum",
        "",
        dca.asset.symbol,
        f"{dca.start_date.isoformat()} â†’ {dca.end_date.isoformat()}",
        "",
        f"ðŸ’° Total capital: {format_currency(dca.total_invested)}",
        "",
        "ðŸ“… DCA",
        f"Total invested: {format_currency(dca.total_invested)}",
        f"Accumulated: {format_asset_quantity(dca.asset, dca.total_units)}",
        f"Contribution: {format_currency(dca.investment_per_period)} / "
        f"{dca.frequency.value}",
        f"Purchases: {dca.number_of_purchases}",
        f"Final value: {format_currency(dca.current_value)}",
        f"Profit: {format_currency(dca.profit_loss, show_sign=True)}",
        f"Return: {format_percentage(dca.total_return_percentage)}",
        "",
        "ðŸ’µ Lump Sum",
        f"Initial investment: {format_currency(lump.total_invested)}",
        f"Entry date: {lump.execution_date.isoformat()}",
        f"Bought initially: {format_asset_quantity(lump.asset, lump.units)}",
        f"Final value: {format_currency(lump.current_value)}",
        f"Profit: {format_currency(lump.profit_loss, show_sign=True)}",
        f"Return: {format_percentage(lump.total_return_percentage)}",
        "",
        "ðŸ† Better historical result:",
        (
            "Tie"
            if result.winner is StrategyWinner.TIE
            else f"{winner} by {format_currency(result.value_difference)}"
        ),
        f"Return difference: {result.return_difference:.2f} percentage points",
    ]
    requested_end = dca.requested_end_date or dca.end_date
    if requested_end != dca.end_date:
        lines.extend(
            ("", f"Using completed market data through {dca.end_date.isoformat()}.")
        )
    if dca.asset.asset_type is AssetType.PRECIOUS_METAL_ETF:
        lines.extend(
            (
                "",
                "GLD, SLV, and PPLT are tradable ETF proxies for gold, silver, and platinum.",
            )
        )
    return "\n".join(lines)


def format_current_prices(result: CurrentPricesResult) -> str:
    """Format a compact UTC-stamped snapshot without altering Decimal values."""

    lines = ["ðŸ“ˆ Current Prices", ""]
    lines.extend(
        f"{current.asset.symbol:<5} {format_currency(current.price)}"
        for current in result.prices
    )
    if result.unavailable_symbols:
        lines.extend(("", "Unavailable:", ", ".join(result.unavailable_symbols)))
    fetched_at = result.fetched_at.astimezone(timezone.utc)
    lines.extend(("", f"Updated: {fetched_at:%Y-%m-%d %H:%M} UTC"))
    if any(item.asset.asset_type is AssetType.PRECIOUS_METAL_ETF for item in result.prices):
        lines.extend(
            (
                "",
                "GLD, SLV, and PPLT are tradable ETF proxies for gold, silver, and platinum.",
            )
        )
    return "\n".join(lines)
