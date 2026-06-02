# bybit-automation

A safety-first Bybit futures trading automation runtime.

This project refactors a pair of legacy Bybit strategy and trailing-stop scripts
into a single coordinated Python service with durable state, startup
reconciliation, guarded order execution, realtime cache foundations, manual
config reloads, and local operational checks.

The default runtime mode is `dry_run`. It does not connect to Bybit and does not
place live orders unless you explicitly configure a non-dry-run mode with
credentials.

## Features

- Single-process runtime for strategy, risk, positions, and orders.
- Centralized `OrderManager` for all exchange side effects.
- Typed config loading from TOML.
- SQLite persistence for orders, order events, positions, strategy decisions,
  risk events, bot state, and config versions.
- Startup reconciliation against exchange positions and open orders.
- `SAFE_MODE` behavior for inconsistent or unknown exchange state.
- Redis-backed realtime cache abstraction with no-op fallback.
- WebSocket synchronization foundation for market and account events.
- Manual config reload with safe/unsafe change classification.
- Operational health checks for SQLite, Redis, WebSocket, and exchange
  readiness.
- Typed operational events, notification severities, retry/backoff policies,
  circuit breaker primitives, and dry-run verification.

## Project Layout

```text
src/bybit_automation/     Application package
tests/                    Unit tests and fake exchange fixtures
configs/                  TOML config template
configs.template/         Legacy JSON templates kept for reference
data/                     Local SQLite runtime data, ignored by git
.agents/                  Agent handoff docs, specs, TODOs, and phase logs
```

## Installation

Install `uv`, then sync the project:

```bash
uv sync --locked
```

If your machine has cache or managed-Python permission issues, use project-local
runtime directories:

```bash
# macOS / Linux
export UV_CACHE_DIR=.uv-cache
export UV_PYTHON_INSTALL_DIR=.uv-python

# Windows PowerShell
$env:UV_CACHE_DIR='.uv-cache'
$env:UV_PYTHON_INSTALL_DIR='.uv-python'
```

Then verify the environment:

```bash
uv run python --version
uv run pytest
uv run ruff check .
```

## Configuration

The committed template config is:

```text
configs/config.template.toml
```

For local runtime use, create your own config file, for example:

```text
configs/config.toml
```

Keep secrets out of config files. The config stores environment variable names
such as `BYBIT_API_KEY`, `BYBIT_API_SECRET`, `REDIS_URL`,
`TELEGRAM_BOT_TOKEN`, and `TELEGRAM_CHAT_ID`.

The default template uses:

```toml
[app]
mode = "dry_run"
```

`dry_run` is the safe development mode. Demo/live modes require explicit config
and credentials.

## Usage

Run one safe runtime tick with the template config:

```bash
uv run bybit-automation
```

Run with an explicit config:

```bash
uv run bybit-automation run --config configs/config.toml
```

Run the local no-network dry-run verification flow:

```bash
uv run bybit-automation verify-dry-run --config configs/config.template.toml
```

Validate and apply a manual config reload candidate:

```bash
uv run bybit-automation reload \
  --current configs/config.toml \
  --candidate configs/config.new.toml
```

Manual reloads apply only hot-reloadable changes. Unsafe changes return a
restart-required result and preserve the active config.

## Safety Model

The runtime is designed to fail closed.

On startup, it reconciles exchange positions and open orders against local
SQLite state. If reconciliation finds an unsafe mismatch, the runtime enters
`SAFE_MODE`.

In `SAFE_MODE`:

- new strategy entries are paused,
- risk evaluation can still run for known positions,
- order side effects still go through `OrderManager`,
- the latest reconciliation and tick state are recorded in SQLite `bot_state`.

Common `SAFE_MODE` triggers include:

- an exchange open order that is not known in local SQLite state,
- failure to fetch the exchange startup snapshot,
- other reconciliation issues marked as `safe_mode`.

To clear `SAFE_MODE`, resolve the underlying mismatch first, then restart the
runtime so startup reconciliation can run again. Examples include canceling or
recording unknown exchange orders, restoring network/API access, or fixing local
state after manual review. There is intentionally no blind "clear safe mode"
command.

## Edge Case Handling

The codebase handles important failure cases conservatively:

- Missing or invalid config fails before runtime execution.
- Invalid manual reload candidates do not replace the active config.
- Unsafe reload changes require a safe restart.
- Missing Redis degrades to a no-op realtime cache.
- Redis data is never treated as durable trading state.
- Startup exchange snapshot failures trigger `SAFE_MODE`.
- Stale WebSocket market data pauses strategy entries.
- SQLite stores durable state for restart inspection and recovery.
- Retry/backoff and circuit breaker primitives are available, but order
  placement is not blindly retried because exchange acceptance can be ambiguous.

## Development

Run tests:

```bash
uv run pytest
```

Run lint:

```bash
uv run ruff check .
```

Run the dry-run smoke command:

```bash
uv run bybit-automation
```

## Current Status

The local refactor foundation is complete through Phase 7:

- project foundation,
- single-process REST runtime,
- SQLite persistence,
- startup reconciliation and `SAFE_MODE`,
- Redis cache and coordination foundation,
- WebSocket synchronization foundation,
- manual config reload foundation,
- operational stability foundation.

The next recommended stage is Demo Validation / Release Candidate:

1. run local dry-run verification,
2. add and run Bybit demo read-only preflight with explicit approval,
3. run demo shadow mode,
4. only then plan tiny demo order lifecycle tests.
