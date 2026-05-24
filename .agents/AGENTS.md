# AGENTS.md

This document is the working handoff for AI agents and developers continuing the
refactor of this repository.

## Project Summary

This repository currently contains a small Bybit futures trading bot split into
two independent Python scripts:

- `strategy_bybit.py`
- `trail_bybit.py`

There is also a helper setup script:

- `fast_setup.py`

The current scripts appear to be written as a personal/experimental automated
trading system using `ccxt`, `pandas`, and Telegram notifications.

The user's goal is to gradually refactor this into a more reliable single-process
trading service with:

- `uv` for Python environment and dependency management.
- SQLite for durable state, event history, and recovery.
- Redis for realtime cache, coordination, and short-lived state.
- WebSocket-based synchronization where useful.
- Safer runtime behavior, state recovery, reconciliation, and config reload.

The user has already created a `dev` branch and wants the work to proceed in
small verifiable phases.

## Current Repository State

Observed files:

- `strategy_bybit.py`
- `trail_bybit.py`
- `fast_setup.py`
- `requirements.txt`
- `configs.template/exchange_config.json.template`
- `configs.template/strategy_config.json.template`
- `configs.template/trailing_config.json.template`

Current dependencies from `requirements.txt`:

```text
ccxt==4.4.45
pandas==2.2.3
telebot==0.0.5
```

Environment note from prior inspection:

- The project was inspected from PowerShell on Windows in the original session.
- Shell and Python availability may differ on future machines or sessions.
- Future agents should check the development environment at the start of coding
  work instead of assuming global tools are available.
- The refactor should introduce `uv` early and prefer `uv run ...` for Python
  execution once the project is configured.

## Current Script Behavior

### `strategy_bybit.py`

This script is the entry/order strategy bot.

Observed behavior:

- Loads config files from `./configs`:
  - `exchange_config.json`
  - `strategy_config.json`
  - `trailing_config.json`
- Connects to Bybit through `ccxt.bybit`.
- Optionally enables Bybit demo trading.
- Sets leverage for configured trading pairs.
- Reads `trading_pairs` from config.
- Runs a polling loop on `monitor_interval`.
- For each pair:
  - Fetches current ticker price.
  - Fetches OHLCV candles.
  - Computes EMA trend.
  - Computes ATR.
  - Computes average amplitude.
  - Uses volatility-derived distance to place limit entry orders:
    - If bullish trend, place a buy limit below current price.
    - If bearish trend, place a sell limit above current price.
  - Cancels open orders for the pair before placing new orders.
- Converts configured USDT amount into contract amount using leverage, fee,
  and exchange minimum amount.

Inferred developer intent:

- Automatically keep limit entry orders around a volatility-adjusted price.
- Use EMA as a trend filter.
- Use ATR and average amplitude to choose order distance.
- Manage both long and short opportunities per configured symbol.

### `trail_bybit.py`

This script is the position risk/trailing bot.

Observed behavior:

- Loads the same config files from `./configs`.
- Connects to Bybit through `ccxt.bybit`.
- Initializes Telegram bot using config credentials.
- Runs a frequent polling loop on `monitor_interval`.
- Fetches all positions.
- For each non-zero position:
  - Skips symbols in `blacklist`.
  - Detects new positions and sends Telegram notification.
  - Calculates current profit percentage.
  - Tracks highest seen profit percentage in memory.
  - Assigns a trailing tier based on thresholds:
    - `low_trail_enable_threshold`
    - `first_trail_enable_threshold`
    - `second_trail_enable_threshold`
  - Applies:
    - fixed stop loss,
    - low-tier trailing stop,
    - first-tier trailing stop,
    - second-tier trailing stop.
  - Closes positions using market orders.
  - Sends Telegram messages on detected/closed positions.

Inferred developer intent:

- Let another process/script manage already-open positions.
- Protect positions with stop loss and multi-stage trailing take profit.
- Notify the user when positions are detected or closed.

## Current Architectural Problems

The main issue is not only code style. The runtime model is risky because two
independent processes operate on the same trading account without shared state.

Known or inferred problems:

- `strategy_bybit.py` and `trail_bybit.py` both initialize exchange clients and
  run independently.
- Strategy can cancel and recreate orders while the trailing/risk script is
  managing positions, with no shared state machine.
- There is no central `OrderManager`.
- There is no durable state for:
  - highest profit,
  - active trailing tier,
  - last known position state,
  - order lifecycle,
  - strategy decisions.
