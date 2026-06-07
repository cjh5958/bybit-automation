from __future__ import annotations

from pathlib import Path
import sqlite3

from bybit_automation.app import BotRuntime
from bybit_automation.cache import CachedExchangeClient, NoopRealtimeCache
from bybit_automation.config import parse_config
from bybit_automation.exchange_client import MarketSnapshot, OpenOrder, TradingRules
from bybit_automation.positions import Position
from bybit_automation.storage import PersistenceRepositories, connect_sqlite
from tests.factories import valid_raw_config


class PersistentFakeExchange:
    def __init__(
        self,
        *,
        positions: list[Position] | None = None,
        snapshots: dict[str, MarketSnapshot] | None = None,
        open_orders: list[OpenOrder] | None = None,
        cancel_failures: set[str] | None = None,
    ) -> None:
        self.positions = positions or []
        self.snapshots = snapshots or {}
        self.open_orders = open_orders or []
        self.cancel_failures = cancel_failures or set()
        self.canceled_symbols: list[str] = []

    def fetch_positions(self) -> list[Position]:
        return self.positions

    def fetch_open_orders(self) -> list[OpenOrder]:
        return self.open_orders

    def fetch_market_snapshot(self, symbol: str) -> MarketSnapshot | None:
        return self.snapshots.get(symbol)

    def fetch_trading_rules(self, symbol: str) -> TradingRules:
        return TradingRules(symbol=symbol, tick_size=0.01, min_amount=0.001)

    def create_limit_order(
        self,
        *,
        symbol: str,
        side: str,
        amount: float,
        price: float,
    ) -> dict:
        return {"id": f"{symbol}-{side}-limit", "amount": amount, "price": price}

    def create_market_order(
        self,
        *,
        symbol: str,
        side: str,
        amount: float,
    ) -> dict:
        return {"id": f"{symbol}-{side}-market", "amount": amount}

    def cancel_all_orders(self, symbol: str) -> list[str]:
        if symbol in self.cancel_failures:
            raise RuntimeError(f"cancel failed for {symbol}")
        self.canceled_symbols.append(symbol)
        return [order.exchange_order_id for order in self.open_orders if order.symbol == symbol]


def repositories_for(tmp_path: Path) -> tuple[PersistenceRepositories, sqlite3.Connection]:
    conn = connect_sqlite(tmp_path / "bot.sqlite3", wal=False)
    return PersistenceRepositories.from_connection(conn), conn


def test_runtime_persists_strategy_orders_and_bot_state(tmp_path: Path) -> None:
    raw = valid_raw_config()
    raw["symbols"] = [{"symbol": "MOODENG/USDT:USDT", "enabled": True}]
    config = parse_config(raw, resolve_secrets=False)
    repositories, conn = repositories_for(tmp_path)
    runtime = BotRuntime(
        config,
        exchange=PersistentFakeExchange(
            snapshots={
                "MOODENG/USDT:USDT": MarketSnapshot(
                    symbol="MOODENG/USDT:USDT",
                    mark_price=100,
                    close_prices=(98, 99, 101),
                    atr_pct=1,
                    average_amplitude_pct=1,
                )
            }
        ),
        repositories=repositories,
    )

    report = runtime.run_once()

    assert len(report.strategy_decisions) == 1
    assert len(report.order_results) == 2
    assert conn.execute("SELECT COUNT(*) FROM position_snapshots").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM strategy_decisions").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM order_events").fetchone()[0] == 2
    assert repositories.bot_state.get_json("last_tick") == {
        "market_data_fresh": True,
        "positions_seen": 0,
        "ran_risk": True,
        "ran_strategy": True,
        "safe_mode": False,
        "safe_mode_reason": None,
        "strategy_pause_reason": None,
    }

    conn.close()


