# AI Analysis API

APIs for AI-powered image analysis, prompt trend analysis, and server management.

All POST/PUT/DELETE endpoints require the `X-Requested-With` header (not required when using Bearer API Key).

## Rate Limit

Write endpoints under `/api/analysis/` use the **HEAVY** tier (~20 req/min, burst 5). GET endpoints are unlimited.

---

## Configuration

### GET /api/analysis/config

Get the current AI analysis configuration. API keys are returned masked.

#### Response

```json
{
  "engine": "ollama",
  "api_key": "sk-T...xy",
  "model": "claude-sonnet-4-6",
  "ollama_url": "http://localhost:11434",
  "ollama_model": "llava:latest",
  "openai_api_key": "sk-...xy",
  "openai_model": "gpt-4o-mini",
  "openai_compat_url": "http://localhost:8080/v1",
  "openai_compat_api_key": "***...ey",
  "openai_compat_model": "qwen2-vl",
  "hailo_vlm_model": "qwen2-vl-2b-instruct",
  "fallback_local_only": false,
  "language": "ja",
  "is_local": true,
  "has_servers": true,
  "servers": [],
  "active_server": "ollama-main"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `engine` | string | Current engine type (`claude_api`, `openai`, `ollama`, `openai_compat`, `hailo_vlm`) |
| `api_key` | string | Claude API key (masked) |
| `model` | string | Claude API model name |
| `ollama_url` | string | Ollama server URL |
| `ollama_model` | string | Ollama model name |
| `openai_api_key` | string | OpenAI API key (masked) |
| `openai_model` | string | OpenAI model name |
| `openai_compat_url` | string | OpenAI-compatible server URL |
| `openai_compat_api_key` | string | OpenAI-compatible API key (masked) |
| `openai_compat_model` | string | OpenAI-compatible model name |
| `hailo_vlm_model` | string | Hailo VLM model name |
| `fallback_local_only` | boolean | Whether to restrict to local engines only |
| `language` | string | Language for analysis results (`ja`, `en`, etc.) |
| `is_local` | boolean | Whether the current engine is local (free) |
| `has_servers` | boolean | Whether the server registry is configured |
| `servers` | array | Server list (only when `has_servers` is true) |
| `active_server` | string | Active server ID (only when `has_servers` is true) |

### POST /api/analysis/config

Save AI analysis configuration. Masked values (strings containing `...`) are not overwritten. API keys are automatically encrypted.

#### Rate Limit

HEAVY

#### Request

```json
{
  "engine": "ollama",
  "ollama_url": "http://localhost:11434",
  "ollama_model": "llava:latest",
  "language": "ja"
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `engine` | string | No | Engine type |
| `api_key` | string | No | Claude API key |
| `model` | string | No | Claude API model |
| `ollama_url` | string | No | Ollama server URL |
| `ollama_model` | string | No | Ollama model name |
| `openai_api_key` | string | No | OpenAI API key |
| `openai_model` | string | No | OpenAI model name |
| `openai_compat_url` | string | No | OpenAI-compatible server URL |
| `openai_compat_api_key` | string | No | OpenAI-compatible API key |
| `openai_compat_model` | string | No | OpenAI-compatible model name |
| `hailo_vlm_model` | string | No | Hailo VLM model name |
| `fallback_local_only` | boolean | No | Restrict to local engines only |
| `language` | string | No | Language for analysis results |

#### Response

```json
{
  "success": true
}
```

---

## Engine Discovery

### GET /api/analysis/available-engines

Get a list of configured and reachable engines. Cloud engines are excluded when `fallback_local_only` is enabled.

#### Response

```json
{
  "engines": [
    {
      "type": "ollama",
      "label": "Ollama",
      "model": "llava:latest",
      "models": ["llava:latest", "llava:13b", "bakllava:latest"]
    },
    {
      "type": "hailo_vlm",
      "label": "Hailo VLM",
      "model": "qwen2-vl-2b-instruct",
      "models": ["qwen2-vl-2b-instruct"]
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `engines[].type` | string | Engine type identifier |
| `engines[].label` | string | Display label |
| `engines[].model` | string | Currently configured model |
| `engines[].models` | string[] | List of available models |

---

## Single File Analysis

### POST /api/analysis/analyze/\<file_id\>

Analyze a single file with an AI engine. Supports images, videos, and images inside archives.

#### Rate Limit

HEAVY

#### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `file_id` | int | File ID (path parameter) |

#### Request

JSON body is optional. When omitted, default settings are used.

```json
{
  "mode": "full",
  "engine": "ollama",
  "model": "llava:latest",
  "server_id": "ollama-main"
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `mode` | string | No | Analysis mode. Default `"full"` |
| `engine` | string | No | Override engine type |
| `model` | string | No | Override model name |
| `server_id` | string | No | Specify server ID to use |

#### Response (200)

```json
{
  "success": true,
  "result": {
    "description": "A landscape painting with mountains...",
    "style": "digital art",
    "quality_score": 8,
    "tags": ["landscape", "mountains", "sunset"]
  },
  "engine": "Ollama (llava:latest)"
}
```

#### Error Responses

- `400`: Engine not configured / invalid engine specified
- `404`: File not found / file does not exist on disk
- `500`: Error during analysis

### GET /api/analysis/result/\<file_id\>

Retrieve stored analysis results for a file. Returns all results when multiple engines/modes have been used.

#### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `file_id` | int | File ID (path parameter) |

#### Response (200) -- Results Found

```json
{
  "found": true,
  "result": {
    "engine": "Ollama (llava:latest)",
    "description": "A landscape painting...",
    "style": "digital art",
    "quality_score": 8,
    "analyzed_at": 1709500000
  },
  "results": [
    {
      "engine": "Ollama (llava:latest)",
      "description": "A landscape painting...",
      "style": "digital art",
      "quality_score": 8,
      "analyzed_at": 1709500000
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `found` | boolean | Whether analysis results exist |
| `result` | object | Most recent analysis result (backward compatibility) |
| `results` | array | Array of all analysis results |

#### Response (200) -- No Results

```json
{
  "found": false
}
```

---

## Batch Analysis

### POST /api/analysis/batch

Start a batch AI analysis job on unanalyzed files. Runs in the background.

#### Rate Limit

HEAVY

#### Request

```json
{
  "limit": 10,
  "scan_root": "",
  "file_ids": [],
  "server_ids": ["ollama-main", "openai-compat"]
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `limit` | int | No | Maximum number of files to analyze. Default 10. Capped at 10 for cloud engines. 0 means all files for local engines |
| `scan_root` | string | No | Restrict targets to a specific scan root |
| `file_ids` | int[] | No | Directly specify file IDs to analyze |
| `server_ids` | string[] | No | Server IDs to use. Multiple servers enable parallel analysis |

#### Response (200)

```json
{
  "started": true,
  "count": 10,
  "parallel": false
}
```

| Field | Type | Description |
|-------|------|-------------|
| `started` | boolean | Whether the job was started |
| `count` | int | Number of files to analyze |
| `parallel` | boolean | Whether running in parallel (multiple `server_ids`) |
| `worker` | boolean | True if dispatched via inference worker |
| `subprocess` | boolean | True if running in subprocess (Hailo VLM) |

#### Error Responses

- `400`: No files to analyze
- `409`: AI analysis job already running

### POST /api/analysis/batch/cancel

Cancel a running batch AI analysis job.

#### Rate Limit

HEAVY

#### Request

No body required.

#### Response (200)

```json
{
  "status": "cancelling",
  "message": "AI analysis cancel requested"
}
```

#### Error Responses

- `404`: No running AI analysis job

---

## Prompt Trend Analysis

### POST /api/analysis/trends

Run trend analysis on the 50 most recent prompts. Results are automatically saved to history.

#### Rate Limit

HEAVY

#### Request

No body required.

#### Response (200)

```json
{
  "success": true,
  "result": {
    "summary": "Recent prompts focus on landscape and character art...",
    "top_themes": ["landscape", "character", "fantasy"],
    "trend_direction": "increasing variety"
  }
}
```

#### Error Responses

- `400`: API key not configured (when using cloud engines)
- `500`: Error during trend analysis

### GET /api/analysis/trends/history

Get prompt trend analysis history. Sorted newest first. Maximum 50 entries retained.

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | int | 20 | Number of entries to fetch (max 50) |
| `offset` | int | 0 | Offset |

#### Response

```json
{
  "items": [
    {
      "id": 5,
      "engine": "ollama",
      "analyzed_at": 1709500000,
      "prompt_count": 50,
      "result": {
        "summary": "Recent prompts focus on...",
        "top_themes": ["landscape", "character"]
      }
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `items[].id` | int | History entry ID |
| `items[].engine` | string | Engine type used |
| `items[].analyzed_at` | int | UNIX timestamp of analysis |
| `items[].prompt_count` | int | Number of prompts analyzed |
| `items[].result` | object | Trend analysis result |

### DELETE /api/analysis/trends/history/\<history_id\>

Delete a single trend analysis history entry.

#### Rate Limit

HEAVY

#### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `history_id` | int | History entry ID (path parameter) |

#### Response

```json
{
  "deleted": true
}
```

#### Error Responses

- `404`: History entry not found

---

## Statistics

### GET /api/analysis/stats

Get AI analysis statistics.

#### Response

```json
{
  "total_analyzed": 150,
  "total_files": 1200,
  "styles": [
    { "style": "digital art", "count": 45 },
    { "style": "anime", "count": 30 }
  ],
  "quality_distribution": [
    { "tier": "excellent", "count": 20, "avg_score": 8.5 },
    { "tier": "good", "count": 60, "avg_score": 6.8 },
    { "tier": "average", "count": 50, "avg_score": 4.9 },
    { "tier": "low", "count": 20, "avg_score": 2.3 }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `total_analyzed` | int | Number of analyzed files |
| `total_files` | int | Total number of files (excluding deleted) |
| `styles` | array | Style breakdown (top 10) |
| `styles[].style` | string | Style name |
| `styles[].count` | int | Number of files |
| `quality_distribution` | array | Quality score distribution |
| `quality_distribution[].tier` | string | Quality tier (`excellent` >= 8, `good` >= 6, `average` >= 4, `low` < 4) |
| `quality_distribution[].count` | int | Number of files |
| `quality_distribution[].avg_score` | float | Average score |

---

## Ollama Connection

### GET /api/analysis/ollama/models

Connect to the configured Ollama server and list available models.

#### Response

```json
{
  "available": true,
  "models": [
    { "name": "llava:latest", "size": 4700000000 }
  ]
}
```

#### Error Responses

- `400`: Invalid Ollama URL

### POST /api/analysis/ollama/test

Test connection to an Ollama server at the specified URL.

#### Rate Limit

HEAVY

#### Request

```json
{
  "ollama_url": "http://localhost:11434"
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `ollama_url` | string | Yes | Ollama server URL to test |

#### Response

```json
{
  "available": true,
  "models": [
    { "name": "llava:latest", "size": 4700000000 }
  ]
}
```

#### Error Responses

- `400`: URL is empty / URL is invalid

---

## OpenAI-Compatible Server Connection

### GET /api/analysis/openai-compat/models

Connect to the configured OpenAI-compatible server and list available models.

#### Response

```json
{
  "available": true,
  "models": [
    { "id": "qwen2-vl-7b-instruct" }
  ]
}
```

#### Error Responses

- `400`: URL not configured / URL is invalid

### POST /api/analysis/openai-compat/test

Test connection to an OpenAI-compatible server at the specified URL.

#### Rate Limit

HEAVY

#### Request

```json
{
  "url": "http://localhost:8080/v1",
  "api_key": "optional-key"
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `url` | string | Yes | URL to test |
| `api_key` | string | No | API key (if required) |

#### Response

```json
{
  "available": true,
  "models": [
    { "id": "qwen2-vl-7b-instruct" }
  ]
}
```

#### Error Responses

- `400`: URL is empty / URL is invalid

---

## AI Server Registry

Register and manage multiple AI servers with priority-based fallback and parallel analysis.

### GET /api/analysis/servers

List all registered servers with status. API keys are masked.

#### Response

```json
{
  "servers": [
    {
      "id": "ollama-main",
      "name": "Ollama (llava:latest)",
      "type": "ollama",
      "priority": 10,
      "enabled": true,
      "config": {
        "base_url": "http://localhost:11434",
        "model": "llava:latest"
      },
      "is_active": true,
      "status": "unknown"
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `servers[].id` | string | Server ID (immutable) |
| `servers[].name` | string | Display name |
| `servers[].type` | string | Engine type (`claude_api`, `openai`, `ollama`, `openai_compat`, `hailo_vlm`) |
| `servers[].priority` | int | Priority (lower = higher priority) |
| `servers[].enabled` | boolean | Enabled/disabled |
| `servers[].config` | object | Engine-specific configuration |
| `servers[].is_active` | boolean | Whether this is the currently active server |
| `servers[].status` | string | Connection status (always `"unknown"` in list view) |

### POST /api/analysis/servers

Register a new server. The first server is automatically set as active.

#### Rate Limit

HEAVY

#### Request

```json
{
  "name": "Local Ollama",
  "type": "ollama",
  "config": {
    "base_url": "http://localhost:11434",
    "model": "llava:latest"
  }
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | string | Yes | Server name |
| `type` | string | Yes | Engine type |
| `config` | object | Yes | Engine-specific configuration |
| `priority` | int | No | Priority |
| `enabled` | boolean | No | Enabled/disabled. Default true |

#### Response (201)

```json
{
  "success": true,
  "server": {
    "id": "local-ollama",
    "name": "Local Ollama",
    "type": "ollama",
    "priority": 10,
    "enabled": true,
    "config": { "base_url": "http://localhost:11434", "model": "llava:latest" }
  }
}
```

#### Error Responses

- `400`: Validation error / server limit reached

### PUT /api/analysis/servers/\<server_id\>

Update a server's settings. The `id` field cannot be changed.

#### Rate Limit

HEAVY

#### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `server_id` | string | Server ID (path parameter) |

#### Request

```json
{
  "name": "Updated Name",
  "type": "ollama",
  "priority": 20,
  "enabled": true,
  "config": { "base_url": "http://192.168.1.100:11434", "model": "llava:13b" }
}
```

All fields are optional. Only specified fields are updated.

#### Response

```json
{
  "success": true,
  "server": { "id": "ollama-main", "name": "Updated Name", "..." : "..." }
}
```

#### Error Responses

- `400`: Invalid type / server not found

### DELETE /api/analysis/servers/\<server_id\>

Delete a server. If the active server is deleted, the next highest-priority server becomes active automatically.

#### Rate Limit

HEAVY

#### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `server_id` | string | Server ID (path parameter) |

#### Response

```json
{
  "success": true
}
```

#### Error Responses

- `400`: Server not found

### POST /api/analysis/servers/\<server_id\>/activate

Switch the active server.

#### Rate Limit

HEAVY

#### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `server_id` | string | Server ID (path parameter) |

#### Response

```json
{
  "success": true,
  "active": "ollama-main"
}
```

#### Error Responses

- `400`: Server not found

### POST /api/analysis/servers/\<server_id\>/test

Run a connectivity test on a server. Response time is also measured.

#### Rate Limit

HEAVY

#### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `server_id` | string | Server ID (path parameter) |

#### Response

```json
{
  "success": true,
  "available": true,
  "elapsed_ms": 45,
  "server": {
    "id": "ollama-main",
    "name": "Local Ollama",
    "type": "ollama",
    "config": { "..." : "..." }
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `available` | boolean | Whether the server is reachable |
| `elapsed_ms` | int | Connection test response time in milliseconds |
| `server` | object | Server information |

#### Error Responses

- `400`: Server not found

### PUT /api/analysis/servers/reorder

Bulk-update server priorities.

#### Rate Limit

HEAVY

#### Request

```json
{
  "server_ids": ["ollama-main", "openai-compat", "claude-api"]
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `server_ids` | string[] | Yes | Array of server IDs. The specified order becomes the new priority order |

#### Response

```json
{
  "success": true
}
```

#### Error Responses

- `400`: `server_ids` is not an array

### POST /api/analysis/servers/migrate

Auto-migrate from legacy `ai_analysis` config to the new server registry format. Fails if servers already exist.

#### Rate Limit

HEAVY

#### Request

No body required.

#### Response

```json
{
  "success": true,
  "servers": [
    { "id": "ollama", "name": "Ollama (llava:latest)", "type": "ollama", "..." : "..." }
  ],
  "migrated": 3
}
```

| Field | Type | Description |
|-------|------|-------------|
| `servers` | array | Servers created by migration |
| `migrated` | int | Number of servers created |

#### Error Responses

- `400`: `ai_servers` already exists
