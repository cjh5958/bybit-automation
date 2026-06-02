from __future__ import annotations

import argparse
from pathlib import Path

from bybit_automation.app import BotRuntime
from bybit_automation.cache import CachedExchangeClient, create_realtime_cache
from bybit_automation.config import ConfigError, load_config
from bybit_automation.config_reload import ConfigReloadService
from bybit_automation.exchange_client import create_exchange_client
from bybit_automation.storage import PersistenceRepositories, connect_sqlite
from bybit_automation.ws import create_websocket_runtime


def main(argv: list[str] | None = None) -> int:
    """Safe runtime smoke-test CLI entry point.

    The template config defaults to dry_run, so this command does not connect to
    Bybit and does not place, cancel, or close orders by default.
    """

    args = _parse_args(argv)
    if args.command == "reload":
        return reload_with_config(Path(args.current), Path(args.candidate))
    return run_with_config(Path(args.config))


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="bybit-automation")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--config", default="configs/config.template.toml")

    reload_parser = subparsers.add_parser("reload")
    reload_parser.add_argument("--current", default="configs/config.template.toml")
    reload_parser.add_argument("--candidate", required=True)

    parsed = parser.parse_args(argv)
    if parsed.command is None:
        parsed.command = "run"
        parsed.config = "configs/config.template.toml"
    return parsed


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
        cache = create_realtime_cache(config.redis)
        _record_config_reload_signal(repositories, cache)
        websocket = create_websocket_runtime(config, cache)
        repositories.bot_state.set_json(
            "cache_health",
            {
                "enabled": cache.health.enabled,
                "available": cache.health.available,
                "message": cache.health.message,
            },
        )
        repositories.bot_state.set_json(
            "websocket_health",
            {
                "enabled": websocket.enabled,
                "status": websocket.health.status if websocket.health is not None else "disabled",
                "message": websocket.message,
                "reason": websocket.health.reason if websocket.health is not None else None,
            },
        )
        exchange = CachedExchangeClient(create_exchange_client(config), cache)
        runtime = BotRuntime(
            config,
            exchange=exchange,
            repositories=repositories,
            market_stream_health=websocket.health,
        )
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


def reload_with_config(current_config_path: Path, candidate_config_path: Path) -> int:
    try:
        current_config = load_config(current_config_path, resolve_secrets=False)
    except ConfigError as exc:
        print(f"Current config validation failed: {exc}")
        return 1

    conn = connect_sqlite(current_config.sqlite.path, wal=current_config.sqlite.wal)
    try:
        repositories = PersistenceRepositories.from_connection(conn)
        cache = create_realtime_cache(current_config.redis)
        _record_config_reload_signal(repositories, cache)
        service = ConfigReloadService(current_config, repositories=repositories)
        result = service.reload(candidate_config_path, resolve_secrets=False)
        print(f"bybit-automation reload {result.status}: {result.message}")
        if result.status in {"invalid", "requires_restart"}:
            return 2
        return 0
    finally:
        conn.close()


def _record_config_reload_signal(
    repositories: PersistenceRepositories,
    cache: object,
) -> None:
    signal = getattr(cache, "get_config_reload_signal")()
    if signal is None:
        return
    repositories.bot_state.set_json(
        "config_reload_signal",
        {
            "reason": signal.reason,
            "requested_by": signal.requested_by,
            "requested_at": signal.requested_at,
            "applied": False,
        },
    )
