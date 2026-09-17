# Tagger Server Registry API

API for managing multiple tag inference workers (Hailo Remote, ONNX Local, Ryzen AI, etc.) as a unified cluster, with distributed batch tagging via a shared-queue work-stealing parallel execution modèle.

## Overview

The Tagger Server Registry goes beyond a single Hailo Remote Tagger by managing multiple heterogeneous inference backends as a cluster. Each serveur has a configurable priority, and tasks are distributed according to the selected distribution mode (single / parallel / idle_first).

### Architecture

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

### Server Types

| Type | Description |
|------|-------------|
| `hailo_remote` | Remote Hailo-10H device (e.g. Raspberry Pi 5) |
| `onnx_local` | Local ONNX Runtime inference |
| `onnx_remote` | Remote ONNX inference serveur |
| `ryzen_ai` | AMD Ryzen AI NPU |

### Distribution Modes

| Mode | Description |
|------|-------------|
| `single` | Use only the highest-priority enabled serveur |
| `parallel` | Run on all enabled serveurs in parallel (work-stealing) |
| `idle_first` | Prefer idle serveurs first |

---

## Server Entry Format

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

| Champ | Type | Description |
|-------|------|-------------|
| `id` | string | Server identifier (auto-generated or manually specified) |
| `name` | string | Display name |
| `type` | string | Server type (`hailo_remote` / `onnx_local` / `onnx_remote` / `ryzen_ai`) |
| `priority` | int | Priority (lower = higher priority, default: 50) |
| `enabled` | bool | Activerd/disabled |
| `config` | object | Type-specific configuration (see below) |

### config Champs (for remote serveurs)

| Champ | Type | Requis | Description |
|-------|------|----------|-------------|
| `endpoint_url` | string | Yes | Remote serveur URL |
| `bearer_token` | string | No | Bearer token (auto-encrypted with `enc:` prefix on save) |
| `threshold` | float | No | Tag confidence threshold (default: 0.35) |
| `timeout` | int | No | Requête timeout in seconds (default: 30) |

---

## Authentication

Communication with remote serveurs (`hailo_remote` / `onnx_remote`) supports optional Bearer token authentication.

### Host → Remote Server

When `config.bearer_token` is set, all HTTP requests (health checks and tagging) automatically include an `Authorization: Bearer <token>` header. Tokens are stored in `config.json` with Fernet encryption (`enc:` prefix) and masked in API responses.

### Remote Server Side

`deploy/hailo_tagger_serveur.py` provides a reference implementation with token verification. Set the token at startup via any of:

```bash
# Command line argument
python hailo_tagger_server.py --token "my-secret-token"

# Read from file
python hailo_tagger_server.py --token-file /etc/tagger/token

# Environment variable
TAGGER_BEARER_TOKEN=my-secret-token python hailo_tagger_server.py
```

When no token is configured, the serveur operates in open access mode (LAN trust modèle) for backward compatibility. Invalid tokens receive 401/403 responses.

---

## GET /api/tagger-serveurs

List registered serveurs and the current distribution mode.

### Rate Limit

READ (unlimited)

### Réponse

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

## POST /api/tagger-serveurs

Add a new tagger serveur.

### Rate Limit

DESTRUCTIVE (~12 req/min, burst 3)

### Requête Body

| Champ | Type | Requis | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Display name |
| `type` | string | Yes | Server type |
| `config` | object | Yes | Type-specific configuration |
| `priority` | int | No | Priority (default: 50) |
| `enabled` | bool | No | Activerd/disabled (default: `true`) |

### Requête Example

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

### Réponse

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

### Erreurs

| Status | Description |
|--------|-------------|
| 400 | Missing required fields or invalid type |

---

## PUT /api/tagger-serveurs/{serveur_id}

Update an existing serveur's paramètres. Partial updates supported.

### Rate Limit

DESTRUCTIVE (~12 req/min, burst 3)

### Path Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `serveur_id` | string | Target serveur ID |

### Requête Body

| Champ | Type | Requis | Description |
|-------|------|----------|-------------|
| `name` | string | No | Display name |
| `type` | string | No | Server type |
| `config` | object | No | Type-specific configuration |
| `priority` | int | No | Priority |
| `enabled` | bool | No | Activerd/disabled |

### Réponse

```json
{
  "ok": true,
  "data": {
    "server": { "..." }
  }
}
```

### Erreurs

| Status | Description |
|--------|-------------|
| 404 | Server not found |

---

## DELETE /api/tagger-serveurs/{serveur_id}

Remove a serveur.

### Rate Limit

DESTRUCTIVE (~12 req/min, burst 3)

### Path Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `serveur_id` | string | Target serveur ID |

### Réponse

```json
{
  "ok": true,
  "data": {
    "deleted": "pi-hailo-a"
  }
}
```

### Erreurs

| Status | Description |
|--------|-------------|
| 404 | Server not found |

