# SPEC.md

このファイルには、将来のエージェントが処理する必要があるプロジェクト レベルの仕様が記録されます。
ユーザーが明示的に方向を変更しない限り、現在の設計ターゲットとして使用されます。

この文書は簡潔にしてください。詳細な実装メモはコードに含まれています。
テスト、またはフェーズ固有のドキュメント。

## 構成仕様

### 目標

将来の構成システムは次のようになります。

- ローカル開発での編集が簡単、
- コンテナ内で簡単にオーバーライドできます。
- テンプレートとしてコミットしても安全です。
- 実行時使用前に検証済み、
- 正常にロードされるとバージョンが記録されます。
- 将来のホットリロードに適しています。

### ファイル形式

主要な構成形式には TOML を使用します。

予定されているファイル:

```text
configs/config.template.toml
configs/config.toml
```

ルール:

- `configs/config.template.toml` はコミットされています。
- `configs/config.toml` はローカル/ランタイム固有であるため、コミットしないでください。
- シークレットは、コミットされた構成ファイルに直接保存しないでください。
- 実行時のシークレットは環境変数から取得する必要があります。
- コンテナーのデプロイメントでは、`config.toml` をマウントまたは置換できる必要があります。

理論的根拠:

- TOML は人間が判読可能で、`pyproject.toml` と並行して自然に動作します。
- Python 3.11 以降では、`tomllib` を通じて TOML を読み取ることができます。
- 単一の構成ファイルにより、複数の JSON ファイルからのあいまいなマージ動作が回避されます。

### 環境変数とシークレット

Config には、シークレット値ではなく、環境変数名を保存する必要があります。

例:

```toml
[exchange.bybit]
api_key_env = "BYBIT_API_KEY"
api_secret_env = "BYBIT_API_SECRET"
```

予想される動作:

- ローダーは実行時に環境変数名を解決します。
- 必要なシークレットが欠落している場合は、取引開始前の検証に失敗する必要があります。
- ドライラン モードでは、交換の副作用がない場合、交換認証情報の欠落が許可される可能性があります
  が実行されます。

### コンテナに優しいオーバーライド

構成設計では、イメージの再構築を必要とせずにコンテナーをサポートする必要があります。

推奨されるメカニズム:

- `configs/config.toml` をマウントします。
- 環境変数を通じてシークレットを挿入します。
- 必要に応じて、次のような環境変数を通じて構成パスをオーバーライドします。
  `BYBIT_AUTOMATION_CONFIG`。

ランタイム構成を変更するためにソースコードを編集する必要はありません。

### 最上位構造

ターゲット構成構造は次のとおりです。

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

### モードのセマンティクス

`app.mode` は以下をサポートする必要があります。

- `dry_run`: ライブ交換の副作用はありません。開発のための安全なデフォルト。
- `demo`: サポートされている場合はデモ/サンドボックス モードを交換します。
- `live`: リアルトレーディングモード;明示的な構成と有効な認証情報が必要です。

新しい実行時コードはデフォルトでライブ取引を行ってはなりません。

### デフォルトとシンボルの上書きデフォルトとシンボルごとのオーバーライドを使用します。

ルール:

- `[strategy.defaults]` は、共通の戦略設定を定義します。
- `[risk.defaults]` は、共通のリスク/トレーリング設定を定義します。
- 各 `[[symbols]]` エントリは、サポートされている戦略フィールドをオーバーライドできます。
- 後の実装では、シンボルごとのリスクの上書きが可能になる可能性がありますが、これは行う必要があります。
  明示的かつ検証済み。
- ローダーは、実行時に使用する前に、解決されたシンボルごとの構成を生成する必要があります。

これにより、すべての取引ペアで同じ値を繰り返すことがなくなります。

### 命名規則

曖昧な名前は避けてください。

使用:

- `strategy_interval_sec`
- `risk_interval_sec`
- `reconciliation_interval_sec`

`monitor_interval` などの汎用キーを無関係なセクション間で再利用しないでください。

実用的であれば、特に時間間隔など、名前に明示的な単位を使用します。

### 検証ルール

構成は実行時に使用する前に検証する必要があります。

最低限の検証:- `app.mode` は、`dry_run`、`demo`、`live` のいずれかです。
- `exchange.name` がサポートされています。
- 選択したモードに必要な環境変数が存在します。
- 間隔は正の数です。
- レバレッジはプラスです。
- シンボルは空ではなく、一意です。
- 注文金額は負ではありません。
- リスクのパーセンテージとしきい値は負ではありません。
- 後続のしきい値は論理的に順序付けされます。
  - `low_trail_enable_threshold`
  - `first_trail_enable_threshold`
  - `second_trail_enable_threshold`
・Redisの設定はRedisが有効な場合のみ必要です。
- WebSocket の古いデータと再接続の間隔は正です。
- WebSocket 再接続の初期遅延は最大遅延を超えません。

無効な構成を部分的に適用してはなりません。

### ホットリロードルール

最初の実装は手動リロードのみをサポートします。

安全なホットリロード可能なフィールド:

- シンボルの有効化/無効化、
- 注文金額、
- EMA期間、
- 値の乗数、
- リスク/トレーリングしきい値、
- ブラックリスト、
- 実行間隔。

