# Tagger Server Registry API

複数のタグ推論ワーカー（Hailo Remote, ONNX Local, Ryzen AI 等）を統合管理し、共有キューによるワークスティーリング並列実行で分散バッチタグ付けを行う API です。

## 概要

Tagger Server Registry は、単一の Hailo Remote Tagger を超えて、複数の異種推論バックエンドをクラスターとして管理します。各サーバーには優先度が設定され、分散モード（single / parallel / idle_first）に応じてタスクが分配されます。

### アーキテクチャ

```
┌─────────────────────────────────────────────────────┐
│                   eauesque Host                      │
│  ┌──────────────────────────────────────────────┐   │
│  │         Tagger Orchestrator                  │   │
│  │  - Shared queue (work-stealing)              │   │
│  │  - Progress aggregation -> JobManager -> SSE │   │
│  └──────────┬──────────────┬──────────────────┘   │
│    ┌────────▼───┐   ┌──────▼────────────┐          │
│    │ Local ONNX │   │ Hailo HTTP Client │          │
│    │ Worker     │   │ Worker            │          │
│    └────────────┘   └──────────┬────────┘          │
└────────────────────────────────│────────────────────┘
              ┌──────────────────┼──────────────────┐
     ┌────────▼───┐    ┌────────▼───┐    ┌────────▼───┐
     │ Pi A       │    │ Pi B       │    │ Future     │
     │ Hailo 10H  │    │ Hailo 10H  │    │ NPU Server │
     └────────────┘    └────────────┘    └────────────┘
```

### サーバータイプ

| タイプ | 説明 |
|--------|------|
| `hailo_remote` | Hailo-10H 搭載リモートデバイス（Pi 5 等） |
| `onnx_local` | ローカル ONNX Runtime 推論 |
| `onnx_remote` | リモート ONNX 推論サーバー |
| `ryzen_ai` | AMD Ryzen AI NPU |

> **v4.67.0 注**: `onnx_local` / `onnx_remote` / `ryzen_ai` の手動登録はレガシー方式です。
> v4.64.0 以降は mDNS Phase B によるピア自動発見が推奨されており、検出されたピアは
> `mdns-<peer_id>` 形式の ID で自動的に tagger-servers レジストリに登録されます。
> 手動登録は引き続き動作しますが、新規セットアップには自動発見を優先してください。

### 分散モード

| モード | 説明 |
|--------|------|
| `single` | 最高優先度の有効サーバー 1 台のみ使用 |
| `parallel` | 全有効サーバーで並列実行（ワークスティーリング） |
| `idle_first` | アイドル状態のサーバーを優先的に使用 |

---

## サーバーエントリ形式

```json
{
  "id": "pi-hailo-a",
  "name": "Pi5 Hailo A",
  "type": "hailo_remote",
  "priority": 10,
  "enabled": true,
  "config": {
    "endpoint_url": "http://192.168.1.101:8080",
    "bearer_token": "enc:gAAAAABm...",
    "threshold": 0.35,
    "timeout": 30
  }
}
```

| フィールド | 型 | 説明 |
|------------|------|------|
| `id` | string | サーバー識別子（自動生成または手動指定） |
| `name` | string | 表示名 |
| `type` | string | サーバータイプ（`hailo_remote` / `onnx_local` / `onnx_remote` / `ryzen_ai`） |
| `priority` | int | 優先度（小さいほど高優先、デフォルト: 50） |
| `enabled` | bool | 有効/無効 |
| `config` | object | タイプ固有の設定（下記参照） |

### config フィールド（リモートサーバー向け）

| フィールド | 型 | 必須 | 説明 |
|------------|------|------|------|
| `endpoint_url` | string | Yes | リモートサーバーの URL |
| `bearer_token` | string | No | Bearer トークン（保存時に自動暗号化 `enc:` prefix）|
| `threshold` | float | No | タグ信頼度閾値（デフォルト: 0.35）|
| `timeout` | int | No | リクエストタイムアウト秒（デフォルト: 30）|

---

## 認証

リモートサーバー（`hailo_remote` / `onnx_remote`）との通信には、オプションで Bearer トークン認証を使用できます。

### ホスト → リモートサーバー

`config.bearer_token` が設定されている場合、全 HTTP リクエスト（ヘルスチェック・タグ付け）に `Authorization: Bearer <token>` ヘッダーが自動付与されます。トークンは `config.json` に Fernet 暗号化 (`enc:` prefix) で保存され、API レスポンスではマスクされます。

### リモートサーバー側

`deploy/hailo_tagger_server.py` がトークン検証付きの参照実装です。起動時に以下のいずれかでトークンを設定:

