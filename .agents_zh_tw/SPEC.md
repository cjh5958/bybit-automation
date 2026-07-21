# 規格.md

該文件記錄了未來代理應處理的項目級規範
作為目前的設計目標，除非使用者明確改變方向。

保持本文檔簡潔。詳細的實作說明位於程式碼中，
測試或特定階段的文件。

## 配置規範

### 目標

未來的配置系統應該是：

- 易於在本地開發中編輯，
- 易於在容器中覆蓋，
- 可以安全地提交為模板，
- 在運行時使用之前進行驗證，
- 成功載入時進行版本控制，
- 適合未來的熱重載。

### 檔案格式

使用 TOML 作為主要設定格式。

計劃文件：

```text
configs/config.template.toml
configs/config.toml
```

規則：

- `configs/config.template.toml` 已承諾。
- `configs/config.toml` 是本地/運行時特定的，不應提交。
- 秘密不得直接儲存在提交的設定檔中。
- 運行時秘密應該來自環境變數。
- 容器部署應該能夠安裝或取代 `config.toml`。

理由：

- TOML 是人類可讀的，並且可以自然地與 `pyproject.toml` 一起使用。
- Python 3.11+可以透過`tomllib`讀取TOML。
- 單一設定檔可避免多個 JSON 檔案的不明確合併行為。

### 環境變數與秘密

配置應該儲存環境變數名稱，而不是秘密值。

範例：

```toml
[exchange.bybit]
api_key_env = "BYBIT_API_KEY"
api_secret_env = "BYBIT_API_SECRET"
```

預期行為：

- 載入器在運行時解析環境變數名稱。
- 缺少必需的秘密將導致交易開始前驗證失敗。
- 如果沒有交換副作用，試運轉模式可能會允許遺失交換憑證
  將被執行。

### 容器友善的覆蓋

配置設計應該支援容器而不需要重建鏡像。

優選機制：

- 安裝`configs/config.toml`，
- 透過環境變數注入秘密，
- 可以選擇透過環境變數覆蓋配置路徑，例如
  `BYBIT_AUTOMATION_CONFIG`。

不需要編輯原始碼來更改運行時配置。

### 頂層結構

目標配置結構為：

```toml
[app]
mode = "dry_run"
log_level = "INFO"
timezone = "Asia/Taipei"

[exchange]
name = "bybit"
account_type = "future"
enable_rate_limit = true
default_leverage = 10

[exchange.bybit]
api_key_env = "BYBIT_API_KEY"
api_secret_env = "BYBIT_API_SECRET"

[runtime]
strategy_interval_sec = 60
risk_interval_sec = 1
reconciliation_interval_sec = 30
safe_mode_on_startup_mismatch = true

[database.sqlite]
path = "data/bot.sqlite3"
wal = true

[cache.redis]
enabled = false
url_env = "REDIS_URL"
namespace = "bybit-automation"

[websocket]
enabled = false
public_market = true
private_account = true
stale_after_sec = 5
reconnect_initial_delay_sec = 1
reconnect_max_delay_sec = 30

[strategy.defaults]
enabled = true
ema_period = 240
value_multiplier = 3
long_amount_usdt = 30
short_amount_usdt = 30

[risk.defaults]
enabled = true
stop_loss_pct = 0.6
low_trail_enable_threshold = 0.3
first_trail_enable_threshold = 0.8
second_trail_enable_threshold = 2.0
low_trail_stop_loss_pct = 0.2
trail_stop_loss_pct = 0.35
higher_trail_stop_loss_pct = 0.2

[risk]
blacklist = [
  "BTC/USDT:USDT",
  "ETH/USDT:USDT",
  "SOL/USDT:USDT",
]

[[symbols]]
symbol = "MOODENG/USDT:USDT"
enabled = true

[[symbols]]
symbol = "1000X/USDT:USDT"
enabled = true
value_multiplier = 3
long_amount_usdt = 30
short_amount_usdt = 30
```

### 模式語義

`app.mode` 應支援：

- `dry_run`：沒有即時交易所副作用；開發的安全預設值。
- `demo`：支援的交換演示/沙盒模式。
- `live`：真實交易模式；必須需要明確設定和有效憑證。

新的運行時代碼不得預設為即時交易。

### 預設值和符號覆蓋使用預設值加上每個符號覆蓋。

規則：

- `[strategy.defaults]` 定義通用策略設定。
- `[risk.defaults]` 定義常見風險/追蹤設定。
- 每個 `[[symbols]]` 條目都可以覆寫支援的策略欄位。
- 稍後的實施可能允許每個符號的風險覆蓋，但這應該是
  明確並經過驗證。
- 載入程式應在執行時間使用之前產生已解析的每個符號配置。

這避免了每個交易對重複相同的值。

### 命名規則

避免有歧義的名稱。

用途：

- `strategy_interval_sec`
- `risk_interval_sec`
- `reconciliation_interval_sec`

不要在不相關的部分中重複使用通用金鑰，例如 `monitor_interval`。

如果可行，請在名稱中使用明確的單位，尤其是時間間隔。

### 驗證規則

在運行時使用之前必須驗證配置。

