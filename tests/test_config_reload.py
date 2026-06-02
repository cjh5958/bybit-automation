from __future__ import annotations

from pathlib import Path
from typing import Any

from bybit_automation.config import parse_config
from bybit_automation.config_reload import (
    ConfigReloadService,
    build_reload_plan,
    validate_reload_candidate,
)
from tests.factories import valid_raw_config


def write_config(path: Path, raw: dict[str, Any]) -> None:
    text = f"""
[app]
mode = "{raw["app"]["mode"]}"
log_level = "{raw["app"]["log_level"]}"
timezone = "{raw["app"]["timezone"]}"

[exchange]
name = "{raw["exchange"]["name"]}"
account_type = "{raw["exchange"]["account_type"]}"
enable_rate_limit = {str(raw["exchange"]["enable_rate_limit"]).lower()}
default_leverage = {raw["exchange"]["default_leverage"]}

[exchange.bybit]
api_key_env = "{raw["exchange"]["bybit"]["api_key_env"]}"
api_secret_env = "{raw["exchange"]["bybit"]["api_secret_env"]}"

[telegram]
enabled = {str(raw["telegram"]["enabled"]).lower()}
bot_token_env = "{raw["telegram"]["bot_token_env"]}"
chat_id_env = "{raw["telegram"]["chat_id_env"]}"

[runtime]
strategy_interval_sec = {raw["runtime"]["strategy_interval_sec"]}
risk_interval_sec = {raw["runtime"]["risk_interval_sec"]}
reconciliation_interval_sec = {raw["runtime"]["reconciliation_interval_sec"]}
safe_mode_on_startup_mismatch = {str(raw["runtime"]["safe_mode_on_startup_mismatch"]).lower()}

[database.sqlite]
path = "{raw["database"]["sqlite"]["path"]}"
wal = {str(raw["database"]["sqlite"]["wal"]).lower()}

[cache.redis]
enabled = {str(raw["cache"]["redis"]["enabled"]).lower()}
url_env = "{raw["cache"]["redis"]["url_env"]}"
namespace = "{raw["cache"]["redis"]["namespace"]}"

[websocket]
enabled = {str(raw["websocket"]["enabled"]).lower()}
public_market = {str(raw["websocket"]["public_market"]).lower()}
private_account = {str(raw["websocket"]["private_account"]).lower()}
stale_after_sec = {raw["websocket"]["stale_after_sec"]}
reconnect_initial_delay_sec = {raw["websocket"]["reconnect_initial_delay_sec"]}
reconnect_max_delay_sec = {raw["websocket"]["reconnect_max_delay_sec"]}

[strategy.defaults]
enabled = {str(raw["strategy"]["defaults"]["enabled"]).lower()}
ema_period = {raw["strategy"]["defaults"]["ema_period"]}
value_multiplier = {raw["strategy"]["defaults"]["value_multiplier"]}
long_amount_usdt = {raw["strategy"]["defaults"]["long_amount_usdt"]}
short_amount_usdt = {raw["strategy"]["defaults"]["short_amount_usdt"]}

[risk.defaults]
enabled = {str(raw["risk"]["defaults"]["enabled"]).lower()}
stop_loss_pct = {raw["risk"]["defaults"]["stop_loss_pct"]}
low_trail_enable_threshold = {raw["risk"]["defaults"]["low_trail_enable_threshold"]}
first_trail_enable_threshold = {raw["risk"]["defaults"]["first_trail_enable_threshold"]}
second_trail_enable_threshold = {raw["risk"]["defaults"]["second_trail_enable_threshold"]}
low_trail_stop_loss_pct = {raw["risk"]["defaults"]["low_trail_stop_loss_pct"]}
trail_stop_loss_pct = {raw["risk"]["defaults"]["trail_stop_loss_pct"]}
higher_trail_stop_loss_pct = {raw["risk"]["defaults"]["higher_trail_stop_loss_pct"]}

[risk]
blacklist = [{", ".join(f'"{item}"' for item in raw["risk"]["blacklist"])}]
"""
    for symbol in raw["symbols"]:
        text += f"""
[[symbols]]
symbol = "{symbol["symbol"]}"
enabled = {str(symbol["enabled"]).lower()}
"""
        for key in ("ema_period", "value_multiplier", "long_amount_usdt", "short_amount_usdt"):
            if key in symbol:
                text += f"{key} = {symbol[key]}\n"
    path.write_text(text, encoding="utf-8")


