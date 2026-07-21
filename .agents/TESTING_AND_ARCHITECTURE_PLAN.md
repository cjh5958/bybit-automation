# Testing, release and architecture evolution plan

This document defines the validation path for `bybit-automation`: from the current local `dry_run` state, through Bybit Demo and Release Candidate (RC), and eventually to a limited Live canary. It also records whether and how the architecture may evolve toward microservices or a distributed design.

This document is an execution plan and does not mean that all commands or capabilities have been implemented. Each stage is clearly marked with its current status.

## 1. Core Conclusions

- Current positioning: early stage of Demo Validation of modular monolith.
- Now suitable: Complete the trading safety and demo verification of a single process first.
- Suitable for the medium term: split into a few coarse-grained services when necessary, rather than splitting into a large number of microservices immediately.
- Before Live, you must pass Gate 0 to Gate 6 of this file in order.
- All operations that will create, cancel or close a position can only be performed by the only `OrderManager`/exchange writer.
- Bybit is the external trading source of truth; SQLite/future PostgreSQL is the local durable record; Redis
  Can only be used as a rebuildable cache and coordination layer.

## 2. Status Labels

- **Already Available**: The program currently has a corresponding entry point or automated test.
- **Partially available**: The underlying components are available, but the actual integration verification has not yet been completed.
- **To be implemented**: Must be added before production execution.
- **Manual Approval**: It will cause side effects of Demo or Live transactions and cannot be directly executed by general automated tests.

## 3. Current verification entry points

| Purpose | Commands | Status | Important Limitations |
| --- | --- | --- | --- |
| Offline testing | `uv run pytest` | Already available | Using fake/mock does not mean Bybit can be connected |
| Static check | `uv run ruff check .` | Already available | Does not verify runtime or exchange behavior |
| Single runtime tick | `uv run bybit-automation test --config <path>` | Already available | If config is `demo`/`live`, the order may actually be sent |
| Forced dry-run verification | `uv run bybit-automation verify-dry-run --config <path>` | Already available | Only verify the local process, not connected to Bybit |
| Config change verification | `uv run bybit-automation reload --current <path> --candidate <path>` | Partially available | Will not directly update another running program |
| Long-running runtime | `uv run bybit-automation run --config <path>` | Already available | It is the production execution entry point, which does not mean it has reached production-ready |
| Demo read-only preflight | No command yet | To be implemented | Must ensure zero trading side effects |
| Demo shadow mode | No command yet/independent execution gate | To be implemented | Currently `demo` will enable Demo order execution |

## 4. Global trading safety rules

Any Demo or Live network validation must comply with:

1. Use an independent API key; Live key must have withdrawal permission turned off.
2. API secrets can only be provided through environment variables or the local secret store, and cannot be written to Git.
3. Clearly record before testing: environment, account, symbol, maximum amount, maximum allowable loss and stop conditions.
4. Positions cannot be established, canceled, modified or closed without manual approval.
5. The `test` command can be regarded as a side-effect-free command only when the config has been confirmed as `dry_run`.
6. Demo/Live must distinguish between "can be connected" and "can send orders"; you cannot just use `app.mode` to control two things at the same time.
7. The position closing order must verify `reduceOnly`, position mode, `positionIdx` and the actual transaction direction.
8. All orders must have a stable client order ID/idempotency key and be able to handle "accepted by the exchange.
   But the machine did not receive a response."
9. Automated testing is not allowed to cancel orders on the account that cannot be confirmed to be created by local robots.
10. When any status cannot be determined, stop new entries and enter `SAFE_MODE`.

## 5. Phased testing and release gate

### Gate 0: Development environment and offline baselineStatus: ** Testing is available; the machine has not yet been re-executed. **

Purpose: Confirm that the current commit can be rebuilt from a clean environment and that all tests that do not require external services pass.

Execution:

```powershell
uv sync --locked
uv run python --version
uv run pytest
uv run ruff check .
```

Minimum acceptance conditions:

- `uv sync --locked` Success.
- Python version conforms to `pyproject.toml`.
- All tests and Ruff passed.
- Bybit credentials are not required for the testing process.
- There are no unexpected artifacts or secrets in Git worktree.

Evidence that should be preserved:

- commit hash, execution time, OS, Python/uv version.
- pytest and Ruff results.
- Failed test and repair records.

### Gate 1: Dry-run runtime verification

Status: ** Already available. **

