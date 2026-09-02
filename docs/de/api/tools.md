# Tools API

Utility APIs für Duplikatserkennung, Hashberechnung, ähnliche Bildsuche, Cacheverwaltung, Ordnerauswahl, DB-Sicherung, Archive Cleanup und Debug-Logging.

---

## Duplicates / Hashes / Scan

### GET /api/tools/find-duplicates

Detect duplicate files based on file hash or filename.

#### Rate Limit

HEAVY

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `cross_directory` | string | `"false"` | Set to `"true"` to detect duplicates across different directories |
| `method` | string | `"hash"` | Detection method: `"hash"` or `"name"` |
| `threshold` | int | `5` | Similarity threshold |

#### Response

```json
{
  "groups": [
    {
      "hash": "abc123...",
      "files": [
        { "id": 1, "path": "/images/photo.png", "filename": "photo.png" },
        { "id": 2, "path": "/backup/photo.png", "filename": "photo.png" }
      ]
    }
  ],
  "total_groups": 1,
  "total_duplicates": 2
}
```

### POST /api/tools/compute-hashes

Start background hash computation for files without hashes.

#### Rate Limit

HEAVY

#### Request

```json
{
  "type": "both",
  "limit": 5000
}
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `type` | string | `"both"` | Hash type: `"md5"`, `"sha256"`, or `"both"` |
| `limit` | int | `5000` | Maximum number of files to process |

#### Response

```json
{
  "started": true,
  "type": "both",
  "limit": 5000
}
```

### POST /api/tools/delete-duplicates

Delete specified files from duplicate groups.

#### Rate Limit

DESTRUCTIVE

#### Request

```json
{
  "groups": [
    {
      "keep": 1,
      "delete": [2, 3]
    }
  ],
  "mode": "soft"
}
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `groups` | array | Required | Deletion targets. `keep` = file ID to keep, `delete` = array of file IDs to remove |
| `mode` | string | `"soft"` | `"soft"` = logical deletion, `"hard"` = physical deletion |

#### Response

```json
{
  "deleted": 2,
  "errors": []
}
```

### GET /api/tools/normalize-tags

Normalize tags (merge duplicates, trim whitespace, etc.).

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `dry_run` | string | `"false"` | Set to `"true"` to preview changes without applying |

#### Response

```json
{
  "normalized": 15,
  "removed": 3,
  "dry_run": false
}
```

### GET /api/tools/find-similar

Find images similar to a specified file (hash-based).

#### Rate Limit

HEAVY

#### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | Reference file ID |
| `threshold` | int | No | Similarity threshold (1-20, default `5`) |

#### Response

```json
{
  "file_id": 42,
  "threshold": 5,
  "results": [
    {
      "id": 43,
      "filename": "similar.png",
      "distance": 3
    }
  ],
  "count": 1
}
```

#### Errors

- `400` — `file_id` missing or invalid
- `404` — Specified file not found

### POST /api/tools/scan

Scan files in a directory and register them in the database.

#### Rate Limit

HEAVY

#### Request

