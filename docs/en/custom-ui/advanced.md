# Advanced Guide -- SSE, Batch Operations, and Security

This guide covers advanced features and implementation patterns for custom UIs.

## Real-time Updates (SSE)

Server-Sent Events allow the UI to receive real-time notifications for scan progress, favorite changes, AI analysis progress, and more.

### Connecting

```javascript
// Use EventSource directly (this is safe in custom UIs)
const sse = new EventSource('/api/events/stream');

// Subscribe to events
sse.addEventListener('scan.progress', (e) => {
  const data = JSON.parse(e.data);
  console.log(`Scan: ${data.scanned}/${data.total}`);
});

sse.addEventListener('scan.complete', (e) => {
  const data = JSON.parse(e.data);
  console.log(`Scan done: ${data.added_count} added`);
  // Reload the grid
  reloadResults();
});
```

**Note**: The reference UI (`ui/default/`) overrides `window.EventSource` with a Proxy, so `new EventSource()` does not work there. This restriction does not apply to custom UIs, which can use EventSource directly.

### Key Events

| Event | Data | UI Usage |
|-------|------|----------|
| `scan.progress` | `{ scanned, total, current_file }` | Progress bar |
| `scan.complete` | `{ added_count, updated_count }` | Reload search results |
| `favorite.add` | `{ file_id, collection_id }` | Update favorite icon |
| `favorite.remove` | `{ file_id, collection_id }` | Update favorite icon |
| `collection.create` | `{ id, name }` | Update collection list |

See [events.md](../api/events.md) for all event types.

### Connection Management

```javascript
class SSEConnection {
  constructor() {
    this.handlers = new Map();
    this.connect();
  }

  connect() {
    this.sse = new EventSource('/api/events/stream');
    this.sse.onerror = () => {
      this.sse.close();
      // Reconnect with exponential backoff
      setTimeout(() => this.connect(), 3000);
    };
    // Re-register existing handlers
    for (const [type, handler] of this.handlers) {
      this.sse.addEventListener(type, handler);
    }
  }

  on(eventType, callback) {
    const handler = (e) => callback(JSON.parse(e.data));
    this.handlers.set(eventType, handler);
    this.sse.addEventListener(eventType, handler);
  }

  close() {
    this.sse.close();
  }
}

// Usage
const sse = new SSEConnection();
sse.on('scan.progress', (data) => updateProgressBar(data));
sse.on('scan.complete', () => reloadResults());
```

### Visibility-aware Connection

You can close the connection when the tab is hidden and reconnect when it becomes visible again, saving resources:

```javascript
document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    sse.close();
  } else {
    sse.connect();
  }
});
```

## Batch Operations

These API patterns execute operations on multiple files at once.

### Batch Rating

```javascript
async function batchRate(items) {
  // items: [{file_id: 1, rating: 5}, {file_id: 2, rating: 3}]
  // Maximum 500 items
  const res = await api('/api/ratings/batch-set', {
    method: 'POST',
    body: JSON.stringify({ items }),
  });
  return res;
}
```

### Batch Tag Operations

```javascript
async function batchSetTags(items) {
  // items: [{file_id: 1, add: ["good"], remove: ["bad"]}, ...]
  const res = await api('/api/tags/batch-set', {
    method: 'POST',
    body: JSON.stringify({ items }),
  });
  return res;
}
```

### Batch Collection Operations

```javascript
// Add to a collection
async function addToCollection(collectionId, fileIds) {
  return api(`/api/collections/${collectionId}/batch-add`, {
    method: 'POST',
    body: JSON.stringify({ file_ids: fileIds }),
  });
}

// Remove from a collection
async function removeFromCollection(collectionId, fileIds) {
  return api(`/api/collections/${collectionId}/batch-remove`, {
    method: 'POST',
    body: JSON.stringify({ file_ids: fileIds }),
  });
}
```

### Handling Partial Failures

Batch operations may partially succeed:

```javascript
const result = await batchRate(items);
if (result.failed && result.failed.length > 0) {
  console.warn(`${result.failed.length} items failed:`, result.failed);
  showToast(`${result.succeeded} succeeded, ${result.failed.length} failed`);
}
```

## Error Handling

### HTTP Status Codes

| Code | Meaning | Action |
|------|---------|--------|
| 200 | Success | -- |
| 304 | Not Modified | Use cache (thumbnails) |
| 400 | Bad Request | Verify input |
| 403 | Auth failure / Invalid CSRF | Check for `X-Requested-With` header |
| 404 | Resource not found | Verify file ID |
| 429 | Rate limited | Wait for the number of seconds in the `Retry-After` header |
| 500 | Server error | Retry or check logs |

### Rate Limit Handling

