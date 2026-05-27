from __future__ import annotations

from pathlib import Path

from bybit_automation.config import parse_config
from bybit_automation.orders import OrderIntent, OrderResult
from bybit_automation.positions import Position
from bybit_automation.risk import RiskDecision
from bybit_automation.state import SymbolRuntimeState
from bybit_automation.storage import PersistenceRepositories, connect_sqlite
from bybit_automation.strategy import StrategyDecision
from tests.factories import valid_raw_config


def test_connect_sqlite_bootstraps_schema_and_wal(tmp_path: Path) -> None:
    db_path = tmp_path / "nested" / "bot.sqlite3"

    conn = connect_sqlite(db_path, wal=True)
    journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    schema_version = conn.execute(
        "SELECT value FROM schema_meta WHERE key = 'schema_version'"
    ).fetchone()[0]

    assert db_path.exists()
    assert journal_mode == "wal"
    assert schema_version == "1"

    conn.close()


def test_bootstrap_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "bot.sqlite3"

    first = connect_sqlite(db_path, wal=False)
    first.close()
    second = connect_sqlite(db_path, wal=False)

    tables = {
        row[0]
        for row in second.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }

    assert "orders" in tables
    assert "risk_events" in tables
    assert "symbol_trailing_state" in tables

    second.close()


def test_repositories_persist_records_across_reopen(tmp_path: Path) -> None:
    db_path = tmp_path / "bot.sqlite3"
    conn = connect_sqlite(db_path, wal=False)
    repositories = PersistenceRepositories.from_connection(conn)

    repositories.positions.append_many(
        [
            Position(
                symbol="MOODENG/USDT:USDT",
                side="long",
                size=2,
                entry_price=100,
                mark_price=103,
            )
        ]
    )
    repositories.strategy_decisions.append_many(
        [
            StrategyDecision(
                symbol="MOODENG/USDT:USDT",
                side="buy",
                target_price=97,
                amount_usdt=30,
                reason="bullish trend",
            )
        ]
    )
    repositories.risk_events.append_many(
        [
            RiskDecision(
                symbol="MOODENG/USDT:USDT",
                action="hold",
                close_side=None,
                reason="risk limits not reached",
                profit_pct=3,
                highest_profit_pct=3,
                trailing_tier=2,
            )
        ]
    )
    repositories.orders.append_result(
        OrderResult(
            intent=OrderIntent(
                action="place_limit",
                symbol="MOODENG/USDT:USDT",
                side="buy",
                amount_usdt=30,
                amount=2.9,
                price=97,
                reason="bullish trend",
            ),
            submitted=False,
            dry_run=True,
            message="dry_run: order intent recorded but not submitted",
        )
    )
    repositories.trailing_state.save(
        SymbolRuntimeState(
            symbol="MOODENG/USDT:USDT",
            highest_profit_pct=3,
            trailing_tier=2,
        )
    )
    repositories.bot_state.set_json("last_tick", {"safe_mode": False})
    conn.close()

    reopened = connect_sqlite(db_path, wal=False)
    reopened_repositories = PersistenceRepositories.from_connection(reopened)

    assert reopened.execute("SELECT COUNT(*) FROM position_snapshots").fetchone()[0] == 1
    assert reopened.execute("SELECT COUNT(*) FROM strategy_decisions").fetchone()[0] == 1
    assert reopened.execute("SELECT COUNT(*) FROM risk_events").fetchone()[0] == 1
    assert reopened.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 1
    assert reopened.execute("SELECT COUNT(*) FROM order_events").fetchone()[0] == 1
    assert reopened_repositories.trailing_state.load(
        "MOODENG/USDT:USDT"
    ).highest_profit_pct == 3
    assert reopened_repositories.bot_state.get_json("last_tick") == {"safe_mode": False}

    reopened.close()


def test_repositories_read_reconciliation_snapshots(tmp_path: Path) -> None:
    db_path = tmp_path / "bot.sqlite3"
    conn = connect_sqlite(db_path, wal=False)
    repositories = PersistenceRepositories.from_connection(conn)

    repositories.positions.append_many(
        [
            Position(
                symbol="MOODENG/USDT:USDT",
                side="long",
                size=1,
                entry_price=100,
                mark_price=101,
            )
        ]
    )
    repositories.positions.append_many(
        [
            Position(
                symbol="MOODENG/USDT:USDT",
                side="long",
                size=2,
                entry_price=100,
                mark_price=103,
            )
        ]
    )
    repositories.orders.append_result(
        OrderResult(
            intent=OrderIntent(
                action="place_limit",
                symbol="MOODENG/USDT:USDT",
                side="buy",
                amount=2,
                price=97,
                reason="submitted order",
            ),
            submitted=True,
            dry_run=False,
            message="order submitted",
            exchange_order_id="order-1",
        )
    )
    repositories.orders.append_result(
        OrderResult(
            intent=OrderIntent(
                action="place_limit",
                symbol="1000X/USDT:USDT",
                side="sell",
                amount=3,
                price=104,
                reason="dry-run order",
            ),
            submitted=False,
            dry_run=True,
            message="dry_run: order intent recorded but not submitted",
        )
    )

    latest_positions = repositories.positions.latest_by_symbol()
    submitted_orders = repositories.orders.list_submitted()

    assert latest_positions["MOODENG/USDT:USDT"].size == 2
    assert latest_positions["MOODENG/USDT:USDT"].profit_pct == 3
    assert len(submitted_orders) == 1
    assert submitted_orders[0].exchange_order_id == "order-1"
    assert submitted_orders[0].dry_run is False

    conn.close()


def test_trailing_state_repository_deletes_stale_state(tmp_path: Path) -> None:
    db_path = tmp_path / "bot.sqlite3"
    conn = connect_sqlite(db_path, wal=False)
    repositories = PersistenceRepositories.from_connection(conn)
    repositories.trailing_state.save_state_values(
        symbol="MOODENG/USDT:USDT",
        highest_profit_pct=4,
        trailing_tier=2,
    )

    repositories.trailing_state.delete("MOODENG/USDT:USDT")

    assert repositories.trailing_state.load("MOODENG/USDT:USDT") is None

    conn.close()


def test_config_version_repository_records_config_file(tmp_path: Path) -> None:
    db_path = tmp_path / "bot.sqlite3"
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
        [app]
        mode = "dry_run"
        log_level = "INFO"
        timezone = "Asia/Taipei"
        """,
        encoding="utf-8",
    )
    conn = connect_sqlite(db_path, wal=False)
    repositories = PersistenceRepositories.from_connection(conn)

    first_id = repositories.config_versions.record_file(config_path)
    second_id = repositories.config_versions.record_file(config_path)

    assert first_id == second_id
    assert conn.execute("SELECT COUNT(*) FROM config_versions").fetchone()[0] == 1

    conn.close()


def test_valid_config_sqlite_settings_can_open_database(tmp_path: Path) -> None:
    raw = valid_raw_config()
    raw["database"]["sqlite"]["path"] = str(tmp_path / "bot.sqlite3")
    config = parse_config(raw, resolve_secrets=False)

    conn = connect_sqlite(config.sqlite.path, wal=config.sqlite.wal)

    assert Path(config.sqlite.path).exists()

    conn.close()
