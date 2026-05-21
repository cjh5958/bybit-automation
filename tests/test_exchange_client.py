from __future__ import annotations

import pytest

from bybit_stream_bot.config import ConfigError, parse_config
from bybit_stream_bot.exchange_client import (
    CcxtBybitExchangeClient,
    DryRunExchangeClient,
    create_exchange_client,
)
from tests.factories import valid_raw_config


class FakeCcxtExchange:
    def __init__(self) -> None:
        self.fetch_ohlcv_calls: list[tuple[str, str, int]] = []

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


def test_create_exchange_client_returns_dry_run_client() -> None:
    config = parse_config(valid_raw_config(), resolve_secrets=False)

    client = create_exchange_client(config)

    assert isinstance(client, DryRunExchangeClient)


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

