from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, TypeAlias

from bybit_automation.orders import OrderSide
from bybit_automation.positions import PositionSide


StreamStatus: TypeAlias = Literal[
    "stopped",
    "connecting",
    "healthy",
    "stale",
    "reconnecting",
    "failed",
]


@dataclass(frozen=True)
class StreamHealth:
    status: StreamStatus
    last_message_at: float | None = None
    last_heartbeat_at: float | None = None
    stale_after_sec: float = 5.0
    reason: str | None = None

    def is_fresh(self, now: float) -> bool:
        if self.status != "healthy" or self.last_message_at is None:
            return False
        return now - self.last_message_at <= self.stale_after_sec


@dataclass(frozen=True)
class MarketStreamEvent:
    symbol: str
    event_time: float
    mark_price: float | None = None
    close_prices: tuple[float, ...] = ()
    ohlcv: tuple[tuple[float, ...], ...] = ()
    atr_pct: float = 0.0
    average_amplitude_pct: float = 0.0


@dataclass(frozen=True)
class OrderStreamEvent:
    exchange_order_id: str
    symbol: str
    event_time: float
    side: OrderSide | None
    amount: float
    price: float | None
    status: str


@dataclass(frozen=True)
class PositionStreamEvent:
    symbol: str
    event_time: float
    side: PositionSide
    size: float
    entry_price: float
    mark_price: float


@dataclass(frozen=True)
class ExecutionStreamEvent:
    execution_id: str
    order_id: str
    symbol: str
    event_time: float
    side: OrderSide | None
    amount: float
    price: float


AccountStreamEvent: TypeAlias = OrderStreamEvent | PositionStreamEvent | ExecutionStreamEvent
StreamEvent: TypeAlias = MarketStreamEvent | AccountStreamEvent


class StreamEventHandler(Protocol):
    def handle_stream_event(self, event: StreamEvent) -> None:
        raise NotImplementedError


class WebSocketStream(Protocol):
    @property
    def health(self) -> StreamHealth:
        raise NotImplementedError

    def start(self, handler: StreamEventHandler) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError
