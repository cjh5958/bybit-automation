from __future__ import annotations

from bybit_automation.exchange_client import OpenOrder
from bybit_automation.positions import Position
from bybit_automation.reconciliation import (
    build_reconciliation_report,
    failed_reconciliation_report,
)
from bybit_automation.storage.repositories import (
    OrderRecord,
    PositionSnapshotRecord,
    TrailingStateRecord,
)


def test_reconciliation_accepts_matching_active_position_and_known_open_order() -> None:
    report = build_reconciliation_report(
        exchange_positions=[
            Position(
                symbol="MOODENG/USDT:USDT",
                side="long",
                size=1,
                entry_price=100,
                mark_price=102,
            )
        ],
        exchange_open_orders=[
            OpenOrder(
                exchange_order_id="order-1",
                symbol="MOODENG/USDT:USDT",
                side="buy",
                amount=1,
                price=97,
                status="open",
            )
        ],
        local_positions={},
        local_orders=[
            OrderRecord(
                symbol="MOODENG/USDT:USDT",
                action="place_limit",
                side="buy",
                amount=1,
                price=97,
                submitted=True,
                dry_run=False,
                exchange_order_id="order-1",
                created_at="2026-05-27T00:00:00+00:00",
            )
        ],
        trailing_states={
            "MOODENG/USDT:USDT": TrailingStateRecord(
                symbol="MOODENG/USDT:USDT",
                highest_profit_pct=2,
                trailing_tier=1,
            )
        },
    )

    assert report.consistent
    assert report.safe_mode_required is False
    assert report.stale_trailing_state_symbols == ()


def test_reconciliation_marks_stale_trailing_state_for_confirmed_closed_position() -> None:
    report = build_reconciliation_report(
        exchange_positions=[],
        exchange_open_orders=[],
        local_positions={},
        local_orders=[],
        trailing_states={
            "MOODENG/USDT:USDT": TrailingStateRecord(
                symbol="MOODENG/USDT:USDT",
                highest_profit_pct=5,
                trailing_tier=2,
            )
        },
    )

    assert report.safe_mode_required is False
    assert report.stale_trailing_state_symbols == ("MOODENG/USDT:USDT",)
    assert report.issues[0].code == "stale_trailing_state"


def test_reconciliation_requires_safe_mode_for_unknown_exchange_open_order() -> None:
    report = build_reconciliation_report(
        exchange_positions=[],
        exchange_open_orders=[
            OpenOrder(
                exchange_order_id="exchange-only",
                symbol="MOODENG/USDT:USDT",
                side="buy",
                amount=1,
                price=97,
                status="open",
            )
        ],
        local_positions={},
        local_orders=[],
        trailing_states={},
    )

    assert report.safe_mode_required is True
    assert report.issues[0].code == "unknown_exchange_open_order"


def test_reconciliation_warns_when_local_snapshot_looks_open_but_exchange_is_flat() -> None:
    report = build_reconciliation_report(
        exchange_positions=[],
        exchange_open_orders=[],
        local_positions={
            "MOODENG/USDT:USDT": PositionSnapshotRecord(
                symbol="MOODENG/USDT:USDT",
                side="long",
                size=1,
                entry_price=100,
                mark_price=103,
                profit_pct=3,
                created_at="2026-05-27T00:00:00+00:00",
            )
        },
        local_orders=[],
        trailing_states={},
    )

    assert report.safe_mode_required is False
    assert report.issues[0].code == "local_position_snapshot_closed"


def test_failed_reconciliation_requires_safe_mode() -> None:
    report = failed_reconciliation_report("network unavailable")

    assert report.safe_mode_required is True
    assert report.issues[0].code == "exchange_snapshot_failed"
    assert report.issues[0].message == "network unavailable"
