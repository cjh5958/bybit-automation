from __future__ import annotations

from pathlib import Path

from bybit_automation.config import parse_config
from bybit_automation.config_reload import build_reload_plan, validate_reload_candidate
from tests.factories import valid_raw_config


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
