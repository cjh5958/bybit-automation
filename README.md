# bybit-automation

A safety-first Bybit futures trading automation runtime for strategy entry,
position risk management, durable state, and operational checks.

The default mode is `dry_run`. In `dry_run`, the program does not connect to
Bybit and does not place orders. Demo or live trading must be enabled explicitly
in your local config and requires API credentials from environment variables.

## Features

- Single-process runtime for strategy, risk, positions, and orders.
- Centralized `OrderManager` for placing, canceling, and closing orders.
- TOML configuration with environment-variable based secrets.
- SQLite persistence for orders, order events, positions, decisions, bot state,
  and config versions.
- Startup reconciliation and `SAFE_MODE` for unknown or inconsistent exchange
  state.
- Optional Redis realtime cache with no-op fallback.
- WebSocket event ingestion foundation and stale market-data guard.
- Manual config reload with safe and restart-required change classification.
- Health checks, typed operational events, notification severities,
  retry/backoff policies, circuit breaker primitives, and dry-run verification.

## Requirements

- Git
- `uv`
- Python 3.11 or newer managed by `uv`

Install dependencies:

```bash
uv sync --locked
```

If your machine has uv cache or managed-Python permission issues, use
project-local runtime directories:

```bash
# macOS / Linux
export UV_CACHE_DIR=.uv-cache
export UV_PYTHON_INSTALL_DIR=.uv-python

# Windows PowerShell
$env:UV_CACHE_DIR='.uv-cache'
$env:UV_PYTHON_INSTALL_DIR='.uv-python'
```

## Configuration

Start from the committed template:

```bash
cp configs/config.template.toml configs/config.toml
```

Windows PowerShell:

```powershell
Copy-Item configs\config.template.toml configs\config.toml
```

Edit `configs/config.toml`.

### Runtime Mode

Use `dry_run` for local checks:

```toml
[app]
mode = "dry_run"
```

Use `demo` for Bybit demo trading:

```toml
[app]
mode = "demo"
```

Do not use `live` until you have completed demo validation and reviewed the
config carefully.

### API Credentials

The config stores environment variable names, not secret values:

```toml
[exchange.bybit]
api_key_env = "BYBIT_API_KEY"
api_secret_env = "BYBIT_API_SECRET"
```

Set the actual credentials in your shell.

PowerShell:

```powershell
$env:BYBIT_API_KEY="your-demo-api-key"
$env:BYBIT_API_SECRET="your-demo-api-secret"
```

macOS / Linux:

```bash
export BYBIT_API_KEY="your-demo-api-key"
export BYBIT_API_SECRET="your-demo-api-secret"
```

Never commit API keys or secrets.

Alternatively, copy `.env.example` to `.env` and set local values there:

```bash
cp .env.example .env
```

The CLI loads `.env` from the project root by default and does not override
environment variables already set by your shell. To use a different file:

```bash
uv run bybit-automation run --config configs/config.toml --env-file configs/demo.env
```

### Symbols

Configure the symbols you want to monitor:

```toml
[[symbols]]
symbol = "BTC/USDT:USDT"
enabled = true
long_amount_usdt = 5
short_amount_usdt = 5
```

For initial demo testing, use one highly liquid symbol such as
`BTC/USDT:USDT`. If ccxt reports `BadSymbol`, remove that symbol from the config
or replace it with a market supported by your Bybit environment.

### Strategy Amounts

For read-only style demo observation, set order amounts to `0`:

```toml
long_amount_usdt = 0
short_amount_usdt = 0
```

When you are ready to test demo order flow, use a small demo amount.

### Optional Services

Redis is optional:

```toml
[cache.redis]
enabled = false
```

WebSocket support is currently a synchronization foundation. Keep it disabled
unless you are actively testing that layer:

```toml
[websocket]
enabled = false
```

## Usage

Run a single runtime tick for testing:

```bash
uv run bybit-automation test --config configs/config.toml
```

Run the long-running service:

```bash
uv run bybit-automation run --config configs/config.toml
```

Stop the service with `Ctrl+C`. The shutdown reason is recorded in SQLite
`bot_state`. In service mode, shutdown also best-effort cancels open orders for
enabled symbols in the active config and records the cleanup result in
`bot_state.shutdown_cleanup`.

Run a local no-network dry-run verification:

```bash
uv run bybit-automation verify-dry-run --config configs/config.template.toml
```

Validate and apply a manual config reload candidate:

```bash
uv run bybit-automation reload \
  --current configs/config.toml \
  --candidate configs/config.new.toml
```

Manual reload applies only hot-reloadable changes. Unsafe changes return a
restart-required result and preserve the active config.

## SAFE_MODE

The runtime reconciles exchange positions and open orders against SQLite state
on startup. If the exchange state is unknown or inconsistent, the runtime enters
`SAFE_MODE`.

In `SAFE_MODE`:

- new strategy entries are paused,
- risk evaluation can still run for known positions,
- exchange side effects still go through `OrderManager`,
- reconciliation and tick state are recorded in SQLite `bot_state`.

Common triggers:

- exchange open order unknown to local SQLite state,
- failure to fetch startup exchange snapshots,
- reconciliation issues marked as `safe_mode`.

To clear `SAFE_MODE`, fix the underlying mismatch first, then restart the
runtime so startup reconciliation can pass. There is no blind clear command.

## Inspecting Runtime State

The default SQLite database path is:

```text
data/bot.sqlite3
```

Inspect bot state:

```bash
uv run python -c "import sqlite3; conn=sqlite3.connect('data/bot.sqlite3'); print(conn.execute('select key,value_json from bot_state').fetchall()); conn.close()"
```

Inspect decision and order counts:

```bash
uv run python -c "import sqlite3; conn=sqlite3.connect('data/bot.sqlite3'); print('strategy_decisions', conn.execute('select count(*) from strategy_decisions').fetchone()[0]); print('orders', conn.execute('select count(*) from orders').fetchone()[0]); print('order_events', conn.execute('select count(*) from order_events').fetchone()[0]); conn.close()"
```

## Development

Run tests:

```bash
uv run pytest
```

Run lint:

```bash
uv run ruff check .
```

Run a safe one-tick test with the template config:

```bash
uv run bybit-automation test --config configs/config.template.toml
```

## Status

The runtime currently supports local dry-run operation, Bybit demo REST runtime
testing, SQLite persistence, manual reload checks, health reporting, and
operational safety primitives.

Recommended next steps before live trading:

1. run `verify-dry-run`,
2. run demo mode with a single supported symbol,
3. inspect SQLite state and Bybit demo open orders,
4. run a longer demo service session,
5. only then plan carefully controlled demo order lifecycle tests.
