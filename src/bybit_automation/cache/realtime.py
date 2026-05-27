from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import logging
import os
from typing import Any, Callable, Protocol
from uuid import uuid4

import redis
from redis.exceptions import RedisError

from bybit_automation.config import RedisConfig
from bybit_automation.exchange_client import MarketSnapshot, OpenOrder
from bybit_automation.positions import Position

LOGGER = logging.getLogger(__name__)

DEFAULT_MARKET_TTL_SEC = 120
DEFAULT_ACCOUNT_TTL_SEC = 30
DEFAULT_RELOAD_SIGNAL_TTL_SEC = 3600

_RELEASE_LOCK_SCRIPT = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("DEL", KEYS[1])
end
return 0
"""


@dataclass(frozen=True)
class CacheHealth:
    enabled: bool
    available: bool
    message: str


@dataclass(frozen=True)
class ConfigReloadSignal:
    reason: str
    requested_by: str
    requested_at: str


@dataclass(frozen=True)
class SymbolLock:
    symbol: str
    owner: str
    token: str
    release: Callable[[], None]

    def __enter__(self) -> SymbolLock:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.release()


class RealtimeCache(Protocol):
    health: CacheHealth

    def set_market_snapshot(self, snapshot: MarketSnapshot) -> None:
        raise NotImplementedError

    def get_market_snapshot(self, symbol: str) -> MarketSnapshot | None:
        raise NotImplementedError

    def set_positions(self, positions: list[Position]) -> None:
        raise NotImplementedError

    def get_positions(self) -> list[Position] | None:
        raise NotImplementedError

    def set_open_orders(self, orders: list[OpenOrder]) -> None:
        raise NotImplementedError

    def get_open_orders(self) -> list[OpenOrder] | None:
        raise NotImplementedError

    def acquire_symbol_lock(
        self,
        symbol: str,
        *,
        owner: str,
        ttl_sec: float,
    ) -> SymbolLock | None:
        raise NotImplementedError

    def publish_config_reload_signal(self, *, reason: str, requested_by: str) -> None:
        raise NotImplementedError

    def get_config_reload_signal(self) -> ConfigReloadSignal | None:
        raise NotImplementedError


class NoopRealtimeCache:
    def __init__(self, *, enabled: bool = False, message: str = "redis disabled") -> None:
        self.health = CacheHealth(enabled=enabled, available=False, message=message)

    def set_market_snapshot(self, snapshot: MarketSnapshot) -> None:
        return None

    def get_market_snapshot(self, symbol: str) -> MarketSnapshot | None:
        return None

    def set_positions(self, positions: list[Position]) -> None:
        return None

    def get_positions(self) -> list[Position] | None:
        return None

    def set_open_orders(self, orders: list[OpenOrder]) -> None:
        return None

    def get_open_orders(self) -> list[OpenOrder] | None:
        return None

    def acquire_symbol_lock(
        self,
        symbol: str,
        *,
        owner: str,
        ttl_sec: float,
    ) -> SymbolLock | None:
        return SymbolLock(symbol=symbol, owner=owner, token=str(uuid4()), release=lambda: None)

    def publish_config_reload_signal(self, *, reason: str, requested_by: str) -> None:
        return None

    def get_config_reload_signal(self) -> ConfigReloadSignal | None:
        return None


class RedisRealtimeCache:
    def __init__(
        self,
        *,
        client: Any,
        namespace: str,
        health: CacheHealth | None = None,
        market_ttl_sec: int = DEFAULT_MARKET_TTL_SEC,
        account_ttl_sec: int = DEFAULT_ACCOUNT_TTL_SEC,
        reload_signal_ttl_sec: int = DEFAULT_RELOAD_SIGNAL_TTL_SEC,
    ) -> None:
        self._client = client
        self._namespace = namespace.strip(":")
        self._market_ttl_sec = market_ttl_sec
        self._account_ttl_sec = account_ttl_sec
        self._reload_signal_ttl_sec = reload_signal_ttl_sec
        self.health = health or CacheHealth(
            enabled=True,
            available=True,
            message="redis available",
        )

    def set_market_snapshot(self, snapshot: MarketSnapshot) -> None:
        self._safe_set(
            self._key("market", snapshot.symbol),
            _market_snapshot_payload(snapshot),
            ttl_sec=self._market_ttl_sec,
        )

    def get_market_snapshot(self, symbol: str) -> MarketSnapshot | None:
        payload = self._safe_get(self._key("market", symbol))
        if payload is None:
            return None
        try:
            return _market_snapshot_from_payload(payload)
        except (KeyError, TypeError, ValueError) as exc:
            LOGGER.warning("invalid cached market snapshot for %s: %s", symbol, exc)
            return None

    def set_positions(self, positions: list[Position]) -> None:
        self._safe_set(
            self._key("positions"),
            [_position_payload(position) for position in positions],
            ttl_sec=self._account_ttl_sec,
        )

    def get_positions(self) -> list[Position] | None:
        payload = self._safe_get(self._key("positions"))
        if payload is None:
            return None
        try:
            return [_position_from_payload(item) for item in payload]
        except (KeyError, TypeError, ValueError) as exc:
            LOGGER.warning("invalid cached positions: %s", exc)
            return None

    def set_open_orders(self, orders: list[OpenOrder]) -> None:
        self._safe_set(
            self._key("open_orders"),
            [_open_order_payload(order) for order in orders],
            ttl_sec=self._account_ttl_sec,
        )

    def get_open_orders(self) -> list[OpenOrder] | None:
        payload = self._safe_get(self._key("open_orders"))
        if payload is None:
            return None
        try:
            return [_open_order_from_payload(item) for item in payload]
        except (KeyError, TypeError, ValueError) as exc:
            LOGGER.warning("invalid cached open orders: %s", exc)
            return None

    def acquire_symbol_lock(
        self,
        symbol: str,
        *,
        owner: str,
        ttl_sec: float,
    ) -> SymbolLock | None:
        token = str(uuid4())
        key = self._key("locks", symbol)
        try:
            acquired = bool(self._client.set(key, token, nx=True, px=max(1, int(ttl_sec * 1000))))
        except (RedisError, OSError) as exc:
            LOGGER.warning("redis symbol lock unavailable for %s: %s", symbol, exc)
            return None

        if not acquired:
            return None

        def release() -> None:
            try:
                self._client.eval(_RELEASE_LOCK_SCRIPT, 1, key, token)
            except (RedisError, OSError) as exc:
                LOGGER.warning("redis symbol lock release failed for %s: %s", symbol, exc)

        return SymbolLock(symbol=symbol, owner=owner, token=token, release=release)

    def publish_config_reload_signal(self, *, reason: str, requested_by: str) -> None:
        signal = ConfigReloadSignal(
            reason=reason,
            requested_by=requested_by,
            requested_at=datetime.now(UTC).isoformat(),
        )
        self._safe_set(
            self._key("config_reload_signal"),
            {
                "reason": signal.reason,
                "requested_by": signal.requested_by,
                "requested_at": signal.requested_at,
            },
            ttl_sec=self._reload_signal_ttl_sec,
        )

    def get_config_reload_signal(self) -> ConfigReloadSignal | None:
        payload = self._safe_get(self._key("config_reload_signal"))
        if payload is None:
            return None
        try:
            return ConfigReloadSignal(
                reason=str(payload["reason"]),
                requested_by=str(payload["requested_by"]),
                requested_at=str(payload["requested_at"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            LOGGER.warning("invalid config reload signal: %s", exc)
            return None

    def _key(self, *parts: str) -> str:
        return ":".join((self._namespace, *parts))

    def _safe_set(self, key: str, payload: Any, *, ttl_sec: int) -> None:
        try:
            self._client.set(key, json.dumps(payload, sort_keys=True), ex=ttl_sec)
        except (RedisError, OSError, TypeError) as exc:
            LOGGER.warning("redis cache write skipped for %s: %s", key, exc)

    def _safe_get(self, key: str) -> Any | None:
        try:
            raw = self._client.get(key)
        except (RedisError, OSError) as exc:
            LOGGER.warning("redis cache read skipped for %s: %s", key, exc)
            return None
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            return json.loads(str(raw))
        except json.JSONDecodeError as exc:
            LOGGER.warning("redis cache value is not valid JSON for %s: %s", key, exc)
            return None


def create_realtime_cache(config: RedisConfig) -> RealtimeCache:
    if not config.enabled:
        return NoopRealtimeCache()

    url = config.url or os.getenv(config.url_env)
    if not url:
        return NoopRealtimeCache(
            enabled=True,
            message=f"redis URL env var is missing: {config.url_env}",
        )

    try:
        client = redis.Redis.from_url(url, decode_responses=True)
        client.ping()
    except (RedisError, OSError) as exc:
        LOGGER.warning("redis unavailable; continuing without realtime cache: %s", exc)
        return NoopRealtimeCache(enabled=True, message=f"redis unavailable: {exc}")

    return RedisRealtimeCache(
        client=client,
        namespace=config.namespace,
        health=CacheHealth(enabled=True, available=True, message="redis available"),
    )


def _market_snapshot_payload(snapshot: MarketSnapshot) -> dict[str, Any]:
    return {
        "symbol": snapshot.symbol,
        "mark_price": snapshot.mark_price,
        "close_prices": list(snapshot.close_prices),
        "atr_pct": snapshot.atr_pct,
        "average_amplitude_pct": snapshot.average_amplitude_pct,
        "ohlcv": [list(kline) for kline in snapshot.ohlcv],
    }


def _market_snapshot_from_payload(payload: dict[str, Any]) -> MarketSnapshot:
    return MarketSnapshot(
        symbol=str(payload["symbol"]),
        mark_price=float(payload["mark_price"]),
        close_prices=tuple(float(value) for value in payload["close_prices"]),
        atr_pct=float(payload["atr_pct"]),
        average_amplitude_pct=float(payload["average_amplitude_pct"]),
        ohlcv=tuple(tuple(float(value) for value in kline) for kline in payload.get("ohlcv", [])),
    )


def _position_payload(position: Position) -> dict[str, Any]:
    return {
        "symbol": position.symbol,
        "side": position.side,
        "size": position.size,
        "entry_price": position.entry_price,
        "mark_price": position.mark_price,
    }


def _position_from_payload(payload: dict[str, Any]) -> Position:
    return Position(
        symbol=str(payload["symbol"]),
        side=payload["side"],
        size=float(payload["size"]),
        entry_price=float(payload["entry_price"]),
        mark_price=float(payload["mark_price"]),
    )


def _open_order_payload(order: OpenOrder) -> dict[str, Any]:
    return {
        "exchange_order_id": order.exchange_order_id,
        "symbol": order.symbol,
        "side": order.side,
        "amount": order.amount,
        "price": order.price,
        "status": order.status,
    }


def _open_order_from_payload(payload: dict[str, Any]) -> OpenOrder:
    side = payload.get("side")
    if side not in {"buy", "sell", None}:
        side = None
    return OpenOrder(
        exchange_order_id=str(payload["exchange_order_id"]),
        symbol=str(payload["symbol"]),
        side=side,
        amount=float(payload["amount"]),
        price=float(payload["price"]) if payload.get("price") is not None else None,
        status=str(payload["status"]),
    )
