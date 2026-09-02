# API Analyse IA

APIs pour l'analyse d'images alimentée par l'IA, l'analyse des tendances des invites et la gestion des serveurs.

All POST/PUT/DELETE endpoints require the `X-Requêteed-With` header (not required lors de l'utilisation d'une clé API Bearer).

## Rate Limit

Write endpoints under `/api/analysis/` use the **HEAVY** tier (~20 req/min, burst 5). GET endpoints are unlimited.

---

## Configuration

### GET /api/analysis/config

Obtenir le AI analysis configuration. clé APIs sont retournées masquées.

#### Réponse

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

| Champ | Type | Description |
|-------|------|-------------|
| `engine` | string | Type de moteur actuel (`claude_api`, `openai`, `ollama`, `openai_compat`, `hailo_vlm`) |
| `api_key` | string | Claude clé API (masked) |
| `modèle` | string | Claude API modèle name |
| `ollama_url` | string | Ollama serveur URL |
| `ollama_modèle` | string | Ollama modèle name |
| `openai_api_key` | string | OpenAI clé API (masked) |
| `openai_modèle` | string | OpenAI modèle name |
| `openai_compat_url` | string | OpenAI-compatible serveur URL |
| `openai_compat_api_key` | string | OpenAI-compatible clé API (masked) |
| `openai_compat_modèle` | string | OpenAI-compatible modèle name |
| `hailo_vlm_modèle` | string | Hailo VLM modèle name |
| `fallback_local_only` | boolean | Si to restrict to local engines only |
| `language` | string | Langue des résultats d'analyse (`ja`, `en`, etc.) |
| `is_local` | boolean | Si the current engine is local (free) |
| `has_serveurs` | boolean | Si the serveur registry is configured |
| `serveurs` | array | Liste des serveurs (only when `has_serveurs` is true) |
| `active_serveur` | string | Active serveur ID (only when `has_serveurs` is true) |

### POST /api/analysis/config

Enregistrer la configuration de l'analyse IA. Les valeurs masquées (chaînes contenant `...`) ne sont pas remplacées. Les clés API sont automatiquement chiffrées.

#### Rate Limit

HEAVY

#### Requête

