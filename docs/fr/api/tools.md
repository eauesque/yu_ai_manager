# API Outils

APIs utilitaires pour la détection des doublons, le calcul de hachis, la recherche d'images similaires, la gestion du cache, la sélection de dossier, la sauvegarde de base de données, le nettoyage d'archives et l'enregistrement de débogage.

---

## Doublons / Hachis / Scan

### GET /api/tools/find-duplicates

Détecter les fichiers en doublon en fonction du hachage ou du nom de fichier.

#### Rate Limit

HEAVY

#### Paramètres

| Paramètre | Type | Défaut | Description |
|-----------|------|---------|-------------|
| `cross_directory` | string | `"false"` | Définir sur `"true"` pour détecter les doublons dans différents répertoires |
| `method` | string | `"hash"` | Méthode de détection : `"hash"` ou `"name"` |
| `threshold` | int | `5` | Seuil de similarité |

#### Réponse

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

Demarrer le calcul de hachis en arriere-plan pour les fichiers sans hachis.

#### Rate Limit

HEAVY

#### Requête

```json
{
  "type": "both",
  "limit": 5000
}
```

| Paramètre | Type | Défaut | Description |
|-----------|------|---------|-------------|
| `type` | string | `"both"` | Type de hachis : `"md5"`, `"sha256"` ou `"both"` |
| `limit` | int | `5000` | Nombre maximum de fichiers à traiter |

#### Réponse

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

#### Requête

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

| Paramètre | Type | Défaut | Description |
|-----------|------|---------|-------------|
| `groups` | array | Requis | Deletion targets. `keep` = file ID to keep, `delete` = array of file IDs to remove |
| `mode` | string | `"soft"` | `"soft"` = logical deletion, `"hard"` = physical deletion |

#### Réponse

```json
{
  "deleted": 2,
  "errors": []
}
```

### GET /api/tools/normalize-tags

Normalize tags (merge duplicates, trim whitespace, etc.).

#### Paramètres

| Paramètre | Type | Défaut | Description |
|-----------|------|---------|-------------|
| `dry_run` | string | `"false"` | Set to `"true"` to preview changes without applying |

#### Réponse

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

#### Paramètres

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | Reference file ID |
| `threshold` | int | No | Seuil de similarité (1-20, default `5`) |

#### Réponse

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

#### Erreurs

- `400` — `file_id` missing or invalid
- `404` — Specified file not found

### POST /api/tools/scan

Scan files in a directory and register them in the database.

#### Rate Limit

HEAVY

#### Requête

```json
{
  "path": "/path/to/images",
  "recursive": true,
  "scan_zips": false,
  "compute_hash": false
}
```

| Paramètre | Type | Défaut | Description |
|-----------|------|---------|-------------|
| `path` | string | Requis | Directory path to scan |
| `recursive` | bool | `true` | Analyser récursivement les sous-répertoires |
| `scan_zips` | bool | `false` | Analyser également à l'intérieur des archives ZIP |
| `compute_hash` | bool | `false` | Calculer les hachis des fichiers lors de l'analyse |

#### Réponse

```json
{
  "scanned": 150,
  "new": 42,
  "updated": 5,
  "errors": []
}
```

---

## Recherche de fichiers / Inspection des métadonnées

### GET /api/tools/file-search

Search files in the database by keyword.

#### Paramètres

| Paramètre | Type | Défaut | Description |
|-----------|------|---------|-------------|
| `q` / `query` | string | `""` | Mot-clé de recherche |
| `meta` / `meta_filter` | string | `"all"` | Filtrer par source de métadonnées (`"all"`, `"a1111_png"`, `"novelai_v4_png"`, etc.) |
| `limit` / `n` / `page_size` | int | `100` | Nombre de résultats (1-500) |

#### Réponse

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

#### Requête

`multipart/form-data`:

