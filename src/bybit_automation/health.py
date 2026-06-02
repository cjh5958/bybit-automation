from __future__ import annotations

from dataclasses import dataclass
import sqlite3
from typing import Literal

from bybit_automation.cache import RealtimeCache
from bybit_automation.config import BotConfig
from bybit_automation.ws import WebSocketRuntime


HealthStatus = Literal["pass", "warn", "fail"]


@dataclass(frozen=True)
class HealthCheckResult:
    name: str
    status: HealthStatus
    message: str


@dataclass(frozen=True)
class HealthReport:
    checks: tuple[HealthCheckResult, ...]

    @property
    def status(self) -> HealthStatus:
        statuses = {check.status for check in self.checks}
        if "fail" in statuses:
            return "fail"
        if "warn" in statuses:
            return "warn"
        return "pass"

    def to_payload(self) -> dict:
        return {
            "status": self.status,
            "checks": [
                {
                    "name": check.name,
                    "status": check.status,
                    "message": check.message,
                }
                for check in self.checks
            ],
        }


def build_health_report(
    *,
    config: BotConfig,
    sqlite_conn: sqlite3.Connection,
    cache: RealtimeCache,
    websocket: WebSocketRuntime,
) -> HealthReport:
    return HealthReport(
        checks=(
            check_sqlite(sqlite_conn),
            check_redis(cache),
            check_websocket(websocket),
            check_exchange_readiness(config),
        )
    )


def check_sqlite(conn: sqlite3.Connection) -> HealthCheckResult:
    try:
        conn.execute("CREATE TEMP TABLE IF NOT EXISTS health_check (id INTEGER)")
        conn.execute("INSERT INTO health_check (id) VALUES (1)")
        conn.execute("DELETE FROM health_check")
    except sqlite3.Error as exc:
        return HealthCheckResult("sqlite", "fail", f"sqlite write check failed: {exc}")
    return HealthCheckResult("sqlite", "pass", "sqlite writable")


def check_redis(cache: RealtimeCache) -> HealthCheckResult:
    if not cache.health.enabled:
        return HealthCheckResult("redis", "warn", "redis disabled")
    if not cache.health.available:
        return HealthCheckResult("redis", "warn", cache.health.message)
    return HealthCheckResult("redis", "pass", cache.health.message)


def check_websocket(websocket: WebSocketRuntime) -> HealthCheckResult:
    if not websocket.enabled:
        return HealthCheckResult("websocket", "warn", "websocket disabled")
    if websocket.health is None:
        return HealthCheckResult("websocket", "fail", "websocket enabled without health")
    if websocket.health.status in {"healthy", "stopped"}:
        return HealthCheckResult("websocket", "pass", websocket.message)
    return HealthCheckResult(
        "websocket",
        "warn",
        websocket.health.reason or websocket.message,
    )


def check_exchange_readiness(config: BotConfig) -> HealthCheckResult:
    if config.app.mode == "dry_run":
        return HealthCheckResult("exchange", "pass", "dry_run mode does not require exchange network")
    if not config.exchange.api_key or not config.exchange.api_secret:
        return HealthCheckResult("exchange", "fail", "exchange credentials are missing")
    return HealthCheckResult(
        "exchange",
        "warn",
        f"{config.app.mode} credentials present; network preflight not run",
    )
