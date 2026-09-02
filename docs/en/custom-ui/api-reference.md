# API Reference -- Links and Quick Reference for Custom UI Developers

This page collects links to API documentation along with a quick-reference table of frequently used APIs.

## Documentation Index

### Common Conventions

- [API Common Conventions](../api/README.md) -- Base URL, authentication (4 methods), CSRF protection, rate limiting, response format, pagination

### By Endpoint

- [Search API](../api/search.md) -- GET /api/search, suggestions, groups, server-info
- [Files API](../api/files.md) -- File details, thumbnails, originals, prompt conversion
- [Scan API](../api/scan.md) -- Scan control, scan root management, hash backfill
- [Events API](../api/events.md) -- SSE real-time events, log stream

### Theming

- [CSS Variable List](../api/theming.md) -- Theme custom properties (Light/Dark)

## Quick Reference

### Read Operations (GET, no auth required*)

| Endpoint | Purpose | Key Parameters |
|----------|---------|----------------|
| `/api/search` | File search | `q`, `sort`, `limit`, `cursor`, `rating_min`, `collection_id` |
| `/api/thumbnail/<id>` | Thumbnail image (WebP) | `size` (default 300) |
| `/api/original/<id>` | Original file | Range supported |
| `/api/file/<id>` | File details | -- |
| `/api/suggest` | Tag suggestions | `q`, `limit` |
| `/api/stats/all` | Statistics | -- |
| `/api/collections` | Collection list | -- |
| `/api/server-info` | Server information | -- |
| `/api/events/stream` | SSE stream | `types` |

*Applies in PIN-free environments or with an authenticated session

### Write Operations (POST, `X-Requested-With` header required)

| Endpoint | Purpose | Body Example |
|----------|---------|--------------|
| `/api/ratings/set` | Set rating | `{file_id: 42, rating: 5}` |
| `/api/ratings/batch-set` | Batch rating | `{items: [{file_id, rating}, ...]}` |
| `/api/favorites/add` | Add to favorites | `{file_id: 42}` |
| `/api/favorites/remove` | Remove from favorites | `{file_id: 42}` |
| `/api/tags/batch-set` | Batch tag operations | `{items: [{file_id, add: [], remove: []}]}` |
| `/api/collections` | Create collection | `{name: "My Collection"}` |
| `/api/collections/<id>/batch-add` | Add to collection | `{file_ids: [1, 2, 3]}` |
| `/api/scan-all` | Start scan | `{}` |
| `/api/convert` | Prompt conversion | `{prompt, direction}` |

### UI Management

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/ui/list` | GET | List UIs |
| `/api/ui/switch` | POST | Switch UI |
| `/api/ui/install` | POST | Install UI (localhost only) |
| `/api/ui/<name>/uninstall` | DELETE | Uninstall UI (localhost only) |

## Response Formats

### Search Results

```javascript
{
  results: [
    {
      id: 42,
      path: "/images/00042.png",
      filename: "00042.png",
      width: 1024,
      height: 1536,
      meta_type: "a1111_png",   // a1111_png, novelai_v4_png, comfy_png, unknown
      model_name: "animagine-xl-3.1",
      positive: "1girl, landscape",
      rating: 4,                 // 0-5 (0 = unrated)
      is_favorite: true,
      tags: ["landscape", "sunset"]
    }
  ],
  total: 1500,
  next_cursor: "base64token..."  // null = last page
}
```

### Thumbnails

```
GET /api/thumbnail/42
→ Content-Type: image/webp
→ ETag: "abc123"
→ Cache-Control: max-age=86400
```

The browser caches thumbnails automatically. You can reference them directly in `<img>` tags:

```html
<img src="/api/thumbnail/42" loading="lazy" alt="thumbnail">
```

### Error Responses

```javascript
{
  ok: false,
  error: "Rate limit exceeded",
  code: "RATE_LIMIT",      // optional
  detail: "Retry after 5s"  // optional
}
```

## CSRF Header Notes

```javascript
// Common header helper
const API_HEADERS = {
  'Content-Type': 'application/json',
  'X-Requested-With': 'XMLHttpRequest',
};

// GET: no headers needed
fetch('/api/search?q=test');

// POST: X-Requested-With required
fetch('/api/ratings/set', {
  method: 'POST',
  headers: API_HEADERS,
  body: JSON.stringify({ file_id: 42, rating: 5 }),
});
```
