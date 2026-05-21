from __future__ import annotations

import pytest

from bybit_automation.config import ConfigError, parse_config
from tests.factories import valid_raw_config


def test_parse_config_resolves_symbol_defaults() -> None:
    config = parse_config(valid_raw_config(), resolve_secrets=False)

    assert config.app.mode == "dry_run"
    assert config.symbols[0].value_multiplier == 3
    assert config.symbols[1].value_multiplier == 4
    assert config.risk_blacklist == ("BTC/USDT:USDT",)


def test_parse_config_rejects_duplicate_symbols() -> None:
    raw = valid_raw_config()
    raw["symbols"].append({"symbol": "MOODENG/USDT:USDT"})

    with pytest.raises(ConfigError, match="duplicate symbol"):
        parse_config(raw, resolve_secrets=False)


def test_parse_config_rejects_unordered_risk_thresholds() -> None:
    raw = valid_raw_config()
    raw["risk"]["defaults"]["first_trail_enable_threshold"] = 0.2

    with pytest.raises(ConfigError, match="thresholds"):
        parse_config(raw, resolve_secrets=False)
