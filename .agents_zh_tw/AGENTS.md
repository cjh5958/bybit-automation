# 代理.md

本文檔是人工智慧代理和開發人員繼續進行的工作交接
重構這個儲存庫。

## 專案概要

該儲存庫目前包含一個小型 Bybit 期貨交易機器人，分為
兩個獨立的Python腳本：

- `strategy_bybit.py`
- `trail_bybit.py`

還有一個幫助程序設定腳本：

- `fast_setup.py`

目前的遺留腳本似乎是作為個人/實驗性編寫的
使用 `ccxt`、`pandas` 和腳本本地通知的自動交易系統。

使用者的目標是逐步將其重構為更可靠的單一進程
交易服務：

- `uv` 用於 Python 環境和依賴項管理。
- SQLite 用於持久狀態、事件歷史記錄和復原。
- Redis 用於即時快取、協調和短期狀態。
- 基於 WebSocket 的同步很有用。
- 更安全的運行時行為、狀態恢復、協調和配置重新載入。

用戶已經創建了 `dev` 分支並希望工作繼續進行
小的可驗證階段。

## 目前儲存庫狀態

觀察到的文件：- `strategy_bybit.py`
- `trail_bybit.py`
- `fast_setup.py`
- `requirements.txt`
- `configs.template/exchange_config.json.template`
- `configs.template/strategy_config.json.template`
- `configs.template/trailing_config.json.template`

目前來自 `requirements.txt` 的依賴項：

```text
ccxt==4.4.45
pandas==2.2.3
```

先前檢查的環境說明：

- 在原始工作階段中從 Windows 上的 PowerShell 檢查該項目。
- Shell 和 Python 的可用性在未來的電腦或會話上可能會有所不同。
- 未來的代理應該在編碼開始時檢查開發環境
  工作而不是假設全域工具可用。
- 重構應該儘早引入 `uv` 並且偏好 Python 的 `uv run ...`
  配置項目後執行。

## 目前腳本行為

### `strategy_bybit.py`

腳本是入場/訂單策略機器人。

觀察到的行為：- 從 `./configs` 載入設定檔：
  - `exchange_config.json`
  - `strategy_config.json`
  - `trailing_config.json`
- 透過 `ccxt.bybit` 連接到 Bybit。
- 可選擇啟用Bybit 模擬交易。
- 為配置的交易對設定槓桿。
- 從設定中讀取 `trading_pairs`。
- 在 `monitor_interval` 上執行輪詢循環。
- 對於每對：
  - 取得目前的股票價格。
  - 取得 OHLCV 蠟燭。
  - 計算 EMA 趨勢。
  - 計算 ATR。
  - 計算平均幅度。
  - 使用波動率導出的距離來下限價掛單：
    - 如果趨勢看漲，請將買入限制設定為低於目前價格。
    - 如果趨勢看跌，則將賣出限額設定為高於目前價格。
  - 在下新訂單之前取消該貨幣對的未結訂單。
- 使用槓桿、費用將配置的 USDT 金額轉換為合約金額，
  並兌換最低金額。

推斷開發者意圖：

- 自動將限價掛單保持在波動率調整價格附近。
- 使用 EMA 作為趨勢過濾器。
- 使用ATR和平均振幅來選擇階距。
- 根據配置的交易品種管理多頭和空頭機會。

### `trail_bybit.py`

該腳本是頭寸風險/追蹤機器人。

觀察到的行為：- 從 `./configs` 載入相同的設定檔。
- 透過 `ccxt.bybit` 連接到 Bybit。
- 使用設定憑證初始化舊腳本本機通知程式碼。
- 在 `monitor_interval` 上執行頻繁的輪詢循環。
- 取得所有位置。
- 對於每個非零位置：
  - 跳過 `blacklist` 中的符號。
  - 偵測新位置並發送舊通知。
  - 計算當前利潤百分比。
  - 追蹤記憶中最高的利潤百分比。
  - 根據閾值分配尾隨層：
    - `low_trail_enable_threshold`
    - `first_trail_enable_threshold`
    - `second_trail_enable_threshold`
  - 適用：
    - 固定停損，
    - 低層追蹤停損，
    - 第一層追蹤停損，
    - 第二層追蹤停損。
  - 使用市價訂單平倉。
  - 發送有關偵測到/關閉位置的舊訊息。

推斷開發者意圖：

- 讓另一個進程/腳本管理已經開放的職位。
- 透過停損和多階段追蹤止盈保護部位。
- 當偵測到或平倉時通知使用者。

