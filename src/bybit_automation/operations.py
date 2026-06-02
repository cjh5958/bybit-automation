from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
import logging
from typing import Any, Literal


OperationalSeverity = Literal["info", "warning", "safe_mode", "error"]
OperationalComponent = Literal[
    "runtime",
    "reload",
    "reconciliation",
    "cache",
    "websocket",
    "exchange",
    "storage",
]


@dataclass(frozen=True)
class OperationalEvent:
    component: OperationalComponent
    event_type: str
    severity: OperationalSeverity = "info"
    message: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_log_payload(self) -> dict[str, Any]:
        return {
            "created_at": self.created_at,
            "component": self.component,
            "event_type": self.event_type,
            "severity": self.severity,
            "message": self.message,
            "payload": self.payload,
        }


def log_operational_event(
    event: OperationalEvent,
    *,
    logger: logging.Logger | None = None,
) -> None:
    target = logger or logging.getLogger("bybit_automation.operations")
    target.log(
        _logging_level(event.severity),
        json.dumps(event.to_log_payload(), sort_keys=True),
    )


def _logging_level(severity: OperationalSeverity) -> int:
    if severity == "error":
        return logging.ERROR
    if severity in {"warning", "safe_mode"}:
        return logging.WARNING
    return logging.INFO
