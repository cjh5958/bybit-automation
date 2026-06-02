# SPEC.md

This file records project-level specifications that future agents should treat
as the current design target unless the user explicitly changes direction.

Keep this document concise. Detailed implementation notes belong in code,
tests, or phase-specific documentation.

## Config Specification

### Goals

The future config system should be:

- easy to edit in local development,
- easy to override in containers,
- safe to commit as a template,
- validated before runtime use,
- versioned when successfully loaded,
- suitable for future hot reload.

### File Format

Use TOML for the primary config format.

Planned files:

```text
configs/config.template.toml
configs/config.toml
```

Rules:

- `configs/config.template.toml` is committed.
- `configs/config.toml` is local/runtime-specific and should not be committed.
- Secrets must not be stored directly in committed config files.
- Runtime secrets should come from environment variables.
- Container deployments should be able to mount or replace `config.toml`.

Rationale:

- TOML is human-readable and works naturally beside `pyproject.toml`.
- Python 3.11+ can read TOML through `tomllib`.
- A single config file avoids ambiguous merge behavior from multiple JSON files.

### Environment Variables and Secrets

Config should store environment variable names, not secret values.

Example:

```toml
[exchange.bybit]
api_key_env = "BYBIT_API_KEY"
api_secret_env = "BYBIT_API_SECRET"

[telegram]
enabled = true
bot_token_env = "TELEGRAM_BOT_TOKEN"
chat_id_env = "TELEGRAM_CHAT_ID"
```

Expected behavior:

- The loader resolves env var names at runtime.
- Missing required secrets should fail validation before trading starts.
- Dry-run mode may allow missing exchange credentials if no exchange side effect
  will be performed.

### Container-Friendly Overrides

The config design should support containers without requiring image rebuilds.

Preferred mechanisms:

- mount `configs/config.toml`,
- inject secrets through environment variables,
- optionally override config path through an environment variable such as
  `BYBIT_AUTOMATION_CONFIG`.

Do not require editing source code to change runtime config.

### Top-Level Structure

The target config structure is:

```toml
[app]
mode = "dry_run"
log_level = "INFO"
timezone = "Asia/Taipei"

[exchange]
name = "bybit"
account_type = "future"
enable_rate_limit = true
default_leverage = 10

[exchange.bybit]
api_key_env = "BYBIT_API_KEY"
api_secret_env = "BYBIT_API_SECRET"

[telegram]
enabled = true
bot_token_env = "TELEGRAM_BOT_TOKEN"
chat_id_env = "TELEGRAM_CHAT_ID"

[runtime]
strategy_interval_sec = 60
risk_interval_sec = 1
reconciliation_interval_sec = 30
safe_mode_on_startup_mismatch = true

[database.sqlite]
path = "data/bot.sqlite3"
wal = true

[cache.redis]
enabled = false
url_env = "REDIS_URL"
namespace = "bybit-automation"

[websocket]
enabled = false
public_market = true
private_account = true
stale_after_sec = 5
reconnect_initial_delay_sec = 1
reconnect_max_delay_sec = 30

[strategy.defaults]
enabled = true
ema_period = 240
value_multiplier = 3
long_amount_usdt = 30
short_amount_usdt = 30

[risk.defaults]
enabled = true
stop_loss_pct = 0.6
low_trail_enable_threshold = 0.3
first_trail_enable_threshold = 0.8
second_trail_enable_threshold = 2.0
low_trail_stop_loss_pct = 0.2
trail_stop_loss_pct = 0.35
higher_trail_stop_loss_pct = 0.2

[risk]
blacklist = [
  "BTC/USDT:USDT",
  "ETH/USDT:USDT",
  "SOL/USDT:USDT",
]

[[symbols]]
symbol = "MOODENG/USDT:USDT"
enabled = true

[[symbols]]
symbol = "1000X/USDT:USDT"
enabled = true
value_multiplier = 3
long_amount_usdt = 30
short_amount_usdt = 30
```

### Mode Semantics

`app.mode` should support:

- `dry_run`: no live exchange side effects; safe default for development.
- `demo`: exchange demo/sandbox mode where supported.
- `live`: real trading mode; must require explicit config and valid credentials.

New runtime code must not default to live trading.

### Defaults and Symbol Overrides

Use defaults plus per-symbol overrides.

Rules:

- `[strategy.defaults]` defines common strategy settings.
- `[risk.defaults]` defines common risk/trailing settings.
- Each `[[symbols]]` entry may override supported strategy fields.
- Later implementation may allow per-symbol risk overrides, but this should be
  explicit and validated.
- The loader should produce a resolved per-symbol config before runtime use.

This avoids repeating the same values for every trading pair.

### Naming Rules

Avoid ambiguous names.

Use:

- `strategy_interval_sec`
- `risk_interval_sec`
- `reconciliation_interval_sec`

Do not reuse a generic key such as `monitor_interval` across unrelated sections.

Use explicit units in names where practical, especially for time intervals.

### Validation Rules

Config must be validated before runtime use.

Minimum validation:

- `app.mode` is one of `dry_run`, `demo`, `live`.
- `exchange.name` is supported.
- required env vars exist for the selected mode.
- intervals are positive numbers.
- leverage is positive.
- symbols are non-empty and unique.
- order amounts are non-negative.
- risk percentages and thresholds are non-negative.
- trailing thresholds are logically ordered:
  - `low_trail_enable_threshold`
  - `first_trail_enable_threshold`
  - `second_trail_enable_threshold`
- Redis settings are required only when Redis is enabled.
- WebSocket stale-data and reconnect intervals are positive.
- WebSocket reconnect initial delay does not exceed the max delay.

Invalid config must not partially apply.

### Hot Reload Rules

The first implementation supports manual reload only.

Safe hot-reloadable fields:

- symbol enabled/disabled,
- order amount,
- EMA period,
- value multiplier,
- risk/trailing thresholds,
- blacklist,
- runtime intervals,
- notification enabled flag.

Fields that should not be silently hot-reloaded:

- API key or secret env names,
- exchange name,
- account mode,
- database path,
- Redis URL,
- default leverage.

If a reload contains unsafe changes, the reload service returns
`requires_restart`, preserves the active config, records an audit result when
SQLite is available, and requires an explicit safe-restart flow.

Manual reload entry point:

```text
bybit-automation reload --current configs/config.toml --candidate configs/config.new.toml
```

Expected behavior:

- valid and hot-reloadable candidates apply through the reload service,
- invalid candidates return non-zero and preserve the active config,
- unsafe candidates return non-zero with restart-required paths,
- successful manual reloads are recorded in SQLite `config_versions` with
  `reload_reason = "manual"`,
- all reload attempts write `bot_state.last_config_reload` when SQLite is
  available,
- Redis config reload signals are recorded as notification primitives only and
  do not automatically apply config changes.

### Persistence of Loaded Config

Every successfully loaded config should be recorded in SQLite once SQLite is
available.

Suggested table concept:

```text
config_versions
  id
  loaded_at
  source_path
  content_hash
  normalized_json
  applied_by
  reload_reason
```

Purpose:

- make runtime behavior auditable,
- allow trading decisions to be traced to a config version,
- support safe rollback or diagnosis later.

### Internal Representation

Runtime code should not pass raw dictionaries everywhere.

Preferred approach:

- parse TOML into typed config objects,
- validate once,
- produce resolved runtime config,
- pass typed objects to modules.

Use dataclasses or another lightweight typed model first. Avoid adding a large
dependency solely for config unless validation complexity later justifies it.

### WebSocket Synchronization

WebSocket support is a synchronization layer, not an order command path.

Rules:

- REST remains authoritative for startup snapshots, exchange commands, and
  reconciliation repair.
- Public market stream events may update realtime market cache.
- Private order, position, and execution stream events may update realtime
  account cache.
- Stream health must be tracked through heartbeat/recent-message freshness.
- If WebSocket data is stale or unavailable while enabled, strategy entry
  evaluation should fail closed.
- Redis cache entries created from WebSocket events remain rebuildable and are
  not durable trading state.
- A concrete Bybit WebSocket adapter must remain behind explicit mode guards and
  must not enable live trading by default.

### Current Legacy Mapping

The legacy JSON templates map approximately as follows:

- `exchange_config.json.template` -> `[app]`, `[exchange]`,
  `[exchange.bybit]`, `[telegram]`
- `strategy_config.json.template` -> `[runtime]`, `[strategy.defaults]`,
  `[[symbols]]`
- `trailing_config.json.template` -> `[risk]`, `[risk.defaults]`

During migration, keep legacy files as references until the new config path is
working and validated.