| Champ | Type | Requis | Description |
|-------|------|----------|-------------|
| `file` | file | Yes | Fichier à inspecter |
| `zip_entry` | string | No | Chemin dans l'archive ZIP (for ZIP files) |

#### Réponse

```json
{
  "filename": "image.png",
  "meta_source": "novelai_v4_png",
  "positive": "1girl, landscape",
  "negative": "bad anatomy",
  "parameters": { ... }
}
```

#### Erreurs

- `400` — Aucun fichier téléchargé

---

## Sélection de dossier / Listes de répertoires

### GET /api/tools/select-folder

Open the OS native folder picker dialog. **Only available from localhost.**

#### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `initial` / `path` / `dir` | string | Répertoire initial pour le dialogue |

#### Réponse

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

List directories on the serveur. **Only available from localhost.**

#### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `path` / `dir` / `initial` | string | Directory to list. Empty returns root directories |

#### Réponse

```json
{
  "current": "C:\\Users",
  "parent": "C:\\",
  "dirs": ["user1", "Public"],
  "roots": ["C:\\", "D:\\"]
}
```

#### Erreurs

- `403` — Accès à distance

---

## Gestion du cache

### GET /api/tools/cache-info

Get thumbnail cache status.

#### Réponse

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

#### Réponse

```json
{
  "cleared": 1234
}
```

### POST /api/tools/rebuild-groups

Force rebuild the groups index cache.

#### Rate Limit

DESTRUCTIVE

#### Réponse

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

#### Réponse (202)

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

## Paramètres

### GET /api/paramètres/config

Obtenir le configuration merged with defaults.

#### Réponse

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

### POST /api/paramètres/config

Partially update paramètres. Deep merge is applied to existing nested objects.

#### Rate Limit

DESTRUCTIVE

#### Requête

```json
{
  "theme": "light",
  "backup": {
    "enabled": false
  }
}
```

#### Réponse

```json
{
  "status": "saved"
}
```

#### Erreurs

- `400` — Empty data

---

## Sauvegarde / Restauration de base de données

### GET /api/tools/backup-download

Download the database file directly. **Only available from localhost.**

#### Réponse

- Content-Type: `application/x-sqlite3`
- Content-Disposition: `attachment; filename="tags_backup_20260322_120000.db"`
- Returns 404 if database not found

### POST /api/tools/restore

Restore the database by uploading a `.db` file. **Only available from localhost.** Automatically creates a backup of the existing database before restoring.

#### Rate Limit

WRITE

#### Requête

`multipart/form-data`:

| Champ | Type | Requis | Description |
|-------|------|----------|-------------|
| `file` | file | Yes | Fichier SQLite avec l'extension `.db` |

#### Validation

- Verifies SQLite magic bytes
- Checks for the `files` table
- Rejects databases containing triggers or views

#### Réponse

```json
{
  "success": true,
  "message": "Database restored successfully",
  "backup": "tags.db.backup_1711100000"
}
```

#### Erreurs

- `400` — Aucun fichier téléchargé, wrong extension, or invalid SQLite
- `403` — Accès à distance
- `500` — Backup or restore failure

### POST /api/tools/backup/create

Manually create a managed backup. **Only available from localhost.**

#### Rate Limit

DESTRUCTIVE

#### Réponse

```json
{
  "success": true,
  "filename": "tags_backup_20260322_120000.db",
  "reason": "manual"
}
```

### GET /api/tools/backup/list

List available backups.

#### Réponse

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

#### Requête

