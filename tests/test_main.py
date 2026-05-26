from __future__ import annotations

from pathlib import Path
import sqlite3

from bybit_automation.main import run_with_config


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
        assert conn.execute("SELECT COUNT(*) FROM bot_state").fetchone()[0] == 1
    finally:
        conn.close()