```javascript
async function apiWithRetry(path, options = {}, maxRetries = 3) {
  for (let i = 0; i < maxRetries; i++) {
    const res = await fetch(path, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
        ...options.headers,
      },
    });

    if (res.status === 429) {
      const retryAfter = parseInt(res.headers.get('Retry-After') || '5', 10);
      console.warn(`Rate limited, retry after ${retryAfter}s`);
      await new Promise(r => setTimeout(r, retryAfter * 1000));
      continue;
    }

    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: res.statusText }));
      throw new Error(err.error || `HTTP ${res.status}`);
    }

    return res.json();
  }
  throw new Error('Max retries exceeded');
}
```

### Response Format Detection

There are two response formats (legacy and current):

```javascript
function parseApiResponse(json) {
  // Current format: { ok, error, data }
  if ('ok' in json) {
    if (!json.ok) throw new Error(json.error || 'Unknown error');
    return json.data ?? json;
  }
  // Legacy format: { success, message }
  if ('success' in json) {
    if (!json.success) throw new Error(json.message || 'Unknown error');
    return json;
  }
  // Direct data format (results, etc.)
  return json;
}
```

## Security

### CSRF Protection

All write operations (POST / PUT / DELETE) require the `X-Requested-With` header:

```javascript
// Correct: includes the header
fetch('/api/ratings/set', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-Requested-With': 'XMLHttpRequest',
  },
  body: JSON.stringify({ file_id: 42, rating: 5 }),
});
```

**Exception**: API Key requests with an `Authorization: Bearer sk_...` header do not require the CSRF header.

### XSS Prevention

Sanitize user input and filenames before inserting them into the DOM:

```javascript
function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// Bad: insert filename directly
card.innerHTML = `<p>${file.filename}</p>`;  // XSS risk

// Better: escape first
card.innerHTML = `<p>${escapeHtml(file.filename)}</p>`;

// Best: use the DOM API
const p = document.createElement('p');
p.textContent = file.filename;  // Auto-escaped
card.appendChild(p);
```

### API Key Handling

Do not embed API Keys in client-side code when building a custom UI. Browser-based UIs should use PIN / session authentication, protected by CSRF headers.

## Search Implementation

### Basic Search

```javascript
async function search(query, options = {}) {
  const params = new URLSearchParams({
    q: query,
    limit: String(options.limit || 50),
    sort: options.sort || 'date',
  });

  if (options.cursor) params.set('cursor', options.cursor);
  if (options.minRating) params.set('rating_min', String(options.minRating));
  if (options.collection) params.set('collection_id', String(options.collection));
  if (options.favOnly) params.set('favorites_only', 'true');

  const res = await fetch(`/api/search?${params}`);
  return res.json();
}
```

### Autocomplete

```javascript
let debounceTimer;

function onSearchInput(e) {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(async () => {
    const q = e.target.value;
    if (q.length < 2) return;

    const res = await fetch(`/api/suggest?q=${encodeURIComponent(q)}&limit=10`);
    const { suggestions } = await res.json();
    showSuggestions(suggestions);  // [{value: "1girl", count: 5432}, ...]
  }, 200);
}
```

### Sort Options

```javascript
const SORT_OPTIONS = [
  { value: 'date', label: 'Date (New)' },
  { value: 'name', label: 'Name' },
  { value: 'size', label: 'Size' },
  { value: 'rating', label: 'Rating' },
  { value: 'random', label: 'Random' },
];
```

## Collection Management

```javascript
// List collections
async function getCollections() {
  const res = await fetch('/api/collections');
  return res.json();
}

// Create a collection
async function createCollection(name) {
  return api('/api/collections', {
    method: 'POST',
    body: JSON.stringify({ name }),
  });
}

// Search within a collection
async function searchInCollection(collectionId, query = '') {
  return search(query, { collection: collectionId });
}
```

## Prompt Conversion

Convert prompts between A1111 and NAI formats:

```javascript
async function convertPrompt(prompt, direction) {
  // direction: "a1111_to_nai" or "nai_to_a1111"
  const res = await api('/api/convert', {
    method: 'POST',
    body: JSON.stringify({ prompt, direction }),
  });
  return res.converted;
}
```

## Deployment

### Distributing a Custom UI

There are several ways to distribute a custom UI to other users:

1. **Git repository**: Push to GitHub, then install via the Settings UI
2. **ZIP archive**: Package files as a ZIP and share the download URL
3. **Manual placement**: Copy directly into a `ui/<name>/` directory

### Installation

Install through the "UI" tab on the Settings page, or via the API:

```bash
# Install with curl
curl -X POST http://localhost:5000/api/ui/install \
  -H "X-Requested-With: XMLHttpRequest" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://github.com/user/my-custom-ui.git"}'
```

### manifest.json Requirements

Include the following in the `manifest.json` of a distributed UI:

```json
{
  "name": "my-custom-ui",
  "version": "1.0.0",
  "description": "A beautiful custom UI for YU AI Manager",
  "author": "Your Name",
  "api_version": "1"
}
```

- `name` and `version` are required
- The `name` also becomes the installation directory name
- `"default"` is a reserved name and cannot be used