def test_reload_plan_classifies_hot_reloadable_strategy_changes() -> None:
    current = parse_config(valid_raw_config(), resolve_secrets=False)
    raw_candidate = valid_raw_config()
    raw_candidate["runtime"]["strategy_interval_sec"] = 30
    raw_candidate["strategy"]["defaults"]["long_amount_usdt"] = 40
    raw_candidate["symbols"][0]["enabled"] = False
    raw_candidate["risk"]["blacklist"] = ["BTC/USDT:USDT", "ETH/USDT:USDT"]
    candidate = parse_config(raw_candidate, resolve_secrets=False)

    plan = build_reload_plan(current, candidate)

    assert plan.valid is True
    assert plan.requires_restart is False
    assert {change.path for change in plan.hot_reloadable_changes} == {
        "risk_blacklist[1]",
        "runtime.strategy_interval_sec",
        "strategy_defaults.long_amount_usdt",
        "symbols[0].long_amount_usdt",
        "symbols[0].enabled",
        "symbols[1].long_amount_usdt",
    }
    assert plan.unsafe_changes == ()


def test_reload_plan_classifies_exchange_and_database_changes_as_unsafe() -> None:
    current = parse_config(valid_raw_config(), resolve_secrets=False)
    raw_candidate = valid_raw_config()
    raw_candidate["app"]["mode"] = "demo"
    raw_candidate["exchange"]["account_type"] = "spot"
    raw_candidate["database"]["sqlite"]["path"] = "data/other.sqlite3"
    candidate = parse_config(raw_candidate, resolve_secrets=False)

    plan = build_reload_plan(current, candidate)

    assert plan.valid is True
    assert plan.requires_restart is True
    assert {change.path for change in plan.unsafe_changes} == {
        "app.mode",
        "exchange.account_type",
        "sqlite.path",
    }


def test_validate_reload_candidate_reports_invalid_config_without_candidate(tmp_path: Path) -> None:
    current = parse_config(valid_raw_config(), resolve_secrets=False)
    candidate_path = tmp_path / "invalid.toml"
    candidate_path.write_text("[app]\nmode = \"dry_run\"\n", encoding="utf-8")

    plan = validate_reload_candidate(current, candidate_path, resolve_secrets=False)

    assert plan.valid is False
    assert plan.candidate is None
    assert plan.error is not None
    assert "missing or invalid section" in plan.error
    assert plan.changes == ()


def test_reload_service_applies_safe_candidate_and_calls_callback(tmp_path: Path) -> None:
    current = parse_config(valid_raw_config(), resolve_secrets=False)
    raw_candidate = valid_raw_config()
    raw_candidate["runtime"]["risk_interval_sec"] = 2
    candidate_path = tmp_path / "candidate.toml"
    write_config(candidate_path, raw_candidate)
    applied = []
    service = ConfigReloadService(current, apply_config=applied.append)

    result = service.reload(candidate_path, resolve_secrets=False)

    assert result.status == "applied"
    assert result.active_config.runtime.risk_interval_sec == 2
    assert service.active_config.runtime.risk_interval_sec == 2
    assert applied == [result.active_config]


def test_reload_service_keeps_active_config_when_candidate_is_invalid(tmp_path: Path) -> None:
    current = parse_config(valid_raw_config(), resolve_secrets=False)
    candidate_path = tmp_path / "invalid.toml"
    candidate_path.write_text("[app]\nmode = \"dry_run\"\n", encoding="utf-8")
    service = ConfigReloadService(current)

    result = service.reload(candidate_path, resolve_secrets=False)

    assert result.status == "invalid"
    assert result.active_config is current
    assert service.active_config is current


def test_reload_service_keeps_active_config_when_candidate_requires_restart(
    tmp_path: Path,
) -> None:
    current = parse_config(valid_raw_config(), resolve_secrets=False)
    raw_candidate = valid_raw_config()
    raw_candidate["exchange"]["account_type"] = "spot"
    candidate_path = tmp_path / "candidate.toml"
    write_config(candidate_path, raw_candidate)
    service = ConfigReloadService(current)

    result = service.reload(candidate_path, resolve_secrets=False)

    assert result.status == "requires_restart"
    assert result.active_config is current
    assert service.active_config is current
    assert result.plan.requires_restart is True
    assert result.restart_required_paths == ("exchange.account_type",)
    assert "exchange.account_type" in result.message
