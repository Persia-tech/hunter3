"""FastAPI routes that serialize the existing Decimal-based service layer."""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from backend.app.api.alerts import require_telegram_user, router as alerts_router
from backend.app.api.market_temperature import router as market_temperature_router
from backend.app.config import MAX_COMPARE_ASSETS, validate_production_environment
from backend.app.models.asset import SUPPORTED_ASSETS, get_asset
from backend.app.models.comparison import DCAComparisonResult
from backend.app.models.dca import DCAFrequency, DCAResult
from backend.app.providers.dca_yfinance_provider import YFinanceProvider
from backend.app.services.comparison import (
    DCAComparisonError,
    DCAComparisonService,
)
from backend.app.services.current_prices import (
    CurrentPricesError,
    CurrentPricesService,
)
from backend.app.services.dca_calculator import (
    DCACalculationError,
    DCACalculator,
)
from backend.app.services.dca_market_data import MarketDataService
from backend.app.services.lump_sum import (
    DCAvsLumpSumError,
    DCAvsLumpSumService,
)
from backend.app.services.opportunity_cost import OpportunityCostService


class CalculationRequest(BaseModel):
    asset: str
    start_date: date
    end_date: date
    frequency: DCAFrequency
    contribution: str

    @field_validator("contribution")
    @classmethod
    def positive_decimal(cls, value: str) -> str:
        try:
            amount = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError("contribution must be a decimal") from exc

        if not amount.is_finite() or amount <= 0:
            raise ValueError(
                "contribution must be greater than zero"
            )

        return value


class CompareRequest(BaseModel):
    assets: list[str] = Field(
        min_length=2,
        max_length=MAX_COMPARE_ASSETS,
    )
    start_date: date
    end_date: date
    frequency: DCAFrequency
    contribution: str

    @field_validator("contribution")
    @classmethod
    def positive_decimal(cls, value: str) -> str:
        return CalculationRequest.positive_decimal(value)


def _decimal(value: Decimal) -> str:
    return format(value, "f")


def _chart(
    result: DCAResult,
) -> list[dict[str, str]]:
    units = Decimal(0)
    invested = Decimal(0)
    points = []

    for purchase in result.purchases:
        units += purchase.units_purchased
        invested += purchase.amount_invested

        points.append(
            {
                "date": purchase.execution_date.isoformat(),
                "portfolio_value": _decimal(
                    units * purchase.price
                ),
                "contributions": _decimal(invested),
            }
        )

    if points:
        points[-1]["portfolio_value"] = _decimal(
            result.current_value
        )

    return points


def serialize_dca(
    result: DCAResult,
) -> dict[str, Any]:
    return {
        "asset": result.asset.symbol,
        "asset_name": result.asset.display_name,
        "asset_type": result.asset.asset_type.value,
        "requested_start_date": (
            result.start_date.isoformat()
        ),
        "requested_end_date": (
            result.requested_end_date
            or result.end_date
        ).isoformat(),
        "effective_end_date": (
            result.effective_end_date.isoformat()
        ),
        "frequency": result.frequency.value,
        "contribution": _decimal(
            result.investment_per_period
        ),
        "total_invested": _decimal(
            result.total_invested
        ),
        "total_units": _decimal(
            result.total_units
        ),
        "average_purchase_price": _decimal(
            result.average_purchase_price
        ),
        "final_value": _decimal(
            result.current_value
        ),
        "profit": _decimal(
            result.profit_loss
        ),
        "return_pct": _decimal(
            result.total_return_percentage
        ),
        "purchase_count": (
            result.number_of_purchases
        ),
        "chart": _chart(result),
    }


def require_telegram(
    init_data: Annotated[
        str | None,
        Header(alias="X-Telegram-Init-Data"),
    ] = None,
) -> None:
    """Apply the shared Telegram authentication policy to calculator routes."""
    require_telegram_user(init_data)