- `highest_profits`, `current_tiers`, and detected positions are only in memory.
  They are lost on restart.
- Config is loaded only at startup.
- Config files are merged with `ChainMap`; duplicate keys such as
  `monitor_interval` are ambiguous and can shadow each other.
- Logger setup is duplicated.
- Both scripts contain mojibake/encoding-corrupted Traditional Chinese log
  strings. Some strings may be syntactically unsafe and should be checked once a
  working Python runtime is available.
- REST polling is used for market/account state, which is slower, rate-limited,
  and more vulnerable to network drift than WebSocket streams.
- No explicit safe mode, reconciliation, circuit breaker, or restart recovery.
- Current error handling includes patterns that should be fixed, such as
  recursive retry paths and weak handling of network state.

## Target Product Intent

The intended future system should behave like a single trading service:

```text
market/account sync
  -> strategy decision
  -> order intent
  -> order execution
  -> position tracking
  -> risk/trailing decision
  -> durable event/state storage
  -> notification
```

The service should have one process, one coordinated runtime state, and one path
for all exchange side effects.

Important design principle:

> All exchange side effects, especially placing orders, canceling orders, and
> closing positions, must go through a centralized `OrderManager`.

This prevents conflicting operations between strategy and risk logic.

## Proposed Future Architecture

Suggested package layout:

```text
pyproject.toml
uv.lock
src/
  bybit_automation/
    __init__.py
    main.py
    app.py
    config.py
    logging.py
    exchange_client.py
    notifier.py
    strategy.py
    risk.py
    orders.py
    positions.py
    state.py
    storage/
      sqlite.py
      repositories.py
    cache/
      redis.py
tests/
configs.template/
```

Suggested runtime modules:

- `App` / `BotRuntime`
  - Owns lifecycle and event loop.
- `ConfigLoader`
  - Loads, validates, versions, and reloads config.
- `ExchangeClient`
  - Thin wrapper around Bybit/ccxt operations.
- `MarketDataService`
  - Provides price and OHLCV/K-line data.
- `StrategyEngine`
  - Pure decision logic for entry signals.
- `RiskManager`
  - Pure decision logic for stop loss and trailing take profit.
- `OrderManager`
  - The only module allowed to place/cancel/close exchange orders.
- `PositionManager`
  - Tracks active positions and position state.
- `StateStore`
  - Durable SQLite-backed state and event storage.
- `RealtimeCache`
  - Redis-backed latest prices, locks, and short-lived runtime data.
- `Notifier`
  - Telegram and future notification channels.

Suggested state machine per symbol:

```text
IDLE
  -> ENTRY_ORDER_PLACED
  -> POSITION_OPEN
  -> TRAILING
  -> CLOSING
  -> CLOSED
```

The state machine should protect against contradictory operations such as placing
a new entry while a symbol is closing.

## Tick Definition

Previous discussion clarified that "tick" should mean:

- Program decision tick: one pass of the bot's decision pipeline.

It should not mean:

- Every exchange matching-engine tick.

The existing strategy is not suitable for processing every exchange trade tick.
The current scripts imply slower cadences:

- Strategy loop: roughly minute-level polling.
- Trailing loop: roughly second-level polling.

Future design should separate:

- WebSocket/event ingestion cadence.
- Decision loop cadence.
- Strategy evaluation cadence.
- Risk/trailing evaluation cadence.
- REST reconciliation cadence.

Example target SLAs:

```text
Market data freshness target: under 500ms when WebSocket is healthy.
Risk decision cadence: 250ms to 1s, configurable.
Strategy decision cadence: 30s to 60s, configurable.
REST reconciliation cadence: 10s to 30s, configurable.
```

Do not promise to process every exchange trade tick. Instead, make the cadence
explicit and enforce deadlines.

## SQLite and Redis Responsibilities

### SQLite

SQLite is the durable source for state and history.

Use SQLite for:

- orders
- order events
- trades/executions
- position snapshots
- strategy decisions
- risk events
- bot state
- config versions
- notification logs

Recommended SQLite behavior:

- Enable WAL mode.
- Use transactions for multi-step state updates.
- Prefer append-only event records for important trading events.
- Store enough data to recover after process restart.

### Redis

Redis is a realtime cache and coordination layer, not the durable source of
truth.

Use Redis for:

