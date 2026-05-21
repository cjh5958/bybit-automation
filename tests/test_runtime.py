from __future__ import annotations

from bybit_stream_bot.app import BotRuntime
from bybit_stream_bot.config import parse_config
from bybit_stream_bot.exchange_client import MarketSnapshot
from bybit_stream_bot.positions import Position
from tests.factories import valid_raw_config


class FakeExchange:
    def __init__(
        self,
        *,
        positions: list[Position] | None = None,
        snapshots: dict[str, MarketSnapshot] | None = None,
    ) -> None:
        self.positions = positions or []
        self.snapshots = snapshots or {}
        self.requested_snapshots: list[str] = []

    def fetch_positions(self) -> list[Position]:
        return self.positions

    def fetch_market_snapshot(self, symbol: str) -> MarketSnapshot | None:
        self.requested_snapshots.append(symbol)
        return self.snapshots.get(symbol)


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
