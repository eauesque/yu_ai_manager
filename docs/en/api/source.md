# Source Code Browsing API

A read-only API for browsing project source code.
It is designed so that MCP tools and external AI agents can safely view and search the codebase.

## Security Model

Three layers of defense ensure safety:

### 1. Path Normalization (Traversal Prevention)

- All paths are normalized with `os.path.realpath()` and verified against the project root via prefix matching.
- Traversal attacks such as `../../etc/passwd` or `../../../Windows/System32` are blocked.
- Null byte injection (`\x00`) is also detected and rejected.

### 2. Extension Whitelist

Allowed file extensions for reading:

| Category | Extensions |
|----------|-----------|
| Python | `.py` |
| TypeScript / JavaScript | `.ts`, `.js`, `.mjs`, `.tsx`, `.jsx` |
| Web | `.html`, `.css`, `.scss` |
| Configuration | `.json`, `.yaml`, `.yml`, `.toml`, `.cfg`, `.ini` |
| Documentation | `.md`, `.txt`, `.rst` |
| Scripts | `.sh`, `.bat`, `.cmd`, `.ps1` |
| Other | `.sql`, `.gitignore`, `.gitattributes`, `.editorconfig` |

The following extensionless files are specially permitted: `Dockerfile`, `Makefile`, `Procfile`, `VERSION`, `LICENSE`, `CHANGELOG`, `TODO`

### 3. Sensitive File Blocklist

Files matching the following patterns are rejected:

| Pattern | Reason |
|---------|--------|
| `config.json`, `config_*.json` | Authentication data such as PIN and API Key |
| `*.env`, `.env.*` | Environment variables (secrets) |
| `secret.salt`, `*.key`, `*.pem`, `*.cert` | Encryption keys and certificates |
| `credentials*`, `*token*`, `*secret*` | Authentication data |
| `*.db`, `*.sqlite*` | Database files |
| `pnpm-lock.yaml`, `package-lock.json`, etc. | Lock files (large) |
| Image, video, font, and model files | Binary files |

### Blocked Directories

`.git`, `__pycache__`, `node_modules`, `venv`, `dist`, `data`, `backups`, `screenshots`, `reports`, `src-tauri`

### Read Limits

| Item | Limit |
|------|-------|
| File size | 1 MB |
| Lines per read | 2,000 |
| Tree traversal depth | 6 |
| Search results | 50 |

---

## Endpoints

### GET /api/source/tree

Retrieve a directory tree.

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | string | `""` (root) | Relative path |
| `depth` | int | `3` | Traversal depth (1-6) |

#### Response

```json
{
  "ok": true,
  "root": ".",
  "depth": 3,
  "entries": [
    {
      "name": "core",
      "type": "dir",
      "path": "core",
      "children": [
        {
          "name": "source_core",
          "type": "dir",
          "path": "core/source_core",
          "children": [
            {
              "name": "source_browser.py",
              "type": "file",
              "path": "core/source_core/source_browser.py",
              "size": 8234
            }
          ]
        }
      ]
    },
    {
      "name": "web_ui.py",
      "type": "file",
      "path": "web_ui.py",
      "size": 3456
    }
  ]
}
```

- Directories appear first, followed by files (sorted by name).
- `size` is in bytes (files only).
- `children` is omitted once the traversal reaches the specified `depth`.

---

### GET /api/source/read

Read file contents with line numbers.

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | string | — (required) | Relative file path |
| `offset` | int | `0` | Starting line (0-based) |
| `limit` | int | `2000` | Maximum number of lines |

#### Response

```json
{
  "ok": true,
  "path": "core/source_core/source_browser.py",
  "total_lines": 250,
  "offset": 0,
  "limit": 2000,
  "content": "    1\t\"\"\"Source code browser...\n    2\t\n    3\timport os\n..."
}
```

- `content` uses `{line_number}\t{line_content}` format.
- Use `offset` + `limit` to paginate through long files.

#### Error Examples

```json
{
  "ok": false,
  "error": "This file is not eligible for reading"
}
```

```json
{
  "ok": false,
  "error": "Access outside the project root is prohibited"
}
```

---

### GET /api/source/search

Search within source code by text.

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `q` | string | — (required) | Search text (minimum 2 characters) |
| `glob` | string | `""` (all files) | Filename filter (e.g., `*.py`) |
| `limit` | int | `30` | Maximum number of results (1-50) |

#### Response

```json
{
  "ok": true,
  "query": "def source_tree",
  "glob": "*.py",
  "total": 2,
  "results": [
    {
      "file": "core/source_core/source_browser.py",
      "line": 120,
      "text": "def source_tree("
    },
    {
      "file": "routes/source_api.py",
      "line": 15,
      "text": "    result = source_tree(rel_path, depth_int)"
    }
  ]
}
```

- The search is case-insensitive.
- `text` is truncated to a maximum of 200 characters.

---

## MCP Tools

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `source_tree` | Display directory tree | `path`: str = '', `depth`: int = 3 |
| `source_read` | Read file contents | `path`: str (required), `offset`: int = 0, `limit`: int = 2000 |
| `source_search` | Search source code by text | `query`: str (required), `glob`: str = '', `limit`: int = 30 |

### Usage Examples with MCP

```
# View the project structure
source_tree(path="", depth=2)

# Read a specific file
source_read(path="core/source_core/source_browser.py")

# Search within the codebase
source_search(query="def register_blueprints", glob="*.py")
```

### Scope & Rate Limiting

- **Scope Fence**: Available in the `read_only` scope (permitted in all presets)
- **Budget Tracker**: `read` category (no rate limit)
- **HITL Gate**: Level 0 (no approval required)

---

## Implementation Files

| File | Role |
|------|------|
| `core/source_core/source_browser.py` | Security layer + business logic |
| `routes/source_api.py` | Flask API endpoints (Blueprint) |
| `mcp_server/source_tools.py` | MCP tool registration |