- latest ticker / mark price
- recent K-line buffers
- active positions cache
- open orders cache
- per-symbol locks
- lightweight pub/sub events
- config reload signal

If Redis restarts, the bot must be able to rebuild cache from SQLite plus the
exchange.

## Data Safety and Recovery

The future service should handle shutdowns, network failures, and restarts
without blindly trading from stale assumptions.

Required behaviors:

- On startup, run reconciliation before strategy trading:
  - fetch open orders from exchange,
  - fetch active positions from exchange,
  - fetch balances if needed,
  - compare exchange state with SQLite last known state.
- If state is inconsistent, enter `SAFE_MODE`.
- In `SAFE_MODE`:
  - pause new entries,
  - allow risk-reducing actions if state is sufficiently known,
  - notify the user,
  - require manual confirmation or successful reconciliation before resuming.
- Use client order IDs where possible to correlate local decisions with exchange
  orders.
- On graceful shutdown:
  - stop creating new order intents,
  - finish or cancel pending internal work safely,
  - flush critical state to SQLite,
  - log final runtime state.

Important principle:

> The system cannot guarantee failures never happen. It should guarantee that
> after a failure it can determine what it knows, what it does not know, and avoid
> making an unsafe second mistake.

## WebSocket Direction

Using WebSocket for synchronization is preferred for market/account state.

Recommended split:

```text
WebSocket:
  - ticker / mark price
  - kline
  - order update
  - position update
  - execution update

REST:
  - initial snapshot
  - create orders
  - cancel orders
  - close positions
  - periodic reconciliation
  - fallback after WebSocket disconnect/reconnect
```

Do not remove REST entirely. WebSocket is the realtime stream; REST remains the
authoritative correction and command path.

Required WebSocket behavior:

- heartbeat/ping monitoring
- automatic reconnect with backoff
- stale-data detection
- message gap/drift recovery through REST reconciliation
- pause strategy if market/account state is stale

## Config Reload Direction

The current scripts load config only during initialization. Future versions
should support controlled config reload.

The canonical target config structure is defined in `SPEC.md`. Future agents
should not invent a different config shape without updating `SPEC.md` and
explaining the reason.

Recommended first implementation:

- Manual reload command.
- Validate full config before applying.
- Compute and log config diff.
- Apply only safe hot-reloadable fields.
- Store config version in SQLite.
- If validation fails, keep the existing config.

Potential hot-reloadable fields:

- trading pair enabled/disabled
- order amount
- EMA period
- value multiplier
- trailing thresholds
- blacklist
- monitor intervals
- notification toggles

Fields that should not be casually hot-reloaded:

- API key / secret
- exchange type
- account mode
- database path
- Redis connection
- leverage, unless a safe explicit flow is implemented

Potential reload mechanisms:

- CLI/admin command
- Telegram command
- file modification watcher
- Redis pub/sub signal

Start with manual reload. Add automation only after validation and safe behavior
are solid.

## Phased Refactor Plan

Each phase should be independently testable before moving to the next one.

### Phase 0: Project Foundation with `uv`

Goal:

- Establish a modern Python project skeleton without changing trading behavior.

Tasks:

- Add `pyproject.toml`.
- Generate `uv.lock`.
- Move toward `src/bybit_automation/` package layout.
- Add CLI entry point.
- Keep legacy scripts available for reference.
- Add baseline test/lint tooling.

Suggested commands:

```bash
uv sync
uv run python -m bybit_automation
uv run pytest
```

Acceptance criteria:

- `uv sync` succeeds.
- The new package imports.
- A no-op/new runtime entry point starts.
- Legacy scripts remain untouched unless intentionally migrated.

### Phase 1: Single-Process Runtime, REST-Based

Goal:

- Merge the two runtime processes into one coordinated process while still using
  REST polling.

Tasks:

- Create `App` / `BotRuntime`.
- Add unified config loading.
- Add unified logger.
- Extract:
  - `ExchangeClient`
  - `StrategyEngine`
  - `RiskManager`
  - `OrderManager`
  - `PositionManager`
  - `Notifier`
- Share one runtime state between entry strategy and trailing risk logic.

Acceptance criteria:

- One process can run both entry and risk logic.
- Strategy and risk do not directly conflict.
- All exchange side effects go through `OrderManager`.
- Demo mode can start and perform read-only sync.

### Phase 2: SQLite Persistence

Goal:

- Persist bot state and event history.

Tasks:

