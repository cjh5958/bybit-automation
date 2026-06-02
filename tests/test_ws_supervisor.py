from __future__ import annotations

import pytest

from bybit_automation.ws import (
    HeartbeatStreamEvent,
    MarketStreamEvent,
    ReconnectPolicy,
    StreamEvent,
    StreamEventHandler,
    StreamSupervisor,
)


class FakeClock:
    def __init__(self, now: float = 100) -> None:
        self.now = now

    def monotonic(self) -> float:
        return self.now

    def sleep(self, delay: float) -> None:
        self.now += delay


class RecordingHandler:
    def __init__(self) -> None:
        self.events: list[StreamEvent] = []

    def handle_stream_event(self, event: StreamEvent) -> None:
        self.events.append(event)


class EventStream:
    def __init__(self, events: list[StreamEvent]) -> None:
        self.events = events
        self.stopped = False

    def start(self, handler: StreamEventHandler) -> None:
        for event in self.events:
            handler.handle_stream_event(event)

    def stop(self) -> None:
        self.stopped = True


class FailingStream:
    def start(self, handler: StreamEventHandler) -> None:
        raise RuntimeError("socket down")

    def stop(self) -> None:
        return None


def test_reconnect_policy_caps_exponential_delay() -> None:
    policy = ReconnectPolicy(initial_delay_sec=1, max_delay_sec=5, multiplier=2)

    assert [policy.delay_for_attempt(attempt) for attempt in range(4)] == [1, 2, 4, 5]
    with pytest.raises(ValueError):
        policy.delay_for_attempt(-1)


def test_stream_supervisor_records_messages_and_heartbeat_health() -> None:
    clock = FakeClock()
    handler = RecordingHandler()
    heartbeat = HeartbeatStreamEvent(event_time=100)
    market = MarketStreamEvent(symbol="MOODENG/USDT:USDT", event_time=101, mark_price=10)
    supervisor = StreamSupervisor(
        stream_factory=lambda: EventStream([heartbeat, market]),
        handler=handler,
        stale_after_sec=5,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )

    supervisor.run_until_stopped(max_attempts=1)

    assert handler.events == [heartbeat, market]
    assert supervisor.health.status == "failed"


def test_stream_supervisor_health_turns_stale_without_recent_messages() -> None:
    clock = FakeClock()
    handler = RecordingHandler()
    supervisor = StreamSupervisor(
        stream_factory=lambda: EventStream([]),
        handler=handler,
        stale_after_sec=5,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )

    supervisor.handle_stream_event(HeartbeatStreamEvent(event_time=100))
    clock.now = 106

    assert supervisor.health.status == "stale"
    assert supervisor.health.reason == "market_data_stale"


def test_stream_supervisor_retries_with_backoff_until_max_attempts() -> None:
    clock = FakeClock()
    sleeps: list[float] = []

    def sleep(delay: float) -> None:
        sleeps.append(delay)
        clock.sleep(delay)

    supervisor = StreamSupervisor(
        stream_factory=lambda: FailingStream(),
        handler=RecordingHandler(),
        reconnect_policy=ReconnectPolicy(initial_delay_sec=1, max_delay_sec=3, multiplier=2),
        monotonic=clock.monotonic,
        sleep=sleep,
    )

    supervisor.run_until_stopped(max_attempts=3)

    assert sleeps == [1, 2]
    assert supervisor.health.status == "failed"
    assert supervisor.health.reason == "max reconnect attempts reached"
