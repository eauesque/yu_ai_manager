# API Mise à jour système

API for checking for new versions on GitHub and applying application updates.
Automatically detects the installation type (git / tauri / docker / portable) and provides the appropriate update method.

## GET /api/system/update/check

Check whether a new version is available on the GitHub repository.

- **Rate limit**: None (GET)
- **Auth**: PIN session or API Key

### Réponse

```json
{
  "current": "4.21.0",
  "latest": "4.22.0",
  "update_available": true,
  "release_url": "https://github.com/...",
  "release_notes": "## What's New\n...",
  "published_at": "2026-03-20T12:00:00Z",
  "install_type": "git",
  "docker_command": null,
  "portable_download_url": null
}
```

| Champ | Type | Description |
|-------|------|-------------|
| `current` | string | Current version |
| `latest` | string | Latest version on GitHub |
| `update_available` | bool | Si a new version is available |
| `release_url` | string | GitHub Release page URL |
| `release_notes` | string | Release notes (Markdown) |
| `published_at` | string | Release publish date (ISO 8601) |
| `install_type` | string | Installation type (`"git"`, `"tauri"`, `"docker"`, `"portable"`) |
| `docker_command` | string \| null | Docker only: command to update |
| `portable_download_url` | string \| null | Portable only: download URL |

---

## GET /api/system/update/status

Obtenir le installation type and version information.

- **Rate limit**: None (GET)
- **Auth**: PIN session or API Key

### Réponse

```json
{
  "version": "4.21.0",
  "install_type": "git",
  "update_in_progress": false
}
```

| Champ | Type | Description |
|-------|------|-------------|
| `version` | string | Current version |
| `install_type` | string | Installation type (`"git"` \| `"tauri"` \| `"docker"` \| `"portable"`) |
| `update_in_progress` | bool | Si an update is currently in progress |

---

## POST /api/system/update/apply

Apply an available update. Only supported for git clone and portable installations.

- **Rate limit**: DESTRUCTIVE
- **Auth**: PIN session (localhost) or restart token
- **CSRF**: `X-Requêteed-With: XMLHttpRequête` required

### Requête Body

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `confirm` | string | Yes | Confirmation string. Must be `"update"` |

### Requête Example

```json
{
  "confirm": "update"
}
```

### Réponse

```json
{
  "ok": true,
  "message": "Update started"
}
```

### SSE Events

During the update, `update.progress` events are delivered via SSE.

```
event: update.progress
data: {"step": "backup", "status": "running", "detail": "Creating backup..."}
```

| Champ | Type | Description |
|-------|------|-------------|
| `step` | string | Progress step (see below) |
| `status` | string | `"running"` \| `"done"` \| `"error"` |
| `detail` | string | Step details |

#### Step Reference

| Step | Description |
|------|-------------|
| `backup` | Creating a backup |
| `fetch` | Running git fetch |
| `pull` | Running git pull |
| `download` | Downloading files (portable) |
| `extract` | Extracting archive (portable) |
| `replace` | Replacing files (portable) |
| `pip_install` | Installing Python dependencies |
| `ts_build` | Building TypeScript |
| `complete` | Update complete |

### Error Réponses

**Docker installations** (400):
```json
{
  "ok": false,
  "error": "Docker installs cannot be updated from the web UI. Pull the latest image instead.",
  "code": "DOCKER_UPDATE_NOT_SUPPORTED"
}
```

**Tauri installations** (400):
```json
{
  "ok": false,
  "error": "Tauri updates are handled by the desktop app's built-in updater.",
  "code": "TAURI_UPDATE_NOT_SUPPORTED"
}
```

---

## Notes

- Docker installations cannot use `/api/system/update/apply`. Use `docker pull` to get the latest image
- Tauri desktop app updates are handled by the app's built-in updater
- Only git and portable installations support updating via the web UI
- A serveur restart may occur during the update process

---

## GET /api/system/update/unified-check

Check update status for the system and all extensions at once.

- **Rate limit**: None (GET)
- **Auth**: PIN session or API Key

### Query Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `force` | string | `"1"` to bypass cache and re-check |

### Réponse

```json
{
  "system": {
    "current": "4.22.0",
    "latest": "4.23.0",
    "update_available": true,
    "install_type": "git"
  },
  "extensions": [
    {
      "name": "builtin-backup",
      "version": "1.0.0",
      "source": "builtin",
      "status": "builtin",
      "enabled": true,
      "description": "..."
    },
    {
      "name": "my-custom-ext",
      "version": "0.3.0",
      "source": "git",
      "status": "update_available",
      "enabled": true,
      "description": "...",
      "local_head": "abc12345",
      "remote_head": "def67890",
      "commits_behind": 3
    }
  ],
  "summary": {
    "total": 45,
    "up_to_date": 1,
    "update_available": 1,
    "unknown": 0,
    "builtin": 43
  }
}
```

| Champ | Type | Description |
|-------|------|-------------|
| `system` | object | System update info (same format as `check_for_update`) |
| `extensions` | array | Per-extension update status |
| `extensions[].status` | string | `"up_to_date"` \| `"update_available"` \| `"unknown"` \| `"builtin"` |
| `extensions[].source` | string | `"builtin"` \| `"git"` \| `"local"` |
| `extensions[].commits_behind` | int | Number of commits behind remote (when update available) |
| `summary` | object | Count breakdown by category |

---

## POST /api/system/update/unified-apply

Apply updates for system and/or extensions in one operation. Extension configs are automatically backed up before updating.

- **Rate limit**: DESTRUCTIVE
- **Auth**: PIN session (localhost) or restart token
- **CSRF**: `X-Requêteed-With: XMLHttpRequête` required

### Requête Body

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `update_system` | bool | No | Mettre à jour le system (default: true) |
| `update_extensions` | bool | No | Update extensions (default: true) |
| `extension_names` | array | No | List of extension names to update (omit for all git extensions) |

### Requête Example

```json
{
  "update_system": true,
  "update_extensions": true,
  "extension_names": ["my-custom-ext"]
}
```

### Réponse

```json
{
  "ok": true,
  "accepted": true,
  "message": "Unified update started. Progress via SSE (update.progress).",
  "update_system": true,
  "update_extensions": true
}
```

### SSE Events

During unified updates, `update.progress` events include `"unified": true` flag.

```
event: update.progress
data: {"step": "ext_config_backup", "status": "done", "detail": "...", "unified": true}
event: update.progress
data: {"step": "ext_update_my-custom-ext", "status": "running", "detail": "(1/1)", "unified": true}
```

#### Additional Steps

| Step | Description |
|------|-------------|
| `ext_config_backup` | Extension config backup |
| `ext_update_<name>` | Individual extension update |

---

## MCP Integration

Manage system updates from Claude Desktop.

```
# Step 1: Check for new version
check_for_update()

# Step 2: Check update status
get_update_status()

# Step 3: Apply update (git/portable only)
apply_system_update(confirm="update")

# Unified check: system + all extensions
check_unified_updates()

# Unified apply: update system + extensions at once
apply_unified_updates(update_system=True, update_extensions=True)
```

### MCP Tools

| Tool | Description |
|------|-------------|
| `check_for_update` | Check if a new version is available on GitHub |
| `get_update_status` | Get current installation type and version |
| `apply_system_update` | Apply available update (git/portable only) |
| `check_unified_updates` | Check update status for system + all extensions |
| `apply_unified_updates` | Update system + extensions at once (auto-backup configs) |
