# 測試、發布與架構演進計畫

本文件定義 `bybit-automation` 從目前的本機 `dry_run`，逐步走到 Bybit
Demo、Release Candidate（RC）及有限度 Live canary 的驗證流程；同時記錄未來
是否及如何演進成微服務／分散式架構。

本文件是執行計畫，不代表所有命令或能力都已實作。每個階段會明確標示目前狀態。

## 1. 核心結論

- 現階段定位：模組化單體（modular monolith）的 Demo Validation 前期。
- 現在適合：先完成單一程序的交易安全與 Demo 驗證。
- 中期適合：必要時拆成少數幾個粗粒度服務，而不是立刻拆成大量微服務。
- Live 之前必須依序通過本文件的 Gate 0 至 Gate 6。
- 所有會建立、取消或平倉的操作，都只能由唯一的 `OrderManager`／交易寫入者執行。
- Bybit 是外部交易事實來源；SQLite／未來的 PostgreSQL 是本機持久紀錄；Redis
  只能作為可重建的快取與協調層。

## 2. 狀態標示

- **已具備**：目前程式已有對應入口或自動測試。
- **部分具備**：已有底層元件，但尚未完成真實整合驗證。
- **待實作**：正式執行前必須新增。
- **人工批准**：會造成 Demo 或 Live 交易副作用，不能由一般自動測試直接執行。

## 3. 目前已有的驗證入口

| 目的 | 命令 | 狀態 | 重要限制 |
| --- | --- | --- | --- |
| 離線測試 | `uv run pytest` | 已具備 | 使用 fake／mock，不代表 Bybit 可連線 |
| 靜態檢查 | `uv run ruff check .` | 已具備 | 不會驗證 runtime 或交易所行為 |
| 單次 runtime tick | `uv run bybit-automation test --config <path>` | 已具備 | config 若是 `demo`／`live`，可能真的送單 |
| 強制 dry-run 驗證 | `uv run bybit-automation verify-dry-run --config <path>` | 已具備 | 只驗證本機流程，不連 Bybit |
| 設定變更驗證 | `uv run bybit-automation reload --current <path> --candidate <path>` | 部分具備 | 不會直接更新另一個正在運行的程序 |
| 長時間 runtime | `uv run bybit-automation run --config <path>` | 已具備 | 是正式執行入口，不等於已達 production-ready |
| Demo read-only preflight | 尚無命令 | 待實作 | 必須保證零交易副作用 |
| Demo shadow mode | 尚無命令／獨立 execution gate | 待實作 | 目前 `demo` 會啟用 Demo 訂單執行 |

## 4. 全域交易安全規則

任何 Demo 或 Live 網路驗證都必須遵守：

1. 使用獨立 API key；Live key 必須關閉提領權限。
2. API secret 只能透過環境變數或本機 secret store 提供，不得寫入 Git。
3. 測試前明確記錄：環境、帳戶、symbol、最大名目金額、最大允許損失及停止條件。
4. 未得到人工批准，不得建立、取消、修改或平倉。
5. `test` 命令只有在 config 已確認為 `dry_run` 時，才能當成無副作用命令。
6. Demo／Live 必須區分「可連線」與「可送單」；不能只用 `app.mode` 同時控制兩件事。
7. 平倉命令必須驗證 `reduceOnly`、position mode、`positionIdx` 和實際成交方向。
8. 所有送單必須有穩定的 client order ID／idempotency key，並能處理「交易所已接受，
   但本機沒有收到回應」的情況。
9. 自動化測試不得取消帳戶上無法確認是本機機器人建立的訂單。
10. 任一狀態無法確定時，停止新進場並進入 `SAFE_MODE`。

## 5. 分階段測試與發布閘門

### Gate 0：開發環境與離線基線

狀態：**已具備測試；目前機器尚未重新執行。**

目的：確認目前 commit 可以從乾淨環境重建，而且所有不需外部服務的測試都通過。

執行：

```powershell
uv sync --locked
uv run python --version
uv run pytest
uv run ruff check .
```

最低驗收條件：

- `uv sync --locked` 成功。
- Python 版本符合 `pyproject.toml`。
- 全部測試及 Ruff 通過。
- 測試過程沒有要求 Bybit credentials。
- Git worktree 沒有出現非預期產物或 secrets。

應保存的證據：

- commit hash、執行時間、OS、Python／uv 版本。
- pytest 與 Ruff 結果。
- 失敗測試與修復紀錄。

### Gate 1：Dry-run runtime 驗證

