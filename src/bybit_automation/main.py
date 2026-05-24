from __future__ import annotations

from pathlib import Path

from bybit_automation.app import BotRuntime
from bybit_automation.config import ConfigError, load_config


def main() -> int:
    """Safe runtime smoke-test CLI entry point.

    The template config defaults to dry_run, so this command does not connect to
    Bybit and does not place, cancel, or close orders by default.
    """

    config_path = Path("configs/config.template.toml")
    try:
        config = load_config(config_path, resolve_secrets=False)
    except ConfigError as exc:
        print(f"Config validation failed: {exc}")
        return 1

    runtime = BotRuntime(config)
    report = runtime.run_once()
    print(
        "bybit-automation runtime tick OK "
        f"(mode={config.app.mode}, symbols={len(config.symbols)}, "
        f"positions={report.positions_seen}, safe_mode={report.safe_mode})"
    )
    return 0