def test_runtime_restores_and_persists_trailing_state(tmp_path: Path) -> None:
    raw = valid_raw_config()
    raw["symbols"] = [{"symbol": "MOODENG/USDT:USDT", "enabled": True}]
    config = parse_config(raw, resolve_secrets=False)
    repositories, conn = repositories_for(tmp_path)
    repositories.trailing_state.save_state_values(
        symbol="MOODENG/USDT:USDT",
        highest_profit_pct=5,
        trailing_tier=2,
    )
    runtime = BotRuntime(
        config,
        exchange=PersistentFakeExchange(
            positions=[
                Position(
                    symbol="MOODENG/USDT:USDT",
                    side="long",
                    size=1,
                    entry_price=100,
                    mark_price=104,
                )
            ]
        ),
        repositories=repositories,
    )

    report = runtime.run_once(include_strategy=False)
    saved = repositories.trailing_state.load("MOODENG/USDT:USDT")

    assert report.risk_decisions[0].highest_profit_pct == 5
    assert saved is not None
    assert saved.highest_profit_pct == 5
    assert saved.trailing_tier == 2
    assert conn.execute("SELECT COUNT(*) FROM position_snapshots").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM risk_events").fetchone()[0] == 1

    conn.close()


def test_startup_reconciliation_clears_stale_trailing_state(tmp_path: Path) -> None:
    raw = valid_raw_config()
    raw["symbols"] = [{"symbol": "MOODENG/USDT:USDT", "enabled": True}]
    config = parse_config(raw, resolve_secrets=False)
    repositories, conn = repositories_for(tmp_path)
    repositories.trailing_state.save_state_values(
        symbol="MOODENG/USDT:USDT",
        highest_profit_pct=5,
        trailing_tier=2,
    )

    runtime = BotRuntime(
        config,
        exchange=PersistentFakeExchange(),
        repositories=repositories,
    )

    assert repositories.trailing_state.load("MOODENG/USDT:USDT") is None
    assert runtime.state.get_symbol("MOODENG/USDT:USDT").highest_profit_pct == 0
    assert runtime.state.safe_mode is False
    assert repositories.bot_state.get_json("last_reconciliation") == {
        "exchange_open_orders": 0,
        "exchange_positions": 0,
        "issues": [
            {
                "code": "stale_trailing_state",
                "message": "trailing state exists for a symbol with no active exchange position",
                "severity": "info",
                "symbol": "MOODENG/USDT:USDT",
            }
        ],
        "safe_mode": False,
        "safe_mode_required": False,
        "stale_trailing_state_symbols": ["MOODENG/USDT:USDT"],
    }

    conn.close()


def test_startup_reconciliation_enters_safe_mode_for_unknown_open_order(
    tmp_path: Path,
) -> None:
    raw = valid_raw_config()
    raw["symbols"] = [{"symbol": "MOODENG/USDT:USDT", "enabled": True}]
    config = parse_config(raw, resolve_secrets=False)
    repositories, conn = repositories_for(tmp_path)
    runtime = BotRuntime(
        config,
        exchange=PersistentFakeExchange(
            open_orders=[
                OpenOrder(
                    exchange_order_id="exchange-only",
                    symbol="MOODENG/USDT:USDT",
                    side="buy",
                    amount=1,
                    price=97,
                    status="open",
                )
            ],
            snapshots={
                "MOODENG/USDT:USDT": MarketSnapshot(
                    symbol="MOODENG/USDT:USDT",
                    mark_price=100,
                    close_prices=(98, 99, 101),
                    atr_pct=1,
                    average_amplitude_pct=1,
                )
            },
        ),
        repositories=repositories,
    )

    report = runtime.run_once()

    assert runtime.state.safe_mode is True
    assert runtime.state.safe_mode_reason == "unknown_exchange_open_order"
    assert report.ran_strategy is False
    assert report.strategy_decisions == ()
    assert report.order_results == ()
    assert repositories.bot_state.get_json("last_tick") == {
        "market_data_fresh": True,
        "positions_seen": 0,
        "ran_risk": True,
        "ran_strategy": False,
        "safe_mode": True,
        "safe_mode_reason": "unknown_exchange_open_order",
        "strategy_pause_reason": "safe_mode",
    }

    conn.close()