```json
{
  "path": "/path/to/images",
  "recursive": true,
  "scan_zips": false,
  "compute_hash": false
}
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | string | Required | Directory path to scan |
| `recursive` | bool | `true` | Recursively scan subdirectories |
| `scan_zips` | bool | `false` | Also scan inside ZIP archives |
| `compute_hash` | bool | `false` | Compute file hashes during scan |

#### Response

```json
{
  "scanned": 150,
  "new": 42,
  "updated": 5,
  "errors": []
}
```

---

## File Search / Metadata Inspection

### GET /api/tools/file-search

Search files in the database by keyword.

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `q` / `query` | string | `""` | Search keyword |
| `meta` / `meta_filter` | string | `"all"` | Filter by metadata source (`"all"`, `"a1111_png"`, `"novelai_v4_png"`, etc.) |
| `limit` / `n` / `page_size` | int | `100` | Number of results (1-500) |

#### Response

```json
{
  "results": [
    {
      "id": 1,
      "filename": "image.png",
      "path": "/images/image.png"
    }
  ],
  "count": 1
}
```

### POST /api/inspect

Inspect metadata of an uploaded file. Extracts metadata without registering the file in the database.

#### Rate Limit

WRITE

#### Request

`multipart/form-data`:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | file | Yes | File to inspect |
| `zip_entry` | string | No | Path within ZIP archive (for ZIP files) |

#### Response

```json
{
  "filename": "image.png",
  "meta_source": "novelai_v4_png",
  "positive": "1girl, landscape",
  "negative": "bad anatomy",
  "parameters": { ... }
}
```

#### Errors

- `400` — No file uploaded

---

## Folder Selection / Directory Listing

### GET /api/tools/select-folder

Open the OS native folder picker dialog. **Only available from localhost.**

#### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `initial` / `path` / `dir` | string | Initial directory for the dialog |

#### Response

```json
{
  "path": "C:\\Users\\user\\Pictures",
  "cancelled": false
}
```

When accessed remotely:

```json
{
  "path": null,
  "error": "remote_client_no_gui",
  "cancelled": false,
  "message": "Native folder dialog is not available for remote access. Please use the server folder browser."
}
```

### GET /api/tools/list-dirs

List directories on the server. **Only available from localhost.**

#### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `path` / `dir` / `initial` | string | Directory to list. Empty returns root directories |

#### Response

```json
{
  "current": "C:\\Users",
  "parent": "C:\\",
  "dirs": ["user1", "Public"],
  "roots": ["C:\\", "D:\\"]
}
```

#### Errors

- `403` — Remote access

---

## Cache Management

### GET /api/tools/cache-info

Get thumbnail cache status.

#### Response

```json
{
  "count": 1234,
  "size_mb": 56.7
}
```

### POST /api/tools/clear-cache

Clear all thumbnail cache.

#### Rate Limit

DESTRUCTIVE

#### Response

```json
{
  "cleared": 1234
}
```

### POST /api/tools/rebuild-groups

Force rebuild the groups index cache.

#### Rate Limit

DESTRUCTIVE

#### Response

```json
{
  "status": "rebuilt",
  "folders": 42,
  "zips": 5,
  "file_count": 1500
}
```

### POST /api/tools/faststart-prescan

Pre-generate faststart cache for all MP4/MOV files in the background. Returns 202 immediately.

#### Rate Limit

WRITE

#### Response (202)

```json
{
  "ok": true,
  "started": true,
  "message": "faststart prescan started"
}
```

When already running (200):

```json
{
  "ok": true,
  "started": false,
  "message": "already running"
}
```

---

## Settings

### GET /api/settings/config

Get the current configuration merged with defaults.

#### Response

```json
{
  "port": 5000,
  "pin": "",
  "scan_roots": [],
  "theme": "dark",
  "backup": {
    "enabled": true,
    "periodic_interval_hours": 24
  }
}
```

### POST /api/settings/config

Partially update settings. Deep merge is applied to existing nested objects.

#### Rate Limit

DESTRUCTIVE

#### Request

```json
{
  "theme": "light",
  "backup": {
    "enabled": false
  }
}
```

#### Response

```json
{
  "status": "saved"
}
```

#### Errors

- `400` — Empty data

---

## DB Backup / Restore

### GET /api/tools/backup-download

Download the database file directly. **Only available from localhost.**

#### Response

- Content-Type: `application/x-sqlite3`
- Content-Disposition: `attachment; filename="tags_backup_20260322_120000.db"`
- Returns 404 if database not found

### POST /api/tools/restore

Restore the database by uploading a `.db` file. **Only available from localhost.** Automatically creates a backup of the existing database before restoring.

#### Rate Limit

WRITE

#### Request

`multipart/form-data`:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | file | Yes | SQLite file with `.db` extension |

#### Validation

- Verifies SQLite magic bytes
- Checks for the `files` table
- Rejects databases containing triggers or views

#### Response

```json
{
  "success": true,
  "message": "Database restored successfully",
  "backup": "tags.db.backup_1711100000"
}
```

#### Errors

- `400` — No file uploaded, wrong extension, or invalid SQLite
- `403` — Remote access
- `500` — Backup or restore failure

### POST /api/tools/backup/create

Manually create a managed backup. **Only available from localhost.**

#### Rate Limit

DESTRUCTIVE

#### Response

```json
{
  "success": true,
  "filename": "tags_backup_20260322_120000.db",
  "reason": "manual"
}
```

### GET /api/tools/backup/list

List available backups.

#### Response

```json
{
  "backups": [
    {
      "filename": "tags_backup_20260322_120000.db",
      "size": 1048576,
      "created": "2026-03-22T12:00:00"
    }
  ],
  "count": 1
}
```

### POST /api/tools/backup/restore

Restore database from a named backup. **Only available from localhost.**

#### Rate Limit

DESTRUCTIVE

#### Request

```json
{
  "filename": "tags_backup_20260322_120000.db"
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `filename` | string | Yes | Backup filename to restore from |

#### Response

```json
{
  "success": true,
  "message": "Backup restored",
  "filename": "tags_backup_20260322_120000.db"
}
```

#### Errors

- `400` — Filename missing or backup not found
- `403` — Remote access

### POST /api/tools/backup/delete

Delete a specific backup. **Only available from localhost.**

#### Rate Limit

DESTRUCTIVE

#### Request

```json
{
  "filename": "tags_backup_20260322_120000.db"
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `filename` | string | Yes | Backup filename to delete |

#### Response

```json
{
  "success": true,
  "deleted": "tags_backup_20260322_120000.db"
}
```

### GET /api/tools/backup/status

Get the backup system status.

#### Response

```json
{
  "enabled": true,
  "backup_on_scan_complete": true,
  "periodic_interval_hours": 24,
  "max_generations": 5,
  "cooldown_minutes": 5,
  "scheduler_running": true,
  "last_backup_time": "2026-03-22T11:00:00",
  "within_cooldown": false
}
```

---

## Debug Log

### GET /api/tools/debug-log

Get the tail of the debug log. Returns `enabled: false` when debug mode is disabled.

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | int | `200` | Number of lines to retrieve (1-5000) |
| `filter` | string | `""` | Line filter string (substring match) |

#### Response

```json
{
  "enabled": true,
  "lines": ["2026-03-22 12:00:00 [INFO] Server started", "..."],
  "total_lines": 5000,
  "log_path": "/path/to/debug.log",
  "log_size_kb": 128.5
}
```

### GET /api/tools/debug-log/download

Download the debug log file. **Only available from localhost.**

#### Response

- Content-Type: `text/plain`
- Content-Disposition: `attachment; filename="debug.log"`

#### Errors

- `400` — Debug mode not enabled
- `403` — Remote access
- `404` — Log file not found

### POST /api/tools/debug-log/clear

Clear the debug log. **Only available from localhost.**

#### Rate Limit

WRITE

#### Response

```json
{
  "success": true,
  "message": "Log cleared"
}
```

#### Errors

- `400` — Debug mode not enabled
- `403` — Remote access
- `404` — Log file not found

---

## Archive Cleanup

Tools for detecting and cleaning up duplicated archives and their extracted folders. All endpoints are **only available from localhost.**

### POST /api/tools/archive-cleanup/scan

Scan for archive-folder pairs.

#### Rate Limit

HEAVY

#### Request

```json
{
  "path": "/path/to/check",
  "recursive": false
}
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | string | Required | Directory to scan |
| `recursive` | bool | `false` | Recursively scan subdirectories |

#### Path Validation

- Paths starting with `~` are rejected
- Paths containing `..` are rejected

#### Response

```json
{
  "pairs": [
    {
      "archive_path": "/data/images.zip",
      "folder_path": "/data/images",
      "archive_size": 10485760,
      "folder_size": 12582912,
      "file_count": 42
    }
  ],
  "count": 1
}
```

### POST /api/tools/archive-cleanup/execute

Execute cleanup actions on scanned pairs.

#### Rate Limit

DESTRUCTIVE

#### Request

```json
{
  "actions": [
    { "action": "delete_archive", "archive_path": "/data/images.zip" },
    { "action": "delete_folder", "folder_path": "/data/images" },
    { "action": "skip" }
  ]
}
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `actions` | array | Array of actions |
| `actions[].action` | string | One of `"delete_archive"`, `"delete_folder"`, `"skip"` |
| `actions[].archive_path` | string | Required when action is `delete_archive` |
| `actions[].folder_path` | string | Required when action is `delete_folder` |

#### Response

```json
{
  "results": [
    { "action": "delete_archive", "success": true },
    { "action": "delete_folder", "success": true },
    { "action": "skip", "success": true }
  ]
}
```

### POST /api/tools/archive-cleanup/llm-verify

Verify archive-folder pair identity using LLM (single pair).

#### Rate Limit

HEAVY

#### Request

```json
{
  "archive_path": "/data/images.zip",
  "folder_path": "/data/images",
  "pair_info": {
    "archive_size": 10485760,
    "folder_size": 12582912
  }
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `archive_path` | string | Yes | Archive file path |
| `folder_path` | string | Yes | Extracted folder path |
| `pair_info` | object | No | Additional pair metadata |

#### Response

```json
{
  "verdict": "same",
  "confidence": 0.95,
  "reasoning": "File counts and sizes match exactly."
}
```

### POST /api/tools/archive-cleanup/llm-verify-batch

Batch verify multiple pairs using LLM. Maximum 50 pairs.

#### Rate Limit

HEAVY

#### Request

```json
{
  "pairs": [
    {
      "archive_path": "/data/a.zip",
      "folder_path": "/data/a",
      "pair_info": {}
    }
  ]
}
```

| Parameter | Type | Limit | Description |
|-----------|------|-------|-------------|
| `pairs` | array | Max 50 | Array of pairs to verify |

#### Response

```json
{
  "results": [
    { "result": { "verdict": "same", "confidence": 0.95, "reasoning": "..." } }
  ]
}
```

### GET /api/tools/archive-cleanup/llm-config

Get archive cleanup LLM configuration.

#### Response

```json
{
  "engine": "ollama",
  "base_url": "http://localhost:11434",
  "model": "llama3",
  "api_key": ""
}
```

### POST /api/tools/archive-cleanup/llm-config

Save archive cleanup LLM configuration.

#### Rate Limit

WRITE

#### Request

```json
{
  "engine": "ollama",
  "base_url": "http://localhost:11434",
  "model": "llama3"
}
```

#### Response

```json
{
  "success": true
}
```

### POST /api/tools/archive-cleanup/list-models

List available models for the specified engine.

#### Request

```json
{
  "engine": "ollama",
  "base_url": "http://localhost:11434"
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `engine` | string | Yes | `"ollama"` or `"openai_compat"` |
| `base_url` | string | Yes | Engine API URL |
| `api_key` | string | No | API key for `openai_compat` |

#### Response

```json
{
  "models": ["llama3", "mistral", "codellama"]
}
```

#### Errors

- `400` — Invalid engine or missing `base_url`
