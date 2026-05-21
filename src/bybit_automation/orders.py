from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol


OrderAction = Literal["place_limit", "close_market", "cancel_all"]
OrderSide = Literal["buy", "sell"]


@dataclass(frozen=True)
class OrderIntent:
    action: OrderAction
    symbol: str
    side: OrderSide | None = None
    amount_usdt: float = 0.0
    price: float | None = None
    reason: str = ""
    amount: float = 0.0


@dataclass(frozen=True)
class OrderResult:
    intent: OrderIntent
    submitted: bool
    dry_run: bool
    message: str
    exchange_order_id: str | None = None


class OrderExecutor(Protocol):
    def create_limit_order(
        self,
        *,
        symbol: str,
        side: OrderSide,
        amount: float,
        price: float,
    ) -> dict[str, Any]:
        raise NotImplementedError

    def create_market_order(
        self,
        *,
        symbol: str,
        side: OrderSide,
        amount: float,
    ) -> dict[str, Any]:
        raise NotImplementedError

    def cancel_all_orders(self, symbol: str) -> list[str]:
        raise NotImplementedError


class OrderManager:
    def __init__(self, *, dry_run: bool, executor: OrderExecutor | None = None) -> None:
        self._dry_run = dry_run
        self._executor = executor

    def execute(self, intent: OrderIntent) -> OrderResult:
        if self._dry_run:
            return OrderResult(
                intent=intent,
                submitted=False,
                dry_run=True,
                message="dry_run: order intent recorded but not submitted",
            )

        if self._executor is None:
            raise RuntimeError("order executor is required outside dry_run mode")

        if intent.action == "place_limit":
            _require_side(intent)
            _require_positive_amount(intent.amount)
            if intent.price is None or intent.price <= 0:
                raise ValueError("limit order price must be positive")
            order = self._executor.create_limit_order(
                symbol=intent.symbol,
                side=intent.side,
                amount=intent.amount,
                price=intent.price,
            )
            return _submitted_result(intent, order)

        if intent.action == "close_market":
            _require_side(intent)
            _require_positive_amount(intent.amount)
            order = self._executor.create_market_order(
                symbol=intent.symbol,
                side=intent.side,
                amount=intent.amount,
            )
            return _submitted_result(intent, order)

        if intent.action == "cancel_all":
            canceled_order_ids = self._executor.cancel_all_orders(intent.symbol)
            return OrderResult(
                intent=intent,
                submitted=True,
                dry_run=False,
                message=f"canceled {len(canceled_order_ids)} open orders",
                exchange_order_id=None,
            )

        raise ValueError(f"unsupported order action: {intent.action}")


def _require_side(intent: OrderIntent) -> None:
    if intent.side not in {"buy", "sell"}:
        raise ValueError(f"{intent.action} requires buy or sell side")


def _require_positive_amount(amount: float) -> None:
    if amount <= 0:
        raise ValueError("order amount must be positive")


def _submitted_result(intent: OrderIntent, order: dict[str, Any]) -> OrderResult:
    return OrderResult(
        intent=intent,
        submitted=True,
        dry_run=False,
        message="order submitted",
        exchange_order_id=str(order.get("id")) if order.get("id") is not None else None,
    )