## 目前的架構問題主要問題不僅僅是程式碼風格。運行時模型是有風險的，因為兩個
獨立的進程在同一個交易帳戶上運行，沒有共享狀態。

已知或推斷的問題：- `strategy_bybit.py` 和 `trail_bybit.py` 皆初始化交換客戶端並
  獨立運作。
- 當追蹤/風險腳本處於運行狀態時，策略可以取消並重新建立訂單
  管理職位，沒有共享狀態機。
- 沒有中央`OrderManager`。
- 沒有持久狀態：
  - 最高利潤，
  - 活動尾隨層，
  - 最後已知的位置狀態，
  - 訂單生命週期，
  - 戰略決策。
- `highest_profits`、`current_tiers` 和偵測到的位置僅存在於記憶體中。
  它們在重新啟動時丟失。
- 配置僅在啟動時載入。
- 設定檔與`ChainMap`合併；重複的鍵，例如
  `monitor_interval` 是不明確的，可以互相影子。
- 記錄器設定重複。
- 兩個腳本都包含 mojibake/編碼損壞的繁體中文日誌
  字串。有些字串在語法上可能不安全，應該檢查一次
  工作Python運行時可用。
- REST 輪詢用於市場/帳戶狀態，速度較慢，速率有限，
  並且比 WebSocket 流更容易受到網路漂移的影響。
- 沒有明確的安全模式、協調、斷路器或重新啟動恢復。- 目前的錯誤處理包括應該修復的模式，例如
  遞歸重試路徑和網路狀態處理較弱。

## 目標產品意圖

預期的未來系統應該像單一交易服務一樣運作：

```text
market/account sync
  -> strategy decision
  -> order intent
  -> order execution
  -> position tracking
  -> risk/trailing decision
  -> durable event/state storage
  -> notification
```

服務應該有一個行程、一個協調的運行時狀態和一條路徑
對於所有交換副作用。

重要設計原則：

> 所有交易所的副作用，尤其是下訂單、取消訂單和
> 平倉，必須經過集中`OrderManager`。

這可以防止策略和風險邏輯之間的操作衝突。

## 建議的未來架構

建議的封裝佈局：

```text
pyproject.toml
uv.lock
src/
  bybit_automation/
    __init__.py
    main.py
    app.py
    config.py
    logging.py
    exchange_client.py
    notifier.py
    strategy.py
    risk.py
    orders.py
    positions.py
    state.py
    storage/
      sqlite.py
      repositories.py
    cache/
      redis.py
tests/
configs.template/
```

建議的運行時模組：- `App` / `BotRuntime`
  - 擁有生命週期和事件循環。
- `ConfigLoader`
  - 載入、驗證、版本和重新載入配置。
- `ExchangeClient`
  - Bybit/ccxt 操作的薄包裝。
- `MarketDataService`
  - 提供價格和 OHLCV/K 線資料。
- `StrategyEngine`
  - 入場訊號的純粹決策邏輯。
- `RiskManager`
  - 停損與追蹤停盈的純決策邏輯。
- `OrderManager`
  - 唯一允許下達/取消/關閉兌換訂單的模組。
- `PositionManager`
  - 追蹤活動位置和位置狀態。
- `StateStore`
  - 由 SQLite 支援的持久性狀態和事件儲存。
- `RealtimeCache`
  - Redis 支援最新價格、鎖定和短期運行時資料。
- `Notifier`
  - 本地操作通知事件和未來的通知管道。

每個符號的建議狀態機：

```text
IDLE
  -> ENTRY_ORDER_PLACED
  -> POSITION_OPEN
  -> TRAILING
  -> CLOSING
  -> CLOSED
```

狀態機應該防止矛盾的操作，例如放置
符號關閉時的新條目。

## 勾選定義

先前的討論澄清了「tick」的意思：

- 程序決策標記：機器人決策管道的一次傳遞。

它不應該意味著：

- 每個交易所匹配引擎勾選。現有策略不適合處理每個交易所交易報價。
目前的腳本意味著節奏較慢：

- 策略循環：大致分鐘級投票。
- 尾隨循環：大致為二級輪詢。

未來的設計應該分開：

- WebSocket/事件攝取節奏。
- 決策循環節奏。
- 策略評估節奏。
- 風險/追蹤評估節奏。
- REST 協調節奏。

目標 SLA 範例：

```text
Market data freshness target: under 500ms when WebSocket is healthy.
Risk decision cadence: 250ms to 1s, configurable.
Strategy decision cadence: 30s to 60s, configurable.
REST reconciliation cadence: 10s to 30s, configurable.
```