```json
{
  "filename": "tags_backup_20260322_120000.db"
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `filename` | string | Yes | Backup filename to restore from |

#### Réponse

```json
{
  "success": true,
  "message": "Backup restored",
  "filename": "tags_backup_20260322_120000.db"
}
```

#### Erreurs

- `400` — Filename missing or backup not found
- `403` — Accès à distance

### POST /api/tools/backup/delete

Delete a specific backup. **Only available from localhost.**

#### Rate Limit

DESTRUCTIVE

#### Requête

```json
{
  "filename": "tags_backup_20260322_120000.db"
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `filename` | string | Yes | Backup filename to delete |

#### Réponse

```json
{
  "success": true,
  "deleted": "tags_backup_20260322_120000.db"
}
```

### GET /api/tools/backup/status

Get the backup system status.

#### Réponse

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

## Journal de débogage

### GET /api/tools/debug-log

Get the tail of the debug log. Returns `enabled: false` when debug mode is disabled.

#### Paramètres

| Paramètre | Type | Défaut | Description |
|-----------|------|---------|-------------|
| `limit` | int | `200` | Number of lines to retrieve (1-5000) |
| `filter` | string | `""` | Line filter string (substring match) |

#### Réponse

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

#### Réponse

- Content-Type: `text/plain`
- Content-Disposition: `attachment; filename="debug.log"`

#### Erreurs

- `400` — Debug mode not enabled
- `403` — Accès à distance
- `404` — Log file not found

### POST /api/tools/debug-log/clear

Clear the debug log. **Only available from localhost.**

#### Rate Limit

WRITE

#### Réponse

```json
{
  "success": true,
  "message": "Log cleared"
}
```

#### Erreurs

- `400` — Debug mode not enabled
- `403` — Accès à distance
- `404` — Log file not found

---

## Nettoyage d'archives

Tools for detecting and cleaning up duplicated archives and their extracted folders. All endpoints are **only available from localhost.**

### POST /api/tools/archive-cleanup/scan

Scan for archive-folder pairs.

#### Rate Limit

HEAVY

#### Requête

```json
{
  "path": "/path/to/check",
  "recursive": false
}
```

| Paramètre | Type | Défaut | Description |
|-----------|------|---------|-------------|
| `path` | string | Requis | Directory to scan |
| `recursive` | bool | `false` | Analyser récursivement les sous-répertoires |

#### Path Validation

- Paths starting with `~` are rejected
- Paths containing `..` are rejected

#### Réponse

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

#### Requête

```json
{
  "actions": [
    { "action": "delete_archive", "archive_path": "/data/images.zip" },
    { "action": "delete_folder", "folder_path": "/data/images" },
    { "action": "skip" }
  ]
}
```

| Paramètre | Type | Description |
|-----------|------|-------------|
| `actions` | array | Tableau of actions |
| `actions[].action` | string | One of `"delete_archive"`, `"delete_folder"`, `"skip"` |
| `actions[].archive_path` | string | Requis when action is `delete_archive` |
| `actions[].folder_path` | string | Requis when action is `delete_folder` |

#### Réponse

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

#### Requête

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

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `archive_path` | string | Yes | Archive file path |
| `folder_path` | string | Yes | Extracted folder path |
| `pair_info` | object | No | Additional pair metadata |

#### Réponse

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

#### Requête

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

| Paramètre | Type | Limit | Description |
|-----------|------|-------|-------------|
| `pairs` | array | Max 50 | Tableau of pairs to verify |

#### Réponse

```json
{
  "results": [
    { "result": { "verdict": "same", "confidence": 0.95, "reasoning": "..." } }
  ]
}
```

### GET /api/tools/archive-cleanup/llm-config

Get archive cleanup LLM configuration.

#### Réponse

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

#### Requête

```json
{
  "engine": "ollama",
  "base_url": "http://localhost:11434",
  "model": "llama3"
}
```

#### Réponse

```json
{
  "success": true
}
```

### POST /api/tools/archive-cleanup/list-modèles

List available modèles for the specified engine.

#### Requête

```json
{
  "engine": "ollama",
  "base_url": "http://localhost:11434"
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `engine` | string | Yes | `"ollama"` or `"openai_compat"` |
| `base_url` | string | Yes | Engine API URL |
| `api_key` | string | No | clé API for `openai_compat` |

#### Réponse

```json
{
  "models": ["llama3", "mistral", "codellama"]
}
```

#### Erreurs

- `400` — Invalid engine or missing `base_url`
