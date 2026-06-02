from __future__ import annotations

from dataclasses import dataclass
import logging
import time
from typing import Callable

from bybit_automation.ws.events import (
    HeartbeatStreamEvent,
    StreamEvent,
    StreamEventHandler,
    StreamHealth,
    WebSocketStream,
)

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReconnectPolicy:
    initial_delay_sec: float = 1.0
    max_delay_sec: float = 30.0
    multiplier: float = 2.0

    def delay_for_attempt(self, attempt: int) -> float:
        if attempt < 0:
            raise ValueError("attempt must be non-negative")
        delay = self.initial_delay_sec * (self.multiplier**attempt)
        return min(delay, self.max_delay_sec)


class StreamSupervisor:
    def __init__(
        self,
        *,
        stream_factory: Callable[[], WebSocketStream],
        handler: StreamEventHandler,
        reconnect_policy: ReconnectPolicy | None = None,
        stale_after_sec: float = 5.0,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._stream_factory = stream_factory
        self._handler = handler
        self._reconnect_policy = reconnect_policy or ReconnectPolicy()
        self._stale_after_sec = stale_after_sec
        self._monotonic = monotonic
        self._sleep = sleep
        self._stopped = False
        self._stream: WebSocketStream | None = None
        self._health = StreamHealth(status="stopped", stale_after_sec=stale_after_sec)

    @property
    def health(self) -> StreamHealth:
        now = float(self._monotonic())
        if self._health.status == "healthy" and not self._health.is_fresh(now):
            return StreamHealth(
                status="stale",
                last_message_at=self._health.last_message_at,
                last_heartbeat_at=self._health.last_heartbeat_at,
                stale_after_sec=self._stale_after_sec,
                reason="market_data_stale",
            )
        return self._health

    def handle_stream_event(self, event: StreamEvent) -> None:
        now = float(self._monotonic())
        last_heartbeat_at = self._health.last_heartbeat_at
        if isinstance(event, HeartbeatStreamEvent):
            last_heartbeat_at = now

        self._health = StreamHealth(
            status="healthy",
            last_message_at=now,
            last_heartbeat_at=last_heartbeat_at,
            stale_after_sec=self._stale_after_sec,
        )
        self._handler.handle_stream_event(event)

    def run_until_stopped(self, *, max_attempts: int | None = None) -> None:
        attempt = 0
        while not self._stopped and (max_attempts is None or attempt < max_attempts):
            self._health = StreamHealth(
                status="connecting" if attempt == 0 else "reconnecting",
                stale_after_sec=self._stale_after_sec,
            )
            try:
                self._stream = self._stream_factory()
                self._stream.start(self)
                if self._stopped:
                    break
                raise RuntimeError("stream stopped unexpectedly")
            except Exception as exc:  # noqa: BLE001 - supervisor must keep reconnecting.
                LOGGER.warning("websocket stream failed; reconnecting: %s", exc)
                self._health = StreamHealth(
                    status="reconnecting",
                    stale_after_sec=self._stale_after_sec,
                    reason=str(exc),
                )
                delay = self._reconnect_policy.delay_for_attempt(attempt)
                attempt += 1
                if max_attempts is not None and attempt >= max_attempts:
                    break
                self._sleep(delay)

        if not self._stopped and max_attempts is not None and attempt >= max_attempts:
            self._health = StreamHealth(
                status="failed",
                stale_after_sec=self._stale_after_sec,
                reason="max reconnect attempts reached",
            )

    def stop(self) -> None:
        self._stopped = True
        if self._stream is not None:
            self._stream.stop()
        self._health = StreamHealth(status="stopped", stale_after_sec=self._stale_after_sec)