不要承諾處理每個交易所交易報價。相反，要調整節奏
明確並強制執行最後期限。

## SQLite 和 Redis 的職責

### SQLite

SQLite 是狀態和歷史的持久來源。

使用 SQLite 用於：

- 訂單
- 訂購活動
- 交易/執行
- 位置快照
- 戰略決策
- 風險事件
- 機器人狀態
- 配置版本
- 通知日誌

推薦的 SQLite 行為：

- 啟用 WAL 模式。
- 使用事務進行多步驟狀態更新。
- 對於重要的交易事件，首選僅附加事件記錄。
- 儲存足夠的資料以便在進程重新啟動後恢復。

### Redis

Redis是即時快取和協調層，而不是持久性來源
真相。

將 Redis 用於：- 最新的股票代號/標記價格
- 近期K線緩衝
- 活躍倉位緩存
- 開啟訂單緩存
- 每個符號鎖
- 輕量級發布/訂閱事件
- 配置重新載入訊號

如果 Redis 重新啟動，機器人必須能夠從 SQLite 以及
交換。

## 資料安全與復原

未來的服務應該處理關閉、網路故障和重新啟動
無需根據過時的假設進行盲目交易。

要求的行為：

- 啟動時，在策略交易之前執行對帳：
  - 從交易所取得未結訂單，
  - 從交易所獲取活躍頭寸，
  - 如果需要的話獲取餘額，
  - 將交換狀態與 SQLite 最後已知狀態進行比較。
- 如果狀態不一致，請輸入 `SAFE_MODE`。
- 在 `SAFE_MODE` 中：
  - 暫停新條目，
  - 如果狀態充分了解，則允許採取降低風險的行動，
  - 通知用戶，
  - 恢復前需要手動確認或成功協調。
- 盡可能使用客戶訂單 ID 將本地決策與交易所關聯起來
  訂單。
- 正常關閉時：
  - 停止建立新的訂單意圖，
  - 安全地完成或取消待定的內部工作，
  - 將關鍵狀態刷新到 SQLite，
  - 記錄最終運行時狀態。重要原則：

> 系統不能保證永遠不會發生故障。應該保證
> 發生故障後，它可以確定自己知道什麼、不知道什麼，並避免
> 犯了第二個不安全的錯誤。

## WebSocket 方向

對於市場/帳戶狀態，首選使用 WebSocket 進行同步。

推薦分割：

```text
WebSocket:
  - ticker / mark price
  - kline
  - order update
  - position update
  - execution update

REST:
  - initial snapshot
  - create orders
  - cancel orders
  - close positions
  - periodic reconciliation
  - fallback after WebSocket disconnect/reconnect
```

不要完全刪除 REST。 WebSocket是即時串流；休息仍然是
權威修正和命令路徑。

所需的 WebSocket 行為：

- 心跳/ping監測
- 自動重新連線並進行退避
- 陳舊資料檢測
- 透過 REST 協調恢復訊息間隙/漂移
- 如果市場/帳戶狀態過時，則暫停策略

## 配置重新載入方向

當前腳本僅在初始化期間載入配置。未來版本
應該支援受控配置重新載入。

規範的目標配置結構在 `SPEC.md` 中定義。未來的代理商
在不更新 `SPEC.md` 的情況下不應發明不同的配置形狀
解釋原因。

推薦的第一個實作：- 手動重新載入命令。
- 在應用之前驗證完整配置。
- 計算並記錄配置差異。
- 僅套用安全的可熱重載欄位。
- 在 SQLite 中儲存設定版本。
- 如果驗證失敗，則保留現有設定。

潛在的熱重載欄位：

- 交易對啟用/停用
- 訂單金額
- EMA週期
- 價值乘數
- 尾隨閾值
- 黑名單
- 監控間隔
- 通知嚴重性閾值

不應該隨意熱重載的欄位：

- API 金鑰/秘密
- 交換類型
- 帳戶模式
- 資料庫路徑
- Redis連接
- 槓桿作用，除非實施安全的明確流程

潛在的重載機制：

- CLI/管理命令
- 文件修改觀察者
- Redis 發布/訂閱訊號

從手動重新加載開始。僅在驗證和安全行為後添加自動化
是固體。

## 分階段重構計劃

在進入下一階段之前，每個階段都應該可以獨立測試。

### 第 0 階段：使用 `uv` 進行專案基礎

目標：

- 在不改變交易行為的情況下建立現代Python項目骨架。

