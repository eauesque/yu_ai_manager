# Extensions API

APIs for managing extensions, installation, security, and authoring.

---

## GET /api/extensions

List all installed extensions.

### Parameters

None

### Response

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

| Field | Type | Description |
|-------|------|-------------|
| `extensions` | array | Array of extension information |
| `total` | int | Total number of extensions |
| `category_order` | string[] | Display order of categories |

## GET /api/extensions/\<name\>

Get detailed information about a specific extension.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | string | Extension name (path parameter) |

### Response

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

### Errors

- `404` — Extension not found

## POST /api/extensions/\<name\>/toggle

Toggle an extension's enabled/disabled state.

### Rate Limit

WRITE

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | string | Extension name (path parameter) |

### Request

```json
{
  "enabled": true
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `enabled` | boolean | No | `true` to enable, `false` to disable. Omit to toggle (invert current state) |

### Response

```json
{
  "name": "builtin-sd-webui-bridge",
  "enabled": true,
  "message": "Extension 'builtin-sd-webui-bridge' enabled"
}
```

### Errors

- `404` — Extension not found

## GET /api/extensions/\<name\>/config

Get the configuration schema and current values for an extension.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | string | Extension name (path parameter) |

### Response

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

### Errors

- `404` — Extension not found

## POST /api/extensions/\<name\>/config

Save extension configuration values. Includes validation.

### Rate Limit

WRITE

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | string | Extension name (path parameter) |

### Request

```json
{
  "values": {
    "api_url": "http://127.0.0.1:7860",
    "timeout": 30
  }
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `values` | object | Yes | Map of field keys to values |

### Response

```json
{
  "ok": true,
  "saved": {
    "api_url": "http://127.0.0.1:7860",
    "timeout": 30
  }
}
```

### Errors

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

### Request

```json
{
  "url": "https://github.com/user/my-extension.git"
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `url` | string | Yes | Git repository URL. `git` and `repo` are accepted as aliases |

### Response

```json
{
  "ok": true,
  "name": "my-extension",
  "message": "Extension installed successfully"
}
```

### Errors

- `400` — URL not provided or invalid URL format
- `403` — Access from non-localhost

## POST /api/extensions/\<name\>/update

Update a specific extension to the latest version (git pull).

### Rate Limit

WRITE

### Access Restriction

Localhost only

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | string | Extension name (path parameter) |

### Response

```json
{
  "ok": true,
  "name": "my-extension",
  "message": "Extension updated successfully"
}
```

### Errors

- `403` — Access from non-localhost
- `404` — Extension not found

## POST /api/extensions/update-all

Batch update all Git-installed extensions.

### Rate Limit

WRITE

### Access Restriction

Localhost only

### Response

```json
{
  "results": [
    {"name": "my-extension", "ok": true, "message": "Updated"},
    {"name": "other-ext", "ok": false, "error": "Git pull failed"}
  ]
}
```

### Errors

- `403` — Access from non-localhost

## DELETE /api/extensions/\<name\>/uninstall

Uninstall an extension (delete directory).

### Rate Limit

DESTRUCTIVE

### Access Restriction

Localhost only

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | string | Extension name (path parameter) |

### Response

```json
{
  "ok": true,
  "name": "my-extension",
  "message": "Extension uninstalled"
}
```

### Errors

- `403` — Access from non-localhost
- `404` — Extension not found

---

## Security & Permissions

## GET /api/extensions/\<name\>/permissions

Get permission information and approval state for an extension.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | string | Extension name (path parameter) |

### Response

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

| Field | Type | Description |
|-------|------|-------------|
| `trust_level` | string | Trust level (`trusted`, `L1`, `L2`) |
| `approved` | boolean | Whether the user has approved this extension |
| `permissions.required` | array | List of required permissions |
| `permissions.optional` | array | List of optional permissions |
| `granted` | object/null | Details of granted permissions. `null` if not yet approved |

### Errors

- `404` — Extension not found

## POST /api/extensions/\<name\>/permissions

Approve or revoke extension permissions.

### Rate Limit

WRITE

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | string | Extension name (path parameter) |

### Request (Approve)

```json
{
  "action": "approve",
  "granted": ["network", "filesystem_read"],
  "denied": ["filesystem_write"]
}
```

### Request (Revoke)

```json
{
  "action": "revoke"
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `action` | string | No | `"approve"` (default) or `"revoke"` |
| `granted` | string[] | No | List of permission names to grant (for approve) |
| `denied` | string[] | No | List of permission names to deny (for approve) |

### Response (Approve)

```json
{
  "name": "my-extension",
  "action": "approved",
  "granted": ["network", "filesystem_read"],
  "denied": ["filesystem_write"]
}
```

### Response (Revoke)

```json
{
  "name": "my-extension",
  "action": "revoked"
}
```

### Errors

- `400` — `granted` is not a list
- `404` — Extension not found

## GET /api/extensions/\<name\>/scan-results

Get static analysis results for extension code. Returns both ManifestAuthority and CodeVerifier results.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | string | Extension name (path parameter) |

### Response

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

| Field | Type | Description |
|-------|------|-------------|
| `manifest_review.approved` | boolean | Whether the manifest passed review |
| `manifest_review.issues` | array | List of issues (`severity`, `message`) |
| `code_scan` | object/null | Code scan results. `null` if no directory |
| `code_scan.findings` | array | List of findings |

### Errors

- `404` — Extension not found

## POST /api/extensions/\<name\>/rescan

Re-scan extension code. Returns the same result format as `scan-results`.

### Rate Limit

WRITE

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | string | Extension name (path parameter) |

### Response

Same format as `GET /api/extensions/<name>/scan-results`.

## GET /api/extensions/\<name\>/tokens

Get capability token issuance status for an extension.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | string | Extension name (path parameter) |

### Response

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

### Errors

- `404` — Extension not found

## GET /api/extensions/\<name\>/integrity

Get file integrity status for an extension. Also includes revocation tracker and import guard information.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | string | Extension name (path parameter) |

### Response

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

| Field | Type | Description |
|-------|------|-------------|
| `integrity` | object | File integrity check results |
| `revocation` | object | Token revocation tracker information |
| `import_guard` | object | Import guard denial count |

### Errors

- `404` — Extension not found

---

## Hooks & Marketplace

## GET /api/extensions/hooks

List registered extension hooks and hook definitions.

### Parameters

None

### Response

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

| Field | Type | Description |
|-------|------|-------------|
| `hooks` | object | Map of hook names to registered extension lists |
| `definitions` | object | Available hook definitions. `mode` is the execution mode |

## GET /api/extensions/marketplace

Search marketplace extensions.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `q` | string | No | Search query (query parameter). Empty string returns all |

### Response

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

| Field | Type | Description |
|-------|------|-------------|
| `extensions` | array | Marketplace extension information |
| `extensions[].installed` | boolean | Whether the extension is installed locally |
| `total` | int | Total number of search results |

## POST /api/extensions/marketplace/refresh

Force refresh the marketplace cache.

### Rate Limit

WRITE

### Response

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

### Parameters

None

### Response

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

| Field | Type | Description |
|-------|------|-------------|
| `available` | boolean | Whether process isolation is available |
| `processes` | object | Map of extension names to process status |

## GET /api/extensions/os-isolation

Get OS-level isolation status (Phase D). Also includes process isolation information.

### Parameters

None

### Response

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

| Field | Type | Description |
|-------|------|-------------|
| `os_isolation` | object | OS-level isolation information |
| `config.enabled` | boolean | Whether OS isolation is enabled |
| `config.apparmor` | boolean | AppArmor (Linux) usage status |
| `config.macos_sandbox_exec` | boolean | macOS sandbox-exec usage status |
| `config.macos_user_isolation` | boolean | macOS user isolation usage status |
| `config.windows_restricted_token` | boolean | Windows restricted token usage status |
| `config.windows_job_object` | boolean | Windows Job Object usage status |
| `processes` | object | Process isolation status |

---

## Extension Authoring

APIs for creating and editing custom extensions. Based on the concession model, only the `extensions/custom-{name}/` directory is writable.

All endpoints are restricted to **localhost access only**.

### Security Constraints

- Extension name: lowercase alphanumeric and hyphens only (`[a-z0-9-]`), max 50 characters, `builtin-` prefix prohibited
- File types: whitelist only (`entrypoint`, `template`, `static_css`, `static_js`, `config`, `readme`)
- Binary files: completely prohibited
- File size limits: 10KB to 50KB depending on type

## POST /api/extensions/author/create

Create a new custom extension with scaffold files.

### Rate Limit

WRITE

### Access Restriction

Localhost only

### Request

```json
{
  "name": "my-tool",
  "description": "A useful tool extension"
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | string | Yes | Extension name (`[a-z0-9-]`, max 50 characters) |
| `description` | string | No | Extension description |

### Response

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

### Errors

- `400` — Invalid name or extension already exists
- `403` — Access from non-localhost

## POST /api/extensions/author/\<name\>/write

Write a file to a custom extension.

### Rate Limit

WRITE

### Access Restriction

Localhost only

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | string | Extension name (path parameter, without `custom-` prefix) |

### Request

```json
{
  "file_type": "entrypoint",
  "filename": "my_tool_ext",
  "content": "\"\"\"My tool extension.\"\"\"\n\nfrom quart import Blueprint\n..."
}
```

| Parameter | Type | Required | Description |
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

### Response

```json
{
  "ok": true,
  "file": "my_tool_ext.py",
  "size": 256
}
```

### Errors

- `400` — Validation error (invalid name, file type, size exceeded, binary detected)
- `403` — Access from non-localhost

## GET /api/extensions/author/\<name\>/read

Read a file from a custom extension.

### Access Restriction

Localhost only

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | string | Extension name (path parameter) |

### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_type` | string | Yes | File type |
| `filename` | string | Yes | Filename without extension |

### Response

```json
{
  "ok": true,
  "file": "my_tool_ext.py",
  "content": "\"\"\"My tool extension.\"\"\"\n...",
  "size": 256
}
```

### Errors

- `400` — Validation error
- `403` — Access from non-localhost

## GET /api/extensions/author/\<name\>/files

List all files in a custom extension.

### Access Restriction

Localhost only

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | string | Extension name (path parameter) |

### Response

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

### Errors

- `400` — Invalid extension name
- `403` — Access from non-localhost

## POST /api/extensions/author/\<name\>/validate

Validate a custom extension's extension.json and code. Runs CodeVerifier without registering the extension.

### Rate Limit

WRITE

### Access Restriction

Localhost only

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | string | Extension name (path parameter) |

### Response (Success)

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

### Response (Issues Found)

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

| Field | Type | Description |
|-------|------|-------------|
| `ok` | boolean | Whether all checks passed |
| `issues` | string[] | Manifest and code verification issues |
| `code_findings` | array | CodeVerifier findings |
| `manifest` | object | Parsed extension.json contents |

### Errors

- `400` — Invalid extension name or extension does not exist
- `403` — Access from non-localhost
