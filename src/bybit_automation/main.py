from __future__ import annotations

from pathlib import Path

from bybit_automation.app import BotRuntime
from bybit_automation.config import ConfigError, load_config
from bybit_automation.storage import PersistenceRepositories, connect_sqlite


def main() -> int:
    """Safe runtime smoke-test CLI entry point.

    The template config defaults to dry_run, so this command does not connect to
    Bybit and does not place, cancel, or close orders by default.
    """

    config_path = Path("configs/config.template.toml")
    return run_with_config(config_path)


def run_with_config(config_path: Path) -> int:
    try:
        config = load_config(config_path, resolve_secrets=False)
    except ConfigError as exc:
        print(f"Config validation failed: {exc}")
        return 1

    conn = connect_sqlite(config.sqlite.path, wal=config.sqlite.wal)
    runtime: BotRuntime | None = None
    try:
        repositories = PersistenceRepositories.from_connection(conn)
        repositories.config_versions.record_file(config_path)
        runtime = BotRuntime(config, repositories=repositories)
        report = runtime.run_once()
        print(
            "bybit-automation runtime tick OK "
            f"(mode={config.app.mode}, symbols={len(config.symbols)}, "
            f"positions={report.positions_seen}, safe_mode={report.safe_mode})"
        )
        runtime.shutdown(reason="completed")
    except KeyboardInterrupt:
        if runtime is not None:
            runtime.shutdown(reason="keyboard_interrupt")
        print("bybit-automation interrupted; shutdown state saved")
        return 130
    except Exception:
        if runtime is not None:
            runtime.shutdown(reason="error")
        raise
    finally:
        conn.close()
    return 0
