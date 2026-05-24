from __future__ import annotations

from bybit_automation.app import BotRuntime
from bybit_automation.config import parse_config
from bybit_automation.exchange_client import MarketSnapshot, TradingRules
from bybit_automation.positions import Position
from bybit_automation.state import RuntimeState
from tests.factories import valid_raw_config


class FakeExchange:
    def __init__(
        self,
        *,
        positions: list[Position] | None = None,
        snapshots: dict[str, MarketSnapshot] | None = None,
        trading_rules: dict[str, TradingRules] | None = None,
    ) -> None:
        self.positions = positions or []
        self.snapshots = snapshots or {}
        self.trading_rules = trading_rules or {}
        self.requested_snapshots: list[str] = []

    def fetch_positions(self) -> list[Position]:
        return self.positions

    def fetch_market_snapshot(self, symbol: str) -> MarketSnapshot | None:
        self.requested_snapshots.append(symbol)
        return self.snapshots.get(symbol)

    def fetch_trading_rules(self, symbol: str) -> TradingRules:
        return self.trading_rules.get(
            symbol,
            TradingRules(symbol=symbol, tick_size=0.01, min_amount=0.001),
        )


def test_runtime_tick_dry_run_with_no_positions_has_strategy_noops() -> None:
    config = parse_config(valid_raw_config(), resolve_secrets=False)
    runtime = BotRuntime(config, exchange=FakeExchange())

    report = runtime.run_once()

    assert report.positions_seen == 0
    assert report.safe_mode is False
    assert len(report.strategy_decisions) == 2
    assert {decision.reason for decision in report.strategy_decisions} == {
        "market snapshot unavailable"
    }
    assert report.order_results == ()


def test_runtime_closing_risk_order_is_dry_run_only() -> None:
    raw = valid_raw_config()
    raw["symbols"] = [{"symbol": "MOODENG/USDT:USDT", "enabled": True}]
    config = parse_config(raw, resolve_secrets=False)
    exchange = FakeExchange(
        positions=[
            Position(
                symbol="MOODENG/USDT:USDT",
                side="long",
                size=1,
                entry_price=100,
                mark_price=98,
            )
        ]
    )
    runtime = BotRuntime(config, exchange=exchange)

    report = runtime.run_once()

    assert report.risk_decisions[0].action == "close"
    assert report.order_results[0].dry_run is True
    assert report.order_results[0].submitted is False
    assert report.order_results[0].intent.amount == 1


def test_runtime_skips_strategy_for_active_position_symbol() -> None:
    raw = valid_raw_config()
    raw["symbols"] = [{"symbol": "MOODENG/USDT:USDT", "enabled": True}]
    config = parse_config(raw, resolve_secrets=False)
    exchange = FakeExchange(
        positions=[
            Position(
                symbol="MOODENG/USDT:USDT",
                side="long",
                size=1,
                entry_price=100,
                mark_price=101,
            )
        ],
        snapshots={
            "MOODENG/USDT:USDT": MarketSnapshot(
                symbol="MOODENG/USDT:USDT",
                mark_price=101,
                close_prices=(99, 100, 101),
                atr_pct=1,
                average_amplitude_pct=1,
            )
        },
    )
    runtime = BotRuntime(config, exchange=exchange)

    report = runtime.run_once()

    assert report.strategy_decisions == ()
    assert exchange.requested_snapshots == []


def test_runtime_executes_strategy_entry_order_intents_in_dry_run() -> None:
    raw = valid_raw_config()
    raw["symbols"] = [{"symbol": "MOODENG/USDT:USDT", "enabled": True}]
    config = parse_config(raw, resolve_secrets=False)
    state = RuntimeState()
    exchange = FakeExchange(
        snapshots={
            "MOODENG/USDT:USDT": MarketSnapshot(
                symbol="MOODENG/USDT:USDT",
                mark_price=100,
                close_prices=(98, 99, 101),
                atr_pct=1,
                average_amplitude_pct=1,
            )
        },
        trading_rules={
            "MOODENG/USDT:USDT": TradingRules(
                symbol="MOODENG/USDT:USDT",
                tick_size=0.01,
                min_amount=0.001,
            )
        },
    )
    runtime = BotRuntime(config, exchange=exchange, state=state)

    report = runtime.run_once()

    assert report.strategy_decisions[0].should_place_order is True
    assert [result.intent.action for result in report.order_results] == [
        "cancel_all",
        "place_limit",
    ]
    assert all(result.dry_run for result in report.order_results)
    assert report.order_results[1].intent.side == "buy"
    assert report.order_results[1].intent.price == 97.0
    assert report.order_results[1].intent.amount > 0
    assert state.get_symbol("MOODENG/USDT:USDT").status == "ENTRY_ORDER_PLACED"
