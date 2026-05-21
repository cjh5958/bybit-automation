from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from bybit_automation.state import RuntimeState


PositionSide = Literal["long", "short"]


@dataclass(frozen=True)
class Position:
    symbol: str
    side: PositionSide
    size: float
    entry_price: float
    mark_price: float

    @property
    def profit_pct(self) -> float:
        if self.side == "long":
            return (self.mark_price - self.entry_price) / self.entry_price * 100
        return (self.entry_price - self.mark_price) / self.entry_price * 100


class PositionManager:
    def __init__(self, state: RuntimeState) -> None:
        self._state = state

    def sync_positions(self, positions: list[Position]) -> None:
        active_symbols = {position.symbol for position in positions if position.size != 0}

        for position in positions:
            if position.size == 0:
                continue
            symbol_state = self._state.get_symbol(position.symbol)
            symbol_state.status = "POSITION_OPEN"
            symbol_state.position_side = position.side
            symbol_state.entry_price = position.entry_price
            symbol_state.size = position.size
            symbol_state.highest_profit_pct = max(
                symbol_state.highest_profit_pct,
                position.profit_pct,
            )

        for symbol, symbol_state in self._state.symbols.items():
            if symbol not in active_symbols and symbol_state.status in {
                "POSITION_OPEN",
                "TRAILING",
                "CLOSING",
            }:
                symbol_state.status = "CLOSED"
                symbol_state.position_side = None
                symbol_state.entry_price = None
                symbol_state.size = 0.0
