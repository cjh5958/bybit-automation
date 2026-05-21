from __future__ import annotations

from dataclasses import dataclass

from bybit_stream_bot.config import BotConfig
from bybit_stream_bot.exchange_client import ExchangeClient, create_exchange_client
from bybit_stream_bot.log import configure_logging
from bybit_stream_bot.notifier import Notifier
from bybit_stream_bot.orders import OrderIntent, OrderManager, OrderResult
from bybit_stream_bot.positions import Position, PositionManager
from bybit_stream_bot.risk import RiskDecision, RiskManager
from bybit_stream_bot.state import RuntimeState
from bybit_stream_bot.strategy import StrategyDecision, StrategyEngine


@dataclass(frozen=True)
class RuntimeReport:
    positions_seen: int
    strategy_decisions: tuple[StrategyDecision, ...]
    risk_decisions: tuple[RiskDecision, ...]
    order_results: tuple[OrderResult, ...]
    safe_mode: bool


class BotRuntime:
    def __init__(
        self,
        config: BotConfig,
        *,
        exchange: ExchangeClient | None = None,
        state: RuntimeState | None = None,
        notifier: Notifier | None = None,
    ) -> None:
        self.config = config
        self.state = state or RuntimeState()
        self.exchange = exchange or create_exchange_client(config)
        self.notifier = notifier or Notifier()
        self.strategy = StrategyEngine()
        self.risk = RiskManager()
        self.positions = PositionManager(self.state)
        self.orders = OrderManager(
            dry_run=config.app.mode == "dry_run",
            executor=self.exchange,
        )

    def run_once(self) -> RuntimeReport:
        configure_logging(self.config.app.log_level)

        current_positions = self.exchange.fetch_positions()
        self.positions.sync_positions(current_positions)

        risk_decisions = self._evaluate_risk(current_positions)
        order_results = self._execute_risk_orders(risk_decisions)

        strategy_decisions: list[StrategyDecision] = []
        if not self.state.safe_mode:
            strategy_decisions = self._evaluate_strategy(current_positions)

        return RuntimeReport(
            positions_seen=len(current_positions),
            strategy_decisions=tuple(strategy_decisions),
            risk_decisions=tuple(risk_decisions),
            order_results=tuple(order_results),
            safe_mode=self.state.safe_mode,
        )

    def _evaluate_risk(self, positions: list[Position]) -> list[RiskDecision]:
        decisions: list[RiskDecision] = []
        for position in positions:
            if position.symbol in self.config.risk_blacklist:
                continue
            symbol_state = self.state.get_symbol(position.symbol)
            decision = self.risk.evaluate(position, symbol_state, self.config.risk_defaults)
            symbol_state.highest_profit_pct = decision.highest_profit_pct
            symbol_state.trailing_tier = decision.trailing_tier
            if decision.trailing_tier >= 0 and symbol_state.status == "POSITION_OPEN":
                symbol_state.status = "TRAILING"
            decisions.append(decision)
        return decisions

    def _execute_risk_orders(self, decisions: list[RiskDecision]) -> list[OrderResult]:
        results: list[OrderResult] = []
        for decision in decisions:
            if decision.action != "close" or decision.close_side is None:
                continue
            symbol_state = self.state.get_symbol(decision.symbol)
            symbol_state.status = "CLOSING"
            results.append(
                self.orders.execute(
                    OrderIntent(
                        action="close_market",
                        symbol=decision.symbol,
                        side=decision.close_side,
                        amount=symbol_state.size,
                        reason=decision.reason,
                    )
                )
            )
        return results

    def _evaluate_strategy(self, positions: list[Position]) -> list[StrategyDecision]:
        active_symbols = {position.symbol for position in positions if position.size != 0}
        decisions: list[StrategyDecision] = []
        for symbol_config in self.config.symbols:
            if symbol_config.symbol in active_symbols:
                continue
            market = self.exchange.fetch_market_snapshot(symbol_config.symbol)
            decisions.extend(self.strategy.evaluate(symbol_config, market))
        return decisions