def create_app(
    calculator: DCACalculator | None = None,
    comparison: DCAComparisonService | None = None,
    lump_sum: DCAvsLumpSumService | None = None,
    prices: CurrentPricesService | None = None,
) -> FastAPI:
    validate_production_environment()
    if calculator is None:
        market = MarketDataService(
            YFinanceProvider()
        )

        calculator = DCACalculator(
            market
        )
    else:
        market = getattr(
            calculator,
            "_market_data",
            None,
        )

    comparison = (
        comparison
        or DCAComparisonService(calculator)
    )

    lump_sum = (
        lump_sum
        or DCAvsLumpSumService(
            calculator,
            market,
        )
    )

    prices = (
        prices
        or CurrentPricesService(market)
    )

    app = FastAPI(
        title="DCA Mini App API",
        docs_url="/api/docs",
    )

    origins = [
        item.strip()
        for item in os.getenv(
            "MINI_APP_ORIGINS",
            "",
        ).split(",")
        if item.strip()
    ]

    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=[
                "GET",
                "POST",
                "PATCH",
                "DELETE",
            ],
            allow_headers=[
                "Content-Type",
                "X-Telegram-Init-Data",
            ],
        )

    auth = [
        Depends(require_telegram)
    ]

    @app.get(
        "/api/assets",
        dependencies=auth,
    )
    def assets_route() -> dict[str, Any]:
        return {
            "assets": [
                {
                    "symbol": asset.symbol,
                    "name": asset.display_name,
                    "category": (
                        asset.asset_type.value
                    ),
                }
                for asset
                in SUPPORTED_ASSETS.values()
            ],
            "max_compare_assets": (
                MAX_COMPARE_ASSETS
            ),
        }

    @app.post(
        "/api/dca",
        dependencies=auth,
    )
    def dca_route(
        request: CalculationRequest,
    ) -> dict[str, Any]:
        try:
            return serialize_dca(
                calculator.calculate(
                    get_asset(
                        request.asset
                    ),
                    request.start_date,
                    request.end_date,
                    request.frequency,
                    Decimal(
                        request.contribution
                    ),
                )
            )

        except (
            ValueError,
            DCACalculationError,
        ) as exc:
            raise HTTPException(
                status_code=422,
                detail=str(exc),
            ) from exc

    @app.post(
        "/api/compare",
        dependencies=auth,
    )
    def compare_route(
        request: CompareRequest,
    ) -> dict[str, Any]:
        try:
            selected = [
                get_asset(symbol)
                for symbol
                in request.assets
            ]

            result = comparison.compare(
                selected,
                request.start_date,
                request.end_date,
                request.frequency,
                Decimal(
                    request.contribution
                ),
            )

            unavailable = (
                result.unavailable_symbols
                if isinstance(
                    result,
                    DCAComparisonResult,
                )
                else ()
            )

            rows = [
                serialize_dca(item)
                for item
                in result
            ]

            return {
                "results": rows,
                "unavailable": unavailable,
                "effective_end_date": (
                    rows[0][
                        "effective_end_date"
                    ]
                ),
            }

        except (
            ValueError,
            DCAComparisonError,
        ) as exc:
            raise HTTPException(
                status_code=422,
                detail=str(exc),
            ) from exc

    @app.post(
        "/api/lump-sum",
        dependencies=auth,
    )
    def lump_route(
        request: CalculationRequest,
    ) -> dict[str, Any]:
        try:
            result = lump_sum.compare(
                get_asset(
                    request.asset
                ),
                request.start_date,
                request.end_date,
                request.frequency,
                Decimal(
                    request.contribution
                ),
            )

            dca = serialize_dca(
                result.dca
            )

            lump = result.lump_sum

            return {
                "asset": dca["asset"],
                "asset_name": (
                    dca["asset_name"]
                ),
                "effective_end_date": (
                    dca[
                        "effective_end_date"
                    ]
                ),
                "total_capital": _decimal(
                    result.dca.total_invested
                ),
                "dca": dca,
                "lump_sum": {
                    "total_invested": _decimal(
                        lump.total_invested
                    ),
                    "total_units": _decimal(
                        lump.units
                    ),
                    "final_value": _decimal(
                        lump.current_value
                    ),
                    "profit": _decimal(
                        lump.profit_loss
                    ),
                    "return_pct": _decimal(
                        lump.total_return_percentage
                    ),
                },
                "winner": (
                    result.winner.value
                ),
                "value_difference": _decimal(
                    result.value_difference
                ),
            }

        except (
            ValueError,
            DCAvsLumpSumError,
        ) as exc:
            raise HTTPException(
                status_code=422,
                detail=str(exc),
            ) from exc

    @app.get(
        "/api/prices",
        dependencies=auth,
    )
    def prices_route() -> dict[str, Any]:
        try:
            result = prices.get_all()

            return {
                "prices": [
                    {
                        "symbol": (
                            row.asset.symbol
                        ),
                        "name": (
                            row.asset.display_name
                        ),
                        "price": _decimal(
                            row.price
                        ),
                    }
                    for row
                    in result.prices
                ],
                "unavailable": (
                    result.unavailable_symbols
                ),
                "fetched_at": (
                    result.fetched_at.isoformat()
                ),
            }

        except CurrentPricesError as exc:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Market data is "
                    "temporarily unavailable"
                ),
            ) from exc

    app.include_router(
        alerts_router
    )
    app.include_router(market_temperature_router)
    from backend.app.api.opportunity_cost import create_router as create_opportunity_router
    app.include_router(create_opportunity_router(OpportunityCostService(market)))

    return app


app = create_app()
