# bybit-automation

Refactor-in-progress Bybit futures trading automation service.

Phase 3 is complete: the project now has a single-process REST-based runtime
foundation with guarded exchange/order abstractions, SQLite persistence, startup
reconciliation against exchange positions/open orders, stale trailing-state
cleanup, `SAFE_MODE` for inconsistent startup state, and basic shutdown state
persistence. Current work is ready to begin Phase 4 Redis cache and
coordination. New runtime code must default to `dry_run` and must not place live
orders by default.

Project layout:

- `src/bybit_automation/`: application package.
- `tests/`: unit tests and fake exchange fixtures.
- `configs/`: new TOML config templates and local runtime config.
- `configs.template/`: legacy JSON templates kept for migration reference.
- `data/`: local SQLite runtime database location, ignored by git.
- `.agents/`: AI agent handoff docs, specs, TODOs, and phase logs.

Agent handoff documents live under `.agents/`.
