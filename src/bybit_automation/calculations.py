from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Sequence


Ohlcv = Sequence[float | int | str]


def round_price_to_tick(price: float, tick_size: float) -> str:
    if tick_size <= 0:
        raise ValueError("tick_size must be positive")

    tick = Decimal(str(tick_size))
    raw_price = Decimal(str(price))
    ticks = (raw_price / tick).to_integral_value(rounding=ROUND_HALF_UP)
    adjusted = ticks * tick
    decimals = max(0, -tick.as_tuple().exponent)
    return f"{adjusted:.{decimals}f}"


def convert_usdt_to_contract_amount(
    *,
    price: float,
    amount_usdt: float,
    min_amount: float,
    commission: float = 0.00055,
    leverage: int = 10,
) -> float:
    if price <= 0:
        raise ValueError("price must be positive")
    if amount_usdt < 0:
        raise ValueError("amount_usdt must be non-negative")
    if min_amount <= 0:
        raise ValueError("min_amount must be positive")
    if leverage <= 0:
        raise ValueError("leverage must be positive")

    init_margin = min_amount * price / leverage
    open_fee = min_amount * price * commission
    close_fee_buy = min_amount * price * (1 - 1 / leverage) * commission
    close_fee_sell = min_amount * price * (1 + 1 / leverage) * commission
    unit_cost = max(
        init_margin + open_fee + close_fee_buy,
        init_margin + open_fee + close_fee_sell,
    )

    return int(amount_usdt / unit_cost) * min_amount


def ema(values: Sequence[float], period: int) -> float:
    if not values:
        raise ValueError("values must not be empty")
    if period < 0:
        raise ValueError("period must be non-negative")
    if period == 0:
        return float(values[-1])

    multiplier = 2 / (period + 1)
    ema_value = float(values[0])
    for value in values[1:]:
        ema_value = (float(value) - ema_value) * multiplier + ema_value
    return ema_value


def calculate_atr(klines: Sequence[Ohlcv], period: int = 60) -> float:
    if period <= 0:
        raise ValueError("period must be positive")
    if len(klines) < period + 1:
        raise ValueError("not enough klines to calculate ATR")

    true_ranges: list[float] = []
    for index in range(1, len(klines)):
        high = float(klines[index][2])
        low = float(klines[index][3])
        previous_close = float(klines[index - 1][4])
        true_ranges.append(
            max(
                high - low,
                abs(high - previous_close),
                abs(low - previous_close),
            )
        )

    return sum(true_ranges[-period:]) / period


def calculate_average_amplitude(klines: Sequence[Ohlcv], period: int = 60) -> float:
    if period <= 0:
        raise ValueError("period must be positive")
    if len(klines) < period:
        raise ValueError("not enough klines to calculate average amplitude")

    amplitudes: list[float] = []
    for kline in klines[-period:]:
        high = float(kline[2])
        low = float(kline[3])
        close = float(kline[4])
        if close <= 0:
            raise ValueError("close price must be positive")
        amplitudes.append((high - low) / close * 100)

    return sum(amplitudes) / len(amplitudes)

