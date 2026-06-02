from __future__ import annotations

import sqlite3

from bybit_automation.cache import CacheHealth, NoopRealtimeCache, RedisRealtimeCache
from bybit_automation.config import parse_config
from bybit_automation.health import (
    HealthCheckResult,
    HealthReport,
    build_health_report,
    check_exchange_readiness,
)
from bybit_automation.ws import StreamHealth, WebSocketRuntime
from tests.factories import valid_raw_config
from tests.test_cache import FakeRedis


def test_health_report_status_uses_worst_check() -> None:
    assert HealthReport((HealthCheckResult("a", "pass", "ok"),)).status == "pass"
    assert (
        HealthReport(
            (
                HealthCheckResult("a", "pass", "ok"),
                HealthCheckResult("b", "warn", "careful"),
            )
        ).status
        == "warn"
    )
    assert (
        HealthReport(
            (
                HealthCheckResult("a", "warn", "careful"),
                HealthCheckResult("b", "fail", "bad"),
            )
        ).status
        == "fail"
    )


def test_build_health_report_for_default_dry_run_is_warn_because_optional_services_disabled() -> None:
    config = parse_config(valid_raw_config(), resolve_secrets=False)
    conn = sqlite3.connect(":memory:")
    websocket = WebSocketRuntime(enabled=False, health=None, message="websocket disabled")

    report = build_health_report(
        config=config,
        sqlite_conn=conn,
        cache=NoopRealtimeCache(),
        websocket=websocket,
    )

    assert report.status == "warn"
    assert report.to_payload()["checks"] == [
        {"name": "sqlite", "status": "pass", "message": "sqlite writable"},
        {"name": "redis", "status": "warn", "message": "redis disabled"},
        {"name": "websocket", "status": "warn", "message": "websocket disabled"},
        {
            "name": "exchange",
            "status": "pass",
            "message": "dry_run mode does not require exchange network",
        },
    ]
    conn.close()


def test_health_report_passes_when_optional_services_are_available() -> None:
    raw = valid_raw_config()
    raw["cache"]["redis"]["enabled"] = True
    raw["websocket"]["enabled"] = True
    config = parse_config(raw, resolve_secrets=False)
    conn = sqlite3.connect(":memory:")
    cache = RedisRealtimeCache(
        client=FakeRedis(),
        namespace="bot",
        health=CacheHealth(enabled=True, available=True, message="redis available"),
    )
    websocket = WebSocketRuntime(
        enabled=True,
        health=StreamHealth(status="healthy", last_message_at=100),
        message="websocket healthy",
    )

    report = build_health_report(
        config=config,
        sqlite_conn=conn,
        cache=cache,
        websocket=websocket,
    )

    assert report.status == "pass"
    conn.close()


def test_exchange_readiness_fails_for_demo_without_credentials() -> None:
    raw = valid_raw_config()
    raw["app"]["mode"] = "demo"
    config = parse_config(raw, resolve_secrets=False)

    result = check_exchange_readiness(config)

    assert result.status == "fail"
    assert result.message == "exchange credentials are missing"
