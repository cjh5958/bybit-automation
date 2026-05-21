from __future__ import annotations


def valid_raw_config() -> dict:
    return {
        "app": {"mode": "dry_run", "log_level": "INFO", "timezone": "Asia/Taipei"},
        "exchange": {
            "name": "bybit",
            "account_type": "future",
            "enable_rate_limit": True,
            "default_leverage": 10,
            "bybit": {
                "api_key_env": "BYBIT_API_KEY",
                "api_secret_env": "BYBIT_API_SECRET",
            },
        },
        "telegram": {
            "enabled": False,
            "bot_token_env": "TELEGRAM_BOT_TOKEN",
            "chat_id_env": "TELEGRAM_CHAT_ID",
        },
        "runtime": {
            "strategy_interval_sec": 60,
            "risk_interval_sec": 1,
            "reconciliation_interval_sec": 30,
            "safe_mode_on_startup_mismatch": True,
        },
        "database": {"sqlite": {"path": "data/bot.sqlite3", "wal": True}},
        "cache": {
            "redis": {
                "enabled": False,
                "url_env": "REDIS_URL",
                "namespace": "bybit-automation",
            }
        },
        "strategy": {
            "defaults": {
                "enabled": True,
                "ema_period": 3,
                "value_multiplier": 3,
                "long_amount_usdt": 30,
                "short_amount_usdt": 30,
            }
        },
        "risk": {
            "defaults": {
                "enabled": True,
                "stop_loss_pct": 0.6,
                "low_trail_enable_threshold": 0.3,
                "first_trail_enable_threshold": 0.8,
                "second_trail_enable_threshold": 2.0,
                "low_trail_stop_loss_pct": 0.2,
                "trail_stop_loss_pct": 0.35,
                "higher_trail_stop_loss_pct": 0.2,
            },
            "blacklist": ["BTC/USDT:USDT"],
        },
        "symbols": [
            {"symbol": "MOODENG/USDT:USDT", "enabled": True},
            {
                "symbol": "1000X/USDT:USDT",
                "enabled": True,
                "value_multiplier": 4,
            },
        ],
    }