Purpose: Verify complete runtime assembly, SQLite writing, policy/risk control decisions and safe shutdown without touching Bybit.

Execution:

```powershell
uv run bybit-automation verify-dry-run --config configs/config.template.toml
uv run bybit-automation test --config configs/config.template.toml
```

Also must-test:

- `verify-dry-run` The `demo` and `live` configs must be rejected.
- Clear failures when config is missing, invalid symbol, negative interval, or wrong database path.
- SQLite WAL, schema bootstrap, config version and `bot_state` are normal.
- Launching twice in a row will not allow new positions to inherit the old trailing state.
- `Ctrl+C`／SIGTERM will save the shutdown reason.
- The ccxt Bybit client will not be created under dry-run, nor will positions be created, canceled or closed.

Minimum acceptance conditions: All inspections pass, and evidence of "zero Bybit network requests" can be provided.

### Gate 2: Bybit Demo read-only preflight

Status: **To be implemented. **

Suggested new entrance:

```powershell
uv run bybit-automation preflight --config configs/config.demo.toml
```

Purpose: Verify credentials, network, account mode and market settings, but does not change Bybit status at all.

preflight only allows:

- Query server time and time deviation.
- Query the account/API permissions and confirm that it is a Demo environment.
- Read configured symbols and market metadata.
- Read ticker, OHLCV, open positions and unfilled orders.
- Read the minimum order quantity, price tick, quantity accuracy and position mode.
- Create health report and SQLite audit records.

preflight specifically prohibits:

- Set leverage.
- Create, modify or cancel orders.
- Close the position.
- Change account settings.

Minimum acceptance conditions:- Can programmatically prove that the current connection is Demo, not Live.
- All configured symbols can be parsed.
- Permissions and account patterns are as expected.
- Positions before and after execution are exactly the same as open orders.
- If any check fails, a non-zero exit code will be returned without any trading side effects.

### Gate 3: Demo shadow mode

Status: **To be implemented. **

Purpose: Run a complete strategy using real demo quotes and account information, but block all exchange side effects.

Prerequisite for implementation: Separate the connection environment and execution permissions, for example:

```toml
[app]
mode = "demo"

[execution]
enabled = false
```

"Set amount to 0" cannot be used instead of execution gate because it does not guarantee the cancellation of orders, closing positions or new additions in the future.
Side effects are blocked.

Test content:

- Read Demo ticker, K-line, positions and open orders.
- Execution strategy, risk control, scheduling and persistence.
- Write order intent to SQLite but `submitted=false`.
- Simulate position inconsistency, WebSocket stale, Redis unavailable and API timeout.
- Confirmed that `SAFE_MODE` will stop new entries, but still generate auditable risk control decisions.
- Run for at least 30 minutes, then 2 hours and 24 hours shadow session.

Minimum acceptance conditions: The Bybit Demo account does not have any status changes caused by the system before and after the entire session.

### Gate 4: Controlled Demo order life cycle

Status: **To be implemented; each test requires manual approval. **

Prerequisite: Gate 0 to Gate 3 all pass, use a single high-liquidity symbol and the minimum amount allowed for the transaction.

Execute in sequence and cannot be completed automatically in one go:

1. Create a small limit order that will not be executed immediately.
2. Query the order from REST and use the client order ID to match the SQLite intent.
3. Cancel the order created by the robot and confirm that it will not affect other orders.
4. Create a small-amount Demo order that can be traded, and confirm the order, execution, and position status.
5. Use `reduceOnly` to close the position and confirm that the reverse position will not be opened.
6. Obtain order results repeatedly and confirm that event resending will not create duplicate local records.
7. Test graceful shutdown to only process unfilled orders belonging to the local robot.

Exception cases:

- Deliberately simulate the response timeout after sending the order, and then use the client order ID to find out the exchange result.
- Send the same intent repeatedly to confirm idempotent protection.
- The order is canceled after it is partially filled.
- The mark price changes rapidly when closing a position.
- position mode does not match the setting.Minimum acceptance conditions: no duplicate orders, no reverse opening of positions, no manual order cancellation by mistake, and SQLite can be completely rebuilt
The relationship between each intent and exchange order/execution.

### Gate 5: Reconciliation and fault resilience drills

Status: **Partially available; basic components are available and full integration needs to be completed. **

Must-test situations:

