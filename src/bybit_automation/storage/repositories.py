from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import sqlite3
import tomllib
from typing import Any

from bybit_automation.orders import OrderResult
from bybit_automation.positions import Position
from bybit_automation.risk import RiskDecision
from bybit_automation.state import SymbolRuntimeState
from bybit_automation.strategy import StrategyDecision


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class TrailingStateRecord:
    symbol: str
    highest_profit_pct: float
    trailing_tier: int


class PositionSnapshotRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def append_many(self, positions: list[Position]) -> None:
        timestamp = utc_now()
        with self._conn:
            self._conn.executemany(
                """
                INSERT INTO position_snapshots (
                    created_at, symbol, side, size, entry_price, mark_price, profit_pct
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        timestamp,
                        position.symbol,
                        position.side,
                        position.size,
                        position.entry_price,
                        position.mark_price,
                        position.profit_pct,
                    )
                    for position in positions
                ],
            )


class StrategyDecisionRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def append_many(self, decisions: list[StrategyDecision]) -> None:
        timestamp = utc_now()
        with self._conn:
            self._conn.executemany(
                """
                INSERT INTO strategy_decisions (
                    created_at, symbol, side, target_price, amount_usdt, reason,
                    should_place_order
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        timestamp,
                        decision.symbol,
                        decision.side,
                        decision.target_price,
                        decision.amount_usdt,
                        decision.reason,
                        int(decision.should_place_order),
                    )
                    for decision in decisions
                ],
            )


class RiskEventRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def append_many(self, decisions: list[RiskDecision]) -> None:
        timestamp = utc_now()
        with self._conn:
            self._conn.executemany(
                """
                INSERT INTO risk_events (
                    created_at, symbol, action, close_side, reason, profit_pct,
                    highest_profit_pct, trailing_tier
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        timestamp,
                        decision.symbol,
                        decision.action,
                        decision.close_side,
                        decision.reason,
                        decision.profit_pct,
                        decision.highest_profit_pct,
                        decision.trailing_tier,
                    )
                    for decision in decisions
                ],
            )


class OrderRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def append_result(self, result: OrderResult) -> int:
        timestamp = utc_now()
        intent = result.intent
        with self._conn:
            cursor = self._conn.execute(
                """
                INSERT INTO orders (
                    created_at, action, symbol, side, amount_usdt, amount, price,
                    reason, submitted, dry_run, message, exchange_order_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp,
                    intent.action,
                    intent.symbol,
                    intent.side,
                    intent.amount_usdt,
                    intent.amount,
                    intent.price,
                    intent.reason,
                    int(result.submitted),
                    int(result.dry_run),
                    result.message,
                    result.exchange_order_id,
                ),
            )
            order_id = int(cursor.lastrowid)
            self._conn.execute(
                """
                INSERT INTO order_events (
                    order_id, created_at, symbol, action, event_type, message, payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order_id,
                    timestamp,
                    intent.symbol,
                    intent.action,
                    _order_event_type(result),
                    result.message,
                    json.dumps(asdict(result), sort_keys=True),
                ),
            )
            return order_id


class TrailingStateRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def save(self, state: SymbolRuntimeState) -> None:
        self.save_state_values(
            symbol=state.symbol,
            highest_profit_pct=state.highest_profit_pct,
            trailing_tier=state.trailing_tier,
        )

    def save_state_values(
        self,
        *,
        symbol: str,
        highest_profit_pct: float,
        trailing_tier: int,
    ) -> None:
        timestamp = utc_now()
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO symbol_trailing_state (
                    symbol, highest_profit_pct, trailing_tier, updated_at
                )
                VALUES (?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    highest_profit_pct = excluded.highest_profit_pct,
                    trailing_tier = excluded.trailing_tier,
                    updated_at = excluded.updated_at
                """,
                (symbol, highest_profit_pct, trailing_tier, timestamp),
            )

    def load(self, symbol: str) -> TrailingStateRecord | None:
        row = self._conn.execute(
            """
            SELECT symbol, highest_profit_pct, trailing_tier
            FROM symbol_trailing_state
            WHERE symbol = ?
            """,
            (symbol,),
        ).fetchone()
        if row is None:
            return None
        return TrailingStateRecord(
            symbol=str(row["symbol"]),
            highest_profit_pct=float(row["highest_profit_pct"]),
            trailing_tier=int(row["trailing_tier"]),
        )

    def load_all(self) -> dict[str, TrailingStateRecord]:
        rows = self._conn.execute(
            """
            SELECT symbol, highest_profit_pct, trailing_tier
            FROM symbol_trailing_state
            """
        ).fetchall()
        return {
            str(row["symbol"]): TrailingStateRecord(
                symbol=str(row["symbol"]),
                highest_profit_pct=float(row["highest_profit_pct"]),
                trailing_tier=int(row["trailing_tier"]),
            )
            for row in rows
        }


class BotStateRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def set_json(self, key: str, value: dict[str, Any]) -> None:
        timestamp = utc_now()
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO bot_state (key, value_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value_json = excluded.value_json,
                    updated_at = excluded.updated_at
                """,
                (key, json.dumps(value, sort_keys=True), timestamp),
            )

    def get_json(self, key: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT value_json FROM bot_state WHERE key = ?",
            (key,),
        ).fetchone()
        if row is None:
            return None
        value = json.loads(str(row["value_json"]))
        if not isinstance(value, dict):
            raise ValueError(f"bot_state[{key}] is not a JSON object")
        return value


class ConfigVersionRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def record_file(
        self,
        path: str | Path,
        *,
        applied_by: str = "runtime",
        reload_reason: str = "startup",
    ) -> int:
        config_path = Path(path)
        raw_content = config_path.read_bytes()
        content_hash = hashlib.sha256(raw_content).hexdigest()
        normalized = tomllib.loads(raw_content.decode("utf-8"))
        normalized_json = json.dumps(normalized, sort_keys=True)

        with self._conn:
            self._conn.execute(
                """
                INSERT OR IGNORE INTO config_versions (
                    loaded_at, source_path, content_hash, normalized_json, applied_by,
                    reload_reason
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    utc_now(),
                    str(config_path),
                    content_hash,
                    normalized_json,
                    applied_by,
                    reload_reason,
                ),
            )
            row = self._conn.execute(
                "SELECT id FROM config_versions WHERE content_hash = ?",
                (content_hash,),
            ).fetchone()
        if row is None:
            raise RuntimeError("failed to record config version")
        return int(row["id"])


@dataclass
class PersistenceRepositories:
    positions: PositionSnapshotRepository
    strategy_decisions: StrategyDecisionRepository
    risk_events: RiskEventRepository
    orders: OrderRepository
    trailing_state: TrailingStateRepository
    bot_state: BotStateRepository
    config_versions: ConfigVersionRepository

    @classmethod
    def from_connection(cls, conn: sqlite3.Connection) -> PersistenceRepositories:
        return cls(
            positions=PositionSnapshotRepository(conn),
            strategy_decisions=StrategyDecisionRepository(conn),
            risk_events=RiskEventRepository(conn),
            orders=OrderRepository(conn),
            trailing_state=TrailingStateRepository(conn),
            bot_state=BotStateRepository(conn),
            config_versions=ConfigVersionRepository(conn),
        )


def _order_event_type(result: OrderResult) -> str:
    if result.dry_run:
        return "dry_run_recorded"
    if result.submitted:
        return "submitted"
    return "recorded"
