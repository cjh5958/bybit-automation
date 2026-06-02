from __future__ import annotations

from dataclasses import dataclass

from bybit_automation.cache import RealtimeCache
from bybit_automation.config import BotConfig
from bybit_automation.ws.events import StreamEvent, StreamEventHandler, StreamHealth
from bybit_automation.ws.ingestion import AccountStreamIngestor, MarketStreamIngestor
from bybit_automation.ws.supervisor import ReconnectPolicy, StreamSupervisor


@dataclass(frozen=True)
class WebSocketRuntime:
    enabled: bool
    health: StreamHealth | None
    message: str
    supervisors: tuple[StreamSupervisor, ...] = ()

    def start(self) -> None:
        for supervisor in self.supervisors:
            supervisor.run_until_stopped()

    def stop(self) -> None:
        for supervisor in self.supervisors:
            supervisor.stop()


class CompositeStreamEventHandler:
    def __init__(self, handlers: tuple[StreamEventHandler, ...]) -> None:
        self._handlers = handlers

    def handle_stream_event(self, event: StreamEvent) -> None:
        for handler in self._handlers:
            handler.handle_stream_event(event)


def create_websocket_runtime(config: BotConfig, cache: RealtimeCache) -> WebSocketRuntime:
    if not config.websocket.enabled:
        return WebSocketRuntime(
            enabled=False,
            health=None,
            message="websocket disabled",
        )

    handler = CompositeStreamEventHandler(
        (
            MarketStreamIngestor(cache),
            AccountStreamIngestor(cache),
        )
    )
    _ = handler
    _ = ReconnectPolicy(
        initial_delay_sec=config.websocket.reconnect_initial_delay_sec,
        max_delay_sec=config.websocket.reconnect_max_delay_sec,
    )

    return WebSocketRuntime(
        enabled=True,
        health=StreamHealth(
            status="failed",
            stale_after_sec=config.websocket.stale_after_sec,
            reason="concrete Bybit WebSocket adapter is not implemented",
        ),
        message="websocket enabled but concrete Bybit adapter is not implemented; strategy fails closed",
    )
