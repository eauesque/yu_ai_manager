# Scan API

APIs for file scanning and scan root management.

## Scan Control

### POST /api/scan/start

Start a scan.

### Request

```json
{
  "root_indices": [0, 1],
  "force": false
}
```

| Field | Type | Description |
|-------|------|-------------|
| `root_indices` | int[] | Indices of roots to scan (omit for all roots) |
| `force` | bool | Re-scan existing files |

### Response

```json
{
  "ok": true,
  "message": "Scan started"
}
```

### GET /api/scan/status

Retrieve scan progress.

### Response

```json
{
  "scanning": true,
  "progress": 45,
  "total": 1500,
  "current_file": "/images/output/00042.png",
  "errors": 0,
  "started_at": 1709500000
}
```

### POST /api/scan/cancel

Cancel a running scan.

### GET /api/scan/interrupted

Retrieve information about an interrupted scan.

### POST /api/scan/resume

Resume an interrupted scan.

### POST /api/scan/dismiss

Discard the interrupted scan state.

## Scan Worker CLI

Since v3.27.0, scans run in a separate process (worker).
The worker can be controlled directly from the CLI in addition to the WebUI API.

```bash
# Start a scan
python -m core.scan.scan_worker start --db ./tags.db --root /path/to/images [--scan-zips] [--force] [--resume]

# Stop a scan (SIGTERM -> graceful shutdown)
python -m core.scan.scan_worker stop

# Check status
python -m core.scan.scan_worker status
```

### IPC Files

| File | Content |
|------|---------|
| `/tmp/yu-scan/worker.pid` | Worker PID |
| `/tmp/yu-scan/progress.json` | Progress (JSON: running, phase, current, total, percent, message, detail, error) |

The WebUI polls this progress file and relays the data through `GET /api/scan/status` and SSE events (`scan.progress`, `scan.complete`).

## Scan Errors

### GET /api/scan-errors

List of errors that occurred during scanning.

| Parameter | Type | Description |
|-----------|------|-------------|
| `type` | string | Error type filter |
| `resolved` | bool | Resolved errors only |
| `limit` | int | Number of results |

### POST /api/scan-errors/<id>/resolve

Mark an error as resolved.

### POST /api/scan-errors/clear

Delete all resolved errors at once.

## Scan Root Management

### GET /api/scan-roots

List registered scan roots.

### Response

```json
{
  "roots": [
    {
      "path": "O:\\webui\\outputs",
      "enabled": true,
      "file_count": 15000
    }
  ]
}
```

### POST /api/scan-roots

Add a scan root.

```json
{
  "path": "O:\\webui\\outputs"
}
```

### PUT /api/scan-roots/<index>

Update a scan root (change path, toggle enabled/disabled).

### DELETE /api/scan-roots/<index>

Delete a scan root.

### POST /api/scan-roots/<idx>/toggle

Toggle a scan root enabled/disabled.

### POST /api/scan-roots/batch-toggle

Enable or disable all scan roots at once.

```json
{ "enabled": true }
```

### POST /api/scan-roots/reorder

Change the order of scan roots.

```json
{ "order": [2, 0, 1] }
```

`order` is an array of the existing indices in their new order.

### POST /api/scan-all

Background-scan all scan roots (equivalent to `POST /api/scan/start` with `root_indices` omitted).

## Scan Queue

Manage the scan waiting queue.

### GET /api/scan/queue

Return the list of items in the queue.

```json
{ "items": [...], "count": 3 }
```

### DELETE /api/scan/queue/<queue_id>

Remove a specific item from the queue.

### POST /api/scan/queue/clear

Clear the entire queue.

```json
{ "status": "cleared", "cleared": 3 }
```

## Scan History

### GET /api/scan/history

Return past scan run history in reverse chronological order (admin scope required).

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | int | 50 | Maximum number of results |

### POST /api/scan/history/clear

Delete all scan history.

## Scanned Roots (Debug)

### GET /api/scanned-roots

Return the list of root directories for files registered in the DB.

### POST /api/scanned-roots/purge

Permanently delete all file records under the specified path from the DB (irreversible).

```json
{ "path": "/old/images" }
```

## Hash Backfill

### POST /api/hash-backfill/start

Start background hash computation for existing files.

### GET /api/hash-backfill/status

Retrieve progress.

### POST /api/hash-backfill/cancel

Cancel the computation.

## Background Jobs

### GET /api/jobs/status

Status of all background jobs. Used for UI banner display.

```json
{
  "jobs": [
    {
      "type": "scan",
      "status": "running",
      "progress": 45,
      "total": 1500
    }
  ]
}
```