狀態：**已具備。**

目的：驗證完整 runtime 組裝、SQLite 寫入、策略／風控決策與安全關閉，不接觸 Bybit。

執行：

```powershell
uv run bybit-automation verify-dry-run --config configs/config.template.toml
uv run bybit-automation test --config configs/config.template.toml
```

另外必測：

- `verify-dry-run` 必須拒絕 `demo` 與 `live` config。
- 缺少 config、無效 symbol、負數 interval、錯誤資料庫路徑時能清楚失敗。
- SQLite WAL、schema bootstrap、config version 與 `bot_state` 正常。
- 連續啟動兩次不會讓新持倉繼承舊 trailing state。
- `Ctrl+C`／SIGTERM 會保存 shutdown reason。
- dry-run 下不會建立 ccxt Bybit client，也不會建立、取消或平倉。

最低驗收條件：所有檢查通過，而且能提出「零 Bybit 網路請求」的證據。

### Gate 2：Bybit Demo read-only preflight

狀態：**待實作。**

建議新增入口：

```powershell
uv run bybit-automation preflight --config configs/config.demo.toml
```

目的：驗證 credentials、網路、帳戶模式與市場設定，但完全不改變 Bybit 狀態。

preflight 只允許：

- 查詢伺服器時間及時間偏差。
- 查詢帳戶／API 權限，確認是 Demo 環境。
- 讀取 configured symbols 與 market metadata。
- 讀取 ticker、OHLCV、持倉和未成交訂單。
- 讀取最小下單量、價格 tick、數量精度與 position mode。
- 建立 health report 與 SQLite 稽核紀錄。

preflight 明確禁止：

- 設定槓桿。
- 建立、修改或取消訂單。
- 平倉。
- 變更帳戶設定。

最低驗收條件：

- 能以程式化方式證明目前連線是 Demo，不是 Live。
- 所有 configured symbols 均可解析。
- 權限與帳戶模式符合預期。
- 執行前後的持倉與 open orders 完全相同。
- 任一檢查失敗時回傳非零 exit code，且不產生交易副作用。

### Gate 3：Demo shadow mode

狀態：**待實作。**

目的：使用真實 Demo 行情和帳戶資料運行完整策略，但阻擋所有 exchange side effects。

實作前提：將連線環境與執行權限拆開，例如：

```toml
[app]
mode = "demo"

[execution]
enabled = false
```

不能用「金額設成 0」代替 execution gate，因為它無法保證取消訂單、平倉或未來新增的
side effect 都被阻擋。

測試內容：

- 讀取 Demo ticker、K 線、持倉與 open orders。
- 執行策略、風控、排程與持久化。
- 將 order intent 寫入 SQLite，但 `submitted=false`。
- 模擬持倉不一致、WebSocket stale、Redis unavailable 與 API timeout。
- 確認 `SAFE_MODE` 會停止新進場，但仍產生可稽核的風控決策。
- 至少先運行 30 分鐘，再進行 2 小時與 24 小時 shadow session。

最低驗收條件：Bybit Demo 帳戶在整個 session 前後沒有任何由系統造成的狀態變更。

### Gate 4：受控 Demo 訂單生命週期

狀態：**待實作；每次測試均需人工批准。**

前提：Gate 0 至 Gate 3 全部通過，使用單一高流動性 symbol 與交易所允許的最小金額。

依序執行，不可一次自動跑完：

1. 建立一張不會立即成交的小額限價單。
2. 從 REST 查回訂單，以 client order ID 對上 SQLite intent。
3. 取消該張由機器人建立的訂單，確認不影響其他訂單。
4. 建立一張可成交的小額 Demo 訂單，確認 order、execution、position 狀態。
5. 使用 `reduceOnly` 平倉，確認不會反向開倉。
6. 重複取得訂單結果，確認事件重送不會建立重複本機紀錄。
7. 測試 graceful shutdown 只處理屬於本機機器人的未成交訂單。

異常案例：

- 送單後刻意模擬 response timeout，再以 client order ID 查明交易所結果。
- 重複送出相同 intent，確認冪等保護。
- 訂單部分成交後取消。
- 平倉時 mark price 快速變動。
- position mode 與設定不相符。

最低驗收條件：沒有重複訂單、沒有反向開倉、沒有誤取消手動訂單，且 SQLite 可完整重建
每個 intent 到 exchange order／execution 的關係。

### Gate 5：Reconciliation 與故障韌性演練