任務：- 新增 `pyproject.toml`。
- 產生 `uv.lock`。
- 轉向 `src/bybit_automation/` 封裝佈局。
- 新增 CLI 入口點。
- 保留遺留腳本以供參考。
- 新增基準測試/lint 工具。

建議命令：

```bash
uv sync
uv run python -m bybit_automation
uv run pytest
```

驗收標準：

- `uv sync` 成功。
- 新包導入。
- 無操作/新的運行時入口點啟動。
- 除非有意遷移，否則舊腳本保持不變。

### 第 1 階段：單一進程運行時，基於 REST

目標：

- 將兩個運行時進程合併為一個協調進程，同時仍使用
  休息輪詢。

任務：

- 建立 `App` / `BotRuntime`。
- 新增統一配置載入。
- 新增統一記錄器。
- 摘錄：
  - `ExchangeClient`
  - `StrategyEngine`
  - `RiskManager`
  - `OrderManager`
  - `PositionManager`
  - `Notifier`
- 在入場策略和追蹤風險邏輯之間共用一種執行時間狀態。

驗收標準：

- 一個流程可以同時運作進入邏輯和風險邏輯。
- 策略和風險並不直接衝突。
- 所有交易所副作用均透過 `OrderManager`。
- 演示模式可以啟動並執行唯讀同步。

### 第 2 階段：SQLite 持久化

目標：

- 保留機器人狀態和事件歷史記錄。

任務：- 新增 SQLite 架構和遷移或架構引導。
- 啟用 WAL 模式。
- 商店訂單、訂單事件、倉位快照、策略決策、風險事件、
  配置版本和機器人狀態。
- 保持追蹤狀態，例如最高利潤和當前等級。

驗收標準：

- Bot 建立一個 SQLite 資料庫。
- 寫下重要的決定/事件。
- 重新啟動不會遺失追蹤狀態。
- 可以手動檢查 SQLite 狀態。

### 第 3 階段：安全啟動與協調

目標：

- 確保啟動和重新啟動安全性。

任務：

- 啟動時取得未平倉訂單和活躍部位。
- 將交換狀態與 SQLite 狀態進行比較。
- 實施 `SAFE_MODE`。
- 添加優雅關閉。

驗收標準：

- 啟動始終在新條目之前進行協調。
- 不一致的狀態會暫停新條目。
- Ctrl+C/SIGTERM 儲存狀態並乾淨退出。

### 第 4 階段：Redis 快取和協調

目標：

- 新增Redis以實現即時數據和輕量級協調。

任務：

- 新增 `RealtimeCache` 抽象。
- 儲存最新價格、K線快取、未結帳訂單快取、活躍部位快取、
  符號鎖和配置重新載入訊號。
- 定義 Redis 不可用時的行為。

驗收標準：- 機器人可以在可用時使用 Redis。
- Redis 故障不會破壞持久狀態。
- 快取可以從 SQLite 加交換重建。

### 第 5 階段：WebSocket 同步

目標：

- 減少 REST 輪詢並提高及時性。

任務：

- 新增股票/標記價格/K 線的公共 WebSocket 流。
- 新增私人 WebSocket 流以進行訂單/部位/執行更新。
- 保持 REST 進行命令和協調。
- 新增心跳、重新連線、過時資料偵測。

驗收標準：

- 透過 WebSocket 更新市場/帳戶狀態。
- REST 輪詢負載減少。
- WebSocket 斷開連線暫停或安全降級。
- REST 協調修復了偏差。

### 第 6 階段：設定熱重載

目標：

- 允許安全性配置變更而無需完全重新啟動。

任務：

- 新增配置架構驗證。
- 新增手動重新載入條目。
- 儲存配置版本。
- 僅套用安全的可熱重載欄位。

驗收標準：

- 有效的重新加載可以安全地應用。
- 無效的重新載入將被拒絕，而不更改執行時間配置。
- 重新載入被記錄並可選擇通知。

### 第 7 階段：運作穩定性

目標：

- 使服務更像生產。

任務：- 新增結構化日誌記錄。
- 新增健康檢查。
- 新增通知嚴重性。
- 新增重試/退避。
- 新增斷路器。
- 新增試運轉模式。
- 如果需要，新增部署助手。

驗收標準：

- 長時間運行演示模式穩定。
- 故障是可觀察和分類的。
- Exchange/API/Redis/DB 問題會觸發已知行為。

## 測試策略

從不需要即時交換存取的測試開始。

建議的早期測試：

