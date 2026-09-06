"""Telegram-independent, in-memory PNG rendering for calculated results."""

from __future__ import annotations

from collections.abc import Sequence
from io import BytesIO

from backend.app.models.dca import DCAResult
from backend.app.models.lump_sum import DCAvsLumpSumResult

CHART_SERVICE_KEY = "chart_service"


class ChartGenerationError(RuntimeError):
    """Raised when result data cannot produce a meaningful chart."""


class ChartService:
    """Render presentation-only charts from existing Decimal-backed results."""

    def build_dca_chart(self, result: DCAResult) -> BytesIO:
        if not result.purchases:
            raise ChartGenerationError("A DCA chart requires at least one purchase")
        plt = _pyplot()
        figure = None
        try:
            figure, (value_axis, price_axis) = plt.subplots(
                2, 1, figsize=(7, 8), sharex=True
            )
            dates = []
            invested = []
            values = []
            prices = []
            cumulative_invested = result.total_invested * 0
            cumulative_units = result.total_units * 0
            for purchase in result.purchases:
                cumulative_invested += purchase.amount_invested
                cumulative_units += purchase.units_purchased
                dates.append(purchase.execution_date)
                invested.append(float(cumulative_invested))
                values.append(float(cumulative_units * purchase.price))
                prices.append(float(purchase.price))

            value_axis.plot(dates, values, label="Portfolio value", linewidth=2)
            value_axis.plot(dates, invested, label="Invested capital", linewidth=2)
            value_axis.set_ylabel("USD")
            value_axis.legend()
            value_axis.grid(alpha=0.25)
            price_axis.plot(dates, prices, color="#7c3aed", marker="o", markersize=3)
            price_axis.set_ylabel("Asset price (USD)")
            price_axis.set_xlabel("Purchase execution date")
            price_axis.grid(alpha=0.25)
            figure.suptitle(
                f"{result.asset.symbol} DCA â€” {result.start_date:%b %Y} to "
                f"{result.end_date:%b %Y}"
            )
            figure.autofmt_xdate()
            return _render(figure)
        except ChartGenerationError:
            raise
        except Exception as exc:
            raise ChartGenerationError("Could not generate DCA chart") from exc
        finally:
            if figure is not None:
                plt.close(figure)

    def build_comparison_chart(self, results: Sequence[DCAResult]) -> BytesIO:
        if not results:
            raise ChartGenerationError("A comparison chart requires results")
        plt = _pyplot()
        figure = None
        try:
            figure, axis = plt.subplots(figsize=(7, 5))
            symbols = [result.asset.symbol for result in results]
            returns = [float(result.total_return_percentage) for result in results]
            positions = list(range(len(results)))
            colors = ["#16a34a" if value >= 0 else "#dc2626" for value in returns]
            axis.barh(positions, returns, color=colors)
            axis.set_yticks(positions, labels=symbols)
            axis.invert_yaxis()
            axis.axvline(0, color="black", linewidth=0.8)
            axis.set_xlabel("Total return (%)")
            axis.set_title("Return by asset â€” same DCA strategy applied independently")
            axis.grid(axis="x", alpha=0.25)
            return _render(figure)
        except Exception as exc:
            raise ChartGenerationError("Could not generate comparison chart") from exc
        finally:
            if figure is not None:
                plt.close(figure)

    def build_dca_vs_lump_sum_chart(self, result: DCAvsLumpSumResult) -> BytesIO:
        plt = _pyplot()
        figure = None
        try:
            figure, axis = plt.subplots(figsize=(6, 5))
            values = [float(result.dca.current_value), float(result.lump_sum.current_value)]
            bars = axis.bar(["DCA", "Lump Sum"], values, color=["#2563eb", "#f59e0b"])
            returns = (
                result.dca.total_return_percentage,
                result.lump_sum.total_return_percentage,
            )
            for bar, return_value in zip(bars, returns, strict=True):
                axis.annotate(
                    f"{return_value:+.2f}%",
                    (bar.get_x() + bar.get_width() / 2, bar.get_height()),
                    ha="center",
                    va="bottom",
                )
            axis.set_ylabel("Ending value (USD)")
            axis.set_title(f"{result.dca.asset.symbol}: final strategy values")
            axis.grid(axis="y", alpha=0.25)
            return _render(figure)
        except Exception as exc:
            raise ChartGenerationError("Could not generate strategy chart") from exc
        finally:
            if figure is not None:
                plt.close(figure)


def _pyplot():
    try:
        import matplotlib

        matplotlib.use("Agg")
        from matplotlib import pyplot as plt
    except ImportError as exc:
        raise ChartGenerationError("matplotlib is unavailable") from exc
    return plt


def _render(figure: object) -> BytesIO:
    buffer = BytesIO()
    buffer.name = "chart.png"
    figure.tight_layout()  # type: ignore[attr-defined]
    figure.savefig(buffer, format="png", dpi=140, bbox_inches="tight")  # type: ignore[attr-defined]
    buffer.seek(0)
    return buffer
