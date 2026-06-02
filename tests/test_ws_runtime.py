from __future__ import annotations

from bybit_automation.cache import RedisRealtimeCache
from bybit_automation.config import parse_config
from bybit_automation.ws import (
    CompositeStreamEventHandler,
    MarketStreamEvent,
    OrderStreamEvent,
    create_websocket_runtime,
)
from tests.factories import valid_raw_config
from tests.test_cache import FakeRedis


def test_websocket_runtime_is_disabled_by_default() -> None:
    config = parse_config(valid_raw_config(), resolve_secrets=False)
    runtime = create_websocket_runtime(
        config,
        RedisRealtimeCache(client=FakeRedis(), namespace="bot"),
    )

    assert runtime.enabled is False
    assert runtime.health is None
    assert runtime.message == "websocket disabled"


def test_websocket_runtime_fails_closed_when_adapter_is_unimplemented() -> None:
    raw = valid_raw_config()
    raw["websocket"]["enabled"] = True
    config = parse_config(raw, resolve_secrets=False)
    runtime = create_websocket_runtime(
        config,
        RedisRealtimeCache(client=FakeRedis(), namespace="bot"),
    )

    assert runtime.enabled is True
    assert runtime.health is not None
    assert runtime.health.status == "failed"
    assert runtime.health.reason == "concrete Bybit WebSocket adapter is not implemented"


def test_composite_stream_event_handler_fans_out_to_market_and_account_ingestors() -> None:
    cache = RedisRealtimeCache(client=FakeRedis(), namespace="bot")
    from bybit_automation.ws import AccountStreamIngestor, MarketStreamIngestor

    handler = CompositeStreamEventHandler(
        (
            MarketStreamIngestor(cache),
            AccountStreamIngestor(cache),
        )
    )

    handler.handle_stream_event(
        MarketStreamEvent(symbol="MOODENG/USDT:USDT", event_time=100, mark_price=10)
    )
    handler.handle_stream_event(
        OrderStreamEvent(
            exchange_order_id="order-1",
            symbol="MOODENG/USDT:USDT",
            event_time=101,
            side="buy",
            amount=1,
            price=9,
            status="open",
        )
    )

    assert cache.get_market_snapshot("MOODENG/USDT:USDT") is not None
    assert cache.get_open_orders() is not None