- 配置解析和驗證。
- EMA/ATR/振幅計算。
- 策略決策邏輯。
- 風險/追蹤決策邏輯。
- 位置狀態轉換。
- SQLite 儲存庫持久性。
- 使用虛假交換資料的對帳行為。

使用假交換客戶端進行單元測試。不需要 Bybit 憑證
CI 或正常的本地測試運行。

## 未來代理人的實作說明- 除非使用者要求，否則使用繁體中文進行使用者導向的解釋
  否則。
- 保持變更的階段性和可審查性。
- 不要一步重寫整個系統。
- 在新實作達到功能之前不要刪除舊腳本
  奇偶校驗或使用者明確批准刪除。
- 使用 `uv` 進行所有 Python 環境工作。
- 首選 `rg`/`rg --files` 進行儲存庫檢查。
- 在改變交易行為之前，確定改變是否會影響：
  - 下訂單，
  - 訂單取消，
  - 平倉，
  - 停損，
  - 追蹤止盈。
- 將所有即時交易副作用視為高風險。
- 重構和測試期間預設為演示/空運行行為。
- 在提取純邏輯之前或同時添加測試。
- 如果引入 Redis 或 SQLite，請保持抽象的精簡和可測試。
- 在 git 工作樹中保留使用者變更。不要恢復不相關的變更。

## 專案和對話限制

未來的代理應該遵循這些約束，除非用戶明確更改
方向。

### 溝通方式- 預設使用繁體中文與使用者溝通。
- 保持解釋簡潔但技術上精確。
- 討論架構時，分開：
  - 從儲存庫確認的事實，
  - 關於開發者意圖的推斷，
  - 提出的未來設計。
- 不要將假設當作事實。
- 如果決定影響即時交易行為，請在先前明確指出風險
  實施它。
- 喜歡在工作時更新簡短的進度，而不是等到工作結束
  這是一項漫長的任務。
- 當任務是探索性的時，在提出程式碼變更之前總結發現結果。

### 編碼風格- 比起巧妙的抽象，更喜歡簡單、明確的 Python。
- 保持模組較小並專注於一項職責。
- 支援運行時狀態和決策的資料類或類型化模型。
- 新增程式碼的類型提示。
- 偏好使用純函數進行策略和風險計算，以便對其進行測試
  沒有即時交換存取權限。
- 將交易所副作用隔離在 `ExchangeClient` 和
  `OrderManager`。
- 不要讓策略或風險模組直接呼叫`ccxt`。
- 不要讓持久性或快取實作細節洩漏到策略中
  邏輯。
- 除非當前階段需要，否則避免廣泛重寫。
- 保持評論簡短且有用；避免重述明顯的程式碼行為。

### 重構邊界- 在早期階段保留遺留腳本：
  - `strategy_bybit.py`
  - `trail_bybit.py`
  - `fast_setup.py`
- 在使用者批准或替換之前，請勿刪除或重命名舊文件
  達到功能平價。
- 進行增量提交/更改以對應到商定的階段。
- 不引入WebSocket、Redis、SQLite、設定重新載入和策略更改
  全部在同一步驟中。
- 每個階段都應該使專案處於可運行或至少可匯入的狀態
  狀態。
- 在進入下一階段之前，使用本機命令驗證目前階段
  當工具可用時。

### 交易安全規則- 新運行時程式碼的預設示範或試運行行為。
- 切勿新增預設下即時訂單的代碼。
- 任何即時交易路徑都必須需要明確配置。
- 任何可以下達、取消或關閉訂單的模組都必須易於審核。
- 新的訂單相關代碼應盡可能支援冪等性。
- 避免盲目重試下單。重試行為必須考慮是否
  交易所可能已經接受了先前的請求。
- 在未知或不一致的交換狀態下，優先選擇 `SAFE_MODE` 而不是繼續
  正常的策略執行。
- 不要依賴Redis作為交易狀態的唯一記錄。
- SQLite應該被視為持久的本機記錄，同時交換狀態
  仍然是必須協調的外在權威。
- 第 2 階段保持每個符號的尾隨狀態。第 3 階段必須定義其生命週期：
  當對帳證明部位已關閉、清除或檔案已過時時
  `symbol_trailing_state` 在允許該交易品種未來新部位之前
  重複使用運行時狀態。新職位不得繼承舊職位
  `highest_profit_pct` 或 `trailing_tier`。

### 測試和驗證要求- 新的純策略/風險邏輯應包括單元測試。
- 測試不得需要真實的 Bybit 憑證。
- 使用假交易所客戶端或固定裝置進行訂單、頭寸和對帳
  行為。
