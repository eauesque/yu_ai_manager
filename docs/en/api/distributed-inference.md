# Distributed Inference API

REST API for the distributed inference server registry. Distributes CLIP semantic indexing workloads across multiple nodes using a shared-queue strategy.

## Endpoints

### GET /api/inference-servers

Returns the list of registered servers and the current dispatch mode.

**Response:**

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
- `servers`: array of server configuration objects

---

### POST /api/inference-servers

Register a new inference server.

**Request Body:**

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `name` | string | ✓ | — | Display name |
| `endpoint_url` | string | ✓ | — | Worker base URL |
| `inference_types` | string[] | — | `["clip"]` | Supported inference types |
| `priority` | int | — | `50` | Priority (lower value = higher priority) |
| `bearer_token` | string | — | — | Authentication token |
| `timeout` | int | — | `30` | Request timeout in seconds |

**Response:**

```json
{
  "status": "ok",
  "server": { ... }
}
```

---

### PUT /api/inference-servers/{server_id}

Update an existing server's configuration. Accepts a partial body with the same fields as POST.

---

### DELETE /api/inference-servers/{server_id}

Remove a server from the registry.

**Response:**

```json
{ "status": "ok" }
```

---

### POST /api/inference-servers/{server_id}/test

Run a health check against the specified server.

**Response:**

```json
{
  "status": "ok",
  "server_id": 1,
  "healthy": true,
  "latency_ms": 12.5
}
```

---

### GET /api/inference-servers/health

Run health checks against all enabled servers simultaneously.

**Response:**

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

### POST /api/inference-servers/mode

Set the dispatch mode.

**Request Body:**

| Field | Type | Required | Description |
|---|---|---|---|
| `mode` | string | ✓ | `"single"` \| `"parallel"` \| `"idle_first"` |

**Response:**

```json
{ "status": "ok", "mode": "parallel" }
```

---

## Dispatch Modes

| Mode | Description |
|---|---|
| `single` | Use only the highest-priority server (lowest priority value) |
| `parallel` | Distribute work across all enabled servers using a shared queue |
| `idle_first` | Health-check first, then distribute across responsive servers only |

## Distributed Semantic Indexing

Add `distributed: true` to the `POST /api/index/start` request body (semantic search extension) to enable distributed indexing using registered worker servers.

```json
{
  "batch_size": 32,
  "distributed": true
}
```

## Worker Server Setup

```bash
python deploy/hailo_tagger_server.py --port 9090
```

Supported endpoints:

| Path | Description |
|---|---|
| `GET /health` | Health check |
| `POST /tag` | WD-Tagger inference |
| `POST /clip-encode` | CLIP vector encoding |

## MCP Tools

| Tool | Description |
|---|---|
| `inference-servers-list` | List servers and get current mode |
| `inference-server-add` | Register a new server |
| `inference-server-update` | Update server configuration |
| `inference-server-remove` | Remove a server |
| `inference-server-health` | Run health checks |
| `inference-dispatch-mode-set` | Set dispatch mode |
