from __future__ import annotations

import json
import logging

from bybit_automation.operations import OperationalEvent, log_operational_event


def test_operational_event_serializes_stable_payload() -> None:
    event = OperationalEvent(
        component="runtime",
        event_type="tick_completed",
        severity="info",
        message="runtime tick completed",
        payload={"positions_seen": 2},
        created_at="2026-06-02T00:00:00+00:00",
    )

    assert event.to_log_payload() == {
        "component": "runtime",
        "created_at": "2026-06-02T00:00:00+00:00",
        "event_type": "tick_completed",
        "message": "runtime tick completed",
        "payload": {"positions_seen": 2},
        "severity": "info",
    }


def test_log_operational_event_emits_json_payload(caplog) -> None:
    logger = logging.getLogger("tests.operations")
    event = OperationalEvent(
        component="cache",
        event_type="redis_unavailable",
        severity="warning",
        message="redis unavailable",
        payload={"enabled": True},
        created_at="2026-06-02T00:00:00+00:00",
    )

    with caplog.at_level(logging.WARNING, logger="tests.operations"):
        log_operational_event(event, logger=logger)

    assert len(caplog.records) == 1
    assert caplog.records[0].levelno == logging.WARNING
    assert json.loads(caplog.records[0].message) == event.to_log_payload()
