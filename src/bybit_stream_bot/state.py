from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


SymbolStatus = Literal[
    "IDLE",
    "ENTRY_ORDER_PLACED",
    "POSITION_OPEN",
    "TRAILING",
    "CLOSING",
    "CLOSED",
]


@dataclass
class SymbolRuntimeState:
    symbol: str
    status: SymbolStatus = "IDLE"
    position_side: str | None = None
    entry_price: float | None = None
    size: float = 0.0
    highest_profit_pct: float = 0.0
    trailing_tier: int = -1
    last_order_ids: list[str] = field(default_factory=list)


@dataclass
class RuntimeState:
    symbols: dict[str, SymbolRuntimeState] = field(default_factory=dict)
    safe_mode: bool = False

    def get_symbol(self, symbol: str) -> SymbolRuntimeState:
        if symbol not in self.symbols:
            self.symbols[symbol] = SymbolRuntimeState(symbol=symbol)
        return self.symbols[symbol]

