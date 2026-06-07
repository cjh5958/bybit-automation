from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re
from typing import Any, Callable, Literal

from bybit_automation.config import BotConfig, ConfigError, load_config
from bybit_automation.storage import PersistenceRepositories


ChangeSafety = Literal["hot_reloadable", "requires_restart"]
ReloadStatus = Literal["applied", "invalid", "requires_restart", "unchanged"]


@dataclass(frozen=True)
class ConfigChange:
    path: str
    before: Any
    after: Any
    safety: ChangeSafety


@dataclass(frozen=True)
class ConfigReloadPlan:
    valid: bool
    candidate: BotConfig | None
    error: str | None
    changes: tuple[ConfigChange, ...]

    @property
    def hot_reloadable_changes(self) -> tuple[ConfigChange, ...]:
        return tuple(change for change in self.changes if change.safety == "hot_reloadable")

    @property
    def unsafe_changes(self) -> tuple[ConfigChange, ...]:
        return tuple(change for change in self.changes if change.safety == "requires_restart")

    @property
    def unsafe_change_paths(self) -> tuple[str, ...]:
        return tuple(change.path for change in self.unsafe_changes)

    @property
    def requires_restart(self) -> bool:
        return bool(self.unsafe_changes)


@dataclass(frozen=True)
class ConfigReloadResult:
    status: ReloadStatus
    active_config: BotConfig
    plan: ConfigReloadPlan
    message: str
    config_version_id: int | None = None

    @property
    def restart_required_paths(self) -> tuple[str, ...]:
        return self.plan.unsafe_change_paths


class ConfigReloadService:
    def __init__(
        self,
        active_config: BotConfig,
        *,
        apply_config: Callable[[BotConfig], None] | None = None,
        repositories: PersistenceRepositories | None = None,
    ) -> None:
        self._active_config = active_config
        self._apply_config = apply_config
        self._repositories = repositories

    @property
    def active_config(self) -> BotConfig:
        return self._active_config

    def reload(
        self,
        candidate_path: str | Path,
        *,
        resolve_secrets: bool = True,
    ) -> ConfigReloadResult:
        plan = validate_reload_candidate(
            self._active_config,
            candidate_path,
            resolve_secrets=resolve_secrets,
        )
        if not plan.valid:
            result = ConfigReloadResult(
                status="invalid",
                active_config=self._active_config,
                plan=plan,
                message=plan.error or "candidate config is invalid",
            )
            self._audit_reload_result(result)
            return result

        if plan.requires_restart:
            paths = ", ".join(plan.unsafe_change_paths)
            result = ConfigReloadResult(
                status="requires_restart",
                active_config=self._active_config,
                plan=plan,
                message=(
                    "candidate config contains changes that require a safe restart"
                    f": {paths}"
                ),
            )
            self._audit_reload_result(result)
            return result

        if plan.candidate is None:
            raise RuntimeError("valid reload plan did not include candidate config")

        if not plan.changes:
            result = ConfigReloadResult(
                status="unchanged",
                active_config=self._active_config,
                plan=plan,
                message="candidate config has no changes",
            )
            self._audit_reload_result(result)
            return result

        self._active_config = plan.candidate
        if self._apply_config is not None:
            self._apply_config(plan.candidate)

        config_version_id = self._record_successful_config_version(candidate_path)
        result = ConfigReloadResult(
            status="applied",
            active_config=self._active_config,
            plan=plan,
            message="candidate config applied",
            config_version_id=config_version_id,
        )
        self._audit_reload_result(result)
        return result

    def _record_successful_config_version(self, candidate_path: str | Path) -> int | None:
        if self._repositories is None:
            return None
        return self._repositories.config_versions.record_file(
            candidate_path,
            applied_by="manual_reload",
            reload_reason="manual",
        )

    def _audit_reload_result(self, result: ConfigReloadResult) -> None:
        if self._repositories is None:
            return
        self._repositories.bot_state.set_json(
            "last_config_reload",
            {
                "status": result.status,
                "message": result.message,
                "valid": result.plan.valid,
                "change_count": len(result.plan.changes),
                "hot_reloadable_change_count": len(result.plan.hot_reloadable_changes),
                "restart_required_paths": list(result.restart_required_paths),
                "config_version_id": result.config_version_id,
            },
        )


SAFE_PATHS = {
    "runtime.strategy_interval_sec",
    "runtime.risk_interval_sec",
    "runtime.reconciliation_interval_sec",
    "strategy_defaults.enabled",
    "strategy_defaults.ema_period",
    "strategy_defaults.value_multiplier",
    "strategy_defaults.long_amount_usdt",
    "strategy_defaults.short_amount_usdt",
    "risk_defaults.enabled",
    "risk_defaults.stop_loss_pct",
    "risk_defaults.low_trail_enable_threshold",
    "risk_defaults.first_trail_enable_threshold",
    "risk_defaults.second_trail_enable_threshold",
    "risk_defaults.low_trail_stop_loss_pct",
    "risk_defaults.trail_stop_loss_pct",
    "risk_defaults.higher_trail_stop_loss_pct",
}

SAFE_PATH_PREFIXES = {
    "symbols",
    "risk_blacklist",
}


def validate_reload_candidate(
    current: BotConfig,
    candidate_path: str | Path,
    *,
    resolve_secrets: bool = True,
) -> ConfigReloadPlan:
    try:
        candidate = load_config(candidate_path, resolve_secrets=resolve_secrets)
    except ConfigError as exc:
        return ConfigReloadPlan(valid=False, candidate=None, error=str(exc), changes=())

    return build_reload_plan(current, candidate)


def build_reload_plan(current: BotConfig, candidate: BotConfig) -> ConfigReloadPlan:
    changes = tuple(_diff_configs(current, candidate))
    return ConfigReloadPlan(valid=True, candidate=candidate, error=None, changes=changes)


def _diff_configs(current: BotConfig, candidate: BotConfig) -> list[ConfigChange]:
    before = _flatten(asdict(current))
    after = _flatten(asdict(candidate))
    changes: list[ConfigChange] = []
    for path in sorted(before.keys() | after.keys()):
        before_value = before.get(path)
        after_value = after.get(path)
        if before_value == after_value:
            continue
        changes.append(
            ConfigChange(
                path=path,
                before=before_value,
                after=after_value,
                safety=_classify_change(path),
            )
        )
    return changes


def _flatten(value: Any, *, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        flattened: dict[str, Any] = {}
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            flattened.update(_flatten(item, prefix=path))
        return flattened

    if isinstance(value, (list, tuple)):
        flattened = {}
        for index, item in enumerate(value):
            path = f"{prefix}[{index}]"
            flattened.update(_flatten(item, prefix=path))
        if not value:
            flattened[prefix] = ()
        return flattened

    return {prefix: value}


def _classify_change(path: str) -> ChangeSafety:
    normalized = _normalize_indexed_path(path)
    if normalized in SAFE_PATHS:
        return "hot_reloadable"
    if any(normalized == prefix or normalized.startswith(f"{prefix}[]") for prefix in SAFE_PATH_PREFIXES):
        return "hot_reloadable"
    return "requires_restart"


def _normalize_indexed_path(path: str) -> str:
    return re.sub(r"\[\d+\]", "[]", path)
