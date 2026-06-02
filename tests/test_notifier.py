from __future__ import annotations

from bybit_automation.notifier import Notifier


def test_notifier_records_severity_and_keeps_message_compatibility() -> None:
    notifier = Notifier()

    notifier.info("started")
    notifier.warning("redis disabled")
    notifier.safe_mode("unknown order")
    notifier.error("exchange failed")

    assert notifier.messages == [
        "started",
        "redis disabled",
        "unknown order",
        "exchange failed",
    ]
    assert [notification.severity for notification in notifier.notifications] == [
        "info",
        "warning",
        "safe_mode",
        "error",
    ]
