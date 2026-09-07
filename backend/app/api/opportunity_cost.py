"""Opportunity Cost catalog and calculation routes."""

from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend.app.api.dca import require_telegram
from backend.app.data.product_catalog import PRODUCT_BY_ID, PRODUCTS
from backend.app.models.asset import SUPPORTED_ASSETS, get_asset
from backend.app.models.opportunity_cost import OpportunityResult, Purchase, Product
from backend.app.services.dca_market_data import MarketDataError
from backend.app.services.opportunity_cost import OpportunityCostService

router = APIRouter(prefix="/api/opportunity-cost", tags=["opportunity-cost"])


class PurchaseInput(BaseModel):
    product_id: str
    quantity: int = Field(default=1, ge=1, le=99)


class CalculationInput(BaseModel):
    asset: str
    items: list[PurchaseInput] = Field(min_length=1, max_length=100)


class RankingInput(BaseModel):
    items: list[PurchaseInput] = Field(min_length=1, max_length=100)


def _product(product: Product) -> dict[str, Any]:
    return {"id": product.id, "brand": product.brand, "category": product.category,
            "family": product.family, "model": product.model,
            "release_date": product.release_date.isoformat(),
            "release_year": product.release_date.year,
            "launch_price_usd": str(product.launch_price_usd), "image_url": product.image_url,
            "source_url": product.source_url, "active": product.active,
            "display_order": product.display_order}


def _purchases(items: list[PurchaseInput]) -> tuple[Purchase, ...]:
    purchases = []
    seen = set()
    for item in items:
        if item.product_id in seen:
            raise ValueError(f"Duplicate product: {item.product_id}")
        seen.add(item.product_id)
        product = PRODUCT_BY_ID.get(item.product_id)
        if not product or not product.active:
            raise ValueError(f"Unknown product: {item.product_id}")
        purchases.append(Purchase(product, item.quantity))
    return tuple(purchases)


def serialize(result: OpportunityResult, include_items: bool = True) -> dict[str, Any]:
    eligible = sum(item.eligible for item in result.items)
    data = {"asset": {"symbol": result.asset.symbol, "name": result.asset.display_name,
                      "category": result.asset.asset_type.value},
            "current_price": str(result.current_price),
            "current_price_date": result.current_price_date.isoformat(),
            "summary": {"total_spent": str(result.total_spent),
                        "eligible_spent": str(result.eligible_spent),
                        "current_value": str(result.current_value), "gain": str(result.gain),
                        "return_pct": str(result.return_pct),
                        "investment_units": str(result.total_units),
                        "eligible_items": eligible, "total_items": len(result.items)}}
    if include_items:
        data["items"] = [{"product": _product(item.purchase.product),
                          "quantity": item.purchase.quantity, "cost": str(item.cost),
                          "eligible": item.eligible,
                          "requested_date": item.purchase.product.release_date.isoformat(),
                          "price_date": item.price_date.isoformat() if item.price_date else None,
                          "asset_price": str(item.asset_price) if item.asset_price else None,
                          "units": str(item.units), "current_value": str(item.current_value),
                          "gain": str(item.current_value - item.cost) if item.eligible else None,
                          "reason": item.reason} for item in result.items]
    return data


def create_router(service: OpportunityCostService) -> APIRouter:
    configured = APIRouter(prefix=router.prefix, tags=router.tags,
                           dependencies=[Depends(require_telegram)])

    @configured.get("/products")
    def products(category: str | None = None, brand: str | None = None,
                 year: int | None = Query(default=None, ge=2000, le=date.today().year)) -> dict[str, Any]:
        rows = [p for p in PRODUCTS if p.active and (not category or p.category.casefold() == category.casefold())
                and (not brand or p.brand.casefold() == brand.casefold()) and (not year or p.release_date.year == year)]
        return {"products": [_product(p) for p in rows],
                "categories": list(dict.fromkeys(p.category for p in PRODUCTS if p.active))}

    @configured.post("/calculate")
    def calculate(request: CalculationInput) -> dict[str, Any]:
        try:
            return serialize(service.calculate(get_asset(request.asset), _purchases(request.items)))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except MarketDataError as exc:
            raise HTTPException(503, "Market data is temporarily unavailable") from exc

    @configured.post("/best-alternatives")
    def alternatives(request: RankingInput) -> dict[str, Any]:
        try:
            results = service.rank(tuple(SUPPORTED_ASSETS.values()), _purchases(request.items))
            return {"rankings": [serialize(row, include_items=False) for row in results]}
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    return configured
