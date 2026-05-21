from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from bybit_automation.calculations import ema
from bybit_automation.config import SymbolConfig
from bybit_automation.exchange_client import MarketSnapshot


EntrySide = Literal["buy", "sell"]


@dataclass(frozen=True)
class StrategyDecision:
    symbol: str
    side: EntrySide | None
    target_price: float | None
    amount_usdt: float
    reason: str

    @property
    def should_place_order(self) -> bool:
        return self.side is not None and self.target_price is not None and self.amount_usdt > 0


class StrategyEngine:
    def evaluate(
        self,
        symbol_config: SymbolConfig,
        market: MarketSnapshot | None,
    ) -> list[StrategyDecision]:
        if not symbol_config.enabled:
            return [
                StrategyDecision(
                    symbol=symbol_config.symbol,
                    side=None,
                    target_price=None,
                    amount_usdt=0,
                    reason="symbol disabled",
                )
            ]

        if market is None:
            return [
                StrategyDecision(
                    symbol=symbol_config.symbol,
                    side=None,
                    target_price=None,
                    amount_usdt=0,
                    reason="market snapshot unavailable",
                )
            ]

        if symbol_config.ema_period and len(market.close_prices) < symbol_config.ema_period:
            return [
                StrategyDecision(
                    symbol=symbol_config.symbol,
                    side=None,
                    target_price=None,
                    amount_usdt=0,
                    reason="not enough close prices for EMA",
                )
            ]

        close_price = market.close_prices[-1]
        ema_value = ema(market.close_prices, symbol_config.ema_period)
        selected_value = (
            (market.average_amplitude_pct + market.atr_pct) / 2 * symbol_config.value_multiplier
        )

        decisions: list[StrategyDecision] = []
        if symbol_config.ema_period == 0 or close_price > ema_value:
            decisions.append(
                StrategyDecision(
                    symbol=symbol_config.symbol,
                    side="buy",
                    target_price=market.mark_price * (1 - selected_value / 100),
                    amount_usdt=symbol_config.long_amount_usdt,
                    reason="bullish trend",
                )
            )

        if symbol_config.ema_period == 0 or close_price < ema_value:
            decisions.append(
                StrategyDecision(
                    symbol=symbol_config.symbol,
                    side="sell",
                    target_price=market.mark_price * (1 + selected_value / 100),
                    amount_usdt=symbol_config.short_amount_usdt,
                    reason="bearish trend",
                )
            )

        return decisions or [
            StrategyDecision(
                symbol=symbol_config.symbol,
                side=None,
                target_price=None,
                amount_usdt=0,
                reason="flat trend",
            )
        ]
