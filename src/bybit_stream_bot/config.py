from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import tomllib
from typing import Any, Literal


Mode = Literal["dry_run", "demo", "live"]


class ConfigError(ValueError):
    """Raised when runtime configuration is invalid."""


@dataclass(frozen=True)
class AppConfig:
    mode: Mode
    log_level: str
    timezone: str


@dataclass(frozen=True)
class ExchangeConfig:
    name: str
    account_type: str
    enable_rate_limit: bool
    default_leverage: int
    api_key_env: str
    api_secret_env: str
    api_key: str | None = None
    api_secret: str | None = None


@dataclass(frozen=True)
class TelegramConfig:
    enabled: bool
    bot_token_env: str
    chat_id_env: str
    bot_token: str | None = None
    chat_id: str | None = None


@dataclass(frozen=True)
class RuntimeConfig:
    strategy_interval_sec: float
    risk_interval_sec: float
    reconciliation_interval_sec: float
    safe_mode_on_startup_mismatch: bool


@dataclass(frozen=True)
class SqliteConfig:
    path: str
    wal: bool


@dataclass(frozen=True)
class RedisConfig:
    enabled: bool
    url_env: str
    namespace: str
    url: str | None = None


@dataclass(frozen=True)
class StrategyDefaults:
    enabled: bool
    ema_period: int
    value_multiplier: float
    long_amount_usdt: float
    short_amount_usdt: float


@dataclass(frozen=True)
class RiskDefaults:
    enabled: bool
    stop_loss_pct: float
    low_trail_enable_threshold: float
    first_trail_enable_threshold: float
    second_trail_enable_threshold: float
    low_trail_stop_loss_pct: float
    trail_stop_loss_pct: float
    higher_trail_stop_loss_pct: float


@dataclass(frozen=True)
class SymbolConfig:
    symbol: str
    enabled: bool
    ema_period: int
    value_multiplier: float
    long_amount_usdt: float
    short_amount_usdt: float


@dataclass(frozen=True)
class BotConfig:
    app: AppConfig
    exchange: ExchangeConfig
    telegram: TelegramConfig
    runtime: RuntimeConfig
    sqlite: SqliteConfig
    redis: RedisConfig
    strategy_defaults: StrategyDefaults
    risk_defaults: RiskDefaults
    risk_blacklist: tuple[str, ...]
    symbols: tuple[SymbolConfig, ...]


def load_config(path: str | Path, *, resolve_secrets: bool = True) -> BotConfig:
    config_path = Path(path)
    if not config_path.exists():
        raise ConfigError(f"config file does not exist: {config_path}")

    with config_path.open("rb") as config_file:
        raw = tomllib.load(config_file)

    return parse_config(raw, resolve_secrets=resolve_secrets)


