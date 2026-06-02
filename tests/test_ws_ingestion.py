from __future__ import annotations

from bybit_automation.cache import RedisRealtimeCache
from bybit_automation.exchange_client import OpenOrder
from bybit_automation.positions import Position
from bybit_automation.ws import (
    AccountStreamIngestor,
    ExecutionStreamEvent,
    MarketStreamEvent,
    MarketStreamIngestor,
    OrderStreamEvent,
    PositionStreamEvent,
)

from tests.test_cache import FakeRedis


def test_market_stream_ingestor_writes_market_snapshot_to_cache() -> None:
    cache = RedisRealtimeCache(client=FakeRedis(), namespace="bot")
    ingestor = MarketStreamIngestor(cache)

    ingestor.handle_stream_event(
        MarketStreamEvent(
            symbol="MOODENG/USDT:USDT",
            event_time=100,
            mark_price=10,
            close_prices=(9, 9.5, 10),
            atr_pct=1.2,
            average_amplitude_pct=2.3,
        )
    )

    snapshot = cache.get_market_snapshot("MOODENG/USDT:USDT")
    assert snapshot is not None
    assert snapshot.symbol == "MOODENG/USDT:USDT"
    assert snapshot.mark_price == 10
    assert snapshot.close_prices == (9, 9.5, 10)
    assert snapshot.atr_pct == 1.2
    assert snapshot.average_amplitude_pct == 2.3


def test_market_stream_ingestor_derives_close_prices_from_ohlcv() -> None:
    cache = RedisRealtimeCache(client=FakeRedis(), namespace="bot")
    ingestor = MarketStreamIngestor(cache)

    ingestor.handle_stream_event(
        MarketStreamEvent(
            symbol="MOODENG/USDT:USDT",
            event_time=100,
            mark_price=10,
            ohlcv=((1, 9, 11, 8, 10), (2, 10, 12, 9, 11)),
        )
    )

    snapshot = cache.get_market_snapshot("MOODENG/USDT:USDT")
    assert snapshot is not None
    assert snapshot.close_prices == (10, 11)
    assert snapshot.ohlcv == ((1, 9, 11, 8, 10), (2, 10, 12, 9, 11))


def test_market_stream_ingestor_ignores_invalid_or_non_market_events() -> None:
    cache = RedisRealtimeCache(client=FakeRedis(), namespace="bot")
    ingestor = MarketStreamIngestor(cache)

    ingestor.handle_stream_event(
        MarketStreamEvent(symbol="MOODENG/USDT:USDT", event_time=100, mark_price=0)
    )
    ingestor.handle_stream_event(
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

    assert cache.get_market_snapshot("MOODENG/USDT:USDT") is None
    assert cache.get_positions() is None
    assert cache.get_open_orders() is None


def test_account_stream_ingestor_writes_positions_orders_and_executions_to_cache() -> None:
    cache = RedisRealtimeCache(client=FakeRedis(), namespace="bot")
    ingestor = AccountStreamIngestor(cache)

    position = PositionStreamEvent(
        symbol="MOODENG/USDT:USDT",
        event_time=100,
        side="long",
        size=1,
        entry_price=9,
        mark_price=10,
    )
    order = OrderStreamEvent(
        exchange_order_id="order-1",
        symbol="MOODENG/USDT:USDT",
        event_time=101,
        side="buy",
        amount=1,
        price=9,
        status="open",
    )
    execution = ExecutionStreamEvent(
        execution_id="exec-1",
        order_id="order-1",
        symbol="MOODENG/USDT:USDT",
        event_time=102,
        side="buy",
        amount=1,
        price=9,
    )

    ingestor.handle_stream_event(position)
    ingestor.handle_stream_event(order)
    ingestor.handle_stream_event(execution)

    assert cache.get_positions() == [
        Position(
            symbol="MOODENG/USDT:USDT",
            side="long",
            size=1,
            entry_price=9,
            mark_price=10,
        )
    ]
    assert cache.get_open_orders() == [
        OpenOrder(
            exchange_order_id="order-1",
            symbol="MOODENG/USDT:USDT",
            side="buy",
            amount=1,
            price=9,
            status="open",
        )
    ]
    assert cache.get_recent_executions() == [execution]


def test_account_stream_ingestor_removes_closed_positions_and_orders() -> None:
    cache = RedisRealtimeCache(client=FakeRedis(), namespace="bot")
    ingestor = AccountStreamIngestor(cache)

    ingestor.handle_stream_event(
        PositionStreamEvent(
            symbol="MOODENG/USDT:USDT",
            event_time=100,
            side="long",
            size=1,
            entry_price=9,
            mark_price=10,
        )
    )
    ingestor.handle_stream_event(
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

    ingestor.handle_stream_event(
        PositionStreamEvent(
            symbol="MOODENG/USDT:USDT",
            event_time=102,
            side="long",
            size=0,
            entry_price=9,
            mark_price=10,
        )
    )
    ingestor.handle_stream_event(
        OrderStreamEvent(
            exchange_order_id="order-1",
            symbol="MOODENG/USDT:USDT",
            event_time=103,
            side="buy",
            amount=1,
            price=9,
            status="filled",
        )
    )

    assert cache.get_positions() == []
    assert cache.get_open_orders() == []


def test_account_stream_ingestor_trims_recent_executions() -> None:
    cache = RedisRealtimeCache(client=FakeRedis(), namespace="bot")
    ingestor = AccountStreamIngestor(cache, max_recent_executions=2)

    for index in range(3):
        ingestor.handle_stream_event(
            ExecutionStreamEvent(
                execution_id=f"exec-{index}",
                order_id="order-1",
                symbol="MOODENG/USDT:USDT",
                event_time=100 + index,
                side="buy",
                amount=1,
                price=9,
            )
        )

    executions = cache.get_recent_executions()
    assert executions is not None
    assert [execution.execution_id for execution in executions] == ["exec-1", "exec-2"]
