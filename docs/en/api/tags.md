# Tags API

APIs for batch tag operations and tag suggestion/autocomplete.

## POST /api/tags/batch-set

Add or remove tags from multiple files in a single request.

### Rate Limit

WRITE (~120 req/min, burst 30)

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `items` | array | Yes | List of operations (max 500 items) |
| `items[].file_id` | int | Yes | File ID (positive integer) |
| `items[].add` | string[] | No | Tag names to add |
| `items[].remove` | string[] | No | Tag names to remove |

- Each item requires at least one of `add` or `remove`
- Tags that don't exist are auto-created (namespace=null)
- Tags added via API have their source set to `"user"`
- Orphan tags (no remaining file associations) are auto-deleted

### Request Example

```json
{
  "items": [
    {
      "file_id": 42,
      "add": ["landscape", "sunset"],
      "remove": ["lowres"]
    }
  ]
}
```

### Response

```json
{
  "total": 1,
  "succeeded": 1,
  "failed": 0,
  "errors": []
}
```

| Field | Type | Description |
|-------|------|-------------|
| `total` | int | Total number of items processed |
| `succeeded` | int | Number of successful operations |
| `failed` | int | Number of failed operations |
| `errors` | array | List of error details |

### Errors

| Status | Description |
|--------|-------------|
| 400 | Invalid request body (empty items, invalid file_id, both add/remove missing, etc.) |
| 429 | Rate limit exceeded |

---

## GET /api/tags/suggest

Return tag candidates matching a partial search string. Intended for autocomplete.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `q` | string | Yes | Search string |
| `limit` | int | No | Maximum number of results (default: 20, max: 100) |

- Search is case-insensitive (LIKE %q%)
- Results are sorted by `file_count` in descending order
- An empty `q` returns an empty array

### Response

```json
{
  "data": [
    { "id": 1, "tag": "landscape", "namespace": null, "file_count": 150 },
    { "id": 2, "tag": "1girl", "namespace": null, "file_count": 3420 }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `data[].id` | int | Tag ID |
| `data[].tag` | string | Tag name |
| `data[].namespace` | string\|null | Namespace (usually null) |
| `data[].file_count` | int | Number of files associated with this tag |
