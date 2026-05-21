from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from bybit_automation.config import RiskDefaults
from bybit_automation.positions import Position
from bybit_automation.state import SymbolRuntimeState


RiskAction = Literal["hold", "close"]


@dataclass(frozen=True)
class RiskDecision:
    symbol: str
    action: RiskAction
    close_side: Literal["buy", "sell"] | None
    reason: str
    profit_pct: float
    highest_profit_pct: float
    trailing_tier: int


class RiskManager:
    def evaluate(
        self,
        position: Position,
        symbol_state: SymbolRuntimeState,
        risk: RiskDefaults,
    ) -> RiskDecision:
        profit_pct = position.profit_pct
        highest_profit = max(symbol_state.highest_profit_pct, profit_pct)
        tier = _trailing_tier(highest_profit, risk)
        close_side = "sell" if position.side == "long" else "buy"

        if profit_pct <= -risk.stop_loss_pct:
            return RiskDecision(
                symbol=position.symbol,
                action="close",
                close_side=close_side,
                reason="fixed stop loss reached",
                profit_pct=profit_pct,
                highest_profit_pct=highest_profit,
                trailing_tier=tier,
            )

        if tier == 0 and profit_pct <= risk.low_trail_stop_loss_pct:
            return RiskDecision(
                symbol=position.symbol,
                action="close",
                close_side=close_side,
                reason="low-tier trailing stop reached",
                profit_pct=profit_pct,
                highest_profit_pct=highest_profit,
                trailing_tier=tier,
            )

        if tier == 1:
            trail_stop = highest_profit * (1 - risk.trail_stop_loss_pct)
            if profit_pct <= trail_stop:
                return RiskDecision(
                    symbol=position.symbol,
                    action="close",
                    close_side=close_side,
                    reason="first-tier trailing stop reached",
                    profit_pct=profit_pct,
                    highest_profit_pct=highest_profit,
                    trailing_tier=tier,
                )

        if tier == 2:
            trail_stop = highest_profit * (1 - risk.higher_trail_stop_loss_pct)
            if profit_pct <= trail_stop:
                return RiskDecision(
                    symbol=position.symbol,
                    action="close",
                    close_side=close_side,
                    reason="second-tier trailing stop reached",
                    profit_pct=profit_pct,
                    highest_profit_pct=highest_profit,
                    trailing_tier=tier,
                )

        return RiskDecision(
            symbol=position.symbol,
            action="hold",
            close_side=None,
            reason="risk limits not reached",
            profit_pct=profit_pct,
            highest_profit_pct=highest_profit,
            trailing_tier=tier,
        )


def _trailing_tier(highest_profit: float, risk: RiskDefaults) -> int:
    if highest_profit >= risk.second_trail_enable_threshold:
        return 2
    if highest_profit >= risk.first_trail_enable_threshold:
        return 1
    if highest_profit >= risk.low_trail_enable_threshold:
        return 0
    return -1
