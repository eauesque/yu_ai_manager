# Events API (SSE)

Real-time event delivery via Server-Sent Events.

## GET /api/events/stream

The main event stream. All pages share a single connection.

### Connecting

```javascript
// From a TypeScript module
import { sseSubscribe } from '../sse';
sseSubscribe('scan.complete', (data) => { ... });

// From a template inline script
window.sseSubscribe('scan.complete', (data) => { ... });
```

**Important**: Do not use `new EventSource()` directly. `window.EventSource` is overwritten by a Proxy, so direct usage causes errors.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `types` | string | Event types to subscribe to (comma-separated; omit for all events) |

### Connection Limits

- Up to 10 simultaneous connections per IP
- Visibility-aware: the connection enters a reduced state when the tab is hidden
- Automatic reconnection with exponential backoff

## Event Types

### Scan

| Event | Data | Description |
|-------|------|-------------|
| `scan.progress` | `{ scanned, total, current_file }` | Scan progress |
| `scan.complete` | `{ added_count, updated_count, added_ids?, updated_ids? }` | Scan complete |
| `config.scan_roots_changed` | `{}` | Scan root change notification |

### Favorites & Collections

| Event | Data | Description |
|-------|------|-------------|
| `favorite.add` | `{ file_id, collection_id }` | Favorite added |
| `favorite.remove` | `{ file_id, collection_id }` | Favorite removed |
| `collection.create` | `{ id, name }` | Collection created |
| `collection.delete` | `{ id }` | Collection deleted |

### AI Analysis & Tagging

| Event | Data | Description |
|-------|------|-------------|
| `semantic_index.start` | `{ total }` | CLIP indexing started |
| `semantic_index.progress` | `{ done, total }` | CLIP indexing progress |
| `semantic_index.complete` | `{ indexed }` | CLIP indexing complete |
| `vlm_caption.start` | `{ total }` | VLM captioning started |
| `vlm_caption.progress` | `{ done, total }` | VLM captioning progress |
| `vlm_caption.complete` | `{ processed }` | VLM captioning complete |
| `yolo_detect.start` | `{ total }` | YOLO detection started |
| `yolo_detect.progress` | `{ done, total }` | YOLO detection progress |
| `yolo_detect.complete` | `{ detected }` | YOLO detection complete |

### Freeze & Pull-back

| Event | Data | Description |
|-------|------|-------------|
| `fpb.start` | `{ job_id }` | Job started |
| `fpb.progress` | `{ job_id, frame, total }` | Frame progress |
| `fpb.complete` | `{ job_id, output_path }` | Job complete |
| `fpb.error` | `{ job_id, error }` | Job error |

### Chat Logs

| Event | Data | Description |
|-------|------|-------------|
| `chatlog_reprocess.start` | `{ total }` | AI reprocessing started |
| `chatlog_reprocess.progress` | `{ done, total }` | AI reprocessing progress |
| `chatlog_reprocess.complete` | `{ processed }` | AI reprocessing complete |
| `chatlog_reprocess.error` | `{ error }` | AI reprocessing error |

### Scheduler

| Event | Data | Description |
|-------|------|-------------|
| `scheduler.job_executed` | `{ job_id, result }` | Scheduled job completed successfully |
| `scheduler.job_error` | `{ job_id, error }` | Scheduled job failed |

## GET /api/logs/stream

A dedicated SSE stream for server logs. It operates independently from the main stream.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `level` | string | Minimum log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

### Events

| Event | Data | Description |
|-------|------|-------------|
| `log.entry` | `{ seq, ts, level, name, message }` | Log entry |

### Connection Limits

- Up to 3 simultaneous connections per IP (separate from the main stream)
- 15-second heartbeat interval (`: heartbeat\n\n`)
