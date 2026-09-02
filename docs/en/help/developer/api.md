# API Overview

YU AI Manager provides a REST API that allows you to perform all WebUI operations programmatically.
With over 320 endpoints, it covers a wide range of operations from image management to AI analysis.

> **Tip**: For detailed common conventions (authentication, CSRF, rate limiting, response format), see the "API Reference" section.
>
> **Important**: If you add or change endpoints, also read "API Security Guidelines".

## Authentication

Four authentication methods are supported.

| Method | Use Case | Header/Parameter |
|--------|----------|------------------|
| PIN Authentication | Browser sessions | Log in at `/_pin` -> session cookie |
| API Key | Machine-to-machine / MCP | `Authorization: Bearer sk_xxxx` |
| Trusted Proxy | Reverse proxy | `X-Remote-User` header |
| LAN Share Token | Guest access | `/s/<token>` path |

### Testing with curl

```bash
# API Key authentication (no CSRF header required)
curl -H "Authorization: Bearer sk_your_key" \
     http://localhost:5000/api/search?tags=1girl

# PIN authentication requires 2 steps
# 1. Obtain CSRF token
curl -c cookies.txt http://localhost:5000/_pin
# 2. Submit PIN
curl -b cookies.txt -X POST \
     -H "X-Requested-With: XMLHttpRequest" \
     -d "pin=1234" http://localhost:5000/_pin_check
```

### CSRF Protection

All POST/PUT/DELETE `/api/` endpoints require the `X-Requested-With` header.
This is not required for Bearer API Key requests.

## Key Endpoints

### Image Search & Viewing

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/search` | Filter search by tags, date, rating, etc. |
| GET | `/api/search-grouped` | Grouped search by folder/ZIP |
| GET | `/api/file/<id>` | Get detailed image metadata |
| GET | `/api/thumbnail/<id>` | Get thumbnail (WebP, ETag caching) |
| GET | `/api/original/<id>` | Get original image (Range request supported) |
| GET | `/api/suggest` | Tag autocomplete suggestions |

### Ratings, Tags & Annotations

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/ratings/batch-set` | Batch set ratings |
| POST | `/api/tags/batch-set` | Batch edit tags |
| POST | `/api/annotations/batch-set` | Batch set annotations |
| GET | `/api/annotations/<id>` | Get annotations |
| GET | `/api/annotations/search` | Search annotations |

### Collections

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/collections` | List collections |
| POST | `/api/collections` | Create collection |
| PUT | `/api/collections/<id>` | Rename collection |
| DELETE | `/api/collections/<id>` | Delete collection |
| POST | `/api/collections/<id>/batch-add` | Batch add files |
| POST | `/api/collections/<id>/batch-remove` | Batch remove files |

### Scanning

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/scan/start` | Start scan |
| GET | `/api/scan/status` | Get scan progress |
| POST | `/api/scan/cancel` | Cancel scan |
| POST | `/api/scan/resume` | Resume interrupted scan |
| GET | `/api/scan-roots` | List scan roots |
| POST | `/api/scan-roots` | Add scan root |

### AI Analysis

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/analysis/analyze/<id>` | Run AI image analysis |
| GET | `/api/analysis/result/<id>` | Get analysis result |
| POST | `/api/analysis/batch` | Batch analysis |
| POST | `/api/wd-tagger/tag/<id>` | WD-Tagger inference |
| POST | `/api/wd-tagger/batch` | WD-Tagger batch inference |
| POST | `/api/analysis/batch/cancel` | Cancel AI analysis batch |
| POST | `/api/wd-tagger/batch/cancel` | Cancel WD-Tagger batch |
| POST | `/api/tagger-servers/batch/cancel` | Cancel tagger cluster batch |
| POST | `/api/ocr/<id>` | Run OCR |

### Settings

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/settings/schema` | Get settings schema |
| GET | `/api/settings/all` | Get all settings |
| GET | `/api/settings/<key>` | Get setting value |
| PUT | `/api/settings/<key>` | Update setting value |

### Extension Management

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/extensions` | List extensions |
| POST | `/api/extensions/<name>/toggle` | Toggle enable/disable |
| POST | `/api/extensions/install` | Install from Git repository |
| DELETE | `/api/extensions/<name>/uninstall` | Uninstall |

### Agent Safety

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/agent/kill` | Activate Kill Switch |
| POST | `/api/agent/resume` | Release Kill Switch |
| GET | `/api/agent/status` | Safety mechanism status |
| GET | `/api/agent/journal` | Operation journal |
| POST | `/api/agent/undo/<journal_id>` | Undo operation |

## Response Format

All APIs respond with a unified JSON format.

```json
{
  "ok": true,
  "data": { ... },
  "error": null
}
```

On error:

```json
{
  "ok": false,
  "data": null,
  "error": "Error message"
}
```

## Rate Limiting

A 3-tier token bucket system is used.

| Tier | Target | Limit | Burst |
|------|--------|-------|-------|
| READ | All GET requests | Unlimited | - |
| WRITE | POST/PUT/DELETE | ~120 req/min | 30 |
| HEAVY | Similar search, AI analysis, scan | ~20 req/min | 5 |
| DESTRUCTIVE | purge, hard-delete, config writes | ~12 req/min | 3 |

When exceeded, HTTP 429 is returned. Check the `Retry-After` header for the retry wait time in seconds.

## SSE (Server-Sent Events)

Real-time events are delivered via SSE from `/api/events/stream`.
See the "SSE Events" section for details.

> **Note**: Maximum 10 concurrent connections per IP. Upload size limit is 100 MB.

## Internal Design Documentation

Detailed design rationale for the API, SQLite performance optimizations, DB schema design, and other development insights can be viewed in the [MD Viewer](/ext/md-viewer/).
