# Hailo Remote Tagger API

API for sending images to a remote Hailo AI HAT inference server (e.g. Raspberry Pi 5) over the network, running Danbooru tag inference, and saving results to the database.

## Overview

Even without a local GPU or ONNX runtime, you can use a Hailo-10H device on your LAN as a remote tagger. Images are sent as multipart/form-data, and tag JSON is returned as a response.

---

## GET /api/hailo-tagger/config

Retrieve current configuration.

### Rate Limit

READ (unlimited)

### Response

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

| Field | Type | Description |
|-------|------|-------------|
| `enabled` | bool | Whether Hailo Remote Tagger is enabled |
| `endpoint_url` | string | Pi endpoint URL (e.g. `http://192.168.1.50:8080`) |
| `threshold` | float | Tag confidence threshold (only tags above this are saved) |
| `timeout` | int | Request timeout in seconds |

---

## POST /api/hailo-tagger/config

Save configuration. Partial updates supported (only specified fields are changed).

### Rate Limit

DESTRUCTIVE (~12 req/min, burst 3)

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `enabled` | bool | No | Enable/disable |
| `endpoint_url` | string | No | Pi endpoint URL |
| `threshold` | float | No | Tag confidence threshold |
| `timeout` | int | No | Request timeout (seconds) |

### Request Example

```json
{
  "enabled": true,
  "endpoint_url": "http://192.168.1.50:8080",
  "threshold": 0.35
}
```

### Response

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

### Errors

| Status | Description |
|--------|-------------|
| 400 | Invalid JSON object |

---

## GET /api/hailo-tagger/status

Test connection to the Hailo endpoint. Sends a GET request to the `/health` endpoint to verify reachability.

### Rate Limit

READ (unlimited)

### Response (success)

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

### Response (not configured / unreachable)

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

Tag a single file.

### Rate Limit

HEAVY (~20 req/min, burst 5)

### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `file_id` | int | Target file database ID |

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `force` | bool | No | Overwrite existing tags (default: `false`) |

### Response

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

### Errors

| Status | Code | Description |
|--------|------|-------------|
| 400 | `disabled` | Hailo Tagger is disabled |
| 400 | `not_configured` | Endpoint URL not configured |
| 400 | `file_not_found` | File not found in database |
| 400 | `file_missing` | File does not exist on disk |
| 400 | `unsupported_type` | File type not supported for tagging |
| 502 | `request_failed` | Failed to connect to remote server |

---

## POST /api/hailo-tagger/batch

Tag multiple files in batch. Runs as a background job.

### Rate Limit

HEAVY (~20 req/min, burst 5)

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file_ids` | int[] | No | Target file ID list (max 500). Auto-selects untagged files if omitted |
| `limit` | int | No | Max files for auto-selection (default: 100) |
| `force` | bool | No | Overwrite existing tags (default: `false`) |

### Request Example

```json
{
  "file_ids": [1, 2, 3, 4, 5],
  "force": false
}
```

### Response

```json
{
  "ok": true,
  "data": {
    "started": true,
    "job_id": "hailo_tagger"
  }
}
```

### Errors

| Status | Code | Description |
|--------|------|-------------|
| 400 | `batch_too_large` | file_ids exceeds 500 |
| 409 | `job_running` | Batch job already running |

---

## GET /api/hailo-tagger/tags/{file_id}

Retrieve Hailo tags for a file.

### Rate Limit

READ (unlimited)

### Response

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

Delete all Hailo tags for a file.

### Rate Limit

DESTRUCTIVE (~12 req/min, burst 3)

### Response

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

## DB Schema

Hailo tags are stored in a dedicated `file_hailo_tags` table (independent from `file_wd_tags`).

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

| Column | Description |
|--------|-------------|
| `file_id` | Foreign key to files table |
| `tag_name` | Danbooru tag name (e.g. `1girl`, `solo`) |
| `confidence` | Inference confidence (0.0-1.0) |
| `source` | Tag source identifier (`hailo_remote` or `hailo_remote:<server_id>` when using the registry) |
| `created_at` | UNIX timestamp |

---

## Configuration

`hailo_tagger` section in `config.json`:

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

Can also be changed from the Settings page.

> **Note**: To manage multiple tagger servers, use the [Tagger Server Registry API](tagger-servers.md). Legacy configuration can be auto-migrated via `/api/tagger-servers/migrate`. The Tagger Server Registry also supports Bearer token authentication.
