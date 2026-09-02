# Ratings API

API for managing file ratings (1–5 star ratings): setting, retrieving, and viewing statistics.

## POST /api/ratings/set

Set a rating for a file. Specify `rating=0` to clear the rating.

**Rate limit**: WRITE

### Request

```json
{
  "file_id": 42,
  "rating": 5
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | File ID (positive integer) |
| `rating` | int | Yes | Rating value (0–5). 0 clears the rating |

### Response

```json
{
  "file_id": 42,
  "rating": 5
}
```

## POST /api/ratings/batch-set

Set ratings for multiple files at once.

**Rate limit**: WRITE

### Request

```json
{
  "items": [
    { "file_id": 1, "rating": 5 },
    { "file_id": 2, "rating": 3 }
  ]
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `items` | array | Yes | List of rating entries (max 500) |
| `items[].file_id` | int | Yes | File ID (positive integer) |
| `items[].rating` | int | Yes | Rating value (0–5) |

### Response

```json
{
  "total": 2,
  "succeeded": 2,
  "failed": 0,
  "errors": []
}
```

## GET /api/ratings/get

Get the rating for a file. Returns `rating: 0` if the file is unrated.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | File ID (query parameter) |

### Response

```json
{
  "file_id": 42,
  "rating": 5
}
```

> **Note**: Unrated files return `rating: 0`.

## POST /api/ratings/batch

Retrieve ratings for multiple files at once.

### Request

```json
{
  "file_ids": [1, 2, 3]
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_ids` | array | Yes | List of file IDs |

### Response

```json
{
  "ratings": {
    "1": 5,
    "3": 4
  }
}
```

> **Note**: Only rated files appear in the map. Unrated files are omitted from the response.

## GET /api/ratings/stats

Get rating statistics across all files.

### Parameters

None.

### Response

```json
{
  "total_rated": 1234,
  "distribution": {
    "1": 50,
    "2": 100,
    "3": 300,
    "4": 500,
    "5": 284
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `total_rated` | int | Total number of rated files |
| `distribution` | object | File count per rating value (1–5) |