| Failure | Expected Behavior |
| --- | --- |
| When starting, Bybit has an unknown position | Enter `SAFE_MODE`, stop new entries |
| Bybit has local unknown orders at startup | Enter `SAFE_MODE` and cannot cancel directly |
| SQLite has submitted orders but Bybit cannot find them | Record mismatch, manual confirmation or security repair |
| Internet timeout after order delivery | Check/reconcile the order first, do not blindly resend |
| WebSocket interruption or data expiration | Pause new entries and resume after REST repair |
| Redis interrupt/restart | Runtime safety downgrade; rebuild cache from exchange and durable store |
| SQLite locked／Unwritable／Insufficient disk | Stop adding trading side effects and issue error／SAFE_MODE |
| Runtime is restarted after being forcibly terminated | No entry is allowed before the reconciliation is successfully started |
| Duplicate, out-of-sequence or delayed events | Deduplication based on event ID/sequence, no reversal of status |
| Continuous API failure | backoff and circuit breaker actually take effect |
| Invalid config reload | Keep old settings and leave audit records |

Must be completed:

- Connect `reconciliation_interval_sec` to the scheduler instead of just reconciliation at startup.
- Integrate retry/backoff/circuit breaker into read operations that explicitly allow retries.
- Define recovery conditions and manual operation manual for SAFE_MODE.
- Add idempotency and ambiguous-result processing to each exchange side effect.
- Add external notifications instead of just notification list in memory.

Minimum acceptance conditions: All failures are "safe stops or safe downgrades" and there are no unexplained trading side effects.

### Gate 6: Demo soak test and Release Candidate

Status: **Pending execution. **

Recommended timetable:

1. 2 hours shadow.
2. 24 hours shadow.
3. 24-hour limited Demo trading.
4. 72 hours Demo soak.

Period monitoring:- API/WebSocket latency, error rate and reconnect times.
-Quotes freshness.
- Is the strategy/risk tick on time?
- Open order, position and SQLite mismatch times.
- SAFE_MODE times, reasons and recovery time.
- Number of repeated intent/order/executions.
- SQLite size, write latency and WAL behavior.
- Redis availability and cache rebuild time.
- Whether the notice was delivered within an acceptable time.
- CPU, memory, file descriptors and long-term resource growth.

RC minimum acceptance conditions:

- No unexplained crashes, duplicate orders or incorrect positions within 72 hours.
- Every deliberate restart can reconcile and restore the correct state.
- All mismatches can be automatically handled safely or entered into SAFE_MODE.
- Operators can judge whether the system is safe now from files and alarms.
- Deployment, rollback, backup, restore and kill switch drilled.

### Gate 7: Live canary

Status: **Not yet allowed. **

Live canary can only be planned if Gate 0 to Gate 6 are all passed and explicitly approved by the user again.

Minimum protection:

- Independent Live API key without withdrawal permission.
- Single account, single symbol, minimum acceptable position.
- Set the maximum daily loss, maximum position notation, and maximum open orders.
- A ready-to-use global kill switch.
- Show an explicit Live warning on launch and require secondary confirmation or deployment-level approval.
- External notifications, health monitors and manual attendance.
- Confirm the closing position with `reduceOnly` first, and then allow the establishment of a new position.

Live canary should not be automatically triggered by normal CI.

## 6. Evidence that should be saved for each verification

Each time Gate is executed, a verification record is created, which at least contains:

```text
日期與時區：
Git commit：
Config hash：
執行環境：dry_run / demo / live
帳戶識別：只保存遮蔽後識別，不保存 secret
Symbols：
最大交易金額：
執行命令：
開始／結束時間：
測試結果：pass / fail / blocked
SQLite bot_state 摘要：
Bybit 執行前後 positions/open orders 摘要：
SAFE_MODE／告警：
已知問題與後續行動：
批准人（有交易副作用時）：
```

Do not put full API keys, secrets, or replayable authentication data into logs, SQLite evidence, or Git.

## 7. The difference between microservices and decentralized architecture

The two are not mutually exclusive options:

- **Distributed Architecture**: The collaboration of components on different programs or machines is a larger concept.
- **Microservices**: A type of decentralized architecture that breaks capabilities into small services that can be independently deployed, scaled and maintained.
- **Modular Unit**: A deployment unit, but clear modules and interfaces are maintained within the program.Microservices will bring independent deployment and expansion capabilities, but also bring network failures, message duplication/disordering, cross-service reconciliation,
Distributed tracing, version compatibility and more maintenance costs. For trading systems, these are not just engineering complexities;
Directly increases the risk of wrong transactions.

