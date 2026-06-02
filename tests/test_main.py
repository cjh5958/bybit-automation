from __future__ import annotations

from pathlib import Path
import json
import sqlite3

from bybit_automation.main import (
    main,
    reload_with_config,
    run_with_config,
    verify_dry_run_with_config,
)


def test_run_with_config_bootstraps_sqlite_and_records_config(tmp_path: Path) -> None:
    config_text = Path("configs/config.template.toml").read_text(encoding="utf-8")
    db_path = tmp_path / "bot.sqlite3"
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        config_text.replace('path = "data/bot.sqlite3"', f'path = "{db_path.as_posix()}"'),
        encoding="utf-8",
    )

    result = run_with_config(config_path)

    conn = sqlite3.connect(db_path)
    try:
        assert result == 0
        assert conn.execute("SELECT COUNT(*) FROM config_versions").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM strategy_decisions").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM bot_state").fetchone()[0] == 6
        cache_health = conn.execute(
            "SELECT value_json FROM bot_state WHERE key = 'cache_health'"
        ).fetchone()[0]
        assert json.loads(cache_health) == {
            "available": False,
            "enabled": False,
            "message": "redis disabled",
        }
        websocket_health = conn.execute(
            "SELECT value_json FROM bot_state WHERE key = 'websocket_health'"
        ).fetchone()[0]
        assert json.loads(websocket_health) == {
            "enabled": False,
            "message": "websocket disabled",
            "reason": None,
            "status": "disabled",
        }
        health_report = conn.execute(
            "SELECT value_json FROM bot_state WHERE key = 'health_report'"
        ).fetchone()[0]
        assert json.loads(health_report)["status"] == "warn"
        shutdown = conn.execute(
            "SELECT value_json FROM bot_state WHERE key = 'shutdown'"
        ).fetchone()[0]
        assert '"reason": "completed"' in shutdown
    finally:
        conn.close()


def test_main_without_args_runs_default_command(monkeypatch, tmp_path: Path) -> None:
    config_text = Path("configs/config.template.toml").read_text(encoding="utf-8")
    db_path = tmp_path / "bot.sqlite3"
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        config_text.replace('path = "data/bot.sqlite3"', f'path = "{db_path.as_posix()}"'),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    configs_dir = tmp_path / "configs"
    configs_dir.mkdir()
    (configs_dir / "config.template.toml").write_text(config_path.read_text(), encoding="utf-8")

    assert main([]) == 0


def test_reload_with_config_applies_safe_candidate_and_records_audit(tmp_path: Path) -> None:
    config_text = Path("configs/config.template.toml").read_text(encoding="utf-8")
    db_path = tmp_path / "bot.sqlite3"
    current_path = tmp_path / "current.toml"
    candidate_path = tmp_path / "candidate.toml"
    current_text = config_text.replace('path = "data/bot.sqlite3"', f'path = "{db_path.as_posix()}"')
    current_path.write_text(current_text, encoding="utf-8")
    candidate_path.write_text(
        current_text.replace("risk_interval_sec = 1", "risk_interval_sec = 2"),
        encoding="utf-8",
    )

    result = reload_with_config(current_path, candidate_path)

    conn = sqlite3.connect(db_path)
    try:
        assert result == 0
        assert conn.execute("SELECT COUNT(*) FROM config_versions").fetchone()[0] == 1
        audit = json.loads(
            conn.execute(
                "SELECT value_json FROM bot_state WHERE key = 'last_config_reload'"
            ).fetchone()[0]
        )
        assert audit["status"] == "applied"
        assert audit["config_version_id"] == 1
    finally:
        conn.close()


def test_reload_with_config_returns_nonzero_for_unsafe_candidate(tmp_path: Path) -> None:
    config_text = Path("configs/config.template.toml").read_text(encoding="utf-8")
    db_path = tmp_path / "bot.sqlite3"
    current_path = tmp_path / "current.toml"
    candidate_path = tmp_path / "candidate.toml"
    current_text = config_text.replace('path = "data/bot.sqlite3"', f'path = "{db_path.as_posix()}"')
    current_path.write_text(current_text, encoding="utf-8")
    candidate_path.write_text(
        current_text.replace('account_type = "future"', 'account_type = "spot"'),
        encoding="utf-8",
    )

    result = reload_with_config(current_path, candidate_path)

    conn = sqlite3.connect(db_path)
    try:
        assert result == 2
        assert conn.execute("SELECT COUNT(*) FROM config_versions").fetchone()[0] == 0
        audit = json.loads(
            conn.execute(
                "SELECT value_json FROM bot_state WHERE key = 'last_config_reload'"
            ).fetchone()[0]
        )
        assert audit["status"] == "requires_restart"
    finally:
        conn.close()


def test_verify_dry_run_with_config_runs_safe_smoke(tmp_path: Path) -> None:
    config_text = Path("configs/config.template.toml").read_text(encoding="utf-8")
    db_path = tmp_path / "bot.sqlite3"
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        config_text.replace('path = "data/bot.sqlite3"', f'path = "{db_path.as_posix()}"'),
        encoding="utf-8",
    )

    assert verify_dry_run_with_config(config_path) == 0


def test_verify_dry_run_with_config_rejects_demo_mode(tmp_path: Path) -> None:
    config_text = Path("configs/config.template.toml").read_text(encoding="utf-8")
    db_path = tmp_path / "bot.sqlite3"
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        config_text.replace('path = "data/bot.sqlite3"', f'path = "{db_path.as_posix()}"').replace(
            'mode = "dry_run"',
            'mode = "demo"',
        ),
        encoding="utf-8",
    )

    assert verify_dry_run_with_config(config_path) == 2