- 變更配置載入時，測試無效配置和缺失欄位行為。
- 更改持久性時，在可行的情況下測試重新啟動/恢復行​​為。
- 更改訂單流程時，測試狀態轉換和重複操作
  預防。
- 如果由於缺少工具而無法運行命令，請在中明確說明
  最終的回應。

### 開發環境標準

該專案必須可以在 macOS、Linux 和 Windows 上重建，而無需依賴
系統Python版本。

開發機器的最低標準：- Git 可用。
- `uv` 可在 `PATH` 上使用。
- 本專案透過 `uv` 管理 Python。
- 專案運行時Python是3.11或更高版本，符合`pyproject.toml`。
- 測試、lint 和 CLI 煙霧檢查透過 `uv run` 運行，而不是透過全域運行
  `python`、`pip`、`pytest` 或 `ruff` 指令。
- 本地運行時工件，例如 `.venv`、`.uv-cache`、`.uv-python`、本地
  設定檔和 `data/` 未提交。

編碼會話開始時所需的本機環境檢查：- 辨識主機作業系統、體系結構、shell 和目前時區/日期上下文。
- 編輯前檢查目前 git 分支和工作樹狀態。
- 檢查`uv`是否可用以及`uv run python --version`是否報告
  支援的 Python 版本。
- 檢查專案本地`UV_CACHE_DIR`和`UV_PYTHON_INSTALL_DIR`是否
  由於快取、權限或缺少解釋器問題而需要。
- 檢查相關環境變數而不列印秘密值：
  - `BYBIT_API_KEY` 存在或缺失，
  - `BYBIT_API_SECRET` 存在或缺失，
  - 啟用 Redis 時 `REDIS_URL` 存在或缺失，
  - 如果非預設配置路徑存在，則 `BYBIT_AUTOMATION_CONFIG` 存在或缺失
    預計。
- 檢查活動配置是提交的範本還是本機運行時
  配置，並在執行任何命令之前確認所選的 `app.mode`
  可以到達Bybit。
- 檢查當前階段所需的外部服務：
  - SQLite路徑是可寫的，
  - 僅當驗證 Redis 啟用的行為時才能訪問 Redis，
  - Bybit網路存取和憑證僅在明確的情況下才可用
    演示/即時連接測試已獲得批准。- 當任何環境限制影響時，將其記錄在活動階段日誌中
  驗證，尤其是缺少憑證、無法存取網路、
  缺少 Redis，或回退到專案本地 uv 快取/運行時目錄。

推薦的全新結帳環境重建流程：1. 如果電腦尚未安裝基本作業系統工具，請安裝這些工具。
   - Ubuntu/Debian：
     `sudo apt-get update && sudo apt-get install -y git curl ca-certificates`
   - macOS：
     如果 `git` 不可用，請安裝 Xcode 命令列工具，或使用 Homebrew。
   - 窗：
     安裝適用於 Windows 的 Git 並使用 PowerShell。
