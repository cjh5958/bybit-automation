from __future__ import annotations

import pytest

from bybit_automation.resilience import CircuitBreaker, RetryPolicy, run_with_retry


def test_retry_policy_calculates_capped_delays() -> None:
    policy = RetryPolicy(
        max_attempts=4,
        initial_delay_sec=1,
        max_delay_sec=3,
        multiplier=2,
    )

    assert [policy.delay_for_attempt(index) for index in range(4)] == [1, 2, 3, 3]


def test_retry_policy_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="max_attempts"):
        RetryPolicy(max_attempts=0)
    with pytest.raises(ValueError, match="max_delay"):
        RetryPolicy(initial_delay_sec=2, max_delay_sec=1)
    with pytest.raises(ValueError, match="multiplier"):
        RetryPolicy(multiplier=0.5)


def test_run_with_retry_returns_after_transient_failures() -> None:
    attempts = 0
    sleeps: list[float] = []

    def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise TimeoutError("temporary")
        return "ok"

    result = run_with_retry(
        operation,
        policy=RetryPolicy(max_attempts=3, initial_delay_sec=1, max_delay_sec=2),
        retryable=(TimeoutError,),
        sleep=sleeps.append,
    )

    assert result == "ok"
    assert sleeps == [1, 2]


def test_run_with_retry_raises_last_error_after_attempts_exhausted() -> None:
    with pytest.raises(TimeoutError, match="still down"):
        run_with_retry(
            lambda: (_ for _ in ()).throw(TimeoutError("still down")),
            policy=RetryPolicy(max_attempts=2, initial_delay_sec=1),
            retryable=(TimeoutError,),
            sleep=lambda delay: None,
        )


def test_run_with_retry_does_not_retry_non_retryable_error() -> None:
    sleeps: list[float] = []

    with pytest.raises(ValueError, match="bad input"):
        run_with_retry(
            lambda: (_ for _ in ()).throw(ValueError("bad input")),
            policy=RetryPolicy(max_attempts=3, initial_delay_sec=1),
            retryable=(TimeoutError,),
            sleep=sleeps.append,
        )

    assert sleeps == []


def test_circuit_breaker_opens_after_failure_threshold() -> None:
    breaker = CircuitBreaker(failure_threshold=2, recovery_timeout_sec=10)

    assert breaker.allow_request(100)
    breaker.record_failure(100)
    assert breaker.state == "closed"
    breaker.record_failure(101)

    assert breaker.state == "open"
    assert breaker.failure_count == 2
    assert not breaker.allow_request(105)


def test_circuit_breaker_allows_half_open_after_recovery_timeout() -> None:
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout_sec=10)

    breaker.record_failure(100)

    assert not breaker.allow_request(109)
    assert breaker.allow_request(110)
    assert breaker.state == "half_open"


def test_circuit_breaker_closes_after_half_open_success() -> None:
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout_sec=10)
    breaker.record_failure(100)
    assert breaker.allow_request(110)

    breaker.record_success()

    assert breaker.state == "closed"
    assert breaker.failure_count == 0
    assert breaker.opened_at is None


def test_circuit_breaker_reopens_after_half_open_failure() -> None:
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout_sec=10)
    breaker.record_failure(100)
    assert breaker.allow_request(110)

    breaker.record_failure(111)

    assert breaker.state == "open"
    assert breaker.opened_at == 111