```bash
# コマンドライン引数
python hailo_tagger_server.py --token "my-secret-token"

# ファイルから読み込み
python hailo_tagger_server.py --token-file /etc/tagger/token

# 環境変数
TAGGER_BEARER_TOKEN=my-secret-token python hailo_tagger_server.py
```

トークン未設定時は従来通りオープンアクセス（LAN 内信頼モデル）として動作します。不正なトークンには 401/403 を返します。

---

## GET /api/tagger-servers

登録サーバー一覧と現在の分散モードを取得します。

### Rate Limit

READ（無制限）

### レスポンス

```json
{
  "ok": true,
  "data": {
    "servers": [
      {
        "id": "pi-hailo-a",
        "name": "Pi5 Hailo A",
        "type": "hailo_remote",
        "priority": 10,
        "enabled": true,
        "config": {
          "endpoint_url": "http://192.168.1.101:8080",
          "threshold": 0.35,
          "timeout": 30
        }
      }
    ],
    "mode": "parallel"
  }
}
```

---

## POST /api/tagger-servers

新しいタガーサーバーを追加します。

### Rate Limit

DESTRUCTIVE（~12 req/min, burst 3）

### リクエストボディ

| フィールド | 型 | 必須 | 説明 |
|------------|------|------|------|
| `name` | string | Yes | 表示名 |
| `type` | string | Yes | サーバータイプ |
| `config` | object | Yes | タイプ固有の設定 |
| `priority` | int | No | 優先度（デフォルト: 50） |
| `enabled` | bool | No | 有効/無効（デフォルト: `true`） |

### リクエスト例

```json
{
  "name": "Pi5 Hailo A",
  "type": "hailo_remote",
  "config": {
    "endpoint_url": "http://192.168.1.101:8080",
    "threshold": 0.35,
    "timeout": 30
  },
  "priority": 10
}
```

### レスポンス

```json
{
  "ok": true,
  "data": {
    "server": {
      "id": "pi-hailo-a",
      "name": "Pi5 Hailo A",
      "type": "hailo_remote",
      "priority": 10,
      "enabled": true,
      "config": {
        "endpoint_url": "http://192.168.1.101:8080",
        "threshold": 0.35,
        "timeout": 30
      }
    }
  }
}
```

### エラー

| ステータス | 説明 |
|------------|------|
| 400 | 必須フィールドの欠落またはタイプが不正 |

---

## PUT /api/tagger-servers/{server_id}

既存サーバーの設定を更新します。部分更新可能。

### Rate Limit

DESTRUCTIVE（~12 req/min, burst 3）

### パスパラメータ

| パラメータ | 型 | 説明 |
|------------|------|------|
| `server_id` | string | 対象サーバー ID |

### リクエストボディ

| フィールド | 型 | 必須 | 説明 |
|------------|------|------|------|
| `name` | string | No | 表示名 |
| `type` | string | No | サーバータイプ |
| `config` | object | No | タイプ固有の設定 |
| `priority` | int | No | 優先度 |
| `enabled` | bool | No | 有効/無効 |

### レスポンス

```json
{
  "ok": true,
  "data": {
    "server": { "..." }
  }
}
```

### エラー

| ステータス | 説明 |
|------------|------|
| 404 | サーバーが見つからない |

---

## DELETE /api/tagger-servers/{server_id}

サーバーを削除します。

### Rate Limit

DESTRUCTIVE（~12 req/min, burst 3）

### パスパラメータ

| パラメータ | 型 | 説明 |
|------------|------|------|
| `server_id` | string | 対象サーバー ID |

### レスポンス

```json
{
  "ok": true,
  "data": {
    "deleted": "pi-hailo-a"
  }
}
```

### エラー

| ステータス | 説明 |
|------------|------|
| 404 | サーバーが見つからない |

---

## POST /api/tagger-servers/reorder

サーバーの優先度を一括で並び替えます。

### Rate Limit

DESTRUCTIVE（~12 req/min, burst 3）

### リクエストボディ

| フィールド | 型 | 必須 | 説明 |
|------------|------|------|------|
| `order` | string[] | Yes | サーバー ID の配列（優先度順） |

### リクエスト例

```json
{
  "order": ["pi-hailo-a", "local-onnx", "pi-hailo-b"]
}
```

### レスポンス

```json
{
  "ok": true,
  "data": {
    "servers": [ "..." ]
  }
}
```

---

## POST /api/tagger-servers/mode

分散モードを変更します。

### Rate Limit

DESTRUCTIVE（~12 req/min, burst 3）

### リクエストボディ

| フィールド | 型 | 必須 | 説明 |
|------------|------|------|------|
| `mode` | string | Yes | `single` / `parallel` / `idle_first` |

### レスポンス

```json
{
  "ok": true,
  "data": {
    "mode": "parallel"
  }
}
```