- Add SQLite schema and migrations or schema bootstrap.
- Enable WAL mode.
- Store orders, order events, position snapshots, strategy decisions, risk events,
  config versions, and bot state.
- Persist trailing state such as highest profit and current tier.

Acceptance criteria:

- Bot creates a SQLite database.
- Important decisions/events are written.
- Restart does not lose trailing state.
- SQLite state can be inspected manually.

### Phase 3: Safe Startup and Reconciliation

Goal:

- Make startup and restart safe.

Tasks:

- Fetch open orders and active positions on startup.
- Compare exchange state with SQLite state.
- Implement `SAFE_MODE`.
- Add graceful shutdown.

Acceptance criteria:

- Startup always reconciles before new entries.
- Inconsistent state pauses new entries.
- Ctrl+C/SIGTERM saves state and exits cleanly.

### Phase 4: Redis Cache and Coordination

Goal:

- Add Redis for realtime data and lightweight coordination.

Tasks:

- Add `RealtimeCache` abstraction.
- Store latest prices, K-line buffers, open orders cache, active positions cache,
  symbol locks, and config reload signals.
- Define behavior when Redis is unavailable.

Acceptance criteria:

- Bot can use Redis when available.
- Redis failure does not corrupt durable state.
- Cache can be rebuilt from SQLite plus exchange.

### Phase 5: WebSocket Synchronization

Goal:

- Reduce REST polling and improve timeliness.

Tasks:

- Add public WebSocket streams for ticker/mark price/K-line.
- Add private WebSocket streams for order/position/execution updates.
- Keep REST for commands and reconciliation.
- Add heartbeat, reconnect, stale-data detection.

Acceptance criteria:

- Market/account state updates through WebSocket.
- REST polling load is reduced.
- WebSocket disconnect pauses or degrades safely.
- REST reconciliation repairs drift.

### Phase 6: Config Hot Reload

Goal:

- Allow safe config changes without full restart.

Tasks:

- Add config schema validation.
- Add manual reload entry.
- Store config versions.
- Apply only safe hot-reloadable fields.

Acceptance criteria:

- Valid reload applies safely.
- Invalid reload is rejected without altering runtime config.
- Reload is logged and optionally notified.

### Phase 7: Operational Stability

Goal:

- Make the service more production-like.

Tasks:

- Add structured logging.
- Add health checks.
- Add notification severity.
- Add retry/backoff.
- Add circuit breakers.
- Add dry-run mode.
- Add deployment helpers if needed.

Acceptance criteria:

- Long-running demo mode is stable.
- Failures are observable and classified.
- Exchange/API/Redis/DB issues trigger known behavior.

## Testing Strategy

Start with tests that do not require live exchange access.

Recommended early tests:

- Config parsing and validation.
- EMA/ATR/amplitude calculations.
- Strategy decision logic.
- Risk/trailing decision logic.
- Position state transitions.
- SQLite repository persistence.
- Reconciliation behavior using fake exchange data.

Use fake exchange clients for unit tests. Do not require Bybit credentials for
CI or normal local test runs.

## Implementation Notes for Future Agents

- Use Traditional Chinese for user-facing explanations unless the user asks
  otherwise.
- Keep changes phased and reviewable.
- Do not rewrite the whole system in one step.
- Do not remove legacy scripts until the new implementation reaches feature
  parity or the user explicitly approves removal.
- Use `uv` for all Python environment work.
- Prefer `rg`/`rg --files` for repository inspection.
- Before changing trading behavior, identify whether the change affects:
  - order placement,
  - order cancellation,
  - position closing,
  - stop loss,
  - trailing take profit.
- Treat all live trading side effects as high risk.
- Default to demo/dry-run behavior during refactor and tests.
- Add tests before or alongside extraction of pure logic.
- If introducing Redis or SQLite, keep abstractions thin and testable.
- Preserve user changes in the git worktree. Do not revert unrelated changes.

## Project and Conversation Constraints

Future agents should follow these constraints unless the user explicitly changes
direction.

### Communication Style

- Communicate with the user in Traditional Chinese by default.
- Keep explanations concise but technically precise.
- When discussing architecture, separate:
  - confirmed facts from the repository,
  - inferences about developer intent,
  - proposed future design.
- Do not present assumptions as facts.
- If a decision affects live trading behavior, clearly call out the risk before
  implementing it.
- Prefer short progress updates while working instead of waiting until the end of
  a long task.