2.使用Astral官方安裝套件或機器自備的套件安裝`uv`
   經理。
   - Ubuntu/Linux:
     `curl -LsSf https://astral.sh/uv/install.sh | sh`
   - 附 Homebrew 的 macOS：
     `brew install uv`
   - macOS 官方安裝程式：
     `curl -LsSf https://astral.sh/uv/install.sh | sh`
   - Windows PowerShell：
     `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
3. 重新啟動 shell 或根據安裝程式輸出更新 `PATH`，然後
   驗證：
   - `uv --version`
   - `git --version`
4. 在儲存庫根目錄中，使用專案本地 uv 快取/運行時目錄
   機器存在權限問題或代理需要完全一次性狀態時：
   - macOS/Linux：
     `export UV_CACHE_DIR=.uv-cache`
     `export UV_PYTHON_INSTALL_DIR=.uv-python`
   - Windows PowerShell：
     `$env:UV_CACHE_DIR='.uv-cache'`
     `$env:UV_PYTHON_INSTALL_DIR='.uv-python'`
5. 重新建立託管Python和虛擬環境：
   - `uv python install 3.11`
   - `uv sync --locked`
6. 驗證環境：
   - `uv run python --version`
   - `uv run pytest`
   - `uv run ruff check .`
   - `uv run bybit-automation`Ubuntu 從全新結帳快速啟動：

```bash
sudo apt-get update
sudo apt-get install -y git curl ca-certificates
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
export UV_CACHE_DIR=.uv-cache
export UV_PYTHON_INSTALL_DIR=.uv-python
uv python install 3.11
uv sync --locked
uv run python --version
uv run pytest
uv run ruff check .
uv run bybit-automation
```

預期結果：

- `uv run python --version` 報告 Python 3.11 或更高版本。
- 單元測試和 Ruff 在沒有即時 Bybit 憑證的情況下通過。
- CLI 冒煙測試保留在 `dry_run` 中，並使用範本配置。
- CLI可以建立或更新`data/bot.sqlite3`；這是預期的並且
  `data/` 被 git 忽略。

如果開發機器無法安裝 `uv` 或 Python 3.11+，請在編碼之前停止
並將阻塞者記錄在`.agents/TODO.md`或活動階段日誌中。不
嘗試使用不支援的系統 Python 版本驗證此專案。

### 依賴關係和工具規則- 使用 `uv` 進行 Python 依賴項和環境管理。
- 首選 `uv sync --locked` 進行可重複的依賴安裝
  `uv.lock`。
- 重建環境後，對所有專案指令使用 `uv run ...`。
- 當機器具有全域時，首選項目本機 `uv` 運行時/快取位置
  快取或託管 Python 權限問題。
- 原理：不同機器上的先前會話命中全域緩存，
  託管Python和shell `PATH`的差別。保持快取並進行管理
  Python 安裝在工作空間內，讓安裝更方便攜帶。
- 如果 `.venv` 指向缺少的 Python 解釋器，則讓 `uv` 在之後重新建立它
  設定 `UV_CACHE_DIR` 和 `UV_PYTHON_INSTALL_DIR`。
- 在新會話或新機器上開始編碼工作時，檢查
  在做出假設之前先了解開發環境。至少檢查：
  - 主機作業系統、架構、外殼、時區/日期上下文、
  - 目前 git 分支和工作樹狀態，
  - 是否安裝了`uv`，
  - 是否可以透過 `uv` 或 shell 取得可用的 Python 運行時，- 相關環境變數僅透過存在，從不透過列印秘密
    價值觀，
  - 活動配置路徑並選擇 `app.mode`，
  - 當前階段所需的外部服務是否可用
    （例如僅在處理 Redis 行為時使用 Redis，或 Bybit 演示
    僅當已批准的演示連接測試在範圍內時才提供憑證）。
- 如果環境不完整，請解釋問題並提出具體的建議
  在繼續依賴它的更改之前修復。
- 一旦 `pyproject.toml` 存在，首選透過 `uv add` 新增依賴項。
- 避免添加嚴重的依賴項，除非它們解決了明確的問題。
- 首先保持 SQLite 存取簡單。不要引入大型 ORM，除非
  模式的複雜性稍後證明了它的合理性。
- 在抽象後面加入 Redis，以便測試可以在沒有 Redis 伺服器的情況下運行。
- 不需要 Docker 或外部服務進行基本單元測試。

### 文檔規則- 當專案方向、階段、安全規則或
  經營假設發生變化。
- 當專案級技術規格變更時更新`SPEC.md`，
  特別是配置形狀、運行時狀態語意、持久性規則，以及
  安全行為。
- 每當工作完成、新發現、被阻止或
  已過時。已完成的工作不應作為未檢查的 TODO 項目留下。
- 使使用者導向的文件與實際可運行的命令保持一致。
- 在計劃的命令被執行之前，不要將其記錄為工作命令
  按計劃實施或明確標記它們。
- 如果做出新的架構決策，記錄原因，而不僅僅是最終的
  選擇。

### 版本控制工作流程

`dev`分支是代理的標準工作分支。用戶將決定
何時將 `dev` 合併到 `main` 中。

未來的代理商必須使用這個標準的 Git 工作流程，除非使用者明確指出
改變它：1. 首先檢查目前分支和工作樹：
   - `git branch --show-current`
   - `git status --short`
2. 僅在 `dev` 上工作，除非使用者批准另一個分支。
3. 在編輯之前，確定是否有未提交的變更。
   保留使用者變更並且不恢復不相關的檔案。
4. 制定一個與目前階段或任務相關的小型、連貫的變更集。
5. 每當任務狀態改變時，更新同一變更集中的 `.agents/TODO.md`。
6. 使用下列內容更新活動階段日誌，例如 `.agents/phase1.log`：
   - 工作已完成，
   - 進行驗證，
   - 遇到的問題，
   - 問題是如何解決的，
   - 已知的剩餘工作或阻礙因素。
7. 提交前運行相關驗證。對於這個 Python 項目，
   預設驗證是：
   - `uv run pytest`
   - `uv run ruff check .`
   - 運行時行為改變時的 CLI 冒煙測試：
     `uv run bybit-automation`
8. 僅暫存有意文件。
9. 使用簡潔的傳統風格的訊息進行承諾，例如：
   - `chore: bootstrap phase 0 project foundation`
   - `feat: add dry-run runtime skeleton`
   - `docs: define agent git workflow`
10. 將成功提交推送至 `origin/dev`。
11. 以乾淨的工作樹結束，除非使用者明確要求保留更改
    未承諾。如果由於環境問題導致驗證無法運行，請將問題記錄在
活動階段日誌和最終回應。請勿在以下情況下聲稱驗證已通過
它沒有運行。

環境說明：之前的會話需要升級 git 權限
正常 `git add` 或 `git commit` 失敗時的元資料操作
`.git/index.lock` 權限錯誤。將其視為工作區權限問題，
不能作為刪除鎖定檔案或重置儲存庫的理由。重試相同的 git
使用適當的批准/升級路徑進行操作。

### 共享 TODO 規則

- `.agents/TODO.md` 是規範的跨代理任務清單。
- 使用標準 Markdown 複選框，使文件保持跨工具的可移植性。
- 每個編碼或文件任務在執行之前都應保持 `TODO.md` 準確
  代理完成其回合。
- 如果未來的代理程式更改階段範圍、新增封鎖程式或完成任務，它
  必須在相同更改集中更新 `TODO.md`。
- 不要使用特定於工具的任務格式作為唯一的事實來源。

## 第二階段實作片段

SQLite 持久化工作的建議順序：1、儲存基礎：
   - 加入`src/bybit_automation/storage/`，
   - 建立一個精簡的 SQLite 連線/引導模組，
   - 為配置的資料庫路徑建立父目錄，
   - 當 `[database.sqlite].wal = true` 時啟用 WAL 模式，
   - 首先繼續使用標準庫`sqlite3`。
2. 架構引導：
   - 新增冪等模式創建，
   - 包括訂單、訂單事件、倉位快照、策略表
     決策、風險事件、機器人狀態、配置版本和每個符號跟踪
     狀態，
   - 將時間戳記儲存為 ISO-8601 UTC 文字或其他記錄一致的文字
     格式。
3. 儲存庫層：
   - 新增小型儲存庫，而不是在整個運行時暴露原始 SQL，
   - 從訂單事件、策略決策、風險的追加/讀取助手開始
     事件、倉位快照和追蹤狀態，
   - 使用明確交易進行多行更新。
4.運行時整合：
   - 在每個運行時標記後保留策略決策和風險決策，
   - `OrderManager` 返回後保留訂單結果，
   - `PositionManager` 同步後保留位置快照，
   - 儲存和恢復追蹤狀態，例如最高利潤和當前等級。
5.配置版本記錄：- 計算成功載入的配置內容的穩定哈希值，
   - 儲存來源路徑、規範化內容、載入時間和重新載入原因，
   - 尚未實現熱重載；只記錄成功的啟動/載入。
6、測試與驗證：
   - 在測試中使用臨時 SQLite 資料庫文件，
   - 驗證 WAL 模式，
   - 驗證模式引導程式是否冪等，
   - 驗證儲存庫寫入在關閉和重新開啟連線時是否存在，
   - 使所有測試保持離線且無需Bybit憑證。

避免在第 2 階段加入協調或 `SAFE_MODE` 行為，除非是
嚴格需要證明持久性；這些屬於第三階段。

## 立即執行下一個推薦步驟

啟動演示驗證/候選發布階段：

可執行門定義、所需證據和架構演變
決定記錄在 `.agents/TESTING_AND_ARCHITECTURE_PLAN.md` 中。1.在任何網路之前執行本地`bybit-automation verify-dry-run --config ...`
   測試。
2. 新增 Bybit 示範只讀預檢指令，用於檢查憑證、股票代碼、
   未平倉訂單以及未下單或取消訂單的持股。
3. 在任何 Bybit 網路之前需要明確的使用者批准和演示憑證
   驗證。
4. 運行演示影子模式，啟用交換讀取，但訂單仍然執行
   空運轉。
5. 僅在唯讀和影子檢查通過後，規劃一個小型演示訂單生命週期
   對每個步驟進行手動批准的測試。
6.記錄來自日誌、SQLite `bot_state`、運行狀況報告的操作證據，
   協調狀態和配置版本記錄。