最低驗證：- `app.mode` 是 `dry_run`、`demo`、`live` 之一。
- 支援 `exchange.name`。
- 所選模式存在所需的環境變數。
- 間隔是正數。
- 槓桿為正。
- 符號非空且唯一。
- 訂單金額為非負數。
- 風險百分比和閾值是非負的。
- 尾隨閾值依邏輯順序排列：
  - `low_trail_enable_threshold`
  - `first_trail_enable_threshold`
  - `second_trail_enable_threshold`
- 僅當啟用 Redis 時才需要進行 Redis 設定。
- WebSocket 陳舊資料和重新連線間隔為正。
- WebSocket 重新連線初始延遲不超過最大延遲。

無效配置不得部分套用。

### 熱重載規則

第一個實作僅支援手動重新載入。

安全的熱重載欄位：

- 符號啟用/停用，
- 訂單金額，
- EMA期間，
- 價值乘數，
- 風險/追蹤閾值，
- 黑名單，
- 運轉時間間隔。

不應靜默熱重載的欄位：

- API 金鑰或秘密環境名稱，
- 交換姓名，
- 帳戶模式，
- 資料庫路徑，
-Redis 網址，
- 預設槓桿。如果重新載入包含不安全的更改，則重新載入服務將返回
`requires_restart`，保留活動配置，記錄審核結果
SQLite 可用，並且需要明確的安全重啟流程。

手動重新載入入口點：

```text
bybit-automation reload --current configs/config.toml --candidate configs/config.new.toml
```

預期行為：

- 有效且可熱重新加載的候選人透過重新加載服務進行申請，
- 無效候選返回非零並保留活動配置，
- 不安全的候選人返回非零且需要重新啟動的路徑，
- 成功的手動重新載入記錄在 SQLite `config_versions` 中
  `reload_reason = "manual"`,
- 當 SQLite 執行時，所有重新載入嘗試都會寫入 `bot_state.last_config_reload`
  可用，
- Redis 配置重新載入訊號僅記錄為通知原語且
  不自動套用配置變更。

### 載入配置的持久性

一旦 SQLite 啟動，每個成功載入的設定都應該記錄在 SQLite 中
可用。

建議的表格概念：

```text
config_versions
  id
  loaded_at
  source_path
  content_hash
  normalized_json
  applied_by
  reload_reason
```

目的：

- 使運行時行為可審計，
- 允許交易決策追溯到配置版本，
- 支援稍後安全回滾或診斷。

### 內部代表

運行時程式碼不應到處傳遞原始字典。

首選方法：- 將 TOML 解析為類型化的配置對象，
- 驗證一次，
- 產生解析的運行時配置，
- 將類型化物件傳遞給模組。

首先使用資料類別或其他輕量級型別模型。避免添加大
依賴僅用於配置，除非稍後驗證複雜性證明它是合理的。

### WebSocket 同步

WebSocket 支援是同步層，而不是命令命令路徑。

規則：

- REST 對於啟動快照、交換命令和
  和解修復。
- 公共市場流事件可能會更新即時市場快取。
- 私人訂單、部位和執行串流事件可能會即時更新
  帳戶緩存。
- 必須透過心跳/最近訊息的新鮮度來追蹤流的運行狀況。
- 如果WebSocket資料在啟用時陳舊或不可用，則策略輸入
  評估應該失敗關閉。
- 從 WebSocket 事件建立的 Redis 快取條目保持可重建並且可以
  不持久的交易狀態。
- 具體的 Bybit WebSocket 適配器必須保留在明確模式防護後面，並且
  預設情況下不得啟用即時交易。

## 運作穩定性

第 7 階段為重構的運行時建立本機操作基礎。活動活動規則：

- 重要的運行時間、重載、協調、快取、WebSocket、交換和
  儲存事件應使用類型化的操作事件負載。
- 結構化操作日誌在發出時應該是穩定的 JSON 有效負載。
- 通知嚴重性等級為 `info`、`warning`、`safe_mode` 和 `error`。

健康檢查規則：

- SQLite、Redis、WebSocket 和交換準備情況必須單獨報告。
- 試運轉交換準備不得需要網路存取。
- 示範/即時交換準備可以檢查憑證是否存在，但只讀
  網路預檢需要明確的用戶批准。

彈性規則：

- 重試/退避策略必須明確且可測試。
- 不要盲目重試下單，除非冪等性和交易所
  處理接受歧義。
- 斷路器應在策略之前保護重複的外部故障
  邏輯繼續正常進行。

驗證規則：- `bybit-automation verify-dry-run --config ...` 為本地無網絡
  驗證命令。
- 在運行煙霧之前，`verify-dry-run` 必須拒絕非 `dry_run` 配置
  檢查。
- Bybit演示驗證屬於下一個候選版本階段並開始
  僅在明確批准後才進行唯讀連線檢查。

### 目前舊版映射

舊版 JSON 範本映射大致如下：

- `exchange_config.json.template` -> `[app]`, `[exchange]`,
  `[exchange.bybit]`
- `strategy_config.json.template` -> `[runtime]`, `[strategy.defaults]`,
  `[[symbols]]`
- `trailing_config.json.template` -> `[risk]`, `[risk.defaults]`

在遷移過程中，保留舊檔案作為參考，直到新的設定路徑出現
工作並經過驗證。
