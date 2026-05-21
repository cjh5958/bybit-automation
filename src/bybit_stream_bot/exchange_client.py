from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from bybit_stream_bot.positions import Position


@dataclass(frozen=True)
class MarketSnapshot:
    symbol: str
    mark_price: float
    close_prices: tuple[float, ...]
    atr_pct: float
    average_amplitude_pct: float


class ExchangeClient(Protocol):
    def fetch_positions(self) -> list[Position]:
        raise NotImplementedError

    def fetch_market_snapshot(self, symbol: str) -> MarketSnapshot | None:
        raise NotImplementedError


class DryRunExchangeClient:
    """Exchange placeholder for Phase 1.

    It intentionally performs no network calls and no trading side effects.
    """

    def fetch_positions(self) -> list[Position]:
        return []

    def fetch_market_snapshot(self, symbol: str) -> MarketSnapshot | None:
        return None