- When a task is exploratory, summarize findings before proposing code changes.

### Coding Style

- Prefer simple, explicit Python over clever abstractions.
- Keep modules small and focused on one responsibility.
- Favor dataclasses or typed models for runtime state and decisions.
- Add type hints for new code.
- Prefer pure functions for strategy and risk calculations so they can be tested
  without live exchange access.
- Keep exchange side effects isolated behind `ExchangeClient` and
  `OrderManager`.
- Do not let strategy or risk modules call `ccxt` directly.
- Do not let persistence or cache implementation details leak into strategy
  logic.
- Avoid broad rewrites unless the current phase requires them.
- Keep comments short and useful; avoid restating obvious code behavior.

### Refactor Boundaries

- Preserve legacy scripts during early phases:
  - `strategy_bybit.py`
  - `trail_bybit.py`
  - `fast_setup.py`
- Do not delete or rename legacy files until the user approves or the replacement
  reaches feature parity.
- Make incremental commits/changes that map to the agreed phases.
- Do not introduce WebSocket, Redis, SQLite, config reload, and strategy changes
  all in the same step.
- Every phase should leave the project in a runnable or at least importable
  state.
- Before moving to the next phase, verify the current phase with local commands
  when tooling is available.

### Trading Safety Rules

- Default to demo or dry-run behavior for new runtime code.
- Never add code that places live orders by default.
- Any live trading path must require explicit config.
- Any module that can place, cancel, or close orders must be easy to audit.
- New order-related code should support idempotency where possible.
- Avoid blind retries for order placement. Retry behavior must consider whether
  the exchange may have accepted the previous request.
- On unknown or inconsistent exchange state, prefer `SAFE_MODE` over continuing
  normal strategy execution.
- Do not rely on Redis as the only record of trading state.
- SQLite should be treated as the durable local record, while exchange state
  remains the external authority that must be reconciled.

### Testing and Verification Requirements

- New pure strategy/risk logic should include unit tests.
- Tests must not require real Bybit credentials.
- Use fake exchange clients or fixtures for order, position, and reconciliation
  behavior.
- When changing config loading, test invalid config and missing-field behavior.
- When changing persistence, test restart/recovery behavior where practical.
- When changing order flow, test state transitions and duplicate-operation
  prevention.
- If a command cannot be run because tooling is missing, state that clearly in
  the final response.

### Dependency and Tooling Rules

- Use `uv` for Python dependency and environment management.
- On this Windows workspace, prefer project-local `uv` runtime/cache locations
  before running `uv run` commands:
  - PowerShell:
    `$env:UV_CACHE_DIR='.uv-cache'; $env:UV_PYTHON_INSTALL_DIR='.uv-python'`
  - Then run commands such as:
    `uv sync`, `uv run pytest`, `uv run ruff check .`, and
    `uv run bybit-automation`.
- Rationale: previous sessions saw `uv run` fail when using global paths such as
  `C:\Users\User\AppData\Local\uv\cache` or
  `C:\Users\User\AppData\Roaming\uv\python` because of local filesystem or
  permission issues. Keeping cache and managed Python installs inside the
  workspace avoids that startup friction.
- If `.venv` points to a missing Python interpreter, let `uv` recreate it after
  setting `UV_CACHE_DIR` and `UV_PYTHON_INSTALL_DIR`.
- At the start of coding work in a new session or on a new machine, inspect the
  development environment before making assumptions. Check at least:
  - current shell and OS,
  - current git branch and worktree status,
  - whether `uv` is installed,
  - whether a usable Python runtime is available through `uv` or the shell,
  - whether required external services for the current phase are available
    (for example Redis only when working on the Redis phase).
- If the environment is incomplete, explain the issue and propose a concrete
  fix before continuing with changes that depend on it.
- Prefer adding dependencies through `uv add` once `pyproject.toml` exists.
- Avoid adding heavy dependencies unless they solve a clear problem.
- Keep SQLite access simple at first. Do not introduce a large ORM unless the
  schema complexity later justifies it.
- Add Redis behind an abstraction so tests can run without a Redis server.
- Do not require Docker or external services for basic unit tests.

### Documentation Rules

- Update this `AGENTS.md` when project direction, phases, safety rules, or
  operating assumptions change.
- Update `SPEC.md` when project-level technical specifications change,
  especially config shape, runtime state semantics, persistence rules, and
  safety behavior.
