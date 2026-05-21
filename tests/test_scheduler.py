from __future__ import annotations

from bybit_automation.app import BotRuntime
from bybit_automation.config import parse_config
from bybit_automation.scheduler import CadenceScheduler, ScheduledRuntime
from tests.test_runtime import FakeExchange
from tests.factories import valid_raw_config


def runtime_with_intervals(*, risk_interval: float = 1, strategy_interval: float = 60) -> BotRuntime:
    raw = valid_raw_config()
    raw["runtime"]["risk_interval_sec"] = risk_interval
    raw["runtime"]["strategy_interval_sec"] = strategy_interval
    config = parse_config(raw, resolve_secrets=False)
    return BotRuntime(config, exchange=FakeExchange())


def test_scheduler_runs_both_tasks_on_first_tick() -> None:
    runtime = runtime_with_intervals()
    scheduled = ScheduledRuntime(runtime)

    report = scheduled.run_pending(now=0)

    assert report is not None
    assert report.ran_risk is True
    assert report.ran_strategy is True


def test_scheduler_respects_different_risk_and_strategy_cadences() -> None:
    runtime = runtime_with_intervals(risk_interval=1, strategy_interval=60)
    scheduled = ScheduledRuntime(runtime)

    first = scheduled.run_pending(now=0)
    none_due = scheduled.run_pending(now=0.5)
    risk_only = scheduled.run_pending(now=1)
    both_again = scheduled.run_pending(now=60)

    assert first is not None
    assert first.ran_risk is True
    assert first.ran_strategy is True
    assert none_due is None
    assert risk_only is not None
    assert risk_only.ran_risk is True
    assert risk_only.ran_strategy is False
    assert both_again is not None
    assert both_again.ran_risk is True
    assert both_again.ran_strategy is True


def test_scheduler_seconds_until_next_task() -> None:
    scheduler = CadenceScheduler(risk_interval_sec=1, strategy_interval_sec=60)
    tasks = scheduler.due_tasks(now=0)
    scheduler.mark_completed(0, tasks)

    assert scheduler.seconds_until_next_task(0.25) == 0.75

