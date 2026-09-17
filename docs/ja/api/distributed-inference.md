# 分散推論 API

分散推論サーバーレジストリの REST API。複数ノード間で CLIP セマンティックインデックス処理を共有キュー方式で分散します。

> **注意 (v4.67.0)**: この API は旧方式の分散推論サーバー登録に関するドキュメントです。
> 現在のメッシュ推論はピア自動発見 (mDNS Phase B) + ワークスティーリング方式に移行しています。
> 
> - tagger バッチ推論: [/api/tagger-servers](tagger-servers.md)
> - ピア単位の有効/無効制御: [/api/mesh-inference](mesh-inference.md)
> - メッシュ推論アーキテクチャ概要: [メッシュ推論アーキテクチャ](../mesh-inference/overview.md)

## エンドポイント一覧

### GET /api/inference-servers <!-- removed in v4.67.0 -->

登録済みサーバー一覧とディスパッチモードを取得します。

**レスポンス:**

```json
{
  "status": "ok",
  "mode": "single",
  "servers": [
    {
      "id": 1,
      "name": "Hailo Worker 1",
      "endpoint_url": "http://192.168.1.10:9090",
      "inference_types": ["clip"],
      "priority": 50,
      "enabled": true,
      "timeout": 30
    }
  ]
}
```

- `mode`: `"single"` | `"parallel"` | `"idle_first"`
- `servers`: サーバー設定の配列

---

### POST /api/inference-servers <!-- removed in v4.67.0 -->

新規サーバーを追加します。

**リクエストボディ:**

| フィールド | 型 | 必須 | デフォルト | 説明 |
|---|---|---|---|---|
| `name` | string | ✓ | — | 表示名 |
| `endpoint_url` | string | ✓ | — | ワーカー URL |
| `inference_types` | string[] | — | `["clip"]` | 対応推論タイプ |
| `priority` | int | — | `50` | 優先度（低い値が高優先） |
| `bearer_token` | string | — | — | 認証トークン |
| `timeout` | int | — | `30` | タイムアウト秒 |

**レスポンス:**

```json
{
  "status": "ok",
  "server": { ... }
}
```

---

### PUT /api/inference-servers/{server_id} <!-- removed in v4.67.0 -->

既存サーバーの設定を更新します。リクエストボディは POST と同じフィールドを部分的に指定できます。

---

### DELETE /api/inference-servers/{server_id} <!-- removed in v4.67.0 -->

サーバーをレジストリから削除します。

**レスポンス:**

```json
{ "status": "ok" }
```

---

### POST /api/inference-servers/{server_id}/test <!-- removed in v4.67.0 -->

指定サーバーのヘルスチェックを実行します。

**レスポンス:**

```json
{
  "status": "ok",
  "server_id": 1,
  "healthy": true,
  "latency_ms": 12.5
}
```

---

### GET /api/inference-servers/health <!-- removed in v4.67.0 -->

全有効サーバーのヘルスチェックを一括実行します。

**レスポンス:**

```json
{
  "status": "ok",
  "results": [
    { "server_id": 1, "healthy": true, "latency_ms": 12.5 },
    { "server_id": 2, "healthy": false, "error": "Connection refused" }
  ]
}
```

---

### POST /api/inference-servers/mode <!-- removed in v4.67.0 -->

ディスパッチモードを設定します。

**リクエストボディ:**

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `mode` | string | ✓ | `"single"` \| `"parallel"` \| `"idle_first"` |

**レスポンス:**

```json
{ "status": "ok", "mode": "parallel" }
```

---

## ディスパッチモード

| モード | 説明 |
|---|---|
| `single` | 最高優先度（priority 値最小）のサーバーのみ使用 |
| `parallel` | 全有効サーバーで共有キュー方式の並列処理 |
| `idle_first` | ヘルスチェック後、応答可能なサーバーのみで並列処理 |

## セマンティックインデックスの分散実行

`POST /api/index/start`（セマンティック検索エクステンション）のリクエストボディに `distributed: true` を追加することで、登録済みワーカーサーバーを使った分散インデックスが有効になります。

```json
{
  "batch_size": 32,
  "distributed": true
}
```

## ワーカーサーバーのセットアップ

```bash
python deploy/hailo_tagger_server.py --port 9090
```

対応エンドポイント:

| パス | 説明 |
|---|---|
| `GET /health` | ヘルスチェック |
| `POST /tag` | WD-Tagger 推論 |
| `POST /clip-encode` | CLIP ベクトルエンコード |

## MCP ツール

| ツール名 | 説明 |
|---|---|
| `inference-servers-list` | サーバー一覧とモード取得 |
| `inference-server-add` | サーバー追加 |
| `inference-server-update` | サーバー設定更新 |
| `inference-server-remove` | サーバー削除 |
| `inference-server-health` | ヘルスチェック実行 |
| `inference-dispatch-mode-set` | ディスパッチモード設定 |
