from __future__ import annotations

from pathlib import Path
import sqlite3


SCHEMA_VERSION = 1


def connect_sqlite(path: str | Path, *, wal: bool) -> sqlite3.Connection:
    db_path = Path(path)
    if db_path.parent != Path("."):
        db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if wal:
        conn.execute("PRAGMA journal_mode = WAL")
    bootstrap_sqlite(conn)
    return conn


def bootstrap_sqlite(conn: sqlite3.Connection) -> None:
    with conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                action TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT,
                amount_usdt REAL NOT NULL,
                amount REAL NOT NULL,
                price REAL,
                reason TEXT NOT NULL,
                submitted INTEGER NOT NULL,
                dry_run INTEGER NOT NULL,
                message TEXT NOT NULL,
                exchange_order_id TEXT
            );

            CREATE TABLE IF NOT EXISTS order_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER,
                created_at TEXT NOT NULL,
                symbol TEXT NOT NULL,
                action TEXT NOT NULL,
                event_type TEXT NOT NULL,
                message TEXT NOT NULL,
                payload_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(order_id) REFERENCES orders(id)
            );

            CREATE TABLE IF NOT EXISTS position_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                size REAL NOT NULL,
                entry_price REAL NOT NULL,
                mark_price REAL NOT NULL,
                profit_pct REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS strategy_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT,
                target_price REAL,
                amount_usdt REAL NOT NULL,
                reason TEXT NOT NULL,
                should_place_order INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS risk_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                symbol TEXT NOT NULL,
                action TEXT NOT NULL,
                close_side TEXT,
                reason TEXT NOT NULL,
                profit_pct REAL NOT NULL,
                highest_profit_pct REAL NOT NULL,
                trailing_tier INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS bot_state (
                key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS config_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                loaded_at TEXT NOT NULL,
                source_path TEXT NOT NULL,
                content_hash TEXT NOT NULL UNIQUE,
                normalized_json TEXT NOT NULL,
                applied_by TEXT NOT NULL,
                reload_reason TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS symbol_trailing_state (
                symbol TEXT PRIMARY KEY,
                highest_profit_pct REAL NOT NULL,
                trailing_tier INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_orders_symbol_created_at
                ON orders(symbol, created_at);
            CREATE INDEX IF NOT EXISTS idx_order_events_symbol_created_at
                ON order_events(symbol, created_at);
            CREATE INDEX IF NOT EXISTS idx_position_snapshots_symbol_created_at
                ON position_snapshots(symbol, created_at);
            CREATE INDEX IF NOT EXISTS idx_strategy_decisions_symbol_created_at
                ON strategy_decisions(symbol, created_at);
            CREATE INDEX IF NOT EXISTS idx_risk_events_symbol_created_at
                ON risk_events(symbol, created_at);
            """
        )
        conn.execute(
            """
            INSERT INTO schema_meta (key, value, updated_at)
            VALUES ('schema_version', ?, datetime('now'))
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
            """,
            (str(SCHEMA_VERSION),),
        )
