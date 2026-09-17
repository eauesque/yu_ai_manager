# Search API

APIs for file search, suggestions, and grouped display.

## GET /api/search

The main file search endpoint.

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `q` | string | `""` | Search query (text in prompts, tag names) |
| `sort` | string | `"date"` | Sort order: `date`, `name`, `size`, `rating`, `random` |
| `order` | string | `"desc"` | `asc` / `desc` |
| `offset` | int | `0` | Pagination start position |
| `limit` | int | `50` | Number of results (max 200) |
| `cursor` | string | - | Token for cursor-based pagination |
| `meta` | string | `"all"` | Metadata type: `all`, `a1111`, `nai`, `comfy`, `unknown` |
| `tags` | string | - | Tag filter (comma-separated) |
| `rating_min` | int | - | Minimum rating (0-5) |
| `rating_max` | int | - | Maximum rating (0-5) |
| `path` | string | - | Path prefix filter |
| `ext` | string | - | Extension filter (comma-separated, e.g., `png,webp`) |
| `has_prompt` | bool | - | Filter by prompt presence |
| `collection_id` | int | - | Search within a collection |
| `favorites_only` | bool | `false` | Favorites only |
| `group_by` | string | - | Grouping: `folder`, `conversation` |

### Response

```json
{
  "results": [
    {
      "id": 42,
      "path": "/images/output/00042.png",
      "filename": "00042.png",
      "size": 1234567,
      "mtime": 1709500000,
      "width": 1024,
      "height": 1536,
      "meta_type": "a1111_png",
      "model_name": "animagine-xl-3.1",
      "positive": "1girl, landscape, sunset",
      "negative": "low quality",
      "rating": 4,
      "is_favorite": true,
      "tags": ["landscape", "sunset"]
    }
  ],
  "total": 1500,
  "offset": 0,
  "limit": 50,
  "next_cursor": "eyJtdGltZSI6MTcwOTUwMDAwMCwiaWQiOjQyfQ=="
}
```

## GET /api/search-grouped

Search results grouped by folder/ZIP.

### Parameters

The same query parameters as `/api/search`, plus:

| Parameter | Type | Description |
|-----------|------|-------------|
| `group_limit` | int | Maximum number of items shown per group |

## GET /api/groups-index

Index of folder and ZIP container groups. Used for grouping search results.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `sort` | string | Sort order: `name`, `count`, `date` |
| `order` | string | `asc` / `desc` |
| `offset` | int | Pagination start position |
| `limit` | int | Number of results |

## GET /api/group-members

List of file IDs within a specified container.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `key` | string | Container key (folder path or ZIP path) |

## GET /api/suggest

Autocomplete for tags and prompts.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `q` | string | Input text |
| `limit` | int | Number of suggestions (default 10) |

### Response

```json
{
  "suggestions": [
    { "value": "1girl", "count": 5432 },
    { "value": "1boy", "count": 1234 }
  ]
}
```

## GET /api/suggest/lora

LoRA model name suggestions.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `q` | string | Input text |
| `limit` | int | Number of suggestions |

## GET /api/server-info

Basic server information.

### Response

```json
{
  "version": "4.12.1",
  "db_path": "/path/to/tags.db",
  "file_count": 150000,
  "tag_count": 8500,
  "auth_required": false,
  "lan_ip": "192.168.1.100",
  "active_ui": "default"
}
```