狀態：**部分具備；基礎元件已有，完整整合待完成。**

必測情境：

| 故障 | 預期行為 |
| --- | --- |
| 啟動時 Bybit 有本機未知持倉 | 進入 `SAFE_MODE`，停止新進場 |
| 啟動時 Bybit 有本機未知訂單 | 進入 `SAFE_MODE`，不得直接取消 |
| SQLite 有 submitted 訂單但 Bybit 查不到 | 記錄 mismatch，人工確認或安全修復 |
| 送單後網路 timeout | 先查單／對帳，不得盲目重送 |
| WebSocket 中斷或資料過期 | 暫停新進場，REST 修復後才能恢復 |
| Redis 中斷／重啟 | runtime 安全降級；從 exchange 與 durable store 重建 cache |
| SQLite locked／不可寫／磁碟不足 | 停止新增交易副作用並發出 error／SAFE_MODE |
| Runtime 被強制終止後重啟 | 啟動對帳成功前不得進場 |
| 重複、亂序或延遲事件 | 依 event ID／sequence 去重，不能倒退狀態 |
| 連續 API 失敗 | backoff 與 circuit breaker 實際生效 |
| 無效 config reload | 保留舊設定並留下稽核紀錄 |

必須補齊：

- 將 `reconciliation_interval_sec` 接進 scheduler，而不只是啟動時對帳。
- 將 retry／backoff／circuit breaker 接進明確允許重試的讀取操作。
- 定義 SAFE_MODE 的恢復條件與人工操作手冊。
- 為每個 exchange side effect 加入 idempotency 與 ambiguous-result 處理。
- 增加外部通知，而不只是記憶體內的 notification list。

最低驗收條件：所有故障均「安全停止或安全降級」，沒有未解釋的交易副作用。

### Gate 6：Demo soak test 與 Release Candidate

狀態：**待執行。**

建議時程：

1. 2 小時 shadow。
2. 24 小時 shadow。
3. 24 小時受限 Demo trading。
4. 72 小時 Demo soak。

期間監控：

- API／WebSocket latency、錯誤率與 reconnect 次數。
- 行情 freshness。
- strategy／risk tick 是否準時。
- open order、position 和 SQLite mismatch 次數。
- SAFE_MODE 次數、原因與恢復時間。
- 重複 intent／order／execution 數量。
- SQLite 大小、寫入延遲及 WAL 行為。
- Redis 可用性與 cache rebuild 時間。
- 通知是否在可接受時間內送達。
- CPU、記憶體、檔案描述符與長時間資源成長。

RC 最低驗收條件：

- 72 小時內沒有未解釋 crash、重複訂單或錯誤平倉。
- 每次刻意重啟都能 reconciliation 並恢復正確狀態。
- 所有 mismatch 都能自動安全處理或進入 SAFE_MODE。
- 操作者可從文件與告警判斷系統現在是否安全。
- 部署、rollback、backup、restore 與 kill switch 已演練。

### Gate 7：Live canary

狀態：**尚未允許。**

只有 Gate 0 至 Gate 6 全部通過，且由使用者再次明確批准，才能規劃 Live canary。

最低保護：

- 獨立、無提領權限的 Live API key。
- 單帳戶、單 symbol、最小可接受部位。
- 設定每日最大損失、最大 position notional、最大 open orders。
- 可立即使用的 global kill switch。
- 啟動時顯示明確 Live 警告並要求二次確認或 deployment-level approval。
- 外部通知、health monitor 和人工值守。
- 先確認平倉與 `reduceOnly`，再允許建立新倉。

Live canary 不應由一般 CI 自動觸發。

## 6. 每次驗證應保存的證據

每次 Gate 執行建立一筆驗證紀錄，至少包含：

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

禁止把完整 API key、secret 或可重播的認證資料放進 log、SQLite 證據或 Git。

## 7. 微服務與分散式架構的差異

兩者不是互斥選項：

- **分散式架構**：元件在不同程序或機器上協作，是較大的概念。
- **微服務**：分散式架構的一種，把能力拆成可獨立部署、擴縮與維護的小服務。
- **模組化單體**：一個部署單位，但程式內部保持清楚的模組與介面。

微服務會帶來獨立部署與擴展能力，也同時帶來網路失敗、訊息重複／亂序、跨服務對帳、
分散式 tracing、版本相容與更多維運成本。對交易系統而言，這些不只是工程複雜度，也會
直接增加錯誤交易的風險。

## 8. 哪一種最適合目前專案