- Update `TODO.md` whenever work is completed, newly discovered, blocked, or
  made obsolete. Finished work should not be left as unchecked TODO items.
- Keep user-facing documentation aligned with actual runnable commands.
- Do not document planned commands as working commands until they have been
  implemented or clearly label them as planned.
- If new architecture decisions are made, record the reason, not only the final
  choice.

### Version Control Workflow

The `dev` branch is the standard working branch for agents. The user will decide
when to merge `dev` into `main`.

Future agents must use this standard Git workflow unless the user explicitly
changes it:

1. Start by checking the current branch and worktree:
   - `git branch --show-current`
   - `git status --short`
2. Work only on `dev` unless the user approves another branch.
3. Before editing, identify whether there are existing uncommitted changes.
   Preserve user changes and do not revert unrelated files.
4. Make a small, coherent change set tied to the current phase or task.
5. Update `.agents/TODO.md` in the same change set whenever task status changes.
6. Update the active phase log, such as `.agents/phase1.log`, with:
   - work completed,
   - verification performed,
   - issues encountered,
   - how issues were resolved,
   - known remaining work or blockers.
7. Run relevant verification before committing. For this Python project, the
   default verification is:
   - `uv run pytest`
   - `uv run ruff check .`
   - CLI smoke test when runtime behavior changed:
     `uv run bybit-automation`
8. Stage only intentional files.
9. Commit with a concise conventional-style message, for example:
   - `chore: bootstrap phase 0 project foundation`
   - `feat: add dry-run runtime skeleton`
   - `docs: define agent git workflow`
10. Push successful commits to `origin/dev`.
11. End with a clean worktree unless the user explicitly asks to leave changes
    uncommitted.

If verification cannot run because of environment problems, record the issue in
the active phase log and final response. Do not claim a verification passed when
it did not run.

### Shared TODO Rules

- `.agents/TODO.md` is the canonical cross-agent task list.
- Use standard Markdown checkboxes so the file remains portable across tools.
- Every coding or documentation task should leave `TODO.md` accurate before the
  agent finishes its turn.
- If a future agent changes phase scope, adds a blocker, or completes a task, it
  must update `TODO.md` in the same change set.
- Do not use tool-specific task formats as the only source of truth.

## Phase 2 Implementation Slices

Recommended order for SQLite persistence work:

1. Storage foundation:
   - add `src/bybit_automation/storage/`,
   - create a thin SQLite connection/bootstrap module,
   - create parent directories for the configured database path,
   - enable WAL mode when `[database.sqlite].wal = true`,
   - keep using the standard library `sqlite3` first.
2. Schema bootstrap:
   - add idempotent schema creation,
   - include tables for orders, order events, position snapshots, strategy
     decisions, risk events, bot state, config versions, and per-symbol trailing
     state,
   - store timestamps as ISO-8601 UTC text or another documented consistent
     format.
3. Repository layer:
   - add small repositories instead of exposing raw SQL throughout the runtime,
   - start with append/read helpers for order events, strategy decisions, risk
     events, position snapshots, and trailing state,
   - use explicit transactions for multi-row updates.
4. Runtime integration:
   - persist strategy decisions and risk decisions after each runtime tick,
   - persist order results after `OrderManager` returns,
   - persist position snapshots after `PositionManager` syncs,
   - save and restore trailing state such as highest profit and current tier.
5. Config version recording:
   - compute a stable hash of successfully loaded config content,
   - store source path, normalized content, loaded time, and reload reason,
   - do not implement hot reload yet; only record successful startup/load.
6. Tests and verification:
   - use temporary SQLite database files in tests,
   - verify WAL mode,
   - verify schema bootstrap is idempotent,
   - verify repository writes survive closing and reopening the connection,
   - keep all tests offline and free of Bybit credentials.

Avoid adding reconciliation or `SAFE_MODE` behavior in Phase 2 unless it is
strictly needed to prove persistence; those belong to Phase 3.

## Immediate Next Recommended Step

Start Phase 2:

1. Add a thin SQLite connection/bootstrap module.
2. Enable WAL mode based on `[database.sqlite].wal`.
3. Add schema bootstrap for orders, order events, position snapshots, strategy
   decisions, risk events, bot state, config versions, and trailing state.
4. Add repository tests using temporary SQLite databases.
5. Keep runtime behavior in `dry_run` unless the user explicitly approves demo
   or live exchange checks.
