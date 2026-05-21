from __future__ import annotations

from pathlib import Path

from bybit_stream_bot.config import ConfigError, load_config


def main() -> int:
    """Safe Phase 0 CLI entry point.

    This command validates config shape only. It does not connect to Bybit and
    does not place, cancel, or close orders.
    """

    config_path = Path("configs/config.template.toml")
    try:
        config = load_config(config_path, resolve_secrets=False)
    except ConfigError as exc:
        print(f"Config validation failed: {exc}")
        return 1

    print(
        "bybit-stream-bot phase0 startup OK "
        f"(mode={config.app.mode}, symbols={len(config.symbols)})"
    )
    return 0

