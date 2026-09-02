# API Extensions

APIs pour la gestion des extensions, installation, security, and authoring.

---

## GET /api/extensions

Lister tous les installed extensions.

### Paramètres

None

### Réponse

```json
{
  "extensions": [
    {
      "name": "builtin-sd-webui-bridge",
      "version": "1.0.0",
      "description": "SD WebUI Bridge",
      "enabled": true,
      "trust_level": "trusted",
      "category": "integration",
      "directory": "extensions/builtin_sd_webui_bridge"
    }
  ],
  "total": 5,
  "category_order": ["core", "integration", "tools", "ui", "other"]
}
```

| Champ | Type | Description |
|-------|------|-------------|
| `extensions` | array | Tableau of extension information |
| `total` | int | Total number of extensions |
| `category_order` | string[] | Display order of categories |

## GET /api/extensions/\<name\>

Get detailed information about a specific extension.

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `name` | string | Extension name (path parameter) |

### Réponse

```json
{
  "name": "builtin-sd-webui-bridge",
  "version": "1.0.0",
  "description": "SD WebUI Bridge",
  "enabled": true,
  "trust_level": "trusted",
  "category": "integration",
  "directory": "extensions/builtin_sd_webui_bridge"
}
```

### Erreurs

- `404` — Extension not found

## POST /api/extensions/\<name\>/toggle

Toggle an extension's enabled/disabled state.

### Rate Limit

WRITE

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `name` | string | Extension name (path parameter) |

### Requête