def parse_config(raw: dict[str, Any], *, resolve_secrets: bool = True) -> BotConfig:
    app_raw = _section(raw, "app")
    exchange_raw = _section(raw, "exchange")
    bybit_raw = _section(exchange_raw, "bybit")
    telegram_raw = _section(raw, "telegram")
    runtime_raw = _section(raw, "runtime")
    database_raw = _section(raw, "database")
    sqlite_raw = _section(database_raw, "sqlite")
    cache_raw = _section(raw, "cache")
    redis_raw = _section(cache_raw, "redis")
    strategy_raw = _section(raw, "strategy")
    strategy_defaults_raw = _section(strategy_raw, "defaults")
    risk_raw = _section(raw, "risk")
    risk_defaults_raw = _section(risk_raw, "defaults")

    app = AppConfig(
        mode=_mode(_required(app_raw, "mode")),
        log_level=str(_required(app_raw, "log_level")),
        timezone=str(_required(app_raw, "timezone")),
    )

    exchange = ExchangeConfig(
        name=str(_required(exchange_raw, "name")),
        account_type=str(_required(exchange_raw, "account_type")),
        enable_rate_limit=bool(_required(exchange_raw, "enable_rate_limit")),
        default_leverage=_positive_int(_required(exchange_raw, "default_leverage"), "default_leverage"),
        api_key_env=str(_required(bybit_raw, "api_key_env")),
        api_secret_env=str(_required(bybit_raw, "api_secret_env")),
    )

    telegram = TelegramConfig(
        enabled=bool(_required(telegram_raw, "enabled")),
        bot_token_env=str(_required(telegram_raw, "bot_token_env")),
        chat_id_env=str(_required(telegram_raw, "chat_id_env")),
    )

    runtime = RuntimeConfig(
        strategy_interval_sec=_positive_float(
            _required(runtime_raw, "strategy_interval_sec"), "strategy_interval_sec"
        ),
        risk_interval_sec=_positive_float(_required(runtime_raw, "risk_interval_sec"), "risk_interval_sec"),
        reconciliation_interval_sec=_positive_float(
            _required(runtime_raw, "reconciliation_interval_sec"), "reconciliation_interval_sec"
        ),
        safe_mode_on_startup_mismatch=bool(
            _required(runtime_raw, "safe_mode_on_startup_mismatch")
        ),
    )

    sqlite = SqliteConfig(
        path=str(_required(sqlite_raw, "path")),
        wal=bool(_required(sqlite_raw, "wal")),
    )

    redis = RedisConfig(
        enabled=bool(_required(redis_raw, "enabled")),
        url_env=str(_required(redis_raw, "url_env")),
        namespace=str(_required(redis_raw, "namespace")),
    )

    strategy_defaults = StrategyDefaults(
        enabled=bool(_required(strategy_defaults_raw, "enabled")),
        ema_period=_non_negative_int(_required(strategy_defaults_raw, "ema_period"), "ema_period"),
        value_multiplier=_non_negative_float(
            _required(strategy_defaults_raw, "value_multiplier"), "value_multiplier"
        ),
        long_amount_usdt=_non_negative_float(
            _required(strategy_defaults_raw, "long_amount_usdt"), "long_amount_usdt"
        ),
        short_amount_usdt=_non_negative_float(
            _required(strategy_defaults_raw, "short_amount_usdt"), "short_amount_usdt"
        ),
    )

    risk_defaults = RiskDefaults(
        enabled=bool(_required(risk_defaults_raw, "enabled")),
        stop_loss_pct=_non_negative_float(_required(risk_defaults_raw, "stop_loss_pct"), "stop_loss_pct"),
        low_trail_enable_threshold=_non_negative_float(
            _required(risk_defaults_raw, "low_trail_enable_threshold"),
            "low_trail_enable_threshold",
        ),
        first_trail_enable_threshold=_non_negative_float(
            _required(risk_defaults_raw, "first_trail_enable_threshold"),
            "first_trail_enable_threshold",
        ),
        second_trail_enable_threshold=_non_negative_float(
            _required(risk_defaults_raw, "second_trail_enable_threshold"),
            "second_trail_enable_threshold",
        ),
        low_trail_stop_loss_pct=_non_negative_float(
            _required(risk_defaults_raw, "low_trail_stop_loss_pct"),
            "low_trail_stop_loss_pct",
        ),
        trail_stop_loss_pct=_non_negative_float(
            _required(risk_defaults_raw, "trail_stop_loss_pct"), "trail_stop_loss_pct"
        ),
        higher_trail_stop_loss_pct=_non_negative_float(
            _required(risk_defaults_raw, "higher_trail_stop_loss_pct"),
            "higher_trail_stop_loss_pct",
        ),
    )
    _validate_risk_thresholds(risk_defaults)

    symbols = _parse_symbols(raw.get("symbols", []), strategy_defaults)
    risk_blacklist = tuple(str(symbol) for symbol in risk_raw.get("blacklist", []))

    if exchange.name != "bybit":
        raise ConfigError(f"unsupported exchange: {exchange.name}")

    if redis.enabled and not redis.namespace:
        raise ConfigError("redis namespace must not be empty when redis is enabled")

    if resolve_secrets:
        exchange = _resolve_exchange_secrets(exchange, app.mode)
        telegram = _resolve_telegram_secrets(telegram)
        redis = _resolve_redis_url(redis)

    return BotConfig(
        app=app,
        exchange=exchange,
        telegram=telegram,
        runtime=runtime,
        sqlite=sqlite,
        redis=redis,
        strategy_defaults=strategy_defaults,
        risk_defaults=risk_defaults,
        risk_blacklist=risk_blacklist,
        symbols=symbols,
    )