サイレントにホットリロードすべきではないフィールド:

- API キーまたはシークレット環境名、
- 名前を交換し、
- アカウントモード、
- データベースのパス、
- Redis URL、
- デフォルトのレバレッジ。リロードに安全でない変更が含まれている場合、リロード サービスは次の結果を返します。
`requires_restart`、アクティブな構成を保存し、次の場合に監査結果を記録します。
SQLite が利用可能ですが、明示的な安全な再起動フローが必要です。

手動リロード エントリ ポイント:

```text
bybit-automation reload --current configs/config.toml --candidate configs/config.new.toml
```

予想される動作:

- 有効でホットリロード可能な候補者は、リロード サービスを通じて申請します。
- 無効な候補はゼロ以外を返し、アクティブな設定を保持します。
- 安全でない候補は、再起動が必要なパスで非ゼロを返します。
- 成功した手動リロードは SQLite `config_versions` に記録されます。
  `reload_reason = "manual"`、
- SQLite が有効な場合、すべてのリロード試行は `bot_state.last_config_reload` を書き込みます。
  利用可能、
- Redis config リロード信号は通知プリミティブとしてのみ記録され、
  構成変更を自動的に適用しません。

### ロードされた構成の永続性

SQLite が完了したら、正常にロードされたすべての構成を SQLite に記録する必要があります。
利用可能です。

推奨されるテーブルのコンセプト:

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

目的:

- 実行時の動作を監査可能にする、
- 取引の決定を設定バージョンまで追跡できるようにします。
- 安全なロールバックまたは後での診断をサポートします。

### 内部代表者

実行時コードは生の辞書をあらゆる場所に渡すべきではありません。

推奨されるアプローチ:- TOML を型指定された構成オブジェクトに解析します。
- 一度検証して、
- 解決されたランタイム構成を生成します。
- 型付きオブジェクトをモジュールに渡します。

最初にデータクラスまたは別の軽量の型付きモデルを使用します。大量の追加は避けてください
後で検証の複雑さが正当化される場合を除き、構成のみに依存します。

### WebSocket の同期

WebSocket サポートは同期レイヤーであり、オーダー コマンド パスではありません。

ルール:

- REST は、起動スナップショット、コマンドの交換、および
  和解修復。
- パブリック マーケット ストリーム イベントは、リアルタイム マーケット キャッシュを更新する場合があります。
- プライベート注文、ポジション、実行ストリームイベントはリアルタイムで更新される可能性があります
  アカウントのキャッシュ。
- ストリームの健全性は、ハートビート/最近のメッセージの鮮度を通じて追跡する必要があります。
- WebSocket データが古いか、有効化されている間に利用できない場合、戦略エントリ
  評価は失敗して終了する必要があります。
- WebSocket イベントから作成された Redis キャッシュ エントリは再構築可能のままであり、
  持続可能な取引状態ではありません。
- 具体的な Bybit WebSocket アダプターは、明示的モード ガードの背後に留まっている必要があり、
  デフォルトでライブ取引を有効にしてはなりません。

## 動作の安定性

フェーズ 7 では、リファクタリングされたランタイムのローカル運用基盤を確立します。運用イベントのルール:

- 重要なランタイム、リロード、リコンシリエーション、キャッシュ、WebSocket、交換、および
  ストレージ イベントでは、型指定された操作イベント ペイロードを使用する必要があります。
- 構造化された操作ログは、出力時に安定した JSON ペイロードである必要があります。
- 通知重大度レベルは、`info`、`warning`、`safe_mode`、および `error` です。

ヘルスチェックのルール:

- SQLite、Redis、WebSocket、Exchange の準備状況は個別に報告する必要があります。
- ドライラン交換の準備には、ネットワーク アクセスが必要であってはなりません。
- デモ/ライブ交換の準備状況では資格情報の存在を確認できますが、読み取り専用です
  ネットワーク プリフライトには明示的なユーザーの承認が必要です。

回復力のルール:

- 再試行/バックオフ ポリシーは明示的かつテスト可能でなければなりません。
- 冪等性と交換がない限り、やみくもに注文を再試行しないでください。
  受け入れの曖昧さは処理されます。
- 回路ブレーカーは、戦略の前に繰り返される外部障害を保護する必要があります。
  ロジックは通常どおり続行されます。

検証ルール:- `bybit-automation verify-dry-run --config ...` はローカルのネットワークなしです
  検証コマンド。
- `verify-dry-run` は、スモークを実行する前に、非 `dry_run` 構成を拒否する必要があります
  チェックしてください。
- Bybit デモの検証は次のリリース候補段階に属し、開始されます
  読み取り専用の接続チェックは、明示的な承認後にのみ行われます。

### 現在のレガシー マッピング

従来の JSON テンプレートは、ほぼ次のようにマッピングされます。

- `exchange_config.json.template` -> `[app]`、`[exchange]`、
  `[exchange.bybit]`
- `strategy_config.json.template` -> `[runtime]`、`[strategy.defaults]`、
  `[[symbols]]`
- `trailing_config.json.template` -> `[risk]`、`[risk.defaults]`

移行中は、新しい構成パスが設定されるまで、レガシー ファイルを参照として保持します。
動作し、検証されました。
