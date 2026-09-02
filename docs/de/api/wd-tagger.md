# WD Tagger API

APIs for WD Tagger (Waifu Diffusion Tagger) Danbooru auto-tagging. Provides config management, single/batch tagging, tag CRUD, model management, XMP reading, and VLM connection testing.

## GET /api/wd-tagger/config

Get the current WD Tagger configuration.

### Parameters

None

### Response

```json
{
  "config": {
    "model": "SmilingWolf/wd-swinv2-tagger-v3",
    "threshold": 0.35,
    "...": "..."
  }
}
```

## POST /api/wd-tagger/config

Save/update WD Tagger configuration.

### Rate Limit

WRITE

### Request

```json
{
  "model": "SmilingWolf/wd-swinv2-tagger-v3",
  "threshold": 0.35
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| *(any key)* | any | No | Configuration field. Unknown keys or invalid values return `400` |

### Response

```json
{
  "config": {
    "model": "SmilingWolf/wd-swinv2-tagger-v3",
    "threshold": 0.35,
    "...": "..."
  }
}
```

### Errors

| Code | Status | Description |
|------|--------|-------------|
| `invalid_json` | 400 | Request body is not a JSON object |
| `invalid_value` | 400 | Invalid configuration value |

## POST /api/wd-tagger/tag/<file_id>

Run WD Tagger inference on a single file to predict and assign Danbooru tags.

### Rate Limit

HEAVY

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `file_id` | int | File ID (path parameter) |

### Request

```json
{
  "force": false
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `force` | boolean | No | If `true`, overwrite existing tags and re-run inference. Default `false` |

### Response

```json
{
  "file_id": 42,
  "model": "SmilingWolf/wd-swinv2-tagger-v3",
  "tags": [
    {"tag": "1girl", "score": 0.98, "category": "general"},
    {"tag": "solo", "score": 0.95, "category": "general"}
  ]
}
```

### Errors

| Code | Status | Description |
|------|--------|-------------|
| `tag_error` | 400 | Tagging failed (file not found, image load error, etc.) |

## GET /api/wd-tagger/tags/<file_id>

Get stored WD Tagger tags for a specific file.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | File ID (path parameter) |
| `model` | string | No | Filter by model name (query parameter) |
| `all` | boolean | No | When `1`, `true`, or `yes`, return tags from all models and ignore the active model and `model` filter |

### Response

```json
{
  "file_id": 42,
  "tags": [
    {"tag": "1girl", "score": 0.98, "category": "general", "model": "SmilingWolf/wd-swinv2-tagger-v3"},
    {"tag": "solo", "score": 0.95, "category": "general", "model": "SmilingWolf/wd-swinv2-tagger-v3"}
  ]
}
```

## DELETE /api/wd-tagger/tags/<file_id>

Delete WD Tagger tags for a specific file.

### Rate Limit

WRITE

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | File ID (path parameter) |
| `model` | string | No | Filter by model name (query parameter). If omitted, deletes tags from all models |

### Response

```json
{
  "file_id": 42,
  "deleted": 15
}
```

## DELETE /api/wd-tagger/tags/batch

Delete WD Tagger tags for multiple files at once.

### Rate Limit

WRITE

### Request

```json
{
  "file_ids": [1, 2, 3],
  "model": "wd-swinv2-tagger-v3"
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_ids` | list | Yes | Array of file IDs (max 500) |
| `model` | string | No | Filter by model name. If omitted, deletes tags from all models |

### Response

```json
{
  "deleted_files": 3,
  "deleted_tags": 45
}
```

## Active model (v4.192.0+)

Wenn dieselbe Datei mit mehreren WD-Tagger-Modellen neu getaggt wird, behält
`file_wd_tags` die Tags jedes Modells als Verlauf. Mit einem Active model nutzen
Detailanzeige, `ai_analyzed`-Suche und die interne WD-Tagger-Prüfung "bereits
getaggt" nur Tags dieses Modells. Ist kein Active model gesetzt, bleibt das
bisherige Verhalten erhalten und Tags aller Modelle werden gemeinsam verwendet.

### Einstellung in der UI

Der retag modal zeigt oben das aktuelle `Active model`. Über das `Change`
dropdown kann ein verfügbares Modell ausgewählt werden. `(none / reset)` setzt
die Einstellung zurück.

Nach einem Retag wird das verwendete Modell standardmäßig aktiv. Deaktiviere die
Checkbox "Nach dem Retag als aktives Modell setzen", wenn das aktuelle Active
model unverändert bleiben soll.

Rows alter Modelle werden nicht automatisch gelöscht. Sie bleiben als Verlauf in
der Datenbank. Zum expliziten Entfernen aktiviere "Auch Tags anderer Modelle
löschen" im retag modal und bestätige den Dialog nach dem Retag.


### GET /api/wd-tagger/profiles

Returns registered WD Tagger profiles and the current active model. Requires admin scope.

```json
{
  "profiles": [
    {
      "id": "camie_tagger_v2",
      "display_name": "Camie Tagger v2",
      "model_id": "Camais03/camie-tagger-v2",
      "adapter_family": "camie",
      "backend": "onnx",
      "builtin": true,
      "has_tags": false
    }
  ],
  "active_model_id": "Camais03/camie-tagger-v2"
}
```

### GET /api/wd-tagger/active-model

Gibt das aktuelle Active model und die in der Datenbank vorhandenen Modelle
zurück. Admin scope ist erforderlich.

```json
{
  "active_model_id": "SmilingWolf/wd-eva02-large-tagger-v3",
  "available_models": [
    {"model_id": "SmilingWolf/wd-eva02-large-tagger-v3", "file_count": 120},
    {"model_id": "SmilingWolf/wd-swinv2-tagger-v3", "file_count": 340}
  ]
}
```

### PUT /api/wd-tagger/active-model

Ändert das Active model. Admin scope ist erforderlich. Sende `null` oder einen
leeren String als `model_id`, um die Einstellung zurückzusetzen.

```json
{
  "model_id": "SmilingWolf/wd-eva02-large-tagger-v3"
}
```

| Code | Status | Beschreibung |
|------|--------|--------------|
| `invalid_model_id` | 400 | model_id ist zu lang oder enthält Steuerzeichen |
| `unknown_model` | 400 | In der Datenbank existieren keine Tags für dieses Modell |

## POST /api/wd-tagger/batch

Run batch tagging on multiple files. If `file_ids` is specified, only those files are processed. If omitted, automatically selects untagged files up to `limit`.

### Rate Limit

HEAVY

### Request

```json
{
  "file_ids": [1, 2, 3],
  "limit": 100,
  "force": false,
  "scan_root": ""
}
```

| Parameter | Type | Required | Limit | Description |
|-----------|------|----------|-------|-------------|
| `file_ids` | int[] | No | Max 500 | Array of target file IDs. If omitted, untagged files are selected automatically |
| `limit` | int | No | - | Max files to process when `file_ids` is omitted. Default `100` |
| `force` | boolean | No | - | If `true`, overwrite existing tags. Default `false` |
| `scan_root` | string | No | - | Filter by scan root path. Empty string for all files |

### Response

```json
{
  "job_id": "wd_tagger",
  "total": 100,
  "status": "started"
}
```

### Errors

| Code | Status | Description |
|------|--------|-------------|
| `batch_too_large` | 400 | `file_ids` exceeds 500 items |
| `batch_error` | 409 | A batch job is already running |

## POST /api/wd-tagger/batch/cancel

Cancel a running batch tagging job.

### Rate Limit

WRITE

### Request

No body required.

### Response

```json
{
  "status": "cancelling",
  "message": "Batch tagging cancel requested"
}
```

### Errors

| Code | Status | Description |
|------|--------|-------------|
| `job_not_running` | 404 | No running batch tagging job exists |

## GET /api/wd-tagger/stats

Get WD Tagger tagging statistics.

### Parameters

None

### Response

```json
{
  "total_tagged": 1234,
  "total_tags": 56789,
  "models": {
    "SmilingWolf/wd-swinv2-tagger-v3": 1200
  },
  "untagged_unknown": 42
}
```

| Field | Type | Description |
|-------|------|-------------|
| `total_tagged` | int | Number of tagged files |
| `total_tags` | int | Total number of stored tags |
| `models` | object | Number of tagged files per model |
| `untagged_unknown` | int | Number of files with no metadata (`unknown`) and no WD tags |

## GET /api/wd-tagger/untagged

List files with no metadata (`unknown`) that have not been tagged yet. Supports pagination.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `limit` | int | No | Number of results. 1-500, default `100` |
| `offset` | int | No | Number of results to skip. Default `0` |

### Response

```json
{
  "files": [
    {"id": 10, "filepath": "/images/photo.png", "filename": "photo.png"}
  ],
  "total": 42
}
```

## GET /api/wd-tagger/xmp/<file_id>

Read XMP metadata from a specific file.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `file_id` | int | File ID (path parameter) |

### Response

```json
{
  "file_id": 42,
  "xmp": {
    "subject": ["1girl", "solo", "blue_eyes"],
    "description": "...",
    "creator": "..."
  }
}
```

### Errors

| Code | Status | Description |
|------|--------|-------------|
| `file_not_found` | 404 | File does not exist or is soft-deleted |

## GET /api/wd-tagger/vlm/test

Test connectivity to a VLM (Vision Language Model) server. Checks reachability of an OpenAI-compatible API endpoint.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `url` | string | Yes | VLM server URL (query parameter) |

### Response

```json
{
  "ok": true,
  "message": "Connection successful",
  "server_info": "..."
}
```

### Errors

| Code | Status | Description |
|------|--------|-------------|
| `missing_url` | 400 | `url` parameter not provided |
| `invalid_url` | 400 | URL format is invalid |

## GET /api/wd-tagger/vlm/models

List available models on a VLM server. Queries the OpenAI-compatible `/v1/models` endpoint.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `url` | string | Yes | VLM server URL (query parameter) |

### Response

```json
{
  "models": [
    {"id": "llava-v1.6", "object": "model"}
  ]
}
```

### Errors

| Code | Status | Description |
|------|--------|-------------|
| `missing_url` | 400 | `url` parameter not provided |
| `invalid_url` | 400 | URL format is invalid |
| `vlm_connection_error` | 502 | Failed to connect to VLM server |

## POST /api/wd-tagger/model/download

Download a WD Tagger model. Fetches model files from Hugging Face and saves them locally.

### Rate Limit

HEAVY

### Request

```json
{
  "repo": "SmilingWolf/wd-swinv2-tagger-v3"
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `repo` | string | No | Hugging Face repository name. If omitted, uses the `model` value from config |

### Response

```json
{
  "repo": "SmilingWolf/wd-swinv2-tagger-v3",
  "path": "/path/to/model/directory",
  "ready": true
}
```

### Errors

| Code | Status | Description |
|------|--------|-------------|
| `unknown_model` | 400 | Unknown model repository. `hint` contains list of known models |
| `download_failed` | 500 | Download failed |

## GET /api/wd-tagger/model/status

Check the download status of a WD Tagger model.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `repo` | string | No | Hugging Face repository name (query parameter). If omitted, uses the `model` value from config |

### Response

```json
{
  "repo": "SmilingWolf/wd-swinv2-tagger-v3",
  "downloaded": true,
  "path": "/path/to/model/directory",
  "known_models": {
    "SmilingWolf/wd-swinv2-tagger-v3": "SwinV2 (recommended)",
    "SmilingWolf/wd-convnext-tagger-v3": "ConvNeXt",
    "SmilingWolf/wd-vit-tagger-v3": "ViT"
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `repo` | string | Repository name being checked |
| `downloaded` | boolean | Whether the model is downloaded locally |
| `path` | string/null | Local model path if downloaded |
| `known_models` | object | All supported models (repository name -> display name) |

## User profile CRUD (v4.197.0+)

API zum CRUD von benutzererstellten Tagger-Profilen über die Tools-Seiten-UI. Für alle Endpunkte ist Admin-Scope erforderlich. Gemeinsame Error-Shape: `{ok: false, error, code, ...extra}`. Der Request-Body hat ein **hartes 1MB-Limit** (`code: profile_too_large`, 413). `id` muss der Regex `^[a-z0-9][a-z0-9_-]{0,63}$` entsprechen.

### POST /api/wd-tagger/profiles

Neues Benutzerprofil erstellen.

**Request**: Profile-JSON (Schema v2, `profile_version: "2"`). Das Feld `builtin` wird serverseitig zwangsweise auf `false` überschrieben.

**Response (200)**:
```json
{
  "ok": true,
  "profile": { "...": "...サニタイズ済 profile JSON..." },
  "origin": "user",
  "overrides_builtin": false
}
```

| Feld | Beschreibung |
|---|---|
| `profile` | Gespeichertes Profil (`builtin: false` ist garantiert) |
| `origin` | Immer `"user"` |
| `overrides_builtin` | `true`, wenn ein builtin profile mit derselben id existiert (advanced Pfad) |

**Fehler**:

| status | code | Bedingung |
|---|---|---|
| 400 | `validation_failed` | JSON verstößt gegen Schema v2 (`extra.errors=[{path, message}, ...]`) |
| 400 | `invalid_id` | `id` im Body passt nicht zur Regex |
| 409 | `id_conflict` | Gleiche id wie ein bereits existierendes Benutzerprofil |
| 413 | `profile_too_large` | body > 1MB |

### GET /api/wd-tagger/profiles/{id}

Vollständiges schema v2 profile für die angegebene id abrufen (wird von der UI beim Bearbeiten / Duplizieren / Export aufgerufen).

**path**: `id` (Regex-Check erforderlich)

**Response (200)**:
{Gleiche Form wie POST: profile / origin / overrides_builtin}

**Fehler**:
- 400 `invalid_id` (path id passt nicht zur Regex)
- 404 `not_found`

### PUT /api/wd-tagger/profiles/{id}

Vorhandenes Benutzerprofil aktualisieren.

**path**: `id` (Regex-Check erforderlich)

**Request**: Profile-JSON. `body.id` muss mit der path id übereinstimmen (Rename in der UI über `Duplicate → Delete` führen).

**Response (200)**: Gleiche Form wie POST.

**Fehler**:

| status | code | Bedingung |
|---|---|---|
| 400 | `id_immutable` | path id und body id stimmen nicht überein |
| 400 | `invalid_id` | path id passt nicht zur Regex |
| 400 | `validation_failed` | Schema-Verstoß |
| 403 | `builtin_read_only` | path id ist ein builtin profile (keine entsprechende Benutzerdatei) |
| 404 | `not_found` | id nicht registriert |
| 413 | `profile_too_large` | body > 1MB |

### DELETE /api/wd-tagger/profiles/{id}

Benutzerprofil löschen.

**path**: `id`

**Response (200)**:
```json
{"ok": true, "deleted": true}
```

**Fehler**:

| status | code | Bedingung |
|---|---|---|
| 400 | `invalid_id` | ungültige path id |
| 403 | `builtin_read_only` | nur builtin, ohne Benutzer-Override |
| 404 | `not_found` | id nicht registriert |
| 409 | `in_use` | Dieses Profil ist das aktive Modell (enthält `extra.active_model_id`). In der UI zuerst das aktive Profil über `PUT /api/wd-tagger/active-model` wechseln und dann erneut versuchen |

### POST /api/wd-tagger/profiles/{id}/test

Dry-run download. Führt für jedes `files[]` einen HEAD auf HuggingFace aus und lädt bei `required: true` atomar pro Datei herunter (Cache verwendet den bestehenden Pfad wieder).

**path**: `id`

**body**: nicht erforderlich

**Verhalten**:
- per-file timeout: 30s
- Gesamt timeout: 60s
- redirect: allowlist nur für `huggingface.co` / `hf.co` Subdomains, max. 5 hops; userinfo (`user:pass@`) ist SSRFBlocked

**Response (200, Erfolg)**:
```json
{
  "ok": true,
  "files": [
    {"name": "model.onnx", "status": "downloaded", "size": 1234567},
    {"name": "tags.csv",   "status": "cached",     "size": 89012},
    {"name": "optional.json", "status": "skipped_optional", "size": null}
  ]
}
```

`status` Werte:
- `downloaded`: in diesem Lauf heruntergeladen
- `cached`: existiert bereits lokal (nur HEAD)
- `skipped_optional`: `required: false` und 404 / HEAD fehlgeschlagen

**Fehler (status / code)**:

| status | code | Bedingung |
|---|---|---|
| 400 | `invalid_id` / `required_missing` | ungültige path id / required Datei ist 404 auf HF |
| 404 | `not_found` | Profil nicht registriert |
| 408 | `timeout` | Gesamtlimit 60s überschritten |
| 502 | `ssrf_blocked` | redirect außerhalb der HF-allowlist / enthält userinfo / scheme ist nicht http(s) |
| 502 | `hf_unavailable` | HF hat 5xx zurückgegeben |

Im Fehlerfall hat der Body die Form `{"ok": false, "code": ..., "error": ..., "files": [...Teilergebnisse...], "detail": "..."}`.

### Profile-JSON-Format (Schema v2)

```typescript
interface ProfileV2 {
  profile_version: "2";
  id: string;
  display_name: string;
  adapter_family: "wd" | "camie" | "oppai" | "generic_onnx";
  backend: "onnx";
  model_id: string;                        // HF-Repo-Pfad "<owner>/<name>"
  hf_subdir: string | null;
  files: { name: string; required: boolean; size_hint_mb?: number }[];
  default_thresholds: Record<string, number>;
  tag_source: TagSourceSpec;               // type=csv/json_list/json_dict/composite
  threshold_source: ThresholdSourceSpec;   // type=global_per_category/per_tag_json
  preprocess_spec: PreprocessSpec;
  supports_categories: string[];
  categories_mode: "from_tag_source" | "all_general";
  builtin?: boolean;                       // bei Benutzerherkunft immer false (Server erzwingt)
}
```

Details siehe `extensions/builtin_wd_tagger/core_impl/adapters/base.py` (`TaggerProfile`) oder die builtin-Referenzimplementierung (`extensions/builtin_wd_tagger/core_impl/profiles/*.json`).
