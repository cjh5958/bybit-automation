from __future__ import annotations

import pytest

from bybit_automation.config import ConfigError, parse_config
from bybit_automation.exchange_client import (
    CcxtBybitExchangeClient,
    DryRunExchangeClient,
    OpenOrder,
    create_exchange_client,
)
from tests.factories import valid_raw_config


class FakeCcxtExchange:
    def __init__(self) -> None:
        self.fetch_ohlcv_calls: list[tuple[str, str, int]] = []
        self.created_orders: list[dict] = []
        self.canceled_orders: list[tuple[str, str]] = []

    def fetch_positions(self) -> list[dict]:
        return [
            {
                "symbol": "MOODENG/USDT:USDT",
                "side": "long",
                "contracts": 2,
                "entryPrice": 100,
                "markPrice": 103,
                "info": {},
            },
            {
                "symbol": "EMPTY/USDT:USDT",
                "side": "short",
                "contracts": 0,
                "entryPrice": 100,
                "markPrice": 99,
                "info": {},
            },
        ]

    def fetch_ticker(self, symbol: str) -> dict:
        assert symbol == "MOODENG/USDT:USDT"
        return {"last": 100}

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> list[list[float]]:
        self.fetch_ohlcv_calls.append((symbol, timeframe, limit))
        return [[index, 100, 102, 99, 101] for index in range(61)]

    def market(self, symbol: str) -> dict:
        assert symbol == "MOODENG/USDT:USDT"
        return {
            "precision": {"price": 0.01},
            "limits": {"amount": {"min": 0.001}},
        }

    def create_order(
        self,
        *,
        symbol: str,
        type: str,
        side: str,
        amount: float,
        price: float | None,
        params: dict | None = None,
    ) -> dict:
        order = {
            "id": f"{type}-1",
            "symbol": symbol,
            "type": type,
            "side": side,
            "amount": amount,
            "price": price,
            "params": params or {},
        }
        self.created_orders.append(order)
        return order

    def fetch_open_orders(self, symbol: str | None = None, params: dict | None = None) -> list[dict]:
        assert params == {"orderFilter": "Order"}
        if symbol is None:
            return [
                {
                    "id": "order-1",
                    "symbol": "MOODENG/USDT:USDT",
                    "side": "buy",
                    "amount": 1.5,
                    "price": 97,
                    "status": "open",
                    "info": {},
                },
                {
                    "id": "order-2",
                    "symbol": "MOODENG/USDT:USDT",
                    "side": "sell",
                    "amount": 2,
                    "price": 104,
                    "status": "open",
                    "info": {},
                },
            ]
        assert symbol == "MOODENG/USDT:USDT"
        return [{"id": "order-1"}, {"id": "order-2"}]

    def cancel_order(self, order_id: str, symbol: str) -> None:
        self.canceled_orders.append((order_id, symbol))


def test_create_exchange_client_returns_dry_run_client() -> None:
    config = parse_config(valid_raw_config(), resolve_secrets=False)

    client = create_exchange_client(config)

    assert isinstance(client, DryRunExchangeClient)


def test_dry_run_client_returns_empty_open_orders() -> None:
    client = DryRunExchangeClient()

    assert client.fetch_open_orders() == []


def test_ccxt_client_rejects_dry_run_config() -> None:
    config = parse_config(valid_raw_config(), resolve_secrets=False)

    with pytest.raises(ConfigError, match="dry_run"):
        CcxtBybitExchangeClient.from_config(config)


def test_ccxt_client_parses_non_zero_positions() -> None:
    client = CcxtBybitExchangeClient(exchange=FakeCcxtExchange())

    positions = client.fetch_positions()

    assert len(positions) == 1
    assert positions[0].symbol == "MOODENG/USDT:USDT"
    assert positions[0].side == "long"
    assert positions[0].size == 2
    assert positions[0].profit_pct == pytest.approx(3)


def test_ccxt_client_builds_market_snapshot() -> None:
    exchange = FakeCcxtExchange()
    client = CcxtBybitExchangeClient(
        exchange=exchange,
        kline_timeframe="1m",
        kline_limit=61,
        volatility_period=60,
    )

    snapshot = client.fetch_market_snapshot("MOODENG/USDT:USDT")

    assert snapshot is not None
    assert snapshot.mark_price == 100
    assert len(snapshot.close_prices) == 61
    assert snapshot.atr_pct == pytest.approx(3)
    assert snapshot.average_amplitude_pct == pytest.approx(2.9702970297)
    assert exchange.fetch_ohlcv_calls == [("MOODENG/USDT:USDT", "1m", 61)]


def test_ccxt_client_reads_trading_rules() -> None:
    client = CcxtBybitExchangeClient(exchange=FakeCcxtExchange())

    rules = client.fetch_trading_rules("MOODENG/USDT:USDT")

    assert rules.tick_size == 0.01
    assert rules.min_amount == 0.001


def test_ccxt_client_parses_open_orders() -> None:
    client = CcxtBybitExchangeClient(exchange=FakeCcxtExchange())

    orders = client.fetch_open_orders()

    assert orders == [
        OpenOrder(
            exchange_order_id="order-1",
            symbol="MOODENG/USDT:USDT",
            side="buy",
            amount=1.5,
            price=97,
            status="open",
        ),
        OpenOrder(
            exchange_order_id="order-2",
            symbol="MOODENG/USDT:USDT",
            side="sell",
            amount=2,
            price=104,
            status="open",
        ),
    ]


def test_ccxt_client_submits_orders_and_cancels_open_orders() -> None:
    exchange = FakeCcxtExchange()
    client = CcxtBybitExchangeClient(exchange=exchange)

    limit_order = client.create_limit_order(
        symbol="MOODENG/USDT:USDT",
        side="buy",
        amount=1,
        price=100,
    )
    market_order = client.create_market_order(
        symbol="MOODENG/USDT:USDT",
        side="sell",
        amount=1,
    )
    canceled_order_ids = client.cancel_all_orders("MOODENG/USDT:USDT")

    assert limit_order["id"] == "limit-1"
    assert market_order["params"] == {"type": "future"}
    assert canceled_order_ids == ["order-1", "order-2"]
    assert exchange.canceled_orders == [
        ("order-1", "MOODENG/USDT:USDT"),
        ("order-2", "MOODENG/USDT:USDT"),
    ]
