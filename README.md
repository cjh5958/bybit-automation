# bybit-automation

Refactor-in-progress Bybit futures trading automation service.

Phase 4 is complete: the project now has a single-process REST-based runtime
foundation with guarded exchange/order abstractions, SQLite persistence, startup
reconciliation, `SAFE_MODE`, basic shutdown state persistence, and optional Redis
cache/coordination behind a no-op-safe abstraction. Current work is ready to
begin Phase 5 WebSocket synchronization. New runtime code must default to
`dry_run` and must not place live orders by default.

Project layout:

- `src/bybit_automation/`: application package.
- `tests/`: unit tests and fake exchange fixtures.
- `configs/`: new TOML config templates and local runtime config.
- `configs.template/`: legacy JSON templates kept for migration reference.
- `data/`: local SQLite runtime database location, ignored by git.
- `.agents/`: AI agent handoff docs, specs, TODOs, and phase logs.

Agent handoff documents live under `.agents/`.
