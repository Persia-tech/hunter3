"""Independent lump-sum calculations for dated consumer purchases."""

from __future__ import annotations

from collections import OrderedDict
from datetime import date, timedelta
from decimal import Decimal
from threading import Lock
from uuid import uuid4

from backend.app.models.asset import Asset
from backend.app.models.opportunity_cost import OpportunityItem, OpportunityResult, Purchase
from backend.app.models.price import PriceRecord
from backend.app.services.dca_market_data import MarketDataError, MarketDataService


class OpportunityCostError(RuntimeError):
    pass


class OpportunityCostService:
    def __init__(self, market_data: MarketDataService) -> None:
        self._market_data = market_data
        self._historical_cache: dict[tuple[str, date], tuple[date, Decimal] | None] = {}
        self._current_snapshots: OrderedDict[str, dict[str, PriceRecord]] = OrderedDict()
        self._snapshot_lock = Lock()

    def create_snapshot(self) -> str:
        """Create a bounded calculation session for canonical current prices."""

        snapshot_id = uuid4().hex
        with self._snapshot_lock:
            self._current_snapshots[snapshot_id] = {}
            while len(self._current_snapshots) > 128:
                self._current_snapshots.popitem(last=False)
        return snapshot_id

    def calculate(
        self,
        asset: Asset,
        purchases: tuple[Purchase, ...],
        snapshot_id: str | None = None,
    ) -> OpportunityResult:
        if not purchases:
            raise ValueError("Select at least one product")
        latest = self._current_price(asset, snapshot_id)
        dates = tuple(dict.fromkeys(p.product.release_date for p in purchases))
        prices = self._resolve_prices(asset, dates)
        items = []
        for purchase in purchases:
            matched = prices[purchase.product.release_date]
            cost = purchase.product.launch_price_usd * purchase.quantity
            if matched is None:
                items.append(OpportunityItem(purchase, None, None, Decimal(0), Decimal(0),
                                             "Not available at that time"))
                continue
            price_date, price = matched
            units = cost / price
            items.append(OpportunityItem(purchase, price_date, price, units, units * latest.price))
        return OpportunityResult(asset, latest.price, latest.date, tuple(items))

    def rank(
        self,
        assets: tuple[Asset, ...],
        purchases: tuple[Purchase, ...],
        snapshot_id: str | None = None,
    ) -> tuple[OpportunityResult, ...]:
        results = []
        for asset in assets:
            try:
                result = self.calculate(asset, purchases, snapshot_id)
                if any(item.eligible for item in result.items):
                    results.append(result)
            except MarketDataError:
                continue
        return tuple(sorted(results, key=lambda result: result.current_value, reverse=True))

    def _current_price(self, asset: Asset, snapshot_id: str | None) -> PriceRecord:
        if snapshot_id is None:
            return self._market_data.get_latest_price(asset)
        with self._snapshot_lock:
            snapshot = self._current_snapshots.get(snapshot_id)
            if snapshot is None:
                raise ValueError("Calculation session expired; compare investments again")
            cached = snapshot.get(asset.symbol)
            if cached is not None:
                return cached
            latest = self._market_data.get_latest_price(asset)
            return snapshot.setdefault(asset.symbol, latest)

    def _resolve_prices(self, asset: Asset, dates: tuple[date, ...]) -> dict[date, tuple[date, Decimal] | None]:
        result = {day: self._historical_cache[(asset.symbol, day)] for day in dates
                  if (asset.symbol, day) in self._historical_cache}
        missing = tuple(day for day in dates if day not in result)
        if not missing:
            return result
        window = 2 if asset.trades_24_7 else 10
        try:
            records = self._market_data.get_historical_prices(
                asset, min(missing), max(missing) + timedelta(days=window)
            )
        except MarketDataError:
            records = []
        for requested in missing:
            match = next((row for row in records if requested <= row.date <= requested + timedelta(days=window)), None)
            value = (match.date, match.price) if match else None
            self._historical_cache[(asset.symbol, requested)] = value
            result[requested] = value
        return result
