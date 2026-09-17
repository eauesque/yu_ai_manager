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

When the same file is retagged with multiple WD Tagger models, `file_wd_tags`
keeps tags for each model as history. Setting an active model makes detail
display, `ai_analyzed` search, and WD Tagger's internal "already tagged" checks
use only tags from that model. If no active model is set, the previous behavior
is preserved and tags from all models are treated together.

### Configure in the UI

The retag modal shows the current `Active model` at the top. Use the `Change`
dropdown to select one of the available models. Choose `(none / reset)` to clear
the active model.

After a retag completes, the retagged model becomes active by default. Turn off
the "Set as active model after retag" checkbox in the retag modal to keep the
current active model unchanged.

Rows from old models are not deleted automatically. They remain in the database
for history. To remove them explicitly, enable "Also delete tags from other
models" in the retag modal and approve the confirmation dialog after retagging.


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

Returns the current active model and the list of models present in the database.
Admin scope is required.

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

Changes the active model. Admin scope is required. Send `null` or an empty
string as `model_id` to reset to no active model.

```json
{
  "model_id": "SmilingWolf/wd-eva02-large-tagger-v3"
}
```

| Code | Status | Description |
|------|--------|-------------|
| `invalid_model_id` | 400 | model_id is too long or contains control characters |
| `unknown_model` | 400 | No tags for the specified model exist in the database |

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

API to CRUD user-created tagger profiles from the Tools page UI. Admin scope is required for all endpoints. Common error shape is `{ok: false, error, code, ...extra}`. Request body has a **1MB hard cap** (`code: profile_too_large`, 413). `id` must match the `^[a-z0-9][a-z0-9_-]{0,63}$` regex.

### POST /api/wd-tagger/profiles

Create a new user profile.

**Request**: profile JSON (schema v2, `profile_version: "2"`). The `builtin` field is forcibly overwritten to `false` server-side.

**Response (200)**:
```json
{
  "ok": true,
  "profile": { "...": "...サニタイズ済 profile JSON..." },
  "origin": "user",
  "overrides_builtin": false
}
```

| Field | Description |
|---|---|
| `profile` | Saved profile (guaranteed `builtin: false`) |
| `origin` | Always `"user"` |
| `overrides_builtin` | `true` if a builtin profile with the same id exists (advanced path) |

**Errors**:

| status | code | condition |
|---|---|---|
| 400 | `validation_failed` | JSON violates schema v2 (`extra.errors=[{path, message}, ...]`) |
| 400 | `invalid_id` | `id` in body does not match the regex |
| 409 | `id_conflict` | Same id as an existing user profile |
| 413 | `profile_too_large` | body > 1MB |

### GET /api/wd-tagger/profiles/{id}

Retrieve the full schema v2 profile for the specified id (called by the UI for edit / duplicate / Export).

**path**: `id` (regex check required)

**Response (200)**:
{Same shape as POST: profile / origin / overrides_builtin}

**Errors**:
- 400 `invalid_id` (path id does not match the regex)
- 404 `not_found`

### PUT /api/wd-tagger/profiles/{id}

Update an existing user profile.

**path**: `id` (regex check required)

**Request**: profile JSON. `body.id` must match the path id (for rename, guide UI to `Duplicate → Delete`).

**Response (200)**: Same shape as POST.

**Errors**:

| status | code | condition |
|---|---|---|
| 400 | `id_immutable` | path id and body id do not match |
| 400 | `invalid_id` | path id does not match the regex |
| 400 | `validation_failed` | schema violation |
| 403 | `builtin_read_only` | path id is a builtin profile (no corresponding user file) |
| 404 | `not_found` | id not registered |
| 413 | `profile_too_large` | body > 1MB |

### DELETE /api/wd-tagger/profiles/{id}

Delete a user profile.

**path**: `id`

**Response (200)**:
```json
{"ok": true, "deleted": true}
```

**Errors**:

| status | code | condition |
|---|---|---|
| 400 | `invalid_id` | invalid path id |
| 403 | `builtin_read_only` | builtin only, with no user override |
| 404 | `not_found` | id not registered |
| 409 | `in_use` | This profile is the active model (includes `extra.active_model_id`). In the UI, switch the active profile via `PUT /api/wd-tagger/active-model` and then retry |

### POST /api/wd-tagger/profiles/{id}/test

Dry-run download. HEAD each `files[]` on HuggingFace, and for items with `required: true`, performs an atomic per-file download (cache reuses the existing path).