def test_startup_reconciliation_uses_exchange_snapshot_through_cache_wrapper(
    tmp_path: Path,
) -> None:
    raw = valid_raw_config()
    raw["symbols"] = [{"symbol": "MOODENG/USDT:USDT", "enabled": True}]
    config = parse_config(raw, resolve_secrets=False)
    repositories, conn = repositories_for(tmp_path)
    exchange = CachedExchangeClient(
        PersistentFakeExchange(
            open_orders=[
                OpenOrder(
                    exchange_order_id="exchange-only",
                    symbol="MOODENG/USDT:USDT",
                    side="buy",
                    amount=1,
                    price=97,
                    status="open",
                )
            ]
        ),
        NoopRealtimeCache(),
    )

    runtime = BotRuntime(config, exchange=exchange, repositories=repositories)

    assert runtime.state.safe_mode is True
    assert runtime.state.safe_mode_reason == "unknown_exchange_open_order"

    conn.close()


def test_startup_reconciliation_enters_safe_mode_when_exchange_snapshot_fails(
    tmp_path: Path,
) -> None:
    class FailingExchange(PersistentFakeExchange):
        def fetch_open_orders(self) -> list[OpenOrder]:
            raise RuntimeError("network unavailable")

    config = parse_config(valid_raw_config(), resolve_secrets=False)
    repositories, conn = repositories_for(tmp_path)
    runtime = BotRuntime(
        config,
        exchange=FailingExchange(),
        repositories=repositories,
    )

    assert runtime.state.safe_mode is True
    assert runtime.state.safe_mode_reason == "exchange_snapshot_failed"
    assert repositories.bot_state.get_json("last_reconciliation")["issues"][0]["message"] == (
        "network unavailable"
    )

    conn.close()


def test_runtime_shutdown_persists_final_state(tmp_path: Path) -> None:
    config = parse_config(valid_raw_config(), resolve_secrets=False)
    repositories, conn = repositories_for(tmp_path)
    runtime = BotRuntime(
        config,
        exchange=PersistentFakeExchange(
            open_orders=[
                OpenOrder(
                    exchange_order_id="exchange-only",
                    symbol="MOODENG/USDT:USDT",
                    side="buy",
                    amount=1,
                    price=97,
                    status="open",
                )
            ]
        ),
        repositories=repositories,
    )

    runtime.shutdown(reason="keyboard_interrupt")

    assert repositories.bot_state.get_json("shutdown") == {
        "reason": "keyboard_interrupt",
        "safe_mode": True,
        "safe_mode_reason": "unknown_exchange_open_order",
    }

    conn.close()


def test_runtime_shutdown_cleanup_continues_after_symbol_failure(tmp_path: Path) -> None:
    raw = valid_raw_config()
    raw["symbols"] = [
        {"symbol": "MOODENG/USDT:USDT", "enabled": True},
        {"symbol": "1000X/USDT:USDT", "enabled": True},
        {"symbol": "DISABLED/USDT:USDT", "enabled": False},
    ]
    raw["app"]["mode"] = "demo"
    config = parse_config(raw, resolve_secrets=False)
    repositories, conn = repositories_for(tmp_path)
    exchange = PersistentFakeExchange(
        open_orders=[
            OpenOrder(
                exchange_order_id="order-2",
                symbol="1000X/USDT:USDT",
                side="sell",
                amount=1,
                price=100,
                status="open",
            )
        ],
        cancel_failures={"MOODENG/USDT:USDT"},
    )
    runtime = BotRuntime(config, exchange=exchange, repositories=repositories)

    runtime.shutdown(reason="error", cancel_open_orders=True)

    cleanup = repositories.bot_state.get_json("shutdown_cleanup")
    assert cleanup == {
        "reason": "error",
        "success": False,
        "symbols": [
            {
                "symbol": "MOODENG/USDT:USDT",
                "status": "error",
                "error": "cancel failed for MOODENG/USDT:USDT",
            },
            {
                "symbol": "1000X/USDT:USDT",
                "status": "success",
                "submitted": True,
                "dry_run": False,
                "canceled_count": 1,
                "message": "canceled 1 open orders",
            },
        ],
    }
    assert repositories.bot_state.get_json("shutdown")["reason"] == "error"
    assert exchange.canceled_symbols == ["1000X/USDT:USDT"]
    assert conn.execute("SELECT COUNT(*) FROM orders WHERE action = 'cancel_all'").fetchone()[0] == 1

    conn.close()
