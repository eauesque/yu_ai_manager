# Debugging Manual

A comprehensive guide for debugging YU AI Manager.
Intended for developers and AI agents to efficiently investigate and fix bugs.

---

## Table of Contents

1. [Starting the Server](#starting-the-server)
2. [Debug Logging](#debug-logging)
3. [Running Tests](#running-tests)
4. [DB Debugging](#db-debugging)
5. [Authentication Bypass and Testing](#authentication-bypass-and-testing)
6. [MCP Debugging](#mcp-debugging)
7. [Frontend Debugging](#frontend-debugging)
8. [Environment Variables](#environment-variables)
9. [Common Errors and Solutions](#common-errors-and-solutions)
10. [Performance Debugging](#performance-debugging)

---

## Starting the Server

### Development Mode (Recommended)

Start without PIN authentication for local debugging:

```bash
source venv/Scripts/activate  # Windows Git Bash
python web_ui.py --db ./tags.db --config config_test.json --port 5100
```

If `config_test.json` doesn't exist, create it with:

```json
{
  "scan_roots": [],
  "server": {
    "host": "127.0.0.1",
    "port": 5100,
    "lan": false
  },
  "extract_a1111": true,
  "extract_comfyui": true,
  "lowercase_tags": true,
  "compute_hash": false,
  "enable_fts": true,
  "extensions": {}
}
```

### Production-Like (LAN Exposed)

```bash
python web_ui.py --db ./tags.db --host 0.0.0.0 --port 5000 --pin 1234
```

> **Note**: PIN is required when binding to `0.0.0.0`. Since v4.8.1, `--debug` flag is ignored when LAN-exposed (prevents stack trace leakage).

### Port Selection

5100 → 5200 → 5300 → incrementing by 100. Check before starting:

```bash
# Windows
netstat -ano | grep :5100

# Linux/macOS
ss -tlnp | grep :5100
```

### CLI Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--db` | path | `data/tags.db` | SQLite DB file path |
| `--config` | path | `config.json` | Configuration file path |
| `--host` | str | `127.0.0.1` | Bind address |
| `--port` | int | 5000 | Bind port |
| `--lan` | flag | - | Bind to `0.0.0.0` (LAN access) |
| `--pin` | str | - | Enable PIN authentication |
| `--debug` | flag | - | Enable Quart debug mode |
| `--debug-log` | `on`/`off` | - | Enable/disable structured debug logging |
| `--debug-log-file` | path | `logs/debug.log` | Log file output path |
| `--debug-log-max-mb` | int | 10 | Log rotation size (MB) |
| `--debug-log-backups` | int | 5 | Log backup generations |
| `--debug-log-stdout` | `on`/`off` | `on` | Also output to stderr |
| `--allow-restart` | flag | - | Enable `/api/server/restart` |
| `--trusted-proxy-auth` | flag | - | Enable Trusted Proxy auth |
| `--profile` | str | - | Startup profile name |

### launch-args.txt

Place a `launch-args.txt` in the project root to auto-load arguments at startup. CLI arguments take precedence.

---

## Debug Logging

### Enabling

```bash
# Via CLI
python web_ui.py --db ./tags.db --debug-log on

# Via environment variable
export TAGDB_DEBUG=1
python web_ui.py --db ./tags.db
```

### Log Format

Structured debug logs via `dlog()` function (`core/infra_core/debug_log.py`):

```
[DEBUG] 2026-03-15 12:34:56 | scan:prepare | counting_start | root=/path/to/dir, recursive=True
```

Format: `[DEBUG] timestamp | source | event_name | key=value, ...`

### Real-time Monitoring

```bash
# Tail the log file
tail -f logs/debug.log

# Via API
curl http://127.0.0.1:5100/api/debug/logs

# SSE streaming
curl -N "http://127.0.0.1:5100/api/debug/logs?stream=1"
```

### Log Ring Buffer

Running logs are also stored in an in-memory ring buffer (max 1000 entries). Lost on server restart; use file logging for persistence.

---

## Running Tests

### Unit Tests

```bash
source venv/Scripts/activate

# Run all tests
python -m pytest tests/test_basic.py -v

# Specific test only
python -m pytest tests/test_basic.py::TestImports -v

# Stop on first failure
python -m pytest tests/test_basic.py -x
```

### API Integration Tests

```bash
python -m pytest tests/api/ -v
```

### Playwright Browser Tests

```bash
# 1. Start test server
python web_ui.py --db ./tags.db --config config_test.json --port 5100 &

# 2. Run tests
TARGET_URL=http://localhost:5100 python -m pytest tests/test_webui_browser.py -v
```

### Test Output

- Screenshots: `screenshots/`
- Reports: `reports/`

---

## DB Debugging

### Check Schema Version

```bash
python -c "
import sqlite3
con = sqlite3.connect('data/tags.db')
v = con.execute('SELECT MAX(version) FROM schema_version').fetchone()[0]
print(f'Schema version: {v}')
"
```

### Health Check

```bash
python db_health.py --db ./tags.db
```

### Debug SQL Execution

Available only when `YU_DEBUG_MODE=1`:

```bash
curl -X POST http://127.0.0.1:5100/api/debug/query \
  -H "Content-Type: application/json" \
  -H "X-Requested-With: XMLHttpRequest" \
  -d '{"sql":"SELECT COUNT(*) as cnt FROM files WHERE is_deleted=0"}'
```

> **Note**: Since v4.8.1, only SELECT statements are allowed.

### Useful Investigation Queries

```sql
-- File count by source
SELECT meta_source, COUNT(*) as cnt FROM files WHERE is_deleted=0 GROUP BY meta_source;

-- Model usage ranking
SELECT model_name, COUNT(*) as cnt FROM templates GROUP BY model_name ORDER BY cnt DESC LIMIT 20;

-- Orphan tags
SELECT t.id, t.name FROM tags t LEFT JOIN file_tags ft ON t.id=ft.tag_id WHERE ft.tag_id IS NULL;

-- Duplicate path detection
SELECT path, COUNT(*) as cnt FROM files GROUP BY path HAVING cnt > 1;
```

### DB Connection Rules

| Function | Purpose | When to Use |
|----------|---------|-------------|
| `get_readonly_db()` | Read-only | GET APIs, search, thumbnails, stats |
| `get_db()` | Read-write (Row factory) | POST/PUT/DELETE APIs |
| `get_raw_db()` | Read-write (no Row factory) | Batch processing, scans, migrations |

> **Important**: Using `get_db()` in read-only APIs causes write-lock contention during scans, blocking the viewer for seconds. Always use `get_readonly_db()`.

---

## Authentication Bypass and Testing

### Skip PIN Authentication

Start with `config_test.json` (no PIN configured) to skip all authentication.

### API Key Testing

```bash
# Bearer token request (no CSRF header needed)
curl -H "Authorization: Bearer sk_xxxxxxxxxxxxxx" \
  http://127.0.0.1:5000/api/stats/all
```

### API Key Scopes

Since v4.8.1, keys without scopes are **read-only** by default.

| Scope | Allowed Operations |
|-------|-------------------|
| `read` | Search, file detail, thumbnails, stats |
| `rate` | Rating set/get/batch |
| `tag.write` | Tag add/remove |
| `collection.write` | Collection CRUD, favorites |
| `annotate` | Annotation read/write |
| `scan` | Scan start/cancel/resume |
| `admin` | API key management, settings, backup/restore |

### Auth Chain Order

```
static → /s/ (LAN Share) → /_pin → API Key Bearer
→ QuickLock → Trusted Proxy → session → cookie → PIN page
```

---

## MCP Debugging

### Start MCP Server

```bash
source venv/Scripts/activate
python -m mcp_server
```

### Enable Debug Tools

```bash
export YU_DEBUG_MODE=1
export YU_BASE_URL=http://127.0.0.1:5100
export YU_API_KEY=sk_...
python -m mcp_server
```

### Debug Tools (9 tools, YU_DEBUG_MODE=1)

| Tool | Purpose |
|------|---------|
| `debug_health_check` | Server, DB, and table health check |
| `debug_validate_counts` | API stats vs DB actual count comparison |
| `debug_validate_search` | Search API regression check |
| `debug_validate_collection` | Collection count consistency |
| `debug_validate_annotations` | Annotation table integrity |
| `debug_sample_files` | Random sampling field analysis |
| `debug_roundtrip_test` | Annotation/rating/tag round-trip test |
| `debug_readonly_query` | Execute arbitrary SELECT queries |
| `debug_full_report` | Combined report of tools 1-5 |

### Import Check

```bash
python -c "from mcp_server.server import mcp; print('OK')"
```

---

## Extension Security Scan

YU AI Manager has a built-in code scanning feature for Extensions. The scan **runs automatically when an Extension is loaded**, so after adding or modifying an Extension, restart the server to trigger the scan.

### How Automatic Scanning Works

The following checks run sequentially when an Extension is loaded:

```
1. ManifestAuthority.review()   — Manifest review (format, permission validity)
2. CodeVerifier.verify()        — AST static analysis (code scan of all .py files)
3. User consent check           — Permission approval/denial
4. Capability Token issuance    — Execution permission token
```

### What CodeVerifier Detects

| Category | Target | Severity |
|----------|--------|----------|
| Dangerous modules | `subprocess`, `ctypes`, `importlib` | block |
| Direct DB access | `import sqlite3` (should use SandboxedDB) | block |
| Network | `requests`, `urllib`, `httpx`, `aiohttp`, `socket` | warn |
| Dynamic code execution | `eval()`, `exec()`, `__import__()`, `compile()` | block |

Extensions are rejected from loading when `block` severity findings are detected.

### How to Run the Scan

**Normal flow (recommended):**

Restart the server after adding or modifying an Extension. The scan runs automatically during loading, and results are output to the log.

```bash
# Restart server to reload Extensions (scan runs automatically)
python web_ui.py --db ./tags.db --config config_test.json --port 5100
```

**Manual scan only:**

```python
from pathlib import Path
from core.extensions_core.validation.code_verifier import CodeVerifier

result = CodeVerifier().verify(Path("extensions/my-extension"))

# Check results
for finding in result.findings:
    print(f"[{finding.severity}] {finding.file}:{finding.line} - {finding.message}")

print(f"Approved: {result.approved}")
```

### Trust Levels

Extensions are classified into 3 trust levels:

| Level | Condition | Restrictions |
|-------|-----------|-------------|
| L0 Trusted | `builtin-` prefix | No restrictions |
| L1 Verified | Signature verified | Declared permissions only |
| L2 Untrusted | Manually installed | Declared permissions + user consent required |

### Runtime Protection

Protection continues at runtime after loading:

- **Import Guard**: Blocks unauthorized module imports via `sys.meta_path`
- **Integrity Monitor**: Compares SHA-256 hashes every 5 minutes to detect file tampering
- **Token auto-revocation**: Revokes Capability Token on violation detection, stopping execution

### Related Documents

| Document | Location |
|----------|----------|
| Trias Politica Security Model | `docs/development/development_docs/EXTENSION_TRIAS_POLITICA_SPEC.md` |
| Sandbox Spec | `docs/development/development_docs/EXTENSION_SANDBOX_SPEC.md` |
| Hook Spec | `docs/development/development_docs/EXTENSION_HOOKS_SPEC.md` |

---

## Frontend Debugging

### TypeScript Build

```bash
pnpm run build        # esbuild bundle
pnpm run typecheck    # tsc --noEmit (type check only)
```

Output: `ui/default/static/dist/` (gitignored)

### CSRF Interceptor

`src/ts/nav/csrf-fetch.ts` wraps global `fetch` with a Proxy that auto-injects `X-Requested-With` headers on all POST/PUT/DELETE requests.

### SSE Shared Engine

`window.EventSource` is overridden by a Proxy. Direct `new EventSource()` throws an error.

```javascript
// Correct
window.sseSubscribe('scan.progress', (d) => console.log(d.data));

// Wrong (runtime error)
// new EventSource('/api/events/...')
```

### i18n Debugging

```javascript
window.setLang('en');
console.log(window.tr('search.count.normal', { count: 5 }));
```

---

## Environment Variables

### Debug / Logging

| Variable | Values | Default | Description |
|----------|--------|---------|-------------|
| `TAGDB_DEBUG` | `1`/`0` | `0` | Enable structured debug logging |
| `TAGDB_DEBUG_LOG` | path | `logs/debug.log` | Log file path |
| `TAGDB_DEBUG_LOG_MAX_MB` | int | `10` | Log rotation size (MB) |
| `TAGDB_DEBUG_LOG_BACKUPS` | int | `5` | Backup generations |
| `TAGDB_DEBUG_STDOUT` | `1`/`0` | `1` | Output to stderr |

### Server

| Variable | Values | Description |
|----------|--------|-------------|
| `TAGDB_DB` | path | DB file path |
| `TAGDB_CONFIG` | path | config.json path |
| `TAGDB_PROFILE` | str | Startup profile name |
| `TAGDB_ALLOW_RESTART` | `1`/`0` | Enable restart API |

### MCP

| Variable | Values | Description |
|----------|--------|-------------|
| `YU_DEBUG_MODE` | `1` | Register 9 debug tools |
| `YU_BASE_URL` | URL | MCP client base URL |
| `YU_API_KEY` | `sk_...` | MCP client API key |

---

## Common Errors and Solutions

### Server Startup

| Error | Cause | Fix |
|-------|-------|-----|
| `Address already in use` | Port occupied | Use `--port 5200` |
| `database is locked` | DB lock contention | Ensure DB is on local disk |
| `--pin is required` | LAN bind without PIN | Add `--pin <digit>` |
| `ModuleNotFoundError` | venv not activated | `source venv/Scripts/activate && uv pip install -r requirements.txt` |

### Authentication

| Error | Cause | Fix |
|-------|-------|-----|
| PIN page loops | Cookie issue | Check cookies in DevTools |
| `CSRF header missing` (403) | Missing `X-Requested-With` | Add header to fetch requests |
| API Key rejected | Insufficient scopes | Assign required scopes (v4.8.1+) |

### Windows-Specific

| Error | Cause | Fix |
|-------|-------|-----|
| `UnicodeEncodeError` on print | cp932 encoding | Use ASCII-safe characters |
| `pkill` doesn't work | Git Bash limitation | Use `taskkill //F //PID <pid>` |

---

## Performance Debugging

### Viewer Blocking During Scan

**Symptom**: Images stop loading for 5-10 seconds during scan

**Cause**: Read-only APIs using `get_db()` (write-capable connection)

**Fix**: Use `get_readonly_db()` for all read-only APIs

### Rate Limiting

| Tier | Target | Limit |
|------|--------|-------|
| **HEAVY** | Similarity search, hash, AI analysis, scan | ~20 req/min (burst 5) |
| **DESTRUCTIVE** | purge, hard-delete, cache clear | ~12 req/min (burst 3) |
| **WRITE** | Other POST/PUT/DELETE | ~120 req/min (burst 30) |
| GET | Read | Unlimited |

Check `Retry-After` header when receiving 429 responses.

---

## Related Documents

| Document | Location |
|----------|----------|
| DB Read/Write Separation | `docs/development/development_docs/SQLITE_READONLY_SEPARATION.md` |
| Error Format Standard | `docs/development/development_docs/ERROR_HANDLING.md` |
| Cross-Platform Issues | `docs/development/development_docs/CROSS_PLATFORM_ISSUES.md` |
| MCP Debug Tools Spec | `docs/development/development_docs/MCP_DEBUG_TOOLS.md` |
| Quart Migration Log | `docs/development/development_docs/QUART_MIGRATION_DEVLOG.md` |
| QA Handoff | `docs/development/development_docs/QA_HANDOFF.md` |
| Security Checklist | `/security-check` skill |