**path**: `id`

**body**: not required

**Behavior**:
- per-file timeout: 30s
- overall timeout: 60s
- redirect: allowlist only for `huggingface.co` / `hf.co` subdomains, max 5 hops; userinfo (`user:pass@`) is SSRFBlocked

**Response (200, success)**:
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

`status` values:
- `downloaded`: downloaded in this run
- `cached`: already exists locally (HEAD only)
- `skipped_optional`: `required: false` and 404 / HEAD failed

**Errors (status / code)**:

| status | code | condition |
|---|---|---|
| 400 | `invalid_id` / `required_missing` | invalid path id / required file is 404 on HF |
| 404 | `not_found` | profile not registered |
| 408 | `timeout` | exceeded overall 60s |
| 502 | `ssrf_blocked` | redirect is outside HF allowlist / contains userinfo / scheme is not http(s) |
| 502 | `hf_unavailable` | HF returned 5xx |

On error, the body is in the form `{"ok": false, "code": ..., "error": ..., "files": [...partial results...], "detail": "..."}`.

### Profile JSON format (schema v2)

```typescript
interface ProfileV2 {
  profile_version: "2";
  id: string;
  display_name: string;
  adapter_family: "wd" | "camie" | "oppai" | "generic_onnx";
  backend: "onnx";
  model_id: string;                        // HF repo path "<owner>/<name>"
  hf_subdir: string | null;
  files: { name: string; required: boolean; size_hint_mb?: number }[];
  default_thresholds: Record<string, number>;
  tag_source: TagSourceSpec;               // type=csv/json_list/json_dict/composite
  threshold_source: ThresholdSourceSpec;   // type=global_per_category/per_tag_json
  preprocess_spec: PreprocessSpec;
  supports_categories: string[];
  categories_mode: "from_tag_source" | "all_general";
  builtin?: boolean;                       // always false for user origin (server enforces)
}
```

For details, see `extensions/builtin_wd_tagger/core_impl/adapters/base.py` (`TaggerProfile`), or refer to the builtin reference implementation (`extensions/builtin_wd_tagger/core_impl/profiles/*.json`).

---

## Retag Job API

Job API for retagging files with a different model. All 5 endpoints use `POST` and require admin scope.

### POST /api/wd-tagger/retag/single

Retag a single file synchronously and return the result immediately.

**Request**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file_id` | int | Yes | Target file ID |
| `model_id` | string | Yes | Model ID to use (profile `id`) |
| `thresholds` | object | No | e.g. `{"general": 0.35, "character": 0.85}` (default values used if omitted) |
| `overwrite_same_model` | bool | No | Overwrite existing tags from the same model (default `true`) |
| `set_active` | bool | No | Set this model as active after completion (default `true`) |

**Response**: `{"data": {tag result}}`

**Errors**: `404 file_not_found` / `400 invalid_input`

### POST /api/wd-tagger/retag/batch

Retag multiple files asynchronously in batch.

**Request**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `model_id` | string | Yes | Model ID to use |
| `file_ids` | int[] | Yes | Target file IDs (max 500) |
| `thresholds` | object | No | Threshold values |
| `batch_size` | int | No | Parallel processing size (1-64, default 8) |
| `limit` | int | No | Max files to process (0 = unlimited) |
| `set_active` | bool | No | Set as active model after completion (default `true`) |

### POST /api/wd-tagger/retag/backfill

Asynchronously retag untagged files filtered by scan root.

**Request**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `model_id` | string | Yes | Model ID to use |
| `scan_root` | string | No | Filter by scan root path (empty = all files) |
| `force` | bool | No | Re-run even if existing tags are present (default `false`) |
| `thresholds` | object | No | Threshold values |
| `batch_size` | int | No | Parallel processing size |
| `limit` | int | No | Max files to process |

### POST /api/wd-tagger/retag/query

Asynchronously retag files matching a search query.

**Request**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `model_id` | string | Yes | Model ID to use |
| `query_params` | object | Yes | Search parameters, same format as `/api/search` |
| `thresholds` | object | No | Threshold values |
| `batch_size` | int | No | Parallel processing size |
| `limit` | int | No | Max files to process |

### POST /api/wd-tagger/retag/cancel

Cancel a running retag job.

**Response**: `{"data": {"status": "cancelling"}}`

**Errors**: `404 job_not_running` (no running job exists)
