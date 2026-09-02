# Fleet 管理（Fleet Admin）

LAN Cowork の Fleet Admin 機能は、ネットワーク上の複数 yu-ai-manager ノードを中央から管理するための機能です。

## 概要

- **マシン情報収集**: 各ノードの CPU / RAM / GPU / ディスク / バージョン / 稼働時間を中央に集約
- **リモートログ閲覧**: 中央ノードの UI から任意ピアのログを SSE でライブストリーム
- **バージョン更新配布**: 中央から指定ピアに `git pull --ff-only` + graceful restart を指示

## 前提条件

- LAN Cowork 拡張が有効になっていること（`extensions["builtin-lan-cowork"].enabled = true`）
- ピア間でペアリングが完了していること
- git リポジトリとして clone されていること（更新機能を使う場合）
- Python 仮想環境に `psutil>=5.9` がインストールされていること

## セットアップ

### チーフノードの設定

`config.json` に以下を追加:

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "fleet": {
        "chief": true,
        "allow_remote_update": true,
        "allow_update_from": [
          "<ペアリング済み peer_id>"
        ],
        "allow_log_stream_from": [
          "<ペアリング済み peer_id>"
        ],
        "allowed_branches": [
          "main"
        ],
        "timings": {
          "chief_observation_sec": 25,
          "peers_poll_interval_sec": 30,
          "heartbeat_timeout_sec": 60,
          "update_job_timeout_sec": 600,
          "postcheck_timeout_sec": 180
        }
      }
    }
  }
}
```

### 一般ノードの設定

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "fleet": {
        "chief": false,
        "allow_remote_update": true,
        "allow_update_from": [
          "<チーフの peer_id>"
        ],
        "allow_log_stream_from": [
          "<チーフの peer_id>"
        ],
        "allowed_branches": [
          "main"
        ]
      }
    }
  }
}
```

## Fleet 管理 UI へのアクセス

チーフノードのブラウザから `/ext/lan_cowork/fleet/ui` にアクセスします。

一般ノードではこの URL は 404 になります。

## タブ機能

### 概要タブ

- 全ノードのカード表示（CPU / RAM / GPU / Disk 使用率バー付き）
- オンライン / オフライン / 情報取得失敗 の状態表示
- チーフノードには `[CHIEF]` バッジ
- 30 秒ごとの自動更新 + 手動更新ボタン
- 複数チーフ検出時の警告バナー

### ログタブ

- 任意ピアのログを SSE でライブ表示（tail -f 風）
- レベルフィルタ（DEBUG / INFO / WARNING / ERROR）
- 検索ボックス（クライアント側フィルタ）
- 自動スクロール ON/OFF
- 一時停止 / 再開

### アップデートタブ

- バージョン / git commit / ブランチの比較表
- 個別ノードの「Pull & Restart」ボタン
- 複数ノード一括更新（dispatch）
- 進捗表示（precheck → fetching → pulling → restarting → online）
- チーフ自身は一括更新から除外（個別ボタンのみ）

## セキュリティ

### 認可の二層構造

1. **ペアリング（身元確認）**: Bearer token で「誰か」を特定
2. **allowlist（権限）**: 操作ごとに明示的に許可

ペアリング済み = 全権限、ではありません。

### allowlist の設定例

```json
"allow_update_from": [
  "abc123def456",
  {"peer_id": "def456abc789"}
]
```

- 文字列と `{peer_id: ...}` 形式の両方が使えます
- 自機 peer_id は自動的に追加されます（設定不要）

## チーフ自動降格

同一ネットワークに `chief = true` のノードが複数起動した場合、後から起動したノードが自動的に降格します（`chief_observation_sec` 秒の観察後）。

降格後にチーフに復帰するには、設定変更後の再起動が必要です（自動昇格はしません）。

## git 更新の制約

- `git pull --ff-only` のみ使用します（merge/rebase は使いません）
- fast-forward できない場合は即 `failed` になります（ワーキングツリーは変更されません）
- ワーキングツリーが dirty な場合は更新を拒否します

## トラブルシューティング

