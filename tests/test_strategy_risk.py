from __future__ import annotations

from bybit_stream_bot.config import parse_config
from bybit_stream_bot.exchange_client import MarketSnapshot
from bybit_stream_bot.positions import Position
from bybit_stream_bot.risk import RiskManager
from bybit_stream_bot.state import SymbolRuntimeState
from bybit_stream_bot.strategy import StrategyEngine
from tests.factories import valid_raw_config


def test_strategy_engine_places_buy_for_bullish_trend() -> None:
    config = parse_config(valid_raw_config(), resolve_secrets=False)
    market = MarketSnapshot(
        symbol="MOODENG/USDT:USDT",
        mark_price=100,
        close_prices=(98, 99, 101),
        atr_pct=1,
        average_amplitude_pct=1,
    )

    decisions = StrategyEngine().evaluate(config.symbols[0], market)

    assert len(decisions) == 1
    assert decisions[0].side == "buy"
    assert decisions[0].should_place_order is True
    assert decisions[0].target_price == 97


def test_risk_manager_closes_on_fixed_stop_loss() -> None:
    config = parse_config(valid_raw_config(), resolve_secrets=False)
    position = Position(
        symbol="MOODENG/USDT:USDT",
        side="long",
        size=1,
        entry_price=100,
        mark_price=99,
    )

    decision = RiskManager().evaluate(
        position,
        SymbolRuntimeState(symbol=position.symbol),
        config.risk_defaults,
    )

    assert decision.action == "close"
    assert decision.close_side == "sell"
    assert decision.reason == "fixed stop loss reached"

