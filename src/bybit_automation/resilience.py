from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Callable, Literal, TypeVar


T = TypeVar("T")
CircuitBreakerState = Literal["closed", "open", "half_open"]


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    initial_delay_sec: float = 0.5
    max_delay_sec: float = 5.0
    multiplier: float = 2.0

    def __post_init__(self) -> None:
        if self.max_attempts <= 0:
            raise ValueError("max_attempts must be positive")
        if self.initial_delay_sec < 0:
            raise ValueError("initial_delay_sec must be non-negative")
        if self.max_delay_sec < self.initial_delay_sec:
            raise ValueError("max_delay_sec must be at least initial_delay_sec")
        if self.multiplier < 1:
            raise ValueError("multiplier must be at least 1")

    def delay_for_attempt(self, attempt_index: int) -> float:
        if attempt_index < 0:
            raise ValueError("attempt_index must be non-negative")
        return min(
            self.initial_delay_sec * (self.multiplier**attempt_index),
            self.max_delay_sec,
        )


def run_with_retry(
    operation: Callable[[], T],
    *,
    policy: RetryPolicy,
    retryable: tuple[type[BaseException], ...] = (Exception,),
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    last_error: BaseException | None = None
    for attempt in range(policy.max_attempts):
        try:
            return operation()
        except retryable as exc:
            last_error = exc
            if attempt == policy.max_attempts - 1:
                break
            sleep(policy.delay_for_attempt(attempt))
    if last_error is None:
        raise RuntimeError("retry operation failed without an exception")
    raise last_error


@dataclass
class CircuitBreaker:
    failure_threshold: int = 3
    recovery_timeout_sec: float = 30.0
    state: CircuitBreakerState = "closed"
    failure_count: int = 0
    opened_at: float | None = None

    def __post_init__(self) -> None:
        if self.failure_threshold <= 0:
            raise ValueError("failure_threshold must be positive")
        if self.recovery_timeout_sec < 0:
            raise ValueError("recovery_timeout_sec must be non-negative")

    def allow_request(self, now: float) -> bool:
        if self.state == "closed":
            return True
        if self.state == "half_open":
            return True
        if self.opened_at is None:
            return False
        if now - self.opened_at >= self.recovery_timeout_sec:
            self.state = "half_open"
            return True
        return False

    def record_success(self) -> None:
        self.state = "closed"
        self.failure_count = 0
        self.opened_at = None

    def record_failure(self, now: float) -> None:
        if self.state == "half_open":
            self._open(now)
            return

        self.failure_count += 1
        if self.failure_count >= self.failure_threshold:
            self._open(now)

    def _open(self, now: float) -> None:
        self.state = "open"
        self.opened_at = now
