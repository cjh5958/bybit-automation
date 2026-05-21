# TODO.md

This is the shared project TODO list for humans and AI agents.

Rules:

- Use standard Markdown checkboxes only: `- [ ]`, `- [x]`.
- Keep tasks short and action-oriented.
- Add new tasks under the relevant phase.
- When completing work, update this file in the same change set.
- If a task becomes obsolete, mark it complete and add a short note instead of
  silently deleting it.
- If a task is blocked, add `Blocked:` with the reason.

## Current Status

- [x] Analyze legacy scripts and infer project intent.
- [x] Define target phased refactor plan.
- [x] Document agent handoff rules in `.agents/AGENTS.md`.
- [x] Document config specification in `.agents/SPEC.md`.
- [x] Move agent-facing documentation under `.agents/`.
- [x] Create shared agent TODO list.
- [x] Complete Phase 0 project foundation with `uv`.
- [x] Complete first Phase 1 runtime skeleton slice.
- [x] Define standard Git workflow for future agents.

## Phase 0: Project Foundation with `uv`

- [x] Inspect current development environment at session start.
- [x] Confirm current git branch is `dev` or the user-approved working branch.
- [x] Add `pyproject.toml`.
- [x] Add `uv.lock`.
- [x] Add `src/bybit_stream_bot/` package skeleton.
- [x] Add a safe no-op CLI entry point.
- [x] Add `configs/config.template.toml` based on `.agents/SPEC.md`.
- [x] Add baseline tests that do not require Bybit credentials.
- [x] Add or update `.gitignore` entries for local config, SQLite data, caches,
  and virtual environments.
- [x] Verify `uv sync`.
- [x] Verify package import or CLI startup through `uv run`.
- [x] Verify test command through `uv run pytest`.

## Phase 1: Single-Process Runtime, REST-Based

- [x] Create `App` or `BotRuntime` lifecycle.
- [x] Add unified config loading.
- [x] Add unified logging setup.
- [x] Extract an `ExchangeClient` abstraction.
- [x] Extract pure `StrategyEngine` decision logic.
- [x] Extract pure `RiskManager` decision logic.
- [x] Add centralized `OrderManager`.
- [x] Add `PositionManager` and per-symbol runtime state.
- [x] Ensure strategy and risk logic share one runtime state.
- [x] Verify all exchange side effects flow through `OrderManager`.
- [ ] Add concrete REST/ccxt exchange client behind explicit mode guards.
- [ ] Wire demo/live order execution through `OrderManager`.
- [x] Migrate legacy order sizing and tick-size rounding into testable helpers.
- [ ] Add single-process loop scheduling for different strategy/risk cadences.
- [ ] Add tests for REST exchange client using fakes/mocks, not live Bybit.

## Phase 2: SQLite Persistence

- [ ] Add SQLite connection/bootstrap module.
- [ ] Enable WAL mode.
- [ ] Add schema for orders and order events.
- [ ] Add schema for position snapshots.
- [ ] Add schema for strategy decisions and risk events.
- [ ] Add schema for bot state and config versions.
- [ ] Persist trailing state such as highest profit and current tier.
- [ ] Add repository tests using temporary SQLite databases.

## Phase 3: Safe Startup and Reconciliation

- [ ] Fetch open orders on startup.
- [ ] Fetch active positions on startup.
- [ ] Compare exchange state with SQLite state.
- [ ] Implement `SAFE_MODE`.
- [ ] Pause new entries when startup state is inconsistent.
- [ ] Add graceful shutdown behavior.
- [ ] Add tests for reconciliation and safe-mode transitions.

## Phase 4: Redis Cache and Coordination

- [ ] Add Redis cache abstraction.
- [ ] Cache latest prices and recent K-line data.
- [ ] Cache active positions and open orders.
- [ ] Add per-symbol lock semantics.
- [ ] Add config reload signal mechanism.
- [ ] Define and test Redis unavailable behavior.

## Phase 5: WebSocket Synchronization

- [ ] Add public market WebSocket ingestion.
- [ ] Add private order/position/execution WebSocket ingestion.
- [ ] Add heartbeat monitoring.
- [ ] Add reconnect with backoff.
- [ ] Add stale-data detection.
- [ ] Keep REST reconciliation as authoritative correction path.

## Phase 6: Config Hot Reload

- [ ] Add config schema validation.
- [ ] Add manual reload entry point.
- [ ] Store successful config versions in SQLite.
- [ ] Reject invalid config without changing runtime config.
- [ ] Reject or require safe restart for unsafe config changes.
- [ ] Add tests for valid, invalid, and unsafe reloads.

## Phase 7: Operational Stability

- [ ] Add structured logs or clearly typed log events.
- [ ] Add health checks.
- [ ] Add notification severity levels.
- [ ] Add retry/backoff policies.
- [ ] Add circuit breakers for repeated failures.
- [ ] Add dry-run verification flow.
- [ ] Add deployment notes or helpers when runtime shape is stable.