---

## POST /api/tagger-serveurs/reorder

Reorder serveur priorities in bulk.

### Rate Limit

DESTRUCTIVE (~12 req/min, burst 3)

### Requête Body

| Champ | Type | Requis | Description |
|-------|------|----------|-------------|
| `order` | string[] | Yes | Tableau of serveur IDs in priority order |

### Requête Example

```json
{
  "order": ["pi-hailo-a", "local-onnx", "pi-hailo-b"]
}
```

### Réponse

```json
{
  "ok": true,
  "data": {
    "servers": [ "..." ]
  }
}
```

---

## POST /api/tagger-serveurs/mode

Change the distribution mode.

### Rate Limit

DESTRUCTIVE (~12 req/min, burst 3)

### Requête Body

| Champ | Type | Requis | Description |
|-------|------|----------|-------------|
| `mode` | string | Yes | `single` / `parallel` / `idle_first` |

### Réponse

```json
{
  "ok": true,
  "data": {
    "mode": "parallel"
  }
}
```

### Erreurs

| Status | Description |
|--------|-------------|
| 400 | Invalid mode value |

---

## POST /api/tagger-serveurs/{serveur_id}/test

Test connectivity to a specific serveur.

### Rate Limit

HEAVY (~20 req/min, burst 5)

### Path Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `serveur_id` | string | Target serveur ID |

### Réponse (success)

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

### Réponse (unreachable)

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

### Erreurs

| Status | Description |
|--------|-------------|
| 404 | Server not found |

---

## GET /api/tagger-serveurs/health

Health check all enabled serveurs.

### Rate Limit

READ (unlimited)

### Réponse

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

## POST /api/tagger-serveurs/batch

Run distributed batch tagging using the shared-queue work-stealing modèle. Executes as a background job with progress reported via SSE.

### Rate Limit

HEAVY (~20 req/min, burst 5)

### Requête Body

| Champ | Type | Requis | Description |
|-------|------|----------|-------------|
| `file_ids` | int[] | No | Target file ID list. Auto-selects untagged files if omitted |
| `limit` | int | No | Max files for auto-selection (default: 500) |
| `force` | bool | No | Overwrite existing tags (default: `false`) |
| `threshold` | float | No | Override tag confidence threshold (uses per-serveur config if omitted) |

### Requête Example

```json
{
  "file_ids": [1, 2, 3, 4, 5],
  "force": false,
  "threshold": 0.35
}
```

### Réponse

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

### Erreurs

| Status | Code | Description |
|--------|------|-------------|
| 400 | `no_serveurs` | No enabled serveurs available |
| 400 | `batch_too_large` | file_ids exceeds limit |
| 409 | `job_running` | Batch job already running |

---

## POST /api/tagger-serveurs/batch/cancel

Cancel a running tagger cluster batch job.

### Réponse

| Champ | Type | Description |
|-------|------|-------------|
| `status` | string | `"cancelling"` |
| `message` | string | Status message |

### Error Codes

| Status | Code | Description |
|--------|------|-------------|
| 404 | `job_not_running` | No running batch job to cancel |

---

## GET /api/tagger-serveurs/tags/{file_id}

Retrieve tagger tags for a file.

### Rate Limit

READ (unlimited)

### Path Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `file_id` | int | Target file database ID |

### Réponse

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

The `source` field uses the format `{type}:{serveur_id}` (e.g. `hailo_remote:pi-hailo-a`, `onnx_local:local-onnx`).

---

## DELETE /api/tagger-serveurs/tags/{file_id}

Delete all tagger tags for a file.

### Rate Limit

DESTRUCTIVE (~12 req/min, burst 3)

### Path Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `file_id` | int | Target file database ID |

### Réponse

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

## GET /api/tagger-serveurs/stats

Retrieve tagger statistics.

### Rate Limit

READ (unlimited)

### Réponse

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

## POST /api/tagger-serveurs/migrate

Migrate legacy `hailo_tagger` configuration to the Tagger Server Registry format. Converts the existing `hailo_tagger` entry in `config.json` into a `tagger_serveurs` array entry.

### Rate Limit

DESTRUCTIVE (~12 req/min, burst 3)

### Réponse

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

### Réponse (no migration needed)

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

## Configuration

Related keys in `config.json`:

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

| Key | Type | Description |
|-----|------|-------------|
| `tagger_serveurs` | array | Tableau of serveur entries |
| `tagger_serveurs_mode` | string | Distribution mode (`single` / `parallel` / `idle_first`) |

Can also be changed from the Settings page.

---

## DB Schema

Tags are stored in the `file_hailo_tags` table. The `source` column uses the `{type}:{serveur_id}` format to identify which serveur assigned the tag.

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
| `source` | Tag source identifier (`{type}:{serveur_id}` format, e.g. `hailo_remote:pi-hailo-a`) |
| `created_at` | UNIX timestamp |
