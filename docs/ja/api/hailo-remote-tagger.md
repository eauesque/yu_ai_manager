# Hailo Remote Tagger API

Hailo AI HAT 推論サーバー（Raspberry Pi 5 等）にネットワーク経由で画像を送信し、Danbooru タグを推論して DB に保存する API です。

## 概要

ローカルに GPU や ONNX ランタイムがなくても、LAN 上の Hailo-10H 搭載デバイスをリモートタガーとして利用できます。画像は multipart/form-data で送信され、タグ JSON がレスポンスとして返されます。

---

## GET /api/hailo-tagger/config

設定を取得します。

### Rate Limit

READ（無制限）

### レスポンス

```json
{
  "ok": true,
  "data": {
    "config": {
      "enabled": false,
      "endpoint_url": "",
      "threshold": 0.35,
      "timeout": 30
    }
  }
}
```

| フィールド | 型 | 説明 |
|------------|------|------|
| `enabled` | bool | Hailo Remote Tagger 有効/無効 |
| `endpoint_url` | string | Pi エンドポイント URL（例: `http://192.168.1.50:8080`）|
| `threshold` | float | タグ信頼度閾値（これ以上の confidence のタグのみ保存）|
| `timeout` | int | リクエストタイムアウト（秒）|

---

## POST /api/hailo-tagger/config

設定を保存します。部分更新可能（指定したフィールドのみ変更）。

### Rate Limit

DESTRUCTIVE（~12 req/min, burst 3）

### リクエストボディ

| フィールド | 型 | 必須 | 説明 |
|------------|------|------|------|
| `enabled` | bool | No | 有効/無効 |
| `endpoint_url` | string | No | Pi エンドポイント URL |
| `threshold` | float | No | タグ信頼度閾値 |
| `timeout` | int | No | リクエストタイムアウト（秒）|

### リクエスト例

```json
{
  "enabled": true,
  "endpoint_url": "http://192.168.1.50:8080",
  "threshold": 0.35
}
```

### レスポンス

```json
{
  "ok": true,
  "data": {
    "config": {
      "enabled": true,
      "endpoint_url": "http://192.168.1.50:8080",
      "threshold": 0.35,
      "timeout": 30
    }
  }
}
```

### エラー

| ステータス | 説明 |
|------------|------|
| 400 | JSON オブジェクトが不正 |

---

## GET /api/hailo-tagger/status

Hailo エンドポイントへの接続テストを実行します。`/health` エンドポイントに GET を送信して到達可能性を確認します。

### Rate Limit

READ（無制限）

### レスポンス（成功時）

```json
{
  "ok": true,
  "data": {
    "enabled": true,
    "reachable": true,
    "endpoint_url": "http://192.168.1.50:8080"
  }
}
```

### レスポンス（未設定 / 到達不可時）

```json
{
  "ok": true,
  "data": {
    "enabled": true,
    "reachable": false,
    "reason": "Connection refused",
    "endpoint_url": "http://192.168.1.50:8080"
  }
}
```

---

## POST /api/hailo-tagger/tag/{file_id}

単一ファイルにタグを付与します。

### Rate Limit

HEAVY（~20 req/min, burst 5）

### パスパラメータ

| パラメータ | 型 | 説明 |
|------------|------|------|
| `file_id` | int | 対象ファイルの DB ID |

### リクエストボディ

| フィールド | 型 | 必須 | 説明 |
|------------|------|------|------|
| `force` | bool | No | `true` で既存タグを上書き（デフォルト: `false`）|

### レスポンス

```json
{
  "ok": true,
  "data": {
    "file_id": 42,
    "filepath": "/images/test.png",
    "tag_count": 15,
    "tags": [
      {"tag": "1girl", "confidence": 0.95},
      {"tag": "solo", "confidence": 0.88}
    ]
  }
}
```

### エラー

| ステータス | コード | 説明 |
|------------|--------|------|
| 400 | `disabled` | Hailo Tagger が無効 |
| 400 | `not_configured` | エンドポイント URL 未設定 |
| 400 | `file_not_found` | ファイルが見つからない |
| 400 | `file_missing` | ディスク上にファイルが存在しない |
| 400 | `unsupported_type` | タグ付け非対応のファイル形式 |
| 502 | `request_failed` | リモートサーバーへの接続失敗 |

---

## POST /api/hailo-tagger/batch

複数ファイルをバッチでタグ付けします。バックグラウンドジョブとして実行されます。

### Rate Limit

HEAVY（~20 req/min, burst 5）

### リクエストボディ

| フィールド | 型 | 必須 | 説明 |
|------------|------|------|------|
| `file_ids` | int[] | No | 対象ファイル ID リスト（最大 500）。省略時は未タグファイルを自動選択 |
| `limit` | int | No | 自動選択時の最大件数（デフォルト: 100）|
| `force` | bool | No | 既存タグを上書き（デフォルト: `false`）|

### リクエスト例

```json
{
  "file_ids": [1, 2, 3, 4, 5],
  "force": false
}
```

### レスポンス

```json
{
  "ok": true,
  "data": {
    "started": true,
    "job_id": "hailo_tagger"
  }
}
```

### エラー

| ステータス | コード | 説明 |
|------------|--------|------|
| 400 | `batch_too_large` | file_ids が 500 件超 |
| 409 | `job_running` | バッチジョブが既に実行中 |

---

## GET /api/hailo-tagger/tags/{file_id}

ファイルに付与された Hailo タグを取得します。

### Rate Limit

READ（無制限）

### レスポンス

```json
{
  "ok": true,
  "data": {
    "file_id": 42,
    "tags": [
      {"tag_name": "1girl", "confidence": 0.95, "source": "hailo_remote", "created_at": 1710720000},
      {"tag_name": "solo", "confidence": 0.88, "source": "hailo_remote", "created_at": 1710720000}
    ]
  }
}
```

---

## DELETE /api/hailo-tagger/tags/{file_id}

ファイルの Hailo タグを全削除します。

### Rate Limit

DESTRUCTIVE（~12 req/min, burst 3）

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

## DB スキーマ

Hailo タグは専用の `file_hailo_tags` テーブルに保存されます（`file_wd_tags` とは独立）。

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
| `tag_name` | Danbooru タグ名（例: `1girl`, `solo`）|
| `confidence` | 推論信頼度（0.0〜1.0）|
| `source` | タグソース識別子（`hailo_remote` またはレジストリ経由の場合 `hailo_remote:<server_id>`）|
| `created_at` | UNIX タイムスタンプ |

---

## 設定

`config.json` の `hailo_tagger` セクション:

```json
{
  "hailo_tagger": {
    "enabled": true,
    "endpoint_url": "http://192.168.1.50:8080",
    "threshold": 0.35,
    "timeout": 30
  }
}
```

設定画面 (Settings) からも変更可能です。

> **Note**: 複数のタガーサーバーを管理する場合は [Tagger Server Registry API](tagger-servers.md) を使用してください。レガシー設定は `/api/tagger-servers/migrate` で自動移行できます。Tagger Server Registry では Bearer トークン認証もサポートしています。
