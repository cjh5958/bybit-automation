# bybit-automation

一個以安全為優先的 Bybit futures 交易自動化 runtime，支援策略進場、持倉風控、狀態持久化與營運檢查。

預設模式是 `dry_run`。在 `dry_run` 模式下，程式不會連線 Bybit，也不會送出訂單。若要使用 demo 或 live，必須在本機 config 明確啟用，並透過環境變數提供 API credentials。

## 功能

- 單程序 runtime，統一管理策略、風控、持倉與訂單。
- 集中式 `OrderManager`，所有下單、取消、平倉都必須經過它。
- 使用 TOML 設定檔，secret 透過環境變數提供。
- SQLite 持久化 orders、order events、positions、decisions、bot state、config versions。
- 啟動時 reconciliation，遇到未知或不一致的交易所狀態會進入 `SAFE_MODE`。
- 可選 Redis realtime cache，沒有 Redis 時會降級成 no-op cache。
- WebSocket event ingestion foundation 與 stale market-data guard。
- Manual config reload，會區分可 hot reload 與需要 restart 的變更。
- Health checks、typed operational events、notification severity、retry/backoff、circuit breaker、dry-run verification。

## 需求

- Git
- `uv`
- 由 `uv` 管理的 Python 3.11 或更新版本

安裝依賴：

```bash
uv sync --locked
```

如果你的機器遇到 uv cache 或 managed Python 權限問題，可以使用專案內 runtime 目錄：

```bash
# macOS / Linux
export UV_CACHE_DIR=.uv-cache
export UV_PYTHON_INSTALL_DIR=.uv-python

# Windows PowerShell
$env:UV_CACHE_DIR='.uv-cache'
$env:UV_PYTHON_INSTALL_DIR='.uv-python'
```

## 設定

先從 template 建立本機設定檔：

```bash
cp configs/config.template.toml configs/config.toml
```

Windows PowerShell：

```powershell
Copy-Item configs\config.template.toml configs\config.toml
```

接著編輯 `configs/config.toml`。

### Runtime 模式

本機檢查使用 `dry_run`：

```toml
[app]
mode = "dry_run"
```

Bybit demo trading 使用 `demo`：

```toml
[app]
mode = "demo"
```

在完成 demo 驗證並仔細檢查設定前，不要使用 `live`。

### API Credentials

Config 裡放的是環境變數名稱，不是 secret 本身：

```toml
[exchange.bybit]
api_key_env = "BYBIT_API_KEY"
api_secret_env = "BYBIT_API_SECRET"
```

實際 credentials 放在 shell 環境變數。

PowerShell：

```powershell
$env:BYBIT_API_KEY="your-demo-api-key"
$env:BYBIT_API_SECRET="your-demo-api-secret"
```

macOS / Linux：

```bash
export BYBIT_API_KEY="your-demo-api-key"
export BYBIT_API_SECRET="your-demo-api-secret"
```

不要把 API key 或 secret commit 到 git。

### Symbols

設定要監控的交易對：

```toml
[[symbols]]
symbol = "BTC/USDT:USDT"
enabled = true
long_amount_usdt = 5
short_amount_usdt = 5
```

初次 demo 測試建議只使用一個高流動性 symbol，例如 `BTC/USDT:USDT`。如果 ccxt 回報 `BadSymbol`，請從 config 移除該 symbol，或換成你的 Bybit 環境有支援的 market。

### 策略金額

如果只想先觀察 demo runtime，不想送出訂單，可以把金額設為 `0`：

```toml
long_amount_usdt = 0
short_amount_usdt = 0
```

準備測試 demo order flow 時，再改成很小的 demo 金額。

### 可選服務

Redis 是可選的：

```toml
[cache.redis]
enabled = false
```

WebSocket 目前是同步基礎建設。除非你正在測試該層，否則先保持關閉：

```toml
[websocket]
enabled = false
```

## 使用方式

執行一次 runtime tick 做測試：

```bash
uv run bybit-automation test --config configs/config.toml
```

啟動長時間服務：

```bash
uv run bybit-automation run --config configs/config.toml
```

使用 `Ctrl+C` 停止服務。shutdown reason 會寫入 SQLite `bot_state`。

執行本機、不連網的 dry-run verification：

```bash
uv run bybit-automation verify-dry-run --config configs/config.template.toml
```

驗證並套用 manual config reload candidate：

```bash
uv run bybit-automation reload \
  --current configs/config.toml \
  --candidate configs/config.new.toml
```

Manual reload 只會套用可 hot-reload 的變更。不安全的變更會回傳需要 restart，並保留目前 active config。

## SAFE_MODE

Runtime 啟動時會比對交易所 positions/open orders 與 SQLite 狀態。如果交易所狀態未知或不一致，runtime 會進入 `SAFE_MODE`。

進入 `SAFE_MODE` 後：

- 暫停新的策略進場。
- 已知 positions 仍可執行 risk evaluation。
- 所有交易所副作用仍必須經過 `OrderManager`。
- reconciliation 與 tick 狀態會寫入 SQLite `bot_state`。

常見觸發原因：

- 交易所有 open order，但 SQLite 不認得。
- 啟動時抓取 exchange snapshot 失敗。
- reconciliation issue 被標記為 `safe_mode`。

解除方式不是直接按一個 clear 指令，而是先修正造成不一致的根因，然後重啟 runtime，讓 startup reconciliation 重新通過。

## 檢查 Runtime 狀態

預設 SQLite 路徑：

```text
data/bot.sqlite3
```

檢查 bot state：

```bash
uv run python -c "import sqlite3; conn=sqlite3.connect('data/bot.sqlite3'); print(conn.execute('select key,value_json from bot_state').fetchall()); conn.close()"
```

檢查 decisions 與 orders 數量：

```bash
uv run python -c "import sqlite3; conn=sqlite3.connect('data/bot.sqlite3'); print('strategy_decisions', conn.execute('select count(*) from strategy_decisions').fetchone()[0]); print('orders', conn.execute('select count(*) from orders').fetchone()[0]); print('order_events', conn.execute('select count(*) from order_events').fetchone()[0]); conn.close()"
```

## 開發

執行測試：

```bash
uv run pytest
```

執行 lint：

```bash
uv run ruff check .
```

使用 template config 跑安全的一次 tick 測試：

```bash
uv run bybit-automation test --config configs/config.template.toml
```

## 目前狀態

Runtime 目前支援本機 dry-run、Bybit demo REST runtime 測試、SQLite persistence、manual reload checks、health reporting，以及營運安全基礎元件。

進入 live trading 前建議：

1. 先跑 `verify-dry-run`。
2. 使用單一支援的 symbol 跑 demo mode。
3. 檢查 SQLite state 與 Bybit demo open orders。
4. 執行較長時間的 demo service session。
5. 最後才規劃受控的 demo order lifecycle tests。
