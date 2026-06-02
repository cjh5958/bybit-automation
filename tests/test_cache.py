from __future__ import annotations

import pytest
from redis.exceptions import RedisError

from bybit_automation.cache import (
    CachedExchangeClient,
    NoopRealtimeCache,
    RedisRealtimeCache,
    create_realtime_cache,
)
from bybit_automation.config import RedisConfig
from bybit_automation.exchange_client import MarketSnapshot, OpenOrder, TradingRules
from bybit_automation.positions import Position
from bybit_automation.ws import ExecutionStreamEvent


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    def ping(self) -> bool:
        return True

    def set(
        self,
        key: str,
        value: str,
        *,
        ex: int | None = None,
        px: int | None = None,
        nx: bool = False,
    ) -> bool:
        if nx and key in self.values:
            return False
        self.values[key] = value
        if ex is not None:
            self.ttls[key] = ex
        if px is not None:
            self.ttls[key] = px
        return True

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def delete(self, key: str) -> int:
        existed = key in self.values
        self.values.pop(key, None)
        self.ttls.pop(key, None)
        return int(existed)

    def eval(self, script: str, key_count: int, key: str, token: str) -> int:
        if self.values.get(key) != token:
            return 0
        return self.delete(key)


class FailingRedis(FakeRedis):
    def set(self, *args: object, **kwargs: object) -> bool:
        raise RedisError("redis down")

    def get(self, key: str) -> str | None:
        raise RedisError("redis down")

    def eval(self, *args: object, **kwargs: object) -> int:
        raise RedisError("redis down")


class FakeExchange:
    def __init__(
        self,
        *,
        positions: list[Position] | None = None,
        open_orders: list[OpenOrder] | None = None,
        snapshots: dict[str, MarketSnapshot] | None = None,
        fail_market: bool = False,
    ) -> None:
        self.positions = positions or []
        self.open_orders = open_orders or []
        self.snapshots = snapshots or {}
        self.fail_market = fail_market

    def fetch_positions(self) -> list[Position]:
        return self.positions

    def fetch_open_orders(self) -> list[OpenOrder]:
        return self.open_orders

    def fetch_market_snapshot(self, symbol: str) -> MarketSnapshot | None:
        if self.fail_market:
            raise RuntimeError("market unavailable")
        return self.snapshots.get(symbol)

    def fetch_trading_rules(self, symbol: str) -> TradingRules:
        return TradingRules(symbol=symbol, tick_size=0.01, min_amount=0.001)


def test_noop_cache_is_safe_and_lockable() -> None:
    cache = NoopRealtimeCache()

    lock = cache.acquire_symbol_lock("MOODENG/USDT:USDT", owner="test", ttl_sec=1)

    assert cache.get_market_snapshot("MOODENG/USDT:USDT") is None
    assert cache.get_positions() is None
    assert cache.get_open_orders() is None
    assert cache.get_config_reload_signal() is None
    assert lock is not None
    lock.release()


def test_redis_cache_round_trips_market_positions_orders_and_reload_signal() -> None:
    cache = RedisRealtimeCache(client=FakeRedis(), namespace="bot")
    snapshot = MarketSnapshot(
        symbol="MOODENG/USDT:USDT",
        mark_price=100,
        close_prices=(98, 99, 100),
        atr_pct=1.5,
        average_amplitude_pct=2.5,
        ohlcv=((1, 100, 101, 99, 100),),
    )
    positions = [
        Position(
            symbol="MOODENG/USDT:USDT",
            side="long",
            size=2,
            entry_price=95,
            mark_price=100,
        )
    ]
    orders = [
        OpenOrder(
            exchange_order_id="order-1",
            symbol="MOODENG/USDT:USDT",
            side="buy",
            amount=1,
            price=97,
            status="open",
        )
    ]
    executions = [
        ExecutionStreamEvent(
            execution_id="exec-1",
            order_id="order-1",
            symbol="MOODENG/USDT:USDT",
            event_time=100,
            side="buy",
            amount=1,
            price=97,
        )
    ]

    cache.set_market_snapshot(snapshot)
    cache.set_positions(positions)
    cache.set_open_orders(orders)
    cache.set_recent_executions(executions)
    cache.publish_config_reload_signal(reason="manual", requested_by="operator")

    assert cache.get_market_snapshot("MOODENG/USDT:USDT") == snapshot
    assert cache.get_positions() == positions
    assert cache.get_open_orders() == orders
    assert cache.get_recent_executions() == executions
    signal = cache.get_config_reload_signal()
    assert signal is not None
    assert signal.reason == "manual"
    assert signal.requested_by == "operator"


