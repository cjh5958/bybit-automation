from __future__ import annotations

import pytest

from bybit_stream_bot.orders import OrderIntent, OrderManager


class FakeOrderExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def create_limit_order(
        self,
        *,
        symbol: str,
        side: str,
        amount: float,
        price: float,
    ) -> dict:
        self.calls.append(("limit", symbol, side, amount, price))
        return {"id": "limit-1"}

    def create_market_order(
        self,
        *,
        symbol: str,
        side: str,
        amount: float,
    ) -> dict:
        self.calls.append(("market", symbol, side, amount))
        return {"id": "market-1"}

    def cancel_all_orders(self, symbol: str) -> list[str]:
        self.calls.append(("cancel_all", symbol))
        return ["a", "b"]


def test_order_manager_keeps_dry_run_from_submitting() -> None:
    executor = FakeOrderExecutor()
    manager = OrderManager(dry_run=True, executor=executor)

    result = manager.execute(
        OrderIntent(
            action="place_limit",
            symbol="MOODENG/USDT:USDT",
            side="buy",
            amount=1,
            price=100,
        )
    )

    assert result.dry_run is True
    assert result.submitted is False
    assert executor.calls == []


def test_order_manager_submits_limit_order() -> None:
    executor = FakeOrderExecutor()
    manager = OrderManager(dry_run=False, executor=executor)

    result = manager.execute(
        OrderIntent(
            action="place_limit",
            symbol="MOODENG/USDT:USDT",
            side="buy",
            amount=1.5,
            price=100,
        )
    )

    assert result.submitted is True
    assert result.exchange_order_id == "limit-1"
    assert executor.calls == [("limit", "MOODENG/USDT:USDT", "buy", 1.5, 100)]


def test_order_manager_submits_market_close_order() -> None:
    executor = FakeOrderExecutor()
    manager = OrderManager(dry_run=False, executor=executor)

    result = manager.execute(
        OrderIntent(
            action="close_market",
            symbol="MOODENG/USDT:USDT",
            side="sell",
            amount=2,
        )
    )

    assert result.exchange_order_id == "market-1"
    assert executor.calls == [("market", "MOODENG/USDT:USDT", "sell", 2)]


def test_order_manager_submits_cancel_all() -> None:
    executor = FakeOrderExecutor()
    manager = OrderManager(dry_run=False, executor=executor)

    result = manager.execute(OrderIntent(action="cancel_all", symbol="MOODENG/USDT:USDT"))

    assert result.submitted is True
    assert result.message == "canceled 2 open orders"
    assert executor.calls == [("cancel_all", "MOODENG/USDT:USDT")]


def test_order_manager_rejects_missing_executor_outside_dry_run() -> None:
    manager = OrderManager(dry_run=False)

    with pytest.raises(RuntimeError, match="executor"):
        manager.execute(OrderIntent(action="cancel_all", symbol="MOODENG/USDT:USDT"))


def test_order_manager_rejects_invalid_limit_order() -> None:
    manager = OrderManager(dry_run=False, executor=FakeOrderExecutor())

    with pytest.raises(ValueError, match="amount"):
        manager.execute(
            OrderIntent(
                action="place_limit",
                symbol="MOODENG/USDT:USDT",
                side="buy",
                amount=0,
                price=100,
            )
        )