## 8. Which one is most suitable for the current project?

| Options | Current fitness | Reason |
| --- | --- | --- |
| Modular monolith | Best suited for | Single account, low to medium transaction volume, single exchange writer for easy auditing and reconciliation |
| A small number of coarse-grained decentralized services | Suitable for the medium term | The market, transaction core and operating interfaces have clear boundaries and can be expanded separately |
| A large number of fine-grained microservices | Not suitable now | Maintenance and consistency costs are high, and existing security verification has not been completed |

The most worthwhile investment at present is: completing demo verification, idempotent order placement, periodic reconciliation, external alarms and fault drills.
Dismantling microservices before these capabilities are complete will only move unresolved state consistency issues to the network.

## 9. Proposed progressive architecture

### Phase A: Maintaining a modular monolith

Maintain a single process but strengthen internal boundaries:

```text
Market Data
    -> Strategy / Risk
    -> Order Intent
    -> OrderManager（唯一交易寫入者）
    -> Exchange
    -> Persistence / Notification
```

This phase completes Gate 0 to Gate 6 and builds them internally first:

- Clarify command/event models.
- client order ID and idempotency.
- transaction/outbox boundaries.
- Periodic reconciliation.
- Observability, alerts and kill switches.

### Phase B: Split into three coarse-grained services

Only disassemble it when independent expansion or deployment is required:

1. **Market Data Gateway**
   - Maintain Bybit public WebSocket／REST market snapshots.
   - Post ticker, kline and freshness events.
   - If you do not hold private trading permissions, you cannot place orders.

2. **Trading Core**
   - Retain strategy, risk, position state, reconciliation and `OrderManager`.
   - is the only service for each account that can open, cancel or close positions.
   - Before security matures, do not divide risk and execution into two ends of the network.

3. **Operations/Control Plane**
   - Provide health, config proposal, approval, notification, audit query and kill switch.
   - It is not possible to bypass Trading Core and call the exchange directly.

Data layer suggestions:- After multi-program/multi-machine, SQLite files are not shared; instead, durable stores such as PostgreSQL that can be safely parallelized are used.
- Redis maintains caches, locks or short-term coordination, not as the only trading record.
- For event delivery, you can first choose one from Redis Streams, NATS JetStream or RabbitMQ; before the requirements are clear
  No need to import Kafka directly.

### Stage C: Further microservices only when there are clear needs

Consider removing Strategy Workers, Execution Service, and Reconciliation only when the following conditions occur
Service and other more detailed services:

- Manage multiple accounts or exchanges simultaneously.
- Multiple strategies need to be deployed and scaled independently.
- Market throughput is much higher than the capability of a single program.
- Different teams need independent release cycles.
- A single program has become a measurable performance or availability bottleneck.

After removing the independent Execution Service, you still need to ensure:

- There is only one valid exchange writer per account at any time.
- When the message is at-least-once, the consumer must be idempotent.
- command uses stable idempotency key.
- Use outbox/inbox or equivalent mechanisms to avoid data being submitted but events being lost.
- Use account + symbol as sort/partition basis.
- Leader election must cooperate with fencing token to prevent the old leader from continuing to place orders.
- Reconciliation can always fix lost or out-of-order events in exchange status.

## 10. Architecture upgrade decision threshold

Before answering "Should the service be dismantled?", first collect:

- CPU, memory and API latency of a single runtime.
- Expected growth in the number of symbols, accounts, and strategies.
- Acceptable downtime and recovery time.
- Whether it is really necessary to deploy each module independently.
- Whether there is manpower to maintain broker, PostgreSQL, observability and multi-service deployment.

If you still have a single user, a single Bybit account, and a small number of symbols, it is recommended to keep it modular. When Market
When Data needs to be independently expanded, or multiple policies/accounts need to be isolated, then enter stage B. This will be better than direct comprehensive microservices
More secure and easier to identify transaction status issues.

## 11. Suggested sequence for next step1. Restore the `uv` environment and execute Gate 0.
2. Rerun Gate 1 and save the verification evidence of the current commit.
3. Implement read-only Demo preflight.
4. Separate the exchange environment from execution permission and add shadow mode.
5. Fill in the client order ID, `reduceOnly`, periodic reconciliation and external notification.
6. Execute controlled Demo order lifecycle, fault drill and soak test.
7. After Gate 6 is passed, it will be decided whether to proceed with the service split in Phase B.