| 選項 | 現階段適合度 | 原因 |
| --- | --- | --- |
| 模組化單體 | 最適合 | 單一帳戶、低到中等交易量、單一交易寫入者容易稽核與對帳 |
| 少數粗粒度分散式服務 | 中期適合 | 行情、交易核心與營運介面有清楚邊界，可分別擴展 |
| 大量細粒度微服務 | 現在不適合 | 維運與一致性成本高，現有安全驗證尚未完成 |

目前最值得投入的是：完成 Demo 驗證、冪等下單、週期對帳、外部告警與故障演練。
在這些能力完成前拆微服務，只會把未解決的狀態一致性問題搬到網路上。

## 9. 建議的漸進式架構

### 階段 A：維持模組化單體

維持單一程序，但強化內部界線：

```text
Market Data
    -> Strategy / Risk
    -> Order Intent
    -> OrderManager（唯一交易寫入者）
    -> Exchange
    -> Persistence / Notification
```

此階段完成 Gate 0 至 Gate 6，並在內部先建立：

- 明確 command／event models。
- client order ID 與 idempotency。
- transaction／outbox 邊界。
- 週期 reconciliation。
- 可觀測性、告警及 kill switch。

### 階段 B：拆成三個粗粒度服務

只有在需要獨立擴展或部署時再拆：

1. **Market Data Gateway**
   - 維護 Bybit public WebSocket／REST market snapshots。
   - 發布 ticker、kline 和 freshness 事件。
   - 不持有私有交易權限，也不能下單。

2. **Trading Core**
   - 保留 strategy、risk、position state、reconciliation 與 `OrderManager`。
   - 是每個帳戶唯一可建立、取消或平倉的服務。
   - 在安全性成熟前，不要把 risk 與 execution 分到網路兩端。

3. **Operations / Control Plane**
   - 提供 health、config proposal、審批、通知、稽核查詢與 kill switch。
   - 不能繞過 Trading Core 直接呼叫交易所。

資料層建議：

- 多程序／多機後，不共享 SQLite 檔案；改用 PostgreSQL 等可安全並行的 durable store。
- Redis 維持快取、鎖或短期協調，不作為唯一交易紀錄。
- 事件傳遞可先從 Redis Streams、NATS JetStream 或 RabbitMQ 中選一個；在需求明確前
  不需要直接導入 Kafka。

### 階段 C：有明確需求時才進一步微服務化

出現以下條件時才考慮拆出 Strategy Workers、Execution Service、Reconciliation
Service 等更細服務：

- 同時管理多個帳戶或交易所。
- 多個策略需要獨立部署與擴縮。
- 行情吞吐量遠高於單一程序能力。
- 不同團隊需要獨立發布週期。
- 單一程序已成為可量測的效能或可用性瓶頸。

拆出獨立 Execution Service 後仍需保證：

- 每個帳戶在任何時刻只有一個有效交易寫入者。
- 訊息採 at-least-once 時，consumer 必須冪等。
- command 使用穩定 idempotency key。
- 使用 outbox／inbox 或等價機制避免資料已提交但事件遺失。
- 使用 account + symbol 作為排序／分區依據。
- leader election 必須配合 fencing token，避免舊 leader 繼續下單。
- reconciliation 永遠能以交易所狀態修復事件遺失或亂序。

## 10. 架構升級決策門檻

在回答「是否該拆服務」前，先收集：

- 單一 runtime 的 CPU、記憶體與 API latency。
- symbols、帳戶、策略數量的成長預期。
- 可接受停機時間與恢復時間。
- 是否真的需要各模組獨立部署。
- 是否有人力維護 broker、PostgreSQL、observability 與多服務部署。

若目前仍是單一使用者、單一 Bybit 帳戶與少量 symbols，建議保持模組化單體。當 Market
Data 需要獨立擴展、或多個策略／帳戶需要隔離時，再進入階段 B。這會比直接全面微服務化
更安全，也更容易找出交易狀態問題。

## 11. 下一步建議順序

1. 恢復 `uv` 環境並執行 Gate 0。
2. 重跑 Gate 1，保存當前 commit 的驗證證據。
3. 實作只讀 Demo preflight。
4. 將 exchange environment 與 execution permission 分離，加入 shadow mode。
5. 補上 client order ID、`reduceOnly`、週期 reconciliation 和外部通知。
6. 執行受控 Demo order lifecycle、故障演練及 soak test。
7. Gate 6 通過後，再決定是否進行階段 B 的服務拆分。
