from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Callable

from bybit_automation.app import BotRuntime, RuntimeReport


@dataclass(frozen=True)
class ScheduledTasks:
    run_risk: bool
    run_strategy: bool

    @property
    def has_work(self) -> bool:
        return self.run_risk or self.run_strategy


class CadenceScheduler:
    def __init__(
        self,
        *,
        risk_interval_sec: float,
        strategy_interval_sec: float,
    ) -> None:
        if risk_interval_sec <= 0:
            raise ValueError("risk_interval_sec must be positive")
        if strategy_interval_sec <= 0:
            raise ValueError("strategy_interval_sec must be positive")

        self._risk_interval_sec = risk_interval_sec
        self._strategy_interval_sec = strategy_interval_sec
        self._next_risk_at = 0.0
        self._next_strategy_at = 0.0

    def due_tasks(self, now: float) -> ScheduledTasks:
        return ScheduledTasks(
            run_risk=now >= self._next_risk_at,
            run_strategy=now >= self._next_strategy_at,
        )

    def mark_completed(self, now: float, tasks: ScheduledTasks) -> None:
        if tasks.run_risk:
            self._next_risk_at = now + self._risk_interval_sec
        if tasks.run_strategy:
            self._next_strategy_at = now + self._strategy_interval_sec

    def seconds_until_next_task(self, now: float) -> float:
        return max(0.0, min(self._next_risk_at, self._next_strategy_at) - now)


class ScheduledRuntime:
    def __init__(
        self,
        runtime: BotRuntime,
        *,
        scheduler: CadenceScheduler | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._runtime = runtime
        self._scheduler = scheduler or CadenceScheduler(
            risk_interval_sec=runtime.config.runtime.risk_interval_sec,
            strategy_interval_sec=runtime.config.runtime.strategy_interval_sec,
        )
        self._monotonic = monotonic
        self._sleep = sleep

    def run_pending(self, now: float | None = None) -> RuntimeReport | None:
        current_time = self._monotonic() if now is None else now
        tasks = self._scheduler.due_tasks(current_time)
        if not tasks.has_work:
            return None

        report = self._runtime.run_once(
            include_risk=tasks.run_risk,
            include_strategy=tasks.run_strategy,
        )
        self._scheduler.mark_completed(current_time, tasks)
        return report

    def run_forever(self) -> None:
        while True:
            now = self._monotonic()
            report = self.run_pending(now)
            if report is None:
                self._sleep(self._scheduler.seconds_until_next_task(now))

