from __future__ import annotations

import pytest

from bybit_automation.calculations import (
    calculate_atr,
    calculate_average_amplitude,
    convert_usdt_to_contract_amount,
    ema,
    round_price_to_tick,
)


def test_round_price_to_tick_preserves_tick_decimals() -> None:
    assert round_price_to_tick(123.456, 0.01) == "123.46"
    assert round_price_to_tick(123.456, 0.5) == "123.5"
    assert round_price_to_tick(123.456, 1) == "123"


def test_round_price_to_tick_rejects_invalid_tick() -> None:
    with pytest.raises(ValueError, match="tick_size"):
        round_price_to_tick(100, 0)


def test_convert_usdt_to_contract_amount_uses_min_amount_steps() -> None:
    amount = convert_usdt_to_contract_amount(
        price=100,
        amount_usdt=20,
        min_amount=0.001,
        commission=0.0002,
        leverage=10,
    )

    assert amount == pytest.approx(1.991)


def test_convert_usdt_to_contract_amount_returns_zero_when_too_small() -> None:
    amount = convert_usdt_to_contract_amount(
        price=100,
        amount_usdt=0.001,
        min_amount=0.001,
        commission=0.0002,
        leverage=10,
    )

    assert amount == 0


def test_ema_matches_incremental_formula() -> None:
    assert ema((10, 11, 12), 3) == pytest.approx(11.25)
    assert ema((10, 11, 12), 0) == 12


def test_calculate_atr() -> None:
    klines = [
        [1, 10, 12, 9, 11],
        [2, 11, 14, 10, 13],
        [3, 13, 15, 12, 14],
        [4, 14, 16, 13, 15],
    ]

    assert calculate_atr(klines, period=3) == pytest.approx(10 / 3)


def test_calculate_average_amplitude() -> None:
    klines = [
        [1, 10, 12, 10, 10],
        [2, 10, 15, 10, 20],
    ]

    assert calculate_average_amplitude(klines, period=2) == pytest.approx(22.5)