### エラー

| ステータス | 説明 |
|------------|------|
| 400 | 不正なモード値 |

---

## POST /api/tagger-servers/{server_id}/test

指定サーバーへの接続テストを実行します。

### Rate Limit

HEAVY（~20 req/min, burst 5）

### パスパラメータ

| パラメータ | 型 | 説明 |
|------------|------|------|
| `server_id` | string | 対象サーバー ID |

### レスポンス（成功時）

```json
{
  "ok": true,
  "data": {
    "server_id": "pi-hailo-a",
    "reachable": true,
    "latency_ms": 45
  }
}
```

### レスポンス（到達不可時）

```json
{
  "ok": true,
  "data": {
    "server_id": "pi-hailo-a",
    "reachable": false,
    "reason": "Connection refused"
  }
}
```

### エラー

| ステータス | 説明 |
|------------|------|
| 404 | サーバーが見つからない |

---

## GET /api/tagger-servers/health

全有効サーバーのヘルスチェックを実行します。

### Rate Limit

READ（無制限）

### レスポンス

```json
{
  "ok": true,
  "data": {
    "results": [
      {
        "server_id": "pi-hailo-a",
        "name": "Pi5 Hailo A",
        "type": "hailo_remote",
        "reachable": true,
        "latency_ms": 45
      },
      {
        "server_id": "local-onnx",
        "name": "Local ONNX",
        "type": "onnx_local",
        "reachable": true,
        "latency_ms": 2
      }
    ]
  }
}
```

---

## POST /api/tagger-servers/batch

共有キュー・ワークスティーリングモデルで分散バッチタグ付けを実行します。バックグラウンドジョブとして実行され、進捗は SSE で通知されます。

### ワークスティーリングアルゴリズム (v4.67.0)

バッチ実行は以下の手順で並列処理されます:

1. `asyncio.Queue` に処理対象ファイルを全件投入する
2. 各有効ピアが並行して `queue.get_nowait()` を呼び出し、`batch_size` 個ずつアイテムを取得する
3. 処理が速いピアが自然に多くのアイテムを消費する（ワークスティーリング）
4. キューが空になった時点で全ピアが完了を検知し、ジョブが終了する

v4.67.0 より、ピアが `DisableAwareStrategy` によって無効化されている場合はキュー取得をスキップします。
全ピアが無効の場合は即座に `no_enabled_peers` エラーで失敗します（下記エラー表を参照）。

### メッシュ推論トグルとの連携 (v4.67.0)

ピア単位の有効/無効制御は `/api/mesh-inference/toggle` および `/api/mesh-inference/bulk` で管理されます。
この tagger-servers API はバッチ操作（開始・キャンセル・統計）の入口として引き続き動作しますが、
実際のピア選択は `DisableAwareStrategy` を通じてメッシュ推論の有効/無効状態を参照します。

```
POST /api/mesh-inference/toggle   # 特定ピアの有効/無効を切り替え
POST /api/mesh-inference/bulk     # 複数ピアを一括で有効/無効
```

詳細: [/api/mesh-inference](mesh-inference.md)

### Rate Limit

HEAVY（~20 req/min, burst 5）

### リクエストボディ

| フィールド | 型 | 必須 | 説明 |
|------------|------|------|------|
| `file_ids` | int[] | No | 対象ファイル ID リスト。省略時は未タグファイルを自動選択 |
| `limit` | int | No | 自動選択時の最大件数（デフォルト: 500） |
| `force` | bool | No | 既存タグを上書き（デフォルト: `false`） |
| `threshold` | float | No | タグ信頼度閾値の上書き（省略時は各サーバー設定を使用） |

### リクエスト例

```json
{
  "file_ids": [1, 2, 3, 4, 5],
  "force": false,
  "threshold": 0.35
}
```

### レスポンス

```json
{
  "ok": true,
  "data": {
    "started": true,
    "job_id": "tagger_servers_batch",
    "total_files": 5,
    "active_servers": ["pi-hailo-a", "local-onnx"]
  }
}
```

### エラー

| ステータス | コード | 説明 |
|------------|--------|------|
| 400 | `no_servers` | 有効なサーバーが存在しない |
| 400 | `no_enabled_peers` | 全ピアがメッシュ推論トグルで無効化されている（v4.67.0） |
| 400 | `batch_too_large` | file_ids が上限超過 |
| 409 | `job_running` | バッチジョブが既に実行中 |

---

## POST /api/tagger-servers/batch/cancel

実行中のタガークラスターバッチジョブをキャンセルします。

### Response

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | `"cancelling"` |
| `message` | string | ステータスメッセージ |

### Error Codes

| Status | Code | Description |
|--------|------|-------------|
| 404 | `job_not_running` | キャンセル対象のバッチジョブが実行されていません |

