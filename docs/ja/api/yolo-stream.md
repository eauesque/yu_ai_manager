# YOLO Stream API

YOLO リアルタイムストリーム処理に関する API。映像ソース管理、MJPEG 配信、検出ルール、録画・スナップショットの機能を提供する。

全ての POST/PUT/DELETE エンドポイントには `X-Requested-With` ヘッダが必要（Bearer API Key 使用時を除く）。

---

## ソース管理

### GET /ext/hailo-yolo/api/stream/sources

登録済みの全ストリームソースを一覧取得する。

#### レスポンス

```json
{
  "status": "ok",
  "sources": [
    {
      "id": "cam1",
      "name": "Front Camera",
      "url": "rtsp://192.168.1.100:554/stream",
      "type": "rtsp",
      "state": "running",
      "resolution": { "width": 1920, "height": 1080 },
      "fps": 25.0,
      "frame_count": 15420,
      "error": null,
      "viewers": 1
    }
  ]
}
```

### POST /ext/hailo-yolo/api/stream/sources

新しいストリームソースを追加する。

#### リクエスト

```json
{
  "id": "cam2",
  "url": "rtsp://192.168.1.101:554/stream",
  "name": "Back Camera"
}
```

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `id` | string | はい | ソースの一意識別子 |
| `url` | string | はい | RTSP URL またはデバイスインデックス |
| `name` | string | いいえ | 表示名 |

#### レスポンス (201)

```json
{ "status": "ok", "source": { "id": "cam2", "..." : "..." } }
```

### DELETE /ext/hailo-yolo/api/stream/sources/\<id\>

指定ソースを削除する。

#### レスポンス

```json
{ "status": "ok" }
```

### POST /ext/hailo-yolo/api/stream/sources/\<id\>/start

指定ソースのキャプチャを開始する。

#### レスポンス

```json
{ "status": "ok", "source": { "id": "cam1", "state": "running", "..." : "..." } }
```

### POST /ext/hailo-yolo/api/stream/sources/\<id\>/stop

指定ソースのキャプチャを停止する。

#### レスポンス

```json
{ "status": "ok", "source": { "id": "cam1", "state": "stopped", "..." : "..." } }
```

### POST /ext/hailo-yolo/api/stream/sources/\<id\>/test

ソースへの接続テストを実行する。リクエストボディで URL を指定した場合はその URL、省略時は既存ソースの URL を使用する。

#### リクエスト

```json
{ "url": "rtsp://192.168.1.100:554/stream" }
```

#### レスポンス

```json
{ "ok": true, "resolution": { "width": 1920, "height": 1080 } }
```

### GET /ext/hailo-yolo/api/stream/devices

接続済み USB カメラを検出する。

#### レスポンス

```json
{
  "status": "ok",
  "devices": [
    { "index": 0, "name": "USB Camera", "resolution": null }
  ]
}
```

> **注記:** Rust native 応答は Linux だけで USB camera を列挙し、device を開かない。`resolution` は常に `null` となる。Windows/macOS は `devices: []` を返し、数字 camera index による登録にも対応しない。
>
> event fan-out も縮小する。configured webhook 拡張への暗黙 wildcard 配信、custom event 名が `RELAY_TYPES` に一致する場合の LAN relay、専用 MCP event 受け皿への到達は行わない。`mcp_event` は共有 SSE hub へ配信する。

---

## 映像ストリーム

### GET /ext/hailo-yolo/api/stream/\<id\>/mjpeg

YOLO 検出結果をオーバーレイした MJPEG ストリームを返す。ソースあたり最大 4 同時視聴。

- **Content-Type**: `multipart/x-mixed-replace; boundary=frame`

---

## ルール管理

### GET /ext/hailo-yolo/api/stream/rules

全ルールを一覧取得する。

#### レスポンス

```json
{
  "status": "ok",
  "rules": [
    {
      "id": "rule1",
      "name": "Person detection",
      "enabled": true,
      "conditions": {
        "classes": ["person"],
        "min_confidence": 0.7,
        "sources": ["cam1"],
        "schedule": { "start": "22:00", "end": "06:00", "days": ["mon","tue","wed","thu","fri","sat","sun"] }
      },
      "cooldown_sec": 60,
      "actions": [
        { "type": "snapshot", "save_dir": "./detections/snapshots" },
        { "type": "record", "save_dir": "./detections/videos", "duration_sec": 30, "extend_mode": "fixed" },
        { "type": "webhook", "url": "https://example.com/hook", "secret": "hmac-key" },
        { "type": "sse", "channel": "yolo_stream" },
        { "type": "mcp_event", "event": "yolo_stream.detection" }
      ]
    }
  ]
}
```

### POST /ext/hailo-yolo/api/stream/rules

新しいルールを追加する。リクエストボディにルール JSON 全体を渡す。

#### レスポンス (201)

```json
{ "status": "ok", "rule": { "..." : "..." } }
```

### PUT /ext/hailo-yolo/api/stream/rules/\<id\>

既存ルールを更新する。

#### レスポンス

```json
{ "status": "ok", "rule": { "..." : "..." } }
```

### DELETE /ext/hailo-yolo/api/stream/rules/\<id\>

ルールを削除する。

#### レスポンス

```json
{ "status": "ok" }
```

---

## 録画・スナップショット

### GET /ext/hailo-yolo/api/stream/recordings

録画ファイル一覧を取得する。

#### レスポンス

```json
{
  "status": "ok",
  "recordings": [
    { "filename": "cam1_20260328_220500.mp4", "path": "./detections/videos/cam1_20260328_220500.mp4", "size_bytes": 5242880, "created_at": "2026-03-28T22:05:00" }
  ]
}
```

### GET /ext/hailo-yolo/api/stream/snapshot/\<filename\>

スナップショット画像ファイルを返す。

---

## ステータス

### GET /ext/hailo-yolo/api/stream/status

パイプラインとソースの総合ステータスを取得する。

#### レスポンス

```json
{
  "status": "ok",
  "pipeline": { "running": true, "queue_size": 2, "fps": 24.8 },
  "sources": [ { "id": "cam1", "state": "running" } ],
  "rules_count": 3,
  "recorder": { "active_recordings": 1 }
}
```

---

## ルール JSON 構造

| フィールド | 型 | 説明 |
|-----------|------|------|
| `id` | string | ルールの一意識別子 |
| `name` | string | ルール名 |
| `enabled` | boolean | 有効フラグ |
| `conditions.classes` | string[] | 検出対象クラス（例: `["person"]`） |
| `conditions.min_confidence` | number | 最小信頼度（0.0〜1.0） |
| `conditions.sources` | string[] | 対象ソース ID。省略時は全ソース |
| `conditions.schedule` | object | スケジュール（`start`, `end`, `days`） |
| `cooldown_sec` | number | クールダウン秒数 |
| `actions` | object[] | アクション配列 |

### アクションタイプ

| type | 説明 |
|------|------|
| `snapshot` | 検出時にスナップショットを保存 |
| `record` | 検出時に録画を開始 |
| `webhook` | Webhook URL に通知（HMAC 署名付き） |
| `sse` | SSE チャネルにイベント送信 |
| `mcp_event` | MCP イベントを発火 |
