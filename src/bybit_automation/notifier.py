from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal


@dataclass
class Notification:
    severity: Literal["info", "warning", "safe_mode", "error"]
    message: str
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class Notifier:
    notifications: list[Notification] = field(default_factory=list)

    @property
    def messages(self) -> list[str]:
        return [notification.message for notification in self.notifications]

    def info(self, message: str) -> None:
        self.notify("info", message)

    def warning(self, message: str) -> None:
        self.notify("warning", message)

    def safe_mode(self, message: str) -> None:
        self.notify("safe_mode", message)

    def error(self, message: str) -> None:
        self.notify("error", message)

    def notify(
        self,
        severity: Literal["info", "warning", "safe_mode", "error"],
        message: str,
    ) -> None:
        self.notifications.append(Notification(severity=severity, message=message))