---

## GET /api/tagger-servers/tags/{file_id}

ファイルに付与されたタガータグを取得します。

### Rate Limit

READ（無制限）

### パスパラメータ

| パラメータ | 型 | 説明 |
|------------|------|------|
| `file_id` | int | 対象ファイルの DB ID |

### レスポンス

```json
{
  "ok": true,
  "data": {
    "file_id": 42,
    "tags": [
      {"tag_name": "1girl", "confidence": 0.95, "source": "hailo_remote:pi-hailo-a", "created_at": 1710720000},
      {"tag_name": "solo", "confidence": 0.88, "source": "hailo_remote:pi-hailo-a", "created_at": 1710720000}
    ]
  }
}
```

`source` フィールドは `{type}:{server_id}` 形式（例: `hailo_remote:pi-hailo-a`, `onnx_local:local-onnx`）です。

---

## DELETE /api/tagger-servers/tags/{file_id}

ファイルのタガータグを全削除します。

### Rate Limit

DESTRUCTIVE（~12 req/min, burst 3）

### パスパラメータ

| パラメータ | 型 | 説明 |
|------------|------|------|
| `file_id` | int | 対象ファイルの DB ID |

### レスポンス

```json
{
  "ok": true,
  "data": {
    "file_id": 42,
    "deleted": 15
  }
}
```

---

## GET /api/tagger-servers/stats

タガー統計情報を取得します。

### Rate Limit

READ（無制限）

### レスポンス

```json
{
  "ok": true,
  "data": {
    "total_files": 10000,
    "tagged_files": 8500,
    "untagged_files": 1500,
    "servers": {
      "pi-hailo-a": {"tagged": 5000, "type": "hailo_remote"},
      "local-onnx": {"tagged": 3500, "type": "onnx_local"}
    }
  }
}
```

---

## POST /api/tagger-servers/migrate

レガシーの `hailo_tagger` 設定を Tagger Server Registry 形式にマイグレーションします。既存の `config.json` 内 `hailo_tagger` エントリを `tagger_servers` 配列のエントリに変換します。

### Rate Limit

DESTRUCTIVE（~12 req/min, burst 3）

### レスポンス

```json
{
  "ok": true,
  "data": {
    "migrated": true,
    "server": {
      "id": "legacy-hailo",
      "name": "Hailo Remote (migrated)",
      "type": "hailo_remote",
      "priority": 50,
      "enabled": true,
      "config": {
        "endpoint_url": "http://192.168.1.50:8080",
        "threshold": 0.35,
        "timeout": 30
      }
    }
  }
}
```

### レスポンス（マイグレーション不要時）

```json
{
  "ok": true,
  "data": {
    "migrated": false,
    "reason": "No legacy config found"
  }
}
```

---

## 設定

`config.json` の関連キー:

```json
{
  "tagger_servers": [
    {
      "id": "pi-hailo-a",
      "name": "Pi5 Hailo A",
      "type": "hailo_remote",
      "priority": 10,
      "enabled": true,
      "config": {
        "endpoint_url": "http://192.168.1.101:8080",
        "bearer_token": "enc:gAAAAABm...",
        "threshold": 0.35,
        "timeout": 30
      }
    },
    {
      "id": "local-onnx",
      "name": "Local ONNX",
      "type": "onnx_local",
      "priority": 20,
      "enabled": true,
      "config": {
        "threshold": 0.35
      }
    }
  ],
  "tagger_servers_mode": "parallel"
}
```

| キー | 型 | 説明 |
|------|------|------|
| `tagger_servers` | array | サーバーエントリの配列 |
| `tagger_servers_mode` | string | 分散モード（`single` / `parallel` / `idle_first`） |

設定画面 (Settings) からも変更可能です。

---

## DB スキーマ

タグは `file_hailo_tags` テーブルに保存されます。`source` カラムが `{type}:{server_id}` 形式でどのサーバーがタグを付与したか識別します。

```sql
CREATE TABLE file_hailo_tags (
    id         INTEGER PRIMARY KEY,
    file_id    INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    tag_name   TEXT NOT NULL,
    confidence REAL NOT NULL,
    source     TEXT NOT NULL DEFAULT 'hailo_remote',
    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    UNIQUE(file_id, tag_name)
);
```

| カラム | 説明 |
|--------|------|
| `file_id` | files テーブルの外部キー |
| `tag_name` | Danbooru タグ名（例: `1girl`, `solo`） |
| `confidence` | 推論信頼度（0.0〜1.0） |
| `source` | タグソース識別子（`{type}:{server_id}` 形式、例: `hailo_remote:pi-hailo-a`） |
| `created_at` | UNIX タイムスタンプ |
