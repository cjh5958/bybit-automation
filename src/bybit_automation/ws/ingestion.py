from __future__ import annotations

import logging

from bybit_automation.cache import RealtimeCache
from bybit_automation.exchange_client import MarketSnapshot, OpenOrder
from bybit_automation.positions import Position
from bybit_automation.ws.events import (
    ExecutionStreamEvent,
    MarketStreamEvent,
    OrderStreamEvent,
    PositionStreamEvent,
    StreamEvent,
)

LOGGER = logging.getLogger(__name__)


class MarketStreamIngestor:
    def __init__(self, cache: RealtimeCache) -> None:
        self._cache = cache

    def handle_stream_event(self, event: StreamEvent) -> None:
        if not isinstance(event, MarketStreamEvent):
            return

        snapshot = _snapshot_from_market_event(event)
        if snapshot is None:
            LOGGER.warning("ignored invalid market stream event for %s", event.symbol)
            return
        self._cache.set_market_snapshot(snapshot)


class AccountStreamIngestor:
    def __init__(self, cache: RealtimeCache, *, max_recent_executions: int = 100) -> None:
        self._cache = cache
        self._max_recent_executions = max_recent_executions
        self._positions = {
            position.symbol: position for position in (cache.get_positions() or [])
        }
        self._open_orders = {
            order.exchange_order_id: order for order in (cache.get_open_orders() or [])
        }
        self._executions = list(cache.get_recent_executions() or [])

    def handle_stream_event(self, event: StreamEvent) -> None:
        if isinstance(event, PositionStreamEvent):
            self._handle_position(event)
        elif isinstance(event, OrderStreamEvent):
            self._handle_order(event)
        elif isinstance(event, ExecutionStreamEvent):
            self._handle_execution(event)

    def _handle_position(self, event: PositionStreamEvent) -> None:
        if event.size <= 0:
            self._positions.pop(event.symbol, None)
        else:
            self._positions[event.symbol] = Position(
                symbol=event.symbol,
                side=event.side,
                size=event.size,
                entry_price=event.entry_price,
                mark_price=event.mark_price,
            )
        self._cache.set_positions(list(self._positions.values()))

    def _handle_order(self, event: OrderStreamEvent) -> None:
        if _is_closed_order_status(event.status):
            self._open_orders.pop(event.exchange_order_id, None)
        else:
            self._open_orders[event.exchange_order_id] = OpenOrder(
                exchange_order_id=event.exchange_order_id,
                symbol=event.symbol,
                side=event.side,
                amount=event.amount,
                price=event.price,
                status=event.status,
            )
        self._cache.set_open_orders(list(self._open_orders.values()))

    def _handle_execution(self, event: ExecutionStreamEvent) -> None:
        self._executions.append(event)
        self._executions = self._executions[-self._max_recent_executions :]
        self._cache.set_recent_executions(self._executions)


def _snapshot_from_market_event(event: MarketStreamEvent) -> MarketSnapshot | None:
    if not event.symbol or event.mark_price is None or event.mark_price <= 0:
        return None

    close_prices = event.close_prices
    if not close_prices and event.ohlcv:
        close_prices = tuple(float(kline[4]) for kline in event.ohlcv if len(kline) >= 5)

    if not close_prices:
        close_prices = (float(event.mark_price),)

    return MarketSnapshot(
        symbol=event.symbol,
        mark_price=float(event.mark_price),
        close_prices=tuple(float(price) for price in close_prices),
        atr_pct=float(event.atr_pct),
        average_amplitude_pct=float(event.average_amplitude_pct),
        ohlcv=event.ohlcv,
    )


def _is_closed_order_status(status: str) -> bool:
    return status.lower() in {"closed", "canceled", "cancelled", "filled", "rejected"}
