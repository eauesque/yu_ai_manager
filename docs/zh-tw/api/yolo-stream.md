# YOLO Stream API

YOLO 即時串流處理相關 API。提供串流來源管理、MJPEG 傳輸、偵測規則、錄影與快照功能。

所有 POST/PUT/DELETE 端點需要 `X-Requested-With` 標頭（使用 Bearer API Key 時除外）。

---

## 來源管理

### GET /ext/hailo-yolo/api/stream/sources

列出所有已註冊的串流來源。

#### 回應

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

新增串流來源。

#### 請求

```json
{
  "id": "cam2",
  "url": "rtsp://192.168.1.101:554/stream",
  "name": "Back Camera"
}
```

| 參數 | 型別 | 必須 | 說明 |
|------|------|------|------|
| `id` | string | 是 | 來源的唯一識別碼 |
| `url` | string | 是 | RTSP URL 或裝置索引 |
| `name` | string | 否 | 顯示名稱 |

#### 回應 (201)

```json
{ "status": "ok", "source": { "id": "cam2", "..." : "..." } }
```

### DELETE /ext/hailo-yolo/api/stream/sources/\<id\>

移除指定來源。

#### 回應

```json
{ "status": "ok" }
```

### POST /ext/hailo-yolo/api/stream/sources/\<id\>/start

啟動指定來源的擷取。

#### 回應

```json
{ "status": "ok", "source": { "id": "cam1", "state": "running", "..." : "..." } }
```

### POST /ext/hailo-yolo/api/stream/sources/\<id\>/stop

停止指定來源的擷取。

#### 回應

```json
{ "status": "ok", "source": { "id": "cam1", "state": "stopped", "..." : "..." } }
```

### POST /ext/hailo-yolo/api/stream/sources/\<id\>/test

測試來源連線。若請求中提供 URL 則測試該 URL，否則使用既有來源的 URL。

#### 請求

```json
{ "url": "rtsp://192.168.1.100:554/stream" }
```

#### 回應

```json
{ "ok": true, "resolution": { "width": 1920, "height": 1080 } }
```

### GET /ext/hailo-yolo/api/stream/devices

偵測已連接的 USB 攝影機。

#### 回應

```json
{
  "status": "ok",
  "devices": [
    { "index": 0, "name": "USB Camera", "resolution": null }
  ]
}
```

> **說明：** Rust 原生回應僅在 Linux 上列舉 USB 攝影機，而且不會開啟裝置；`resolution` 一律為 `null`。Windows 與 macOS 回傳 `devices: []`，也不支援以數字攝影機 index 註冊。
>
> event fan-out 亦會縮減：不再向已設定的 webhook 擴充功能隱式 wildcard 配送；custom event 名稱符合 `RELAY_TYPES` 時不再進行 LAN relay；不再到達專用 MCP event 接收端。`mcp_event` 透過共用 SSE hub 配送。

---

## 影像串流

### GET /ext/hailo-yolo/api/stream/\<id\>/mjpeg

回傳帶有 YOLO 偵測疊加的 MJPEG 串流。每個來源最多 4 個同時觀看者。

- **Content-Type**: `multipart/x-mixed-replace; boundary=frame`

---

## 規則管理

### GET /ext/hailo-yolo/api/stream/rules

列出所有規則。

#### 回應

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

新增規則。在請求主體中傳入完整的規則 JSON。

#### 回應 (201)

```json
{ "status": "ok", "rule": { "..." : "..." } }
```

### PUT /ext/hailo-yolo/api/stream/rules/\<id\>

更新既有規則。

#### 回應

```json
{ "status": "ok", "rule": { "..." : "..." } }
```

### DELETE /ext/hailo-yolo/api/stream/rules/\<id\>

刪除規則。

#### 回應

```json
{ "status": "ok" }
```

---

## 錄影與快照

### GET /ext/hailo-yolo/api/stream/recordings

列出錄影檔案。

#### 回應

```json
{
  "status": "ok",
  "recordings": [
    { "filename": "cam1_20260328_220500.mp4", "path": "./detections/videos/cam1_20260328_220500.mp4", "size_bytes": 5242880, "created_at": "2026-03-28T22:05:00" }
  ]
}
```

### GET /ext/hailo-yolo/api/stream/snapshot/\<filename\>

提供快照圖片檔案。

---

## 狀態

### GET /ext/hailo-yolo/api/stream/status

取得管線與來源的綜合狀態。

#### 回應

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

## 規則 JSON 結構

| 欄位 | 型別 | 說明 |
|------|------|------|
| `id` | string | 規則的唯一識別碼 |
| `name` | string | 規則名稱 |
| `enabled` | boolean | 啟用旗標 |
| `conditions.classes` | string[] | 偵測目標類別（例：`["person"]`） |
| `conditions.min_confidence` | number | 最低信賴度（0.0〜1.0） |
| `conditions.sources` | string[] | 目標來源 ID。省略時套用全部來源 |
| `conditions.schedule` | object | 排程（`start`、`end`、`days`） |
| `cooldown_sec` | number | 冷卻秒數 |
| `actions` | object[] | 動作陣列 |

### 動作類型

| type | 說明 |
|------|------|
| `snapshot` | 偵測時儲存快照 |
| `record` | 偵測時開始錄影 |
| `webhook` | 傳送通知至 Webhook URL（含 HMAC 簽名） |
| `sse` | 傳送事件至 SSE 頻道 |
| `mcp_event` | 觸發 MCP 事件 |