```json
{
  "engine": "ollama",
  "ollama_url": "http://localhost:11434",
  "ollama_model": "llava:latest",
  "language": "ja"
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `engine` | string | No | Engine type |
| `api_key` | string | No | Claude clé API |
| `modèle` | string | No | Claude API modèle |
| `ollama_url` | string | No | Ollama serveur URL |
| `ollama_modèle` | string | No | Ollama modèle name |
| `openai_api_key` | string | No | OpenAI clé API |
| `openai_modèle` | string | No | OpenAI modèle name |
| `openai_compat_url` | string | No | OpenAI-compatible serveur URL |
| `openai_compat_api_key` | string | No | OpenAI-compatible clé API |
| `openai_compat_modèle` | string | No | OpenAI-compatible modèle name |
| `hailo_vlm_modèle` | string | No | Hailo VLM modèle name |
| `fallback_local_only` | boolean | No | Restrict to local engines only |
| `language` | string | No | Langue des résultats d'analyse |

#### Réponse

```json
{
  "success": true
}
```

---

## Engine Discovery

### GET /api/analysis/available-engines

Obtenir une liste de configured and reachable engines. Cloud engines are excluded when `fallback_local_only` is enabled.

#### Réponse

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

| Champ | Type | Description |
|-------|------|-------------|
| `engines[].type` | string | Engine type identifier |
| `engines[].label` | string | Display label |
| `engines[].modèle` | string | Currently configured modèle |
| `engines[].modèles` | string[] | List of available modèles |

---

## Single File Analysis

### POST /api/analysis/analyze/\<file_id\>

Analyze a single file with an AI engine. Supports images, videos, and images inside archives.

#### Rate Limit

HEAVY

#### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `file_id` | int | File ID (path parameter) |

#### Requête

JSON body is optional. When omitted, default paramètres are used.

```json
{
  "mode": "full",
  "engine": "ollama",
  "model": "llava:latest",
  "server_id": "ollama-main"
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `mode` | string | No | Analysis mode. Défaut `"full"` |
| `engine` | string | No | Override engine type |
| `modèle` | string | No | Override modèle name |
| `serveur_id` | string | No | Specify serveur ID to use |

#### Réponse (200)

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

#### Error Réponses

- `400`: Engine not configured / invalid engine specified
- `404`: File not found / file does not exist on disk
- `500`: Error during analysis

### GET /api/analysis/result/\<file_id\>

Retrieve stored analysis results for a file. Returns all results when multiple engines/modes have been used.

#### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `file_id` | int | File ID (path parameter) |

#### Réponse (200) -- Results Found

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

| Champ | Type | Description |
|-------|------|-------------|
| `found` | boolean | Si analysis results exist |
| `result` | object | Most recent analysis result (backward compatibility) |
| `results` | array | Tableau of all analysis results |

#### Réponse (200) -- No Results

```json
{
  "found": false
}
```

---

## Batch Analysis

### POST /api/analysis/batch

Démarrer a batch AI analysis job on unanalyzed files. Runs in the background.

#### Rate Limit

HEAVY

#### Requête

```json
{
  "limit": 10,
  "scan_root": "",
  "file_ids": [],
  "server_ids": ["ollama-main", "openai-compat"]
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `limit` | int | No | Maximum number of files to analyze. Défaut 10. Capped at 10 for cloud engines. 0 means all files for local engines |
| `scan_root` | string | No | Restrict targets to a specific scan root |
| `file_ids` | int[] | No | Directly specify file IDs to analyze |
| `serveur_ids` | string[] | No | Server IDs to use. Multiple serveurs enable parallel analysis |

#### Réponse (200)

```json
{
  "started": true,
  "count": 10,
  "parallel": false
}
```

| Champ | Type | Description |
|-------|------|-------------|
| `started` | boolean | Si the job was started |
| `count` | int | Number of files to analyze |
| `parallel` | boolean | Si running in parallel (multiple `serveur_ids`) |
| `worker` | boolean | True if dispatched via inference worker |
| `subprocess` | boolean | True if running in subprocess (Hailo VLM) |

#### Error Réponses

- `400`: No files to analyze
- `409`: AI analysis job already running

### POST /api/analysis/batch/cancel

Cancel a running batch AI analysis job.

#### Rate Limit

HEAVY

#### Requête

No body required.

#### Réponse (200)

```json
{
  "status": "cancelling",
  "message": "AI analysis cancel requested"
}
```

#### Error Réponses

- `404`: No running AI analysis job

---

## Prompt Trend Analysis

### POST /api/analysis/trends

Run trend analysis on the 50 most recent prompts. Results are automatically saved to history.

#### Rate Limit

HEAVY

#### Requête

No body required.

#### Réponse (200)

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

#### Error Réponses

- `400`: clé API not configured (when using cloud engines)
- `500`: Error during trend analysis

### GET /api/analysis/trends/history

Get prompt trend analysis history. Sorted newest first. Maximum 50 entries retained.

#### Paramètres

| Paramètre | Type | Défaut | Description |
|-----------|------|---------|-------------|
| `limit` | int | 20 | Number of entries to fetch (max 50) |
| `offset` | int | 0 | Offset |

#### Réponse

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

| Champ | Type | Description |
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

#### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `history_id` | int | History entry ID (path parameter) |

#### Réponse

```json
{
  "deleted": true
}
```

#### Error Réponses

- `404`: History entry not found

---

## Statistics

### GET /api/analysis/stats

Get AI analysis statistics.

#### Réponse

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

| Champ | Type | Description |
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

### GET /api/analysis/ollama/modèles

Connect to the configured Ollama serveur and list available modèles.

#### Réponse

```json
{
  "available": true,
  "models": [
    { "name": "llava:latest", "size": 4700000000 }
  ]
}
```

#### Error Réponses

- `400`: Invalid Ollama URL

### POST /api/analysis/ollama/test

Test connection to an Ollama serveur at the specified URL.

#### Rate Limit

HEAVY

#### Requête

```json
{
  "ollama_url": "http://localhost:11434"
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `ollama_url` | string | Yes | Ollama serveur URL to test |

#### Réponse

```json
{
  "available": true,
  "models": [
    { "name": "llava:latest", "size": 4700000000 }
  ]
}
```

#### Error Réponses

- `400`: URL is empty / URL is invalid

---

## OpenAI-Compatible Server Connection

### GET /api/analysis/openai-compat/modèles

Connect to the configured OpenAI-compatible serveur and list available modèles.

#### Réponse

```json
{
  "available": true,
  "models": [
    { "id": "qwen2-vl-7b-instruct" }
  ]
}
```

#### Error Réponses

- `400`: URL not configured / URL is invalid

### POST /api/analysis/openai-compat/test

Test connection to an OpenAI-compatible serveur at the specified URL.

#### Rate Limit

HEAVY

#### Requête

```json
{
  "url": "http://localhost:8080/v1",
  "api_key": "optional-key"
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `url` | string | Yes | URL to test |
| `api_key` | string | No | clé API (if required) |

#### Réponse

```json
{
  "available": true,
  "models": [
    { "id": "qwen2-vl-7b-instruct" }
  ]
}
```

#### Error Réponses

- `400`: URL is empty / URL is invalid

---

## AI Server Registry

Register and manage multiple AI serveurs with priority-based fallback and parallel analysis.

### GET /api/analysis/serveurs

Lister tous les registered serveurs with status. clé APIs are masked.

#### Réponse

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

| Champ | Type | Description |
|-------|------|-------------|
| `serveurs[].id` | string | Server ID (immutable) |
| `serveurs[].name` | string | Display name |
| `serveurs[].type` | string | Engine type (`claude_api`, `openai`, `ollama`, `openai_compat`, `hailo_vlm`) |
| `serveurs[].priority` | int | Priority (lower = higher priority) |
| `serveurs[].enabled` | boolean | Activerd/disabled |
| `serveurs[].config` | object | Engine-specific configuration |
| `serveurs[].is_active` | boolean | Si this is the currently active serveur |
| `serveurs[].status` | string | Connection status (always `"unknown"` in list view) |

### POST /api/analysis/serveurs

Register a new serveur. The first serveur is automatically set as active.

#### Rate Limit

HEAVY

#### Requête

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

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `name` | string | Yes | Server name |
| `type` | string | Yes | Engine type |
| `config` | object | Yes | Engine-specific configuration |
| `priority` | int | No | Priority |
| `enabled` | boolean | No | Activerd/disabled. Défaut true |

#### Réponse (201)

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

#### Error Réponses

- `400`: Validation error / serveur limit reached

### PUT /api/analysis/serveurs/\<serveur_id\>

Update a serveur's paramètres. The `id` field cannot be changed.

#### Rate Limit

HEAVY

#### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `serveur_id` | string | Server ID (path parameter) |

#### Requête

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

#### Réponse

```json
{
  "success": true,
  "server": { "id": "ollama-main", "name": "Updated Name", "..." : "..." }
}
```

#### Error Réponses

- `400`: Invalid type / serveur not found

### DELETE /api/analysis/serveurs/\<serveur_id\>

Delete a serveur. If the active serveur is deleted, the next highest-priority serveur becomes active automatically.

#### Rate Limit

HEAVY

#### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `serveur_id` | string | Server ID (path parameter) |

#### Réponse

```json
{
  "success": true
}
```

#### Error Réponses

- `400`: Server not found

### POST /api/analysis/serveurs/\<serveur_id\>/activate

Switch the active serveur.

#### Rate Limit

HEAVY

#### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `serveur_id` | string | Server ID (path parameter) |

#### Réponse

```json
{
  "success": true,
  "active": "ollama-main"
}
```

#### Error Réponses

- `400`: Server not found

### POST /api/analysis/serveurs/\<serveur_id\>/test

Run a connectivity test on a serveur. Réponse time is also measured.

#### Rate Limit

HEAVY

#### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `serveur_id` | string | Server ID (path parameter) |

#### Réponse

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

| Champ | Type | Description |
|-------|------|-------------|
| `available` | boolean | Si the serveur is reachable |
| `elapsed_ms` | int | Connection test response time in milliseconds |
| `serveur` | object | Server information |

#### Error Réponses

- `400`: Server not found

### PUT /api/analysis/serveurs/reorder

Bulk-update serveur priorities.

#### Rate Limit

HEAVY

#### Requête

```json
{
  "server_ids": ["ollama-main", "openai-compat", "claude-api"]
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `serveur_ids` | string[] | Yes | Tableau of serveur IDs. The specified order becomes the new priority order |

#### Réponse

```json
{
  "success": true
}
```

#### Error Réponses

- `400`: `serveur_ids` is not an array

### POST /api/analysis/serveurs/migrate

Auto-migrate from legacy `ai_analysis` config to the new serveur registry format. Fails if serveurs already exist.

#### Rate Limit

HEAVY

#### Requête

No body required.

#### Réponse

```json
{
  "success": true,
  "servers": [
    { "id": "ollama", "name": "Ollama (llava:latest)", "type": "ollama", "..." : "..." }
  ],
  "migrated": 3
}
```

| Champ | Type | Description |
|-------|------|-------------|
| `serveurs` | array | Servers created by migration |
| `migrated` | int | Number of serveurs created |

#### Error Réponses

- `400`: `ai_serveurs` already exists
