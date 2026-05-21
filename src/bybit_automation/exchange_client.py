from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import ccxt

from bybit_automation.calculations import calculate_atr, calculate_average_amplitude
from bybit_automation.config import BotConfig, ConfigError
from bybit_automation.orders import OrderSide
from bybit_automation.positions import Position

DEFAULT_KLINE_TIMEFRAME = "1m"
DEFAULT_KLINE_LIMIT = 241
DEFAULT_VOLATILITY_PERIOD = 60


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


class CcxtBybitExchangeClient:
    def __init__(
        self,
        *,
        exchange: Any,
        kline_timeframe: str = DEFAULT_KLINE_TIMEFRAME,
        kline_limit: int = DEFAULT_KLINE_LIMIT,
        volatility_period: int = DEFAULT_VOLATILITY_PERIOD,
    ) -> None:
        self._exchange = exchange
        self._kline_timeframe = kline_timeframe
        self._kline_limit = kline_limit
        self._volatility_period = volatility_period

    @classmethod
    def from_config(cls, config: BotConfig) -> CcxtBybitExchangeClient:
        if config.app.mode == "dry_run":
            raise ConfigError("ccxt exchange client must not be created in dry_run mode")

        if not config.exchange.api_key or not config.exchange.api_secret:
            raise ConfigError("exchange credentials are required to create ccxt client")

        exchange = ccxt.bybit(
            {
                "apiKey": config.exchange.api_key,
                "secret": config.exchange.api_secret,
                "enableRateLimit": config.exchange.enable_rate_limit,
                "options": {"defaultType": config.exchange.account_type},
            }
        )

        if config.app.mode == "demo":
            exchange.enable_demo_trading(True)

        return cls(exchange=exchange)

    def fetch_positions(self) -> list[Position]:
        raw_positions = self._exchange.fetch_positions()
        positions: list[Position] = []
        for raw_position in raw_positions:
            position = _parse_position(raw_position)
            if position is not None:
                positions.append(position)
        return positions

    def fetch_market_snapshot(self, symbol: str) -> MarketSnapshot | None:
        ticker = self._exchange.fetch_ticker(symbol)
        mark_price = _ticker_mark_price(ticker)
        klines = self._exchange.fetch_ohlcv(
            symbol,
            timeframe=self._kline_timeframe,
            limit=self._kline_limit,
        )
        if not klines:
            return None

        close_prices = tuple(float(kline[4]) for kline in klines)
        atr = calculate_atr(klines, period=self._volatility_period)
        return MarketSnapshot(
            symbol=symbol,
            mark_price=mark_price,
            close_prices=close_prices,
            atr_pct=atr / mark_price * 100,
            average_amplitude_pct=calculate_average_amplitude(
                klines,
                period=self._volatility_period,
            ),
        )

    def create_limit_order(
        self,
        *,
        symbol: str,
        side: OrderSide,
        amount: float,
        price: float,
    ) -> dict[str, Any]:
        return self._exchange.create_order(
            symbol=symbol,
            type="limit",
            side=side,
            amount=amount,
            price=price,
        )

    def create_market_order(
        self,
        *,
        symbol: str,
        side: OrderSide,
        amount: float,
    ) -> dict[str, Any]:
        return self._exchange.create_order(
            symbol=symbol,
            type="market",
            side=side,
            amount=amount,
            price=None,
            params={"type": "future"},
        )

    def cancel_all_orders(self, symbol: str) -> list[str]:
        orders = self._exchange.fetch_open_orders(symbol, params={"orderFilter": "Order"})
        canceled_order_ids: list[str] = []
        for order in orders:
            order_id = str(order["id"])
            self._exchange.cancel_order(order_id, symbol)
            canceled_order_ids.append(order_id)
        return canceled_order_ids


def create_exchange_client(config: BotConfig) -> ExchangeClient:
    if config.app.mode == "dry_run":
        return DryRunExchangeClient()
    return CcxtBybitExchangeClient.from_config(config)


def _parse_position(raw_position: dict[str, Any]) -> Position | None:
    symbol = str(raw_position.get("symbol") or "")
    side = str(raw_position.get("side") or "").lower()
    info = raw_position.get("info") or {}
    size = _first_float(raw_position, info, keys=("contracts", "size", "positionAmt"))

    if not symbol or side not in {"long", "short"} or size == 0:
        return None

    entry_price = _first_float(raw_position, info, keys=("entryPrice", "avgPrice"))
    mark_price = _first_float(raw_position, info, keys=("markPrice",))
    if entry_price <= 0 or mark_price <= 0:
        return None

    return Position(
        symbol=symbol,
        side=side,
        size=abs(size),
        entry_price=entry_price,
        mark_price=mark_price,
    )


def _first_float(
    raw_position: dict[str, Any],
    info: dict[str, Any],
    *,
    keys: tuple[str, ...],
) -> float:
    for key in keys:
        value = raw_position.get(key, info.get(key))
        if value not in (None, ""):
            return float(value)
    return 0.0


def _ticker_mark_price(ticker: dict[str, Any]) -> float:
    for key in ("mark", "last", "ask", "bid"):
        value = ticker.get(key)
        if value not in (None, ""):
            price = float(value)
            if price > 0:
                return price
    raise ValueError("ticker does not contain a positive usable price")
