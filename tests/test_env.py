from __future__ import annotations

from pathlib import Path
import os

import pytest

from bybit_automation.config import ConfigError
from bybit_automation.env import load_runtime_env


def test_load_runtime_env_reads_default_dotenv_without_overriding_shell(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BYBIT_API_KEY", "from-shell")
    monkeypatch.delenv("BYBIT_API_SECRET", raising=False)
    (tmp_path / ".env").write_text(
        "BYBIT_API_KEY=from-dotenv\nBYBIT_API_SECRET=secret-from-dotenv\n",
        encoding="utf-8",
    )

    load_runtime_env()

    assert os.environ["BYBIT_API_KEY"] == "from-shell"
    assert os.environ["BYBIT_API_SECRET"] == "secret-from-dotenv"


def test_load_runtime_env_reads_explicit_env_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("BYBIT_API_KEY", raising=False)
    env_path = tmp_path / "demo.env"
    env_path.write_text("BYBIT_API_KEY=from-explicit-file\n", encoding="utf-8")

    load_runtime_env(env_path)

    assert os.environ["BYBIT_API_KEY"] == "from-explicit-file"


def test_load_runtime_env_handles_utf8_bom(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("BYBIT_API_KEY", raising=False)
    env_path = tmp_path / ".env"
    env_path.write_text("\ufeffBYBIT_API_KEY=from-bom-file\n", encoding="utf-8")

    load_runtime_env(env_path)

    assert os.environ["BYBIT_API_KEY"] == "from-bom-file"


def test_load_runtime_env_rejects_missing_explicit_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="env file does not exist"):
        load_runtime_env(tmp_path / "missing.env")
