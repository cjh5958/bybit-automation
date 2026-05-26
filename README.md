# bybit-automation

Refactor-in-progress Bybit futures trading automation service.

Phase 2 is complete: the project now has a single-process REST-based runtime
foundation with guarded exchange/order abstractions and SQLite persistence for
runtime decisions, order results, position snapshots, bot state, config
versions, and trailing state. Current work is ready to begin Phase 3 safe
startup and reconciliation. New runtime code must default to `dry_run` and must
not place live orders by default.

Project layout:

- `src/bybit_automation/`: application package.
- `tests/`: unit tests and fake exchange fixtures.
- `configs/`: new TOML config templates and local runtime config.
- `configs.template/`: legacy JSON templates kept for migration reference.
- `data/`: local SQLite runtime database location, ignored by git.
- `.agents/`: AI agent handoff docs, specs, TODOs, and phase logs.

Agent handoff documents live under `.agents/`.