```json
{
  "enabled": true
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `enabled` | boolean | No | `true` to enable, `false` to disable. Omit to toggle (invert current state) |

### Réponse

```json
{
  "name": "builtin-sd-webui-bridge",
  "enabled": true,
  "message": "Extension 'builtin-sd-webui-bridge' enabled"
}
```

### Erreurs

- `404` — Extension not found

## GET /api/extensions/\<name\>/config

Get the configuration schema and current values for an extension.

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `name` | string | Extension name (path parameter) |

### Réponse

```json
{
  "name": "builtin-sd-webui-bridge",
  "config_schema": {
    "fields": [
      {
        "key": "api_url",
        "label": "API URL",
        "type": "text",
        "default": "http://127.0.0.1:7860",
        "value": "http://127.0.0.1:7860"
      }
    ]
  }
}
```

### Erreurs

- `404` — Extension not found

## POST /api/extensions/\<name\>/config

Save extension configuration values. Includes validation.

### Rate Limit

WRITE

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `name` | string | Extension name (path parameter) |

### Requête

```json
{
  "values": {
    "api_url": "http://127.0.0.1:7860",
    "timeout": 30
  }
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `values` | object | Yes | Map of field keys to values |

### Réponse

```json
{
  "ok": true,
  "saved": {
    "api_url": "http://127.0.0.1:7860",
    "timeout": 30
  }
}
```

### Erreurs

- `404` — Extension not found
- `400` — Validation error

---

## Extension Install / Update / Uninstall

The following endpoints are restricted to **localhost access only**. Remote requests return `403`.

## POST /api/extensions/install

Install an extension from a Git repository.

### Rate Limit

WRITE

### Access Restriction

Localhost only

### Requête

```json
{
  "url": "https://github.com/user/my-extension.git"
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `url` | string | Yes | Git repository URL. `git` and `repo` are accepted as aliases |

### Réponse

```json
{
  "ok": true,
  "name": "my-extension",
  "message": "Extension installed successfully"
}
```

### Erreurs

- `400` — URL not provided or invalid URL format
- `403` — Access from non-localhost

## POST /api/extensions/\<name\>/update

Update a specific extension to the latest version (git pull).

### Rate Limit

WRITE

### Access Restriction

Localhost only

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `name` | string | Extension name (path parameter) |

### Réponse

```json
{
  "ok": true,
  "name": "my-extension",
  "message": "Extension updated successfully"
}
```

### Erreurs

- `403` — Access from non-localhost
- `404` — Extension not found

## POST /api/extensions/update-all

Batch update all Git-installed extensions.

### Rate Limit

WRITE

### Access Restriction

Localhost only

### Réponse

```json
{
  "results": [
    {"name": "my-extension", "ok": true, "message": "Updated"},
    {"name": "other-ext", "ok": false, "error": "Git pull failed"}
  ]
}
```

### Erreurs

- `403` — Access from non-localhost

## DELETE /api/extensions/\<name\>/uninstall

Uninstall an extension (delete directory).

### Rate Limit

DESTRUCTIVE

### Access Restriction

Localhost only

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `name` | string | Extension name (path parameter) |

### Réponse

```json
{
  "ok": true,
  "name": "my-extension",
  "message": "Extension uninstalled"
}
```

### Erreurs

- `403` — Access from non-localhost
- `404` — Extension not found

---

## Sécurité et Permissions

## GET /api/extensions/\<name\>/permissions

Get permission information and approval state for an extension.

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `name` | string | Extension name (path parameter) |

### Réponse

```json
{
  "name": "my-extension",
  "trust_level": "L2",
  "approved": true,
  "permissions": {
    "required": [
      {"name": "network", "reason": "API calls to external service"}
    ],
    "optional": [
      {"name": "filesystem_read", "reason": "Read user images"}
    ]
  },
  "granted": {
    "granted": ["network", "filesystem_read"],
    "denied": [],
    "granted_at": "2025-01-15T10:30:00",
    "auto_approved": false
  }
}
```

| Champ | Type | Description |
|-------|------|-------------|
| `trust_level` | string | Trust level (`trusted`, `L1`, `L2`) |
| `approved` | boolean | Si the user has approved this extension |
| `permissions.required` | array | List of required permissions |
| `permissions.optional` | array | List of optional permissions |
| `granted` | object/null | Details of granted permissions. `null` if not yet approved |

### Erreurs

- `404` — Extension not found

## POST /api/extensions/\<name\>/permissions

Approve or revoke extension permissions.

### Rate Limit

WRITE

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `name` | string | Extension name (path parameter) |

### Requête (Approve)

```json
{
  "action": "approve",
  "granted": ["network", "filesystem_read"],
  "denied": ["filesystem_write"]
}
```

### Requête (Revoke)

```json
{
  "action": "revoke"
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `action` | string | No | `"approve"` (default) or `"revoke"` |
| `granted` | string[] | No | List of permission names to grant (for approve) |
| `denied` | string[] | No | List of permission names to deny (for approve) |

### Réponse (Approve)

```json
{
  "name": "my-extension",
  "action": "approved",
  "granted": ["network", "filesystem_read"],
  "denied": ["filesystem_write"]
}
```

### Réponse (Revoke)

```json
{
  "name": "my-extension",
  "action": "revoked"
}
```

### Erreurs

- `400` — `granted` is not a list
- `404` — Extension not found

## GET /api/extensions/\<name\>/scan-results

Get static analysis results for extension code. Returns both ManifestAuthority and CodeVerifier results.

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `name` | string | Extension name (path parameter) |

### Réponse

```json
{
  "name": "my-extension",
  "trust_level": "L2",
  "manifest_review": {
    "approved": true,
    "issues": []
  },
  "code_scan": {
    "approved": true,
    "findings": [
      {
        "file": "my_ext.py",
        "line": 15,
        "severity": "warning",
        "message": "Uses subprocess module"
      }
    ]
  }
}
```

| Champ | Type | Description |
|-------|------|-------------|
| `manifest_review.approved` | boolean | Si the manifest passed review |
| `manifest_review.issues` | array | List of issues (`severity`, `message`) |
| `code_scan` | object/null | Code scan results. `null` if no directory |
| `code_scan.findings` | array | List of findings |

### Erreurs

- `404` — Extension not found

## POST /api/extensions/\<name\>/rescan

Re-scan extension code. Returns the same result format as `scan-results`.

### Rate Limit

WRITE

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `name` | string | Extension name (path parameter) |

### Réponse

Same format as `GET /api/extensions/<name>/scan-results`.

## GET /api/extensions/\<name\>/tokens

Get capability token issuance status for an extension.

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `name` | string | Extension name (path parameter) |

### Réponse

```json
{
  "name": "my-extension",
  "token_count": 2,
  "tokens": [
    {
      "capability": "network",
      "issued_at": "2025-01-15T10:30:00",
      "expires_at": "2025-01-16T10:30:00"
    }
  ]
}
```

### Erreurs

- `404` — Extension not found

## GET /api/extensions/\<name\>/integrity

Get file integrity status for an extension. Also includes revocation tracker and import guard information.

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `name` | string | Extension name (path parameter) |

### Réponse

```json
{
  "name": "my-extension",
  "integrity": {
    "verified": true,
    "last_check": "2025-01-15T10:30:00",
    "files_changed": 0
  },
  "revocation": {
    "denial_count": 0,
    "last_access": null
  },
  "import_guard": {
    "import_denial_count": 0
  }
}
```

| Champ | Type | Description |
|-------|------|-------------|
| `integrity` | object | File integrity check results |
| `revocation` | object | Token revocation tracker information |
| `import_guard` | object | Import guard denial count |

### Erreurs

- `404` — Extension not found

---

## Hooks et Marketplace

## GET /api/extensions/hooks

List registered extension hooks and hook definitions.

### Paramètres

None

### Réponse

```json
{
  "hooks": {
    "after_scan": [
      {"extension": "builtin-tagger", "priority": 100}
    ]
  },
  "definitions": {
    "after_scan": {"mode": "sequential"},
    "before_import": {"mode": "sequential"}
  }
}
```

| Champ | Type | Description |
|-------|------|-------------|
| `hooks` | object | Map of hook names to registered extension lists |
| `definitions` | object | Available hook definitions. `mode` is the execution mode |

## GET /api/extensions/marketplace

Search marketplace extensions.

### Paramètres

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `q` | string | No | Search query (query parameter). Empty string returns all |

### Réponse

```json
{
  "extensions": [
    {
      "name": "awesome-extension",
      "description": "An awesome extension",
      "author": "developer",
      "version": "1.0.0",
      "installed": false
    }
  ],
  "total": 10
}
```

| Champ | Type | Description |
|-------|------|-------------|
| `extensions` | array | Marketplace extension information |
| `extensions[].installed` | boolean | Si the extension is installed locally |
| `total` | int | Total number of search results |

## POST /api/extensions/marketplace/refresh

Force refresh the marketplace cache.

### Rate Limit

WRITE

### Réponse

```json
{
  "refreshed": true,
  "total": 25
}
```

---

## Isolation

## GET /api/extensions/isolation

Get process isolation status.

### Paramètres

None

### Réponse

```json
{
  "available": true,
  "processes": {
    "my-extension": {
      "pid": 12345,
      "status": "running"
    }
  }
}
```

| Champ | Type | Description |
|-------|------|-------------|
| `available` | boolean | Si process isolation is available |
| `processes` | object | Map of extension names to process status |

## GET /api/extensions/os-isolation

Get OS-level isolation status (Phase D). Also includes process isolation information.

### Paramètres

None

### Réponse

```json
{
  "os_isolation": {
    "platform": "linux",
    "available_backends": ["apparmor"]
  },
  "config": {
    "enabled": true,
    "apparmor": true,
    "macos_sandbox_exec": false,
    "macos_user_isolation": false,
    "windows_restricted_token": false,
    "windows_job_object": false
  },
  "processes": {}
}
```

| Champ | Type | Description |
|-------|------|-------------|
| `os_isolation` | object | OS-level isolation information |
| `config.enabled` | boolean | Si OS isolation is enabled |
| `config.apparmor` | boolean | AppArmor (Linux) usage status |
| `config.macos_sandbox_exec` | boolean | macOS sandbox-exec usage status |
| `config.macos_user_isolation` | boolean | macOS user isolation usage status |
| `config.windows_restricted_token` | boolean | Windows restricted token usage status |
| `config.windows_job_object` | boolean | Windows Job Objet usage status |
| `processes` | object | Process isolation status |

---

## Création d'extension

APIs for creating and editing custom extensions. Based on the concession modèle, only the `extensions/custom-{name}/` directory is writable.

All endpoints are restricted to **localhost access only**.

### Security Constraints

- Extension name: lowercase alphanumeric and hyphens only (`[a-z0-9-]`), max 50 characters, `builtin-` prefix prohibited
- File types: whitelist only (`entrypoint`, `template`, `static_css`, `static_js`, `config`, `readme`)
- Binary files: completely prohibited
- File size limits: 10KB to 50KB depending on type

## POST /api/extensions/author/create

Créer un nouveau custom extension with scaffold files.

### Rate Limit

WRITE

### Access Restriction

Localhost only

### Requête

```json
{
  "name": "my-tool",
  "description": "A useful tool extension"
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `name` | string | Yes | Extension name (`[a-z0-9-]`, max 50 characters) |
| `description` | string | No | Extension description |

### Réponse

```json
{
  "ok": true,
  "name": "custom-my-tool",
  "path": "extensions/custom-my-tool",
  "files": [
    "extension.json",
    "my_tool_ext.py"
  ]
}
```

### Erreurs

- `400` — Invalid name or extension already exists
- `403` — Access from non-localhost

## POST /api/extensions/author/\<name\>/write

Write a file to a custom extension.

### Rate Limit

WRITE

### Access Restriction

Localhost only

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `name` | string | Extension name (path parameter, without `custom-` prefix) |

### Requête

```json
{
  "file_type": "entrypoint",
  "filename": "my_tool_ext",
  "content": "\"\"\"My tool extension.\"\"\"\n\nfrom quart import Blueprint\n..."
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `file_type` | string | Yes | File type. One of: `entrypoint`, `template`, `static_css`, `static_js`, `config`, `readme` |
| `filename` | string | Yes | Filename without extension. Alphanumeric, hyphens, and underscores only |
| `content` | string | Yes | File content (text only) |

### File Type Constraints

| file_type | Extension | Max Size | Notes |
|-----------|-----------|----------|-------|
| `entrypoint` | `.py` | 50KB | Extension entrypoint |
| `template` | `.html` | 50KB | Placed in `templates/{name}/` |
| `static_css` | `.css` | 50KB | Placed in `static/` |
| `static_js` | `.js` | 50KB | Placed in `static/` |
| `config` | `.json` | 10KB | Filename must be `extension` |
| `readme` | `.md` | 20KB | Filename must be `README` |

### Réponse

```json
{
  "ok": true,
  "file": "my_tool_ext.py",
  "size": 256
}
```

### Erreurs

- `400` — Validation error (invalid name, file type, size exceeded, binary detected)
- `403` — Access from non-localhost

## GET /api/extensions/author/\<name\>/read

Read a file from a custom extension.

### Access Restriction

Localhost only

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `name` | string | Extension name (path parameter) |

### Query Paramètres

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `file_type` | string | Yes | File type |
| `filename` | string | Yes | Filename without extension |

### Réponse

```json
{
  "ok": true,
  "file": "my_tool_ext.py",
  "content": "\"\"\"My tool extension.\"\"\"\n...",
  "size": 256
}
```

### Erreurs

- `400` — Validation error
- `403` — Access from non-localhost

## GET /api/extensions/author/\<name\>/files

Lister tous les files in a custom extension.

### Access Restriction

Localhost only

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `name` | string | Extension name (path parameter) |

### Réponse

```json
{
  "ok": true,
  "name": "custom-my-tool",
  "files": [
    {"path": "extension.json", "size": 320},
    {"path": "my_tool_ext.py", "size": 256},
    {"path": "templates/my_tool/index.html", "size": 1024}
  ],
  "total_size": 1600
}
```

### Erreurs

- `400` — Invalid extension name
- `403` — Access from non-localhost

## POST /api/extensions/author/\<name\>/validate

Validate a custom extension's extension.json and code. Runs CodeVerifier without registering the extension.

### Rate Limit

WRITE

### Access Restriction

Localhost only

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `name` | string | Extension name (path parameter) |

### Réponse (Success)

```json
{
  "ok": true,
  "name": "custom-my-tool",
  "issues": [],
  "code_findings": [],
  "manifest": {
    "name": "custom-my-tool",
    "version": "0.1.0",
    "entrypoint": "my_tool_ext.py"
  }
}
```

### Réponse (Issues Found)

```json
{
  "ok": false,
  "name": "custom-my-tool",
  "issues": [
    "Missing required field: version",
    "CodeVerifier rejected: dangerous patterns detected"
  ],
  "code_findings": [
    {
      "severity": "critical",
      "message": "Uses eval()",
      "file": "my_tool_ext.py",
      "line": 42
    }
  ],
  "manifest": {}
}
```

| Champ | Type | Description |
|-------|------|-------------|
| `ok` | boolean | Si all checks passed |
| `issues` | string[] | Manifest and code verification issues |
| `code_findings` | array | CodeVerifier findings |
| `manifest` | object | Parsed extension.json contents |

### Erreurs

- `400` — Invalid extension name or extension does not exist
- `403` — Access from non-localhost
