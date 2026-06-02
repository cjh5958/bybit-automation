from __future__ import annotations

from bybit_automation.ws import (
    MarketStreamEvent,
    OrderStreamEvent,
    PositionStreamEvent,
    StreamEvent,
    StreamEventHandler,
    StreamHealth,
)


class RecordingHandler:
    def __init__(self) -> None:
        self.events: list[StreamEvent] = []

    def handle_stream_event(self, event: StreamEvent) -> None:
        self.events.append(event)


def test_stream_health_freshness_requires_healthy_recent_message() -> None:
    healthy = StreamHealth(status="healthy", last_message_at=100, stale_after_sec=5)
    stale = StreamHealth(status="healthy", last_message_at=100, stale_after_sec=5)
    reconnecting = StreamHealth(status="reconnecting", last_message_at=104, stale_after_sec=5)

    assert healthy.is_fresh(104)
    assert not stale.is_fresh(106)
    assert not reconnecting.is_fresh(104)


def test_stream_event_handler_records_market_and_account_events() -> None:
    handler: StreamEventHandler = RecordingHandler()
    market = MarketStreamEvent(
        symbol="MOODENG/USDT:USDT",
        event_time=100,
        mark_price=10,
        close_prices=(9, 10),
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
    position = PositionStreamEvent(
        symbol="MOODENG/USDT:USDT",
        event_time=102,
        side="long",
        size=1,
        entry_price=9,
        mark_price=10,
    )

    handler.handle_stream_event(market)
    handler.handle_stream_event(order)
    handler.handle_stream_event(position)

    assert isinstance(handler, RecordingHandler)
    assert handler.events == [market, order, position]
