from __future__ import annotations

import logging
from typing import Any

from bybit_automation.cache.realtime import RealtimeCache
from bybit_automation.exchange_client import ExchangeClient, MarketSnapshot, OpenOrder, TradingRules
from bybit_automation.orders import OrderSide
from bybit_automation.positions import Position

LOGGER = logging.getLogger(__name__)


class CachedExchangeClient:
    """Exchange decorator that writes fresh REST reads into realtime cache.

    Startup reconciliation remains exchange-authoritative because positions and
    open orders never fall back to Redis.
    """

    def __init__(self, exchange: ExchangeClient, cache: RealtimeCache) -> None:
        self._exchange = exchange
        self._cache = cache

    def fetch_positions(self) -> list[Position]:
        positions = self._exchange.fetch_positions()
        self._cache.set_positions(positions)
        return positions

    def fetch_open_orders(self) -> list[OpenOrder]:
        orders = self._exchange.fetch_open_orders()
        self._cache.set_open_orders(orders)
        return orders

    def fetch_market_snapshot(self, symbol: str) -> MarketSnapshot | None:
        try:
            snapshot = self._exchange.fetch_market_snapshot(symbol)
        except Exception as exc:
            cached = self._cache.get_market_snapshot(symbol)
            if cached is not None:
                LOGGER.warning(
                    "using cached market snapshot for %s after exchange fetch failed: %s",
                    symbol,
                    exc,
                )
                return cached
            raise

        if snapshot is not None:
            self._cache.set_market_snapshot(snapshot)
        return snapshot

    def fetch_trading_rules(self, symbol: str) -> TradingRules:
        return self._exchange.fetch_trading_rules(symbol)

    def create_limit_order(
        self,
        *,
        symbol: str,
        side: OrderSide,
        amount: float,
        price: float,
    ) -> dict[str, Any]:
        return self._executor().create_limit_order(
            symbol=symbol,
            side=side,
            amount=amount,
            price=price,
        )

    def create_market_order(
        self,
        *,
        symbol: str,
        side: OrderSide,
        amount: float,
    ) -> dict[str, Any]:
        return self._executor().create_market_order(
            symbol=symbol,
            side=side,
            amount=amount,
        )

    def cancel_all_orders(self, symbol: str) -> list[str]:
        return self._executor().cancel_all_orders(symbol)

    def _executor(self) -> Any:
        return self._exchange
