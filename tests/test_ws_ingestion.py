from __future__ import annotations

from bybit_automation.cache import RedisRealtimeCache
from bybit_automation.ws import MarketStreamEvent, MarketStreamIngestor, OrderStreamEvent

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
