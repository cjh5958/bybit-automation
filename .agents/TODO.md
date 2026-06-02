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
- [x] Rename package and CLI to `bybit_automation` / `bybit-automation`.
- [x] Complete Phase 1 single-process REST-based runtime foundation.
- [x] Complete Phase 2 SQLite persistence foundation.
- [x] Define cross-platform minimum development environment and rebuild steps.
- [x] Complete Phase 3 safe startup and reconciliation foundation.
- [x] Complete Phase 4 Redis cache and coordination foundation.
- [x] Complete Phase 5 WebSocket synchronization foundation.

## Pre-Phase 3: Development Environment Standardization

- [x] Document the minimum supported development environment in `.agents/AGENTS.md`.
- [x] Document a fresh-checkout environment rebuild flow using `uv`.
- [x] Record that project commands must run through `uv run`.
- [x] Verify the rebuilt environment on the current machine.

## Phase 0: Project Foundation with `uv`

- [x] Inspect current development environment at session start.
- [x] Confirm current git branch is `dev` or the user-approved working branch.
- [x] Add `pyproject.toml`.
- [x] Add `uv.lock`.
- [x] Add `src/bybit_automation/` package skeleton.
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
- [x] Add concrete REST/ccxt exchange client behind explicit mode guards.
- [x] Wire demo/live order execution through `OrderManager`.
- [x] Migrate legacy order sizing and tick-size rounding into testable helpers.
- [x] Review Phase 1 before Phase 2 and wire strategy entry intents through `OrderManager`.
- [x] Add single-process loop scheduling for different strategy/risk cadences.
- [x] Add tests for REST exchange client using fakes/mocks, not live Bybit.

## Phase 2: SQLite Persistence

- [x] Add SQLite connection/bootstrap module.
- [x] Enable WAL mode.
- [x] Add schema for orders and order events.
- [x] Add schema for position snapshots.
- [x] Add schema for strategy decisions and risk events.
- [x] Add schema for bot state and config versions.
- [x] Persist trailing state such as highest profit and current tier.
- [x] Add repository tests using temporary SQLite databases.

## Phase 3: Safe Startup and Reconciliation

- [x] Fetch open orders on startup.
- [x] Fetch active positions on startup.
- [x] Compare exchange state with SQLite state.
- [x] Clear stale trailing state for confirmed closed positions.
- [x] Prevent new positions from inheriting stale trailing state.
- [x] Implement `SAFE_MODE`.
- [x] Pause new entries when startup state is inconsistent.
- [x] Add graceful shutdown behavior.
- [x] Add tests for reconciliation and safe-mode transitions.

## Phase 4: Redis Cache and Coordination

- [x] Add Redis cache abstraction.
- [x] Cache latest prices and recent K-line data.
- [x] Cache active positions and open orders.
- [x] Add per-symbol lock semantics.
- [x] Add config reload signal mechanism.
- [x] Define and test Redis unavailable behavior.

## Phase 5: WebSocket Synchronization

- [x] Add WebSocket stream event types and stream abstraction.
- [x] Add public market WebSocket ingestion.
- [x] Add private order/position/execution WebSocket ingestion.
- [x] Add heartbeat monitoring.
- [x] Add reconnect with backoff.
- [x] Add stale-data detection.
- [x] Keep REST reconciliation as authoritative correction path.

## Phase 6: Config Hot Reload

- [x] Add config schema validation.
- [ ] Add manual reload entry point.
- [x] Store successful config versions in SQLite.
- [x] Reject invalid config without changing runtime config.
- [x] Reject or require safe restart for unsafe config changes.
- [x] Add tests for valid, invalid, and unsafe reloads.

## Phase 7: Operational Stability

- [ ] Add structured logs or clearly typed log events.
- [ ] Add health checks.
- [ ] Add notification severity levels.
- [ ] Add retry/backoff policies.
- [ ] Add circuit breakers for repeated failures.
- [ ] Add dry-run verification flow.
- [ ] Add deployment notes or helpers when runtime shape is stable.
