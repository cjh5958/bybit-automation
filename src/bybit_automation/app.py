from __future__ import annotations

from dataclasses import dataclass

from bybit_automation.calculations import convert_usdt_to_contract_amount, round_price_to_tick
from bybit_automation.config import BotConfig
from bybit_automation.exchange_client import ExchangeClient, create_exchange_client
from bybit_automation.log import configure_logging
from bybit_automation.notifier import Notifier
from bybit_automation.orders import OrderIntent, OrderManager, OrderResult
from bybit_automation.positions import Position, PositionManager
from bybit_automation.risk import RiskDecision, RiskManager
from bybit_automation.state import RuntimeState
from bybit_automation.storage import PersistenceRepositories
from bybit_automation.strategy import StrategyDecision, StrategyEngine


@dataclass(frozen=True)
class RuntimeReport:
    positions_seen: int
    strategy_decisions: tuple[StrategyDecision, ...]
    risk_decisions: tuple[RiskDecision, ...]
    order_results: tuple[OrderResult, ...]
    safe_mode: bool
    ran_risk: bool
    ran_strategy: bool


class BotRuntime:
    def __init__(
        self,
        config: BotConfig,
        *,
        exchange: ExchangeClient | None = None,
        state: RuntimeState | None = None,
        notifier: Notifier | None = None,
        repositories: PersistenceRepositories | None = None,
    ) -> None:
        self.config = config
        self.state = state or RuntimeState()
        self.exchange = exchange or create_exchange_client(config)
        self.notifier = notifier or Notifier()
        self.repositories = repositories
        self.strategy = StrategyEngine()
        self.risk = RiskManager()
        self.positions = PositionManager(self.state)
        self.orders = OrderManager(
            dry_run=config.app.mode == "dry_run",
            executor=self.exchange,
        )
        self._restore_trailing_state()

    def run_once(
        self,
        *,
        include_risk: bool = True,
        include_strategy: bool = True,
    ) -> RuntimeReport:
        configure_logging(self.config.app.log_level)

        current_positions = self.exchange.fetch_positions()
        self.positions.sync_positions(current_positions)
        if self.repositories is not None:
            self.repositories.positions.append_many(current_positions)

        risk_decisions: list[RiskDecision] = []
        order_results: list[OrderResult] = []
        if include_risk:
            risk_decisions = self._evaluate_risk(current_positions)
            if self.repositories is not None:
                self.repositories.risk_events.append_many(risk_decisions)
                self._persist_trailing_state(risk_decisions)
            risk_order_results = self._execute_risk_orders(risk_decisions)
            self._persist_order_results(risk_order_results)
            order_results.extend(risk_order_results)

        strategy_decisions: list[StrategyDecision] = []
        if include_strategy and not self.state.safe_mode:
            strategy_decisions = self._evaluate_strategy(current_positions)
            if self.repositories is not None:
                self.repositories.strategy_decisions.append_many(strategy_decisions)
            strategy_order_results = self._execute_strategy_orders(strategy_decisions)
            self._persist_order_results(strategy_order_results)
            order_results.extend(strategy_order_results)

        self._persist_bot_state(
            positions_seen=len(current_positions),
            ran_risk=include_risk,
            ran_strategy=include_strategy and not self.state.safe_mode,
        )

        return RuntimeReport(
            positions_seen=len(current_positions),
            strategy_decisions=tuple(strategy_decisions),
            risk_decisions=tuple(risk_decisions),
            order_results=tuple(order_results),
            safe_mode=self.state.safe_mode,
            ran_risk=include_risk,
            ran_strategy=include_strategy and not self.state.safe_mode,
        )

    def _restore_trailing_state(self) -> None:
        if self.repositories is None:
            return
        for symbol, saved_state in self.repositories.trailing_state.load_all().items():
            symbol_state = self.state.get_symbol(symbol)
            symbol_state.highest_profit_pct = saved_state.highest_profit_pct
            symbol_state.trailing_tier = saved_state.trailing_tier

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

    def _execute_strategy_orders(self, decisions: list[StrategyDecision]) -> list[OrderResult]:
        results: list[OrderResult] = []
        for decision in decisions:
            if not decision.should_place_order:
                continue

            rules = self.exchange.fetch_trading_rules(decision.symbol)
            price = float(round_price_to_tick(decision.target_price, rules.tick_size))
            amount = convert_usdt_to_contract_amount(
                price=price,
                amount_usdt=decision.amount_usdt,
                min_amount=rules.min_amount,
                leverage=self.config.exchange.default_leverage,
            )
            if amount <= 0:
                continue

            symbol_state = self.state.get_symbol(decision.symbol)
            symbol_state.status = "ENTRY_ORDER_PLACED"
            results.append(
                self.orders.execute(
                    OrderIntent(
                        action="cancel_all",
                        symbol=decision.symbol,
                        reason="refresh entry order",
                    )
                )
            )
            results.append(
                self.orders.execute(
                    OrderIntent(
                        action="place_limit",
                        symbol=decision.symbol,
                        side=decision.side,
                        amount_usdt=decision.amount_usdt,
                        price=price,
                        reason=decision.reason,
                        amount=amount,
                    )
                )
            )
        return results

    def _persist_trailing_state(self, decisions: list[RiskDecision]) -> None:
        if self.repositories is None:
            return
        for decision in decisions:
            self.repositories.trailing_state.save(self.state.get_symbol(decision.symbol))

    def _persist_order_results(self, results: list[OrderResult]) -> None:
        if self.repositories is None:
            return
        for result in results:
            self.repositories.orders.append_result(result)

    def _persist_bot_state(
        self,
        *,
        positions_seen: int,
        ran_risk: bool,
        ran_strategy: bool,
    ) -> None:
        if self.repositories is None:
            return
        self.repositories.bot_state.set_json(
            "last_tick",
            {
                "positions_seen": positions_seen,
                "safe_mode": self.state.safe_mode,
                "ran_risk": ran_risk,
                "ran_strategy": ran_strategy,
            },
        )
