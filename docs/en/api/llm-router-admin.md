# API: /api/llm_router (Admin)

Admin endpoints for LLM Router management operations. Protected by the standard WebUI session authentication (PIN/session), and completely separate from the OpenAI-compatible `/v1/*` surface.

> **Note**: These are admin endpoints and are distinct from inference endpoints such as `/v1/chat/completions`.

---

## Common Response Format

All endpoints use the `api_result` wrapper. On success, the body is nested under the `data` key.

```json
{
  "status": "ok",
  "data": { ... }
}
```

On error:

```json
{
  "status": "error",
  "error": "Error description"
}
```

---

## GET /api/llm_router/status

A snapshot for rendering the entire dashboard in a single request. Returns all backend information and the alias map.

### Request

```
GET /api/llm_router/status
```

No parameters.

### Response `200 OK`

```json
{
  "status": "ok",
  "data": {
    "router": {
      "version": "1.0.0",
      "alias_count": 2
    },
    "backends": [
      {
        "alias": "ollama-mac",
        "base_url": "http://192.168.1.10:11434",
        "source": "static",
        "status": "ready",
        "slo_state": null,
        "disabled": false,
        "model_count": 3,
        "models": [
          {
            "name": "qwen2.5:7b",
            "context_window": 32768,
            "size_b": 7.6
          },
          {
            "name": "llama3.2:3b",
            "context_window": 128000,
            "size_b": 3.2
          }
        ],
        "last_seen": "2026-04-09T12:34:56.789123",
        "last_error": null
      },
      {
        "alias": "mdns-pi5-hailo",
        "base_url": "http://192.168.1.20:8080",
        "source": "mdns",
        "status": "unreachable",
        "slo_state": "unknown",
        "disabled": false,
        "model_count": 0,
        "models": [],
        "last_seen": null,
        "last_error": "Connection refused"
      }
    ],
    "aliases": {
      "default-llm": "ollama-mac/qwen2.5:7b",
      "fast-chat": "ollama-mac/llama3.2:3b"
    }
  }
}
```

### Field Descriptions

**`router`**

| Field | Type | Description |
|---|---|---|
| `version` | string | Router schema version (currently `"1.0.0"`) |
| `alias_count` | int | Number of defined aliases |

**`backends[]`**

| Field | Type | Description |
|---|---|---|
| `alias` | string | Unique backend identifier |
| `base_url` | string | Base URL of the OpenAI-compatible endpoint |
| `source` | string | `"static"` (config file) or `"mdns"` (auto-discovered) |
| `status` | string | `"ready"` / `"unreachable"` / `"unknown"` |
| `slo_state` | string \| null | `"vision_idle"` / `"vision_active"` / `"unknown"` / `null` |
| `disabled` | bool | `true` if excluded from routing |
| `model_count` | int | Number of exposed models |
| `models[]` | array | Model list (`name`, `context_window`, `size_b`) |
| `last_seen` | string \| null | Last successful connectivity check (ISO 8601) |
| `last_error` | string \| null | Last error message |

**`aliases`**

A map of logical alias names to physical model IDs (`backend-alias/model-name`).

---

## POST /api/llm_router/refresh

Forces a probe on all backends or a specified backend, updating `status` and the model list.

### Request

**To refresh all backends (no body):**

```
POST /api/llm_router/refresh
Content-Type: application/json

{}
```

An empty body without a Content-Type header is also accepted.

**To refresh a specific backend only:**

```json
{
  "alias": "ollama-mac"
}
```

### Response `200 OK`

```json
{
  "status": "ok",
  "data": {
    "refreshed": [
      {
        "alias": "ollama-mac",
        "status": "ready",
        "model_count": 3,
        "disabled": false,
        "last_error": null
      },
      {
        "alias": "mdns-pi5-hailo",
        "status": "unreachable",
        "model_count": 0,
        "disabled": false,
        "last_error": "Connection refused"
      }
    ]
  }
}
```

The `refreshed` array contains only lightweight update results (use `/status` for full details).

### Error `404 Not Found`

When an `alias` is specified but does not exist:

```json
{
  "status": "error",
  "error": "unknown backend: nonexistent-alias"
}
```

### Notes

- Probes are executed synchronously (the response is returned after completion)
- Probes are also executed for backends with `disabled: true` (status is still updated)
- mDNS-discovered backends are included

---

## POST /api/llm_router/backends/`<alias>`/disable

Disables the specified backend. Disabled backends are excluded from routing and the state is persisted to `data/llm_router_state.json`.

### Request

```
POST /api/llm_router/backends/ollama-mac/disable
```

No body required.

### Response `200 OK`

```json
{
  "status": "ok",
  "data": {
    "alias": "ollama-mac",
    "disabled": true
  }
}
```

### Error `404 Not Found`

```json
{
  "status": "error",
  "error": "unknown backend: nonexistent-alias"
}
```

### Error `500 Internal Server Error`

When persistence to disk fails (permission error, disk full, etc.). The in-memory state is rolled back.

```json
{
  "status": "error",
  "error": "failed to persist disabled state"
}
```

### Persistence Mechanism

1. Set the `disabled` flag to `true` in the in-memory catalog
2. Atomically write to `data/llm_router_state.json` (via `.tmp` file and `os.replace`)
3. If the write fails, step 1 is rolled back and a `500` is returned

The disabled state is preserved across application restarts. If an mDNS-discovered backend was disabled before startup, the disabled state is automatically applied after discovery.

---

## POST /api/llm_router/backends/`<alias>`/enable

Enables the specified backend. The reverse of `disable`.

### Request

```
POST /api/llm_router/backends/ollama-mac/enable
```

No body required.

### Response `200 OK`

```json
{
  "status": "ok",
  "data": {
    "alias": "ollama-mac",
    "disabled": false
  }
}
```

### Errors

Same as the `disable` endpoint (`404` / `500`). Persisted with `disabled: false`.

---

## Endpoint Summary

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/llm_router/status` | Get a snapshot of all backends and aliases |
| `POST` | `/api/llm_router/refresh` | Force probe on all or individual backends |
| `POST` | `/api/llm_router/backends/<alias>/disable` | Disable a backend (persisted) |
| `POST` | `/api/llm_router/backends/<alias>/enable` | Enable a backend (persisted) |

## Related Documentation

- [LLM Router WebUI Guide](../llm-router/webui.md)
- [LLM Router Setup](../llm-router/setup.md)
