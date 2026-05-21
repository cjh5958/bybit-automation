from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


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


@dataclass(frozen=True)
class OrderResult:
    intent: OrderIntent
    submitted: bool
    dry_run: bool
    message: str


class OrderManager:
    def __init__(self, *, dry_run: bool) -> None:
        self._dry_run = dry_run

    def execute(self, intent: OrderIntent) -> OrderResult:
        if self._dry_run:
            return OrderResult(
                intent=intent,
                submitted=False,
                dry_run=True,
                message="dry_run: order intent recorded but not submitted",
            )

        raise NotImplementedError("live order execution is not implemented in Phase 1")

