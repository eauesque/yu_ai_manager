# API Flux YOLO

APIs for YOLO real-time stream processing. Provides stream source management, MJPEG delivery, detection rules, and recording/snapshot functionality.

All POST/PUT/DELETE endpoints require the `X-Requêteed-With` header (except lors de l'utilisation d'une clé API Bearer).

---

## Source Management

### GET /ext/hailo-yolo/api/stream/sources

Lister tous les registered stream sources.

#### Réponse

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

#### Requête

```json
{
  "id": "cam2",
  "url": "rtsp://192.168.1.101:554/stream",
  "name": "Back Camera"
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `id` | string | Yes | Unique source identifier |
| `url` | string | Yes | RTSP URL or device index |
| `name` | string | No | Display name |

#### Réponse (201)

```json
{ "status": "ok", "source": { "id": "cam2", "..." : "..." } }
```

### DELETE /ext/hailo-yolo/api/stream/sources/\<id\>

Remove the specified source.

#### Réponse

```json
{ "status": "ok" }
```

### POST /ext/hailo-yolo/api/stream/sources/\<id\>/start

Démarrer capture for the specified source.

#### Réponse

```json
{ "status": "ok", "source": { "id": "cam1", "state": "running", "..." : "..." } }
```

### POST /ext/hailo-yolo/api/stream/sources/\<id\>/stop

Arrêter capture for the specified source.

#### Réponse

```json
{ "status": "ok", "source": { "id": "cam1", "state": "stopped", "..." : "..." } }
```

### POST /ext/hailo-yolo/api/stream/sources/\<id\>/test

Test connection to a source. If a URL is provided in the request body, that URL is tested; otherwise the existing source URL is used.

#### Requête

```json
{ "url": "rtsp://192.168.1.100:554/stream" }
```

#### Réponse

```json
{ "ok": true, "resolution": { "width": 1920, "height": 1080 } }
```

### GET /ext/hailo-yolo/api/stream/devices

Detect connected USB cameras.

#### Réponse

```json
{
  "status": "ok",
  "devices": [
    { "index": 0, "name": "USB Camera", "resolution": null }
  ]
}
```

> **Remarque :** La réponse native Rust énumère les caméras USB uniquement sous Linux et ne les ouvre jamais ; `resolution` vaut toujours `null`. Windows et macOS renvoient `devices: []` et n'acceptent pas l'enregistrement par index numérique de caméra.
>
> La diffusion des événements est également réduite : aucune livraison wildcard implicite aux extensions webhook configurées, aucun relais LAN lorsqu'un nom d'événement personnalisé correspond à `RELAY_TYPES`, et aucun récepteur MCP dédié. `mcp_event` passe par le hub SSE partagé.

---

## Video Stream

### GET /ext/hailo-yolo/api/stream/\<id\>/mjpeg

Returns an MJPEG stream with YOLO detection overlay. Maximum 4 concurrent viewers per source.

- **Content-Type**: `multipart/x-mixed-replace; boundary=frame`

---

## Rule Management

### GET /ext/hailo-yolo/api/stream/rules

Lister tous les rules.

#### Réponse

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

#### Réponse (201)

```json
{ "status": "ok", "rule": { "..." : "..." } }
```

### PUT /ext/hailo-yolo/api/stream/rules/\<id\>

Update an existing rule.

#### Réponse

```json
{ "status": "ok", "rule": { "..." : "..." } }
```

### DELETE /ext/hailo-yolo/api/stream/rules/\<id\>

Delete a rule.

#### Réponse

```json
{ "status": "ok" }
```

---

## Recordings & Snapshots

### GET /ext/hailo-yolo/api/stream/recordings

List recording files.

#### Réponse

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

#### Réponse

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

| Champ | Type | Description |
|-------|------|-------------|
| `id` | string | Unique rule identifier |
| `name` | string | Rule name |
| `enabled` | boolean | Si the rule is active |
| `conditions.classes` | string[] | Target detection classes (e.g. `["person"]`) |
| `conditions.min_confidence` | number | Minimum confidence threshold (0.0-1.0) |
| `conditions.sources` | string[] | Target source IDs. All sources if omitted |
| `conditions.schedule` | object | Schedule (`start`, `end`, `days`) |
| `cooldown_sec` | number | Cooldown in seconds |
| `actions` | object[] | Tableau of actions |

### Action Types

| type | Description |
|------|-------------|
| `snapshot` | Save a snapshot on detection |
| `record` | Démarrer recording on detection |
| `webhook` | Send notification to webhook URL (with HMAC signature) |
| `sse` | Send event to SSE channel |
| `mcp_event` | Fire an MCP event |
