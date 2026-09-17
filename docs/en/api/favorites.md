# Favorites API

API for adding, removing, checking, and listing favorites.

## POST /api/favorites/toggle

Toggle the favorite status of a file. Adds the file if not already favorited; removes it if already present.

- **Rate limit**: WRITE

### Request Body

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | Target file ID (positive integer) |
| `collection_id` | int | No | Collection ID (default: 1) |

```json
{
  "file_id": 42,
  "collection_id": 1
}
```

### Response

```json
{
  "file_id": 42,
  "collection_id": 1,
  "favorited": true
}
```

| Field | Type | Description |
|-------|------|-------------|
| `file_id` | int | Target file ID |
| `collection_id` | int | Collection ID |
| `favorited` | bool | State after toggle. `true` = added, `false` = removed |

## GET /api/favorites/check

Returns which of the specified file IDs are favorited.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `ids` | string | Yes | Comma-separated file IDs (e.g. `1,2,3`) |
| `collection_id` | int | No | Filter to a specific collection |

### Response

```json
{
  "favorites": [1, 3]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `favorites` | int[] | Array of file IDs that are favorited |

## GET /api/favorites/check_collections

Returns the collection IDs that contain the specified file.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | Target file ID |

### Response

```json
{
  "collections": [1, 3]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `collections` | int[] | Array of collection IDs containing this file |

## GET /api/favorites/list

Retrieves a list of favorited file IDs. Results are sorted by added date in descending order. Logically deleted files are excluded.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `collection_id` | int | No | Filter to a specific collection |

### Response

```json
{
  "ids": [42, 55, 67]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `ids` | int[] | Array of favorited file IDs (ordered by `added_at` DESC) |
