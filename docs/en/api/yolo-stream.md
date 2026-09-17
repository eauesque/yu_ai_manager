# YOLO Stream API

APIs for YOLO real-time stream processing. Provides stream source management, MJPEG delivery, detection rules, and recording/snapshot functionality.

All POST/PUT/DELETE endpoints require the `X-Requested-With` header (except when using Bearer API Key).

---

## Source Management

### GET /ext/hailo-yolo/api/stream/sources

List all registered stream sources.

#### Response

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

Add a new stream source.

#### Request

```json
{
  "id": "cam2",
  "url": "rtsp://192.168.1.101:554/stream",
  "name": "Back Camera"
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `id` | string | Yes | Unique source identifier |
| `url` | string | Yes | RTSP URL or device index |
| `name` | string | No | Display name |

#### Response (201)

```json
{ "status": "ok", "source": { "id": "cam2", "..." : "..." } }
```

### DELETE /ext/hailo-yolo/api/stream/sources/\<id\>

Remove the specified source.

#### Response

```json
{ "status": "ok" }
```

### POST /ext/hailo-yolo/api/stream/sources/\<id\>/start

Start capture for the specified source.

#### Response

```json
{ "status": "ok", "source": { "id": "cam1", "state": "running", "..." : "..." } }
```

### POST /ext/hailo-yolo/api/stream/sources/\<id\>/stop

Stop capture for the specified source.

#### Response

```json
{ "status": "ok", "source": { "id": "cam1", "state": "stopped", "..." : "..." } }
```

### POST /ext/hailo-yolo/api/stream/sources/\<id\>/test

Test connection to a source. If a URL is provided in the request body, that URL is tested; otherwise the existing source URL is used.

#### Request

```json
{ "url": "rtsp://192.168.1.100:554/stream" }
```

#### Response

```json
{ "ok": true, "resolution": { "width": 1920, "height": 1080 } }
```

### GET /ext/hailo-yolo/api/stream/devices

Detect connected USB cameras.

#### Response

```json
{
  "status": "ok",
  "devices": [
    { "index": 0, "name": "USB Camera", "resolution": null }
  ]
}
```

> **Note:** The Rust-native response lists USB cameras on Linux only and never opens them; `resolution` is always `null`. Windows and macOS return `devices: []`, and numeric camera-index registration is unsupported there.
>
> Event fan-out is also reduced: there is no implicit wildcard delivery to configured webhook extensions, no LAN relay when a custom event name matches `RELAY_TYPES`, and no dedicated MCP event sink. `mcp_event` is delivered through the shared SSE hub.

---

## Video Stream

### GET /ext/hailo-yolo/api/stream/\<id\>/mjpeg

Returns an MJPEG stream with YOLO detection overlay. Maximum 4 concurrent viewers per source.

- **Content-Type**: `multipart/x-mixed-replace; boundary=frame`

---

## Rule Management

### GET /ext/hailo-yolo/api/stream/rules

List all rules.

#### Response

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

Add a new rule. Pass the full rule JSON in the request body.

#### Response (201)

```json
{ "status": "ok", "rule": { "..." : "..." } }
```

### PUT /ext/hailo-yolo/api/stream/rules/\<id\>

Update an existing rule.

#### Response

```json
{ "status": "ok", "rule": { "..." : "..." } }
```

### DELETE /ext/hailo-yolo/api/stream/rules/\<id\>

Delete a rule.

#### Response

```json
{ "status": "ok" }
```

---

## Recordings & Snapshots

### GET /ext/hailo-yolo/api/stream/recordings

List recording files.

#### Response

```json
{
  "status": "ok",
  "recordings": [
    { "filename": "cam1_20260328_220500.mp4", "path": "./detections/videos/cam1_20260328_220500.mp4", "size_bytes": 5242880, "created_at": "2026-03-28T22:05:00" }
  ]
}
```

### GET /ext/hailo-yolo/api/stream/snapshot/\<filename\>

Serve a snapshot image file.

---

## Status

### GET /ext/hailo-yolo/api/stream/status

Get overall pipeline and source status.

#### Response

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

## Rule JSON Structure

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique rule identifier |
| `name` | string | Rule name |
| `enabled` | boolean | Whether the rule is active |
| `conditions.classes` | string[] | Target detection classes (e.g. `["person"]`) |
| `conditions.min_confidence` | number | Minimum confidence threshold (0.0-1.0) |
| `conditions.sources` | string[] | Target source IDs. All sources if omitted |
| `conditions.schedule` | object | Schedule (`start`, `end`, `days`) |
| `cooldown_sec` | number | Cooldown in seconds |
| `actions` | object[] | Array of actions |

### Action Types

| type | Description |
|------|-------------|
| `snapshot` | Save a snapshot on detection |
| `record` | Start recording on detection |
| `webhook` | Send notification to webhook URL (with HMAC signature) |
| `sse` | Send event to SSE channel |
| `mcp_event` | Fire an MCP event |
