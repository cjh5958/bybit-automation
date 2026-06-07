from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

from bybit_automation.config import ConfigError


def load_runtime_env(env_file: str | Path | None = None) -> None:
    """Load runtime environment variables from .env without overriding the shell."""

    if env_file is None:
        path = Path.cwd() / ".env"
        if not path.exists():
            return
    else:
        path = Path(env_file)
        if not path.exists():
            raise ConfigError(f"env file does not exist: {path}")

    load_dotenv(path, override=False, encoding="utf-8-sig")