def test_redis_symbol_lock_uses_owner_token_on_release() -> None:
    redis_client = FakeRedis()
    cache = RedisRealtimeCache(client=redis_client, namespace="bot")

    first = cache.acquire_symbol_lock("MOODENG/USDT:USDT", owner="worker-1", ttl_sec=2)
    second = cache.acquire_symbol_lock("MOODENG/USDT:USDT", owner="worker-2", ttl_sec=2)

    assert first is not None
    assert second is None
    assert redis_client.ttls["bot:locks:MOODENG/USDT:USDT"] == 2000

    redis_client.values["bot:locks:MOODENG/USDT:USDT"] = "other-owner-token"
    first.release()
    assert redis_client.values["bot:locks:MOODENG/USDT:USDT"] == "other-owner-token"


def test_redis_operation_errors_degrade_to_cache_misses() -> None:
    cache = RedisRealtimeCache(client=FailingRedis(), namespace="bot")

    cache.set_market_snapshot(
        MarketSnapshot(
            symbol="MOODENG/USDT:USDT",
            mark_price=100,
            close_prices=(100,),
            atr_pct=0,
            average_amplitude_pct=0,
        )
    )

    assert cache.get_market_snapshot("MOODENG/USDT:USDT") is None
    assert cache.acquire_symbol_lock("MOODENG/USDT:USDT", owner="test", ttl_sec=1) is None
    assert cache.get_recent_executions() is None


def test_cache_factory_uses_noop_when_disabled_or_missing_url(monkeypatch: pytest.MonkeyPatch) -> None:
    disabled = create_realtime_cache(
        RedisConfig(enabled=False, url_env="REDIS_URL", namespace="bot")
    )
    monkeypatch.delenv("REDIS_URL", raising=False)
    missing_url = create_realtime_cache(
        RedisConfig(enabled=True, url_env="REDIS_URL", namespace="bot")
    )

    assert isinstance(disabled, NoopRealtimeCache)
    assert isinstance(missing_url, NoopRealtimeCache)
    assert disabled.health.enabled is False
    assert missing_url.health.enabled is True
    assert missing_url.health.available is False


def test_cached_exchange_writes_successful_reads_to_cache() -> None:
    cache = RedisRealtimeCache(client=FakeRedis(), namespace="bot")
    snapshot = MarketSnapshot(
        symbol="MOODENG/USDT:USDT",
        mark_price=100,
        close_prices=(98, 99, 100),
        atr_pct=1,
        average_amplitude_pct=1,
    )
    position = Position(
        symbol="MOODENG/USDT:USDT",
        side="long",
        size=1,
        entry_price=98,
        mark_price=100,
    )
    order = OpenOrder(
        exchange_order_id="order-1",
        symbol="MOODENG/USDT:USDT",
        side="buy",
        amount=1,
        price=97,
        status="open",
    )
    exchange = CachedExchangeClient(
        FakeExchange(
            positions=[position],
            open_orders=[order],
            snapshots={"MOODENG/USDT:USDT": snapshot},
        ),
        cache,
    )

    assert exchange.fetch_positions() == [position]
    assert exchange.fetch_open_orders() == [order]
    assert exchange.fetch_market_snapshot("MOODENG/USDT:USDT") == snapshot
    assert cache.get_positions() == [position]
    assert cache.get_open_orders() == [order]
    assert cache.get_market_snapshot("MOODENG/USDT:USDT") == snapshot


def test_cached_exchange_uses_market_cache_only_after_exchange_failure() -> None:
    cache = RedisRealtimeCache(client=FakeRedis(), namespace="bot")
    snapshot = MarketSnapshot(
        symbol="MOODENG/USDT:USDT",
        mark_price=100,
        close_prices=(98, 99, 100),
        atr_pct=1,
        average_amplitude_pct=1,
    )
    cache.set_market_snapshot(snapshot)
    exchange = CachedExchangeClient(FakeExchange(fail_market=True), cache)

    assert exchange.fetch_market_snapshot("MOODENG/USDT:USDT") == snapshot
