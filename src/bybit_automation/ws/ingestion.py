from __future__ import annotations

import logging

from bybit_automation.cache import RealtimeCache
from bybit_automation.exchange_client import MarketSnapshot
from bybit_automation.ws.events import MarketStreamEvent, StreamEvent

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
