# bybit-automation

Refactor-in-progress Bybit futures trading automation service.

The current work is in Phase 1: a single-process dry-run runtime skeleton with
guarded exchange and order abstractions. New runtime code must default to
`dry_run` and must not place live orders by default.

Project layout:

- `src/bybit_automation/`: application package.
- `tests/`: unit tests and fake exchange fixtures.
- `configs/`: new TOML config templates and local runtime config.
- `configs.template/`: legacy JSON templates kept for migration reference.
- `.agents/`: AI agent handoff docs, specs, TODOs, and phase logs.

Agent handoff documents live under `.agents/`.
