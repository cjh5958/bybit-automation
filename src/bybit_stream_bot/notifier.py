from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Notifier:
    messages: list[str] = field(default_factory=list)

    def info(self, message: str) -> None:
        self.messages.append(message)

