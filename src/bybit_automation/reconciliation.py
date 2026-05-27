from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from bybit_automation.exchange_client import OpenOrder
from bybit_automation.positions import Position
from bybit_automation.storage.repositories import (
    OrderRecord,
    PositionSnapshotRecord,
    TrailingStateRecord,
)


ReconciliationSeverity = Literal["info", "warning", "safe_mode"]


@dataclass(frozen=True)
class ReconciliationIssue:
    severity: ReconciliationSeverity
    code: str
    message: str
    symbol: str | None = None


@dataclass(frozen=True)
class ReconciliationReport:
    exchange_positions: tuple[Position, ...]
    exchange_open_orders: tuple[OpenOrder, ...]
    issues: tuple[ReconciliationIssue, ...]
    stale_trailing_state_symbols: tuple[str, ...]

    @property
    def safe_mode_required(self) -> bool:
        return any(issue.severity == "safe_mode" for issue in self.issues)

    @property
    def consistent(self) -> bool:
        return not self.issues


def build_reconciliation_report(
    *,
    exchange_positions: list[Position],
    exchange_open_orders: list[OpenOrder],
    local_positions: dict[str, PositionSnapshotRecord],
    local_orders: list[OrderRecord],
    trailing_states: dict[str, TrailingStateRecord],
) -> ReconciliationReport:
    active_symbols = {position.symbol for position in exchange_positions if position.size != 0}
    local_submitted_order_ids = {
        order.exchange_order_id
        for order in local_orders
        if order.submitted and order.exchange_order_id is not None
    }

    issues: list[ReconciliationIssue] = []
    stale_trailing_symbols: list[str] = []

    for symbol in sorted(trailing_states):
        if symbol not in active_symbols:
            stale_trailing_symbols.append(symbol)
            issues.append(
                ReconciliationIssue(
                    severity="info",
                    code="stale_trailing_state",
                    symbol=symbol,
                    message="trailing state exists for a symbol with no active exchange position",
                )
            )

    for symbol, snapshot in sorted(local_positions.items()):
        if snapshot.size != 0 and symbol not in active_symbols and symbol not in trailing_states:
            issues.append(
                ReconciliationIssue(
                    severity="warning",
                    code="local_position_snapshot_closed",
                    symbol=symbol,
                    message="latest local position snapshot is open but exchange has no active position",
                )
            )

    for order in exchange_open_orders:
        if order.exchange_order_id not in local_submitted_order_ids:
            issues.append(
                ReconciliationIssue(
                    severity="safe_mode",
                    code="unknown_exchange_open_order",
                    symbol=order.symbol,
                    message="exchange has an open order that is not known in local SQLite state",
                )
            )

    return ReconciliationReport(
        exchange_positions=tuple(exchange_positions),
        exchange_open_orders=tuple(exchange_open_orders),
        issues=tuple(issues),
        stale_trailing_state_symbols=tuple(stale_trailing_symbols),
    )


def failed_reconciliation_report(reason: str) -> ReconciliationReport:
    return ReconciliationReport(
        exchange_positions=(),
        exchange_open_orders=(),
        issues=(
            ReconciliationIssue(
                severity="safe_mode",
                code="exchange_snapshot_failed",
                message=reason,
            ),
        ),
        stale_trailing_state_symbols=(),
    )