| 症状 | 原因 | 対処 |
|---|---|---|
| `/fleet/ui` が 404 | `chief = true` 未設定 | config.json を確認して再起動 |
| `/fleet/info` が 500 | psutil 未インストール | `uv pip install psutil>=5.9` |
| `git_not_available` エラー | git がない or PATH 不正 | git インストールを確認 |
| 更新後に `postcheck_online` タイムアウト | 再起動に 3 分以上かかった | `postcheck_timeout_sec` を延長 |
| 複数チーフ検出バナーが消えない | 古いチーフプロセスが残存 | 古いチーフを再起動 |
| リモートから再起動できない (403) | `allow_remote_update` 未設定 | 下記「macOS 固有の注意」参照 |

---

## macOS 固有の注意事項

### リモート再起動 / git pull が動かない場合

macOS ノードをチーフからリモートで再起動・更新するには、**ターゲットの macOS 側**で次の 2 つを設定する必要があります。チーフ側ではなくピア（管理される側）の設定です。

**1. Fleet 許可設定を有効化**

LAN Cowork ページ（ブラウザで `/lan-cowork/peers`）の下部にある **「Fleet 許可」** セクションで GUI から設定します。`config.json` の手書きは不要です。

- 「リモート Fleet 操作を受け入れる」をONにする
- チーフの peer_id 行の「更新+再起動」列をチェックする（または「再起動」列のみ）

再起動のみ許可して更新は許可しない設定も可能です（チーフ側の Fleet Admin で dispatch する更新には update 権限が必要です）。

または、`config.json` で手書き設定することもできます:

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "fleet": {
        "allow_remote_update": true,
        "allow_update_from": [
          "<チーフの peer_id>"
        ]
      }
    }
  }
}
```

**2. チーフの `peer_id` を確認**

チーフの peer_id は Fleet Admin UI の概要タブ、または LAN Cowork → ピア一覧で確認できます。GUI の「Fleet 許可」セクションで設定する場合は、一覧から該当するチーフ行を選択するだけです。`config.json` で手書きする場合のみ peer_id を明示的に追加する必要があります。

> **なぜ macOS だけ詰まりやすいか**  
> Windows / Linux ノードは `start.sh` 相当のスクリプトでセットアップする際に fleet 設定も一緒に行うことが多いですが、macOS はブラウザから手動設定する場合に fleet セクションを後回しにしがちです。設定項目はどの OS も共通です。

### ペアリングは一方向

ピア A が B へペアリングしても、B が A を認証できるだけです。A が B に対してリモート操作（再起動・更新）を送るには、**B 側の `allow_update_from` に A の peer_id を追加**する必要があります。ペアリング済みであっても fleet 操作の許可は別設定です。

### 再起動後にターミナル出力が消える

macOS では再起動時に `subprocess.Popen(start_new_session=True)` で新プロセスを起動し親プロセスを終了します（Linux の `os.execv` とは異なります）。これにより**再起動後の新プロセスは元のターミナルセッションから切り離されます**。サーバーは正常動作していますが、ターミナルにはログが流れなくなります。ログは `logs/` ディレクトリまたはブラウザの Fleet Admin → ログタブで確認してください。

## API リファレンス

### 全ノード共通

| エンドポイント | 説明 |
|---|---|
| `GET /ext/lan_cowork/fleet/info` | マシン情報（Bearer 認証必須） |
| `GET /ext/lan_cowork/fleet/logs/stream` | 自機ログ SSE（allowlist 認可） |
| `POST /ext/lan_cowork/fleet/update` | git pull + 再起動（allowlist 認可） |
| `GET /ext/lan_cowork/fleet/update/status` | update job 状態照会 |

### チーフノードのみ

| エンドポイント | 説明 |
|---|---|
| `GET /ext/lan_cowork/fleet/peers` | 全ピア情報集約 |
| `GET /ext/lan_cowork/fleet/logs/stream?peer_id=X` | 指定ピアのログ SSE リレー |
| `POST /ext/lan_cowork/fleet/update/dispatch` | 複数ピアへの一括更新 |
| `GET /ext/lan_cowork/fleet/update/dispatch/status` | dispatch 進捗照会 |
| `GET /ext/lan_cowork/fleet/ui` | Fleet 管理 UI |