def _parse_symbols(
    symbols_raw: Any, strategy_defaults: StrategyDefaults
) -> tuple[SymbolConfig, ...]:
    if not isinstance(symbols_raw, list):
        raise ConfigError("symbols must be a list")

    symbols: list[SymbolConfig] = []
    seen: set[str] = set()
    for index, raw_symbol in enumerate(symbols_raw):
        if not isinstance(raw_symbol, dict):
            raise ConfigError(f"symbols[{index}] must be a table")

        symbol = str(_required(raw_symbol, "symbol")).strip()
        if not symbol:
            raise ConfigError(f"symbols[{index}].symbol must not be empty")
        if symbol in seen:
            raise ConfigError(f"duplicate symbol: {symbol}")
        seen.add(symbol)

        symbols.append(
            SymbolConfig(
                symbol=symbol,
                enabled=bool(raw_symbol.get("enabled", strategy_defaults.enabled)),
                ema_period=_non_negative_int(
                    raw_symbol.get("ema_period", strategy_defaults.ema_period),
                    f"{symbol}.ema_period",
                ),
                value_multiplier=_non_negative_float(
                    raw_symbol.get("value_multiplier", strategy_defaults.value_multiplier),
                    f"{symbol}.value_multiplier",
                ),
                long_amount_usdt=_non_negative_float(
                    raw_symbol.get("long_amount_usdt", strategy_defaults.long_amount_usdt),
                    f"{symbol}.long_amount_usdt",
                ),
                short_amount_usdt=_non_negative_float(
                    raw_symbol.get("short_amount_usdt", strategy_defaults.short_amount_usdt),
                    f"{symbol}.short_amount_usdt",
                ),
            )
        )

    if not symbols:
        raise ConfigError("at least one symbol is required")
    return tuple(symbols)


def _resolve_exchange_secrets(exchange: ExchangeConfig, mode: Mode) -> ExchangeConfig:
    api_key = os.getenv(exchange.api_key_env)
    api_secret = os.getenv(exchange.api_secret_env)
    if mode in {"demo", "live"} and (not api_key or not api_secret):
        raise ConfigError("exchange API credentials are required outside dry_run mode")
    return ExchangeConfig(**{**exchange.__dict__, "api_key": api_key, "api_secret": api_secret})


def _resolve_telegram_secrets(telegram: TelegramConfig) -> TelegramConfig:
    bot_token = os.getenv(telegram.bot_token_env)
    chat_id = os.getenv(telegram.chat_id_env)
    if telegram.enabled and (not bot_token or not chat_id):
        raise ConfigError("telegram credentials are required when telegram is enabled")
    return TelegramConfig(**{**telegram.__dict__, "bot_token": bot_token, "chat_id": chat_id})


def _resolve_redis_url(redis: RedisConfig) -> RedisConfig:
    url = os.getenv(redis.url_env)
    if redis.enabled and not url:
        raise ConfigError("redis URL is required when redis is enabled")
    return RedisConfig(**{**redis.__dict__, "url": url})


def _section(raw: dict[str, Any], key: str) -> dict[str, Any]:
    value = raw.get(key)
    if not isinstance(value, dict):
        raise ConfigError(f"missing or invalid section: {key}")
    return value


def _required(raw: dict[str, Any], key: str) -> Any:
    if key not in raw:
        raise ConfigError(f"missing required config key: {key}")
    return raw[key]


def _mode(value: Any) -> Mode:
    if value not in {"dry_run", "demo", "live"}:
        raise ConfigError(f"invalid app.mode: {value}")
    return value


def _positive_int(value: Any, name: str) -> int:
    number = int(value)
    if number <= 0:
        raise ConfigError(f"{name} must be positive")
    return number


def _non_negative_int(value: Any, name: str) -> int:
    number = int(value)
    if number < 0:
        raise ConfigError(f"{name} must be non-negative")
    return number


def _positive_float(value: Any, name: str) -> float:
    number = float(value)
    if number <= 0:
        raise ConfigError(f"{name} must be positive")
    return number


def _non_negative_float(value: Any, name: str) -> float:
    number = float(value)
    if number < 0:
        raise ConfigError(f"{name} must be non-negative")
    return number


def _validate_risk_thresholds(risk: RiskDefaults) -> None:
    if not (
        risk.low_trail_enable_threshold
        <= risk.first_trail_enable_threshold
        <= risk.second_trail_enable_threshold
    ):
        raise ConfigError("risk trailing thresholds must be ordered from low to high")

