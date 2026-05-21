# bybit-stream-bot

Refactor-in-progress Bybit futures trading bot.

The current work is in Phase 0: project foundation with `uv`, a safe package
skeleton, and config validation. New runtime code must default to `dry_run` and
must not place live orders by default.

Agent handoff documents live under `.agents/`.

