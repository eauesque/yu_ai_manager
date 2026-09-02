# Collections API

APIs for managing collections (favorite groups).

## GET /api/collections

List all collections. Sorted by `sort_order` ASC, then `id` ASC.

### Parameters

None

### Response

```json
{
  "collections": [
    {
      "id": 1,
      "name": "Favorites",
      "sort_order": 0,
      "created_at": 1709500000,
      "count": 42,
      "is_smart": false,
      "query_json": null
    }
  ]
}
```

## POST /api/collections

Create a new collection.

### Rate Limit

WRITE

### Request

```json
{
  "name": "My Collection",
  "query_json": null
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | string | Yes | Collection name |
| `query_json` | object/null | No | Query for smart collections. Omit for regular collections |

### Response (201)

```json
{
  "id": 2,
  "name": "My Collection",
  "is_smart": false
}
```

## PUT /api/collections/<id>

Rename a collection.

### Rate Limit

WRITE

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `id` | int | Collection ID (path parameter) |

### Request

```json
{
  "name": "Renamed Collection"
}
```

### Response

```json
{
  "id": 2,
  "name": "Renamed Collection"
}
```

## DELETE /api/collections/<id>

Delete a collection. All favorite entries in the collection are also deleted.

The default collection (`id=1`) cannot be deleted.

### Rate Limit

WRITE

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `id` | int | Collection ID (path parameter) |

### Response

```json
{
  "deleted": 2
}
```

## POST /api/collections/reorder

Change the display order of collections.

### Rate Limit

WRITE

### Request

```json
{
  "ids": [3, 1, 2]
}
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `ids` | int[] | Array of collection IDs. The specified order becomes the new sort order |

### Response

```json
{
  "ok": true
}
```

## POST /api/collections/<id>/batch-add

Add files to a collection in bulk. Idempotent: entries that already exist are skipped and counted as successes.

### Rate Limit

WRITE

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `id` | int | Collection ID (path parameter) |

### Request

```json
{
  "file_ids": [1, 2, 3]
}
```

| Parameter | Type | Limit | Description |
|-----------|------|-------|-------------|
| `file_ids` | int[] | Max 500 | Array of file IDs to add |

### Response

```json
{
  "total": 3,
  "succeeded": 3,
  "failed": 0,
  "errors": []
}
```

## POST /api/collections/<id>/batch-remove

Remove files from a collection in bulk.

### Rate Limit

WRITE

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `id` | int | Collection ID (path parameter) |

### Request

```json
{
  "file_ids": [1, 2]
}
```

| Parameter | Type | Limit | Description |
|-----------|------|-------|-------------|
| `file_ids` | int[] | Max 500 | Array of file IDs to remove |

### Response

```json
{
  "total": 2,
  "succeeded": 2,
  "failed": 0,
  "errors": []
}
```

## GET /api/collections/<id>/export/csv

Export files in a collection as CSV.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `id` | int | Collection ID (path parameter) |

### Response

- Content-Type: `text/csv; charset=utf-8`
- CSV columns: `id`, `filename`, `folder`, `path`, `meta_source`, `mtime`, `positive`, `negative`
- Returns 404 if collection not found
