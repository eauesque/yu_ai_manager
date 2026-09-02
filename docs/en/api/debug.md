# Debug API

Internal APIs for debugging and diagnostics. Used for inspecting file metadata, checking model information, and managing scanned root directories.

These endpoints have no frontend UI and are primarily intended for development and troubleshooting.

## GET /api/debug/file-meta/<file_id>

Inspect detailed metadata for a file. Returns metadata stored in the DB, and for files inside ZIP archives, also returns freshly extracted results.

### Authentication

PIN session or API key

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `file_id` | int | File ID (path parameter) |

### Response

```json
{
  "id": 123,
  "path": "/images/sample.png",
  "meta_source": "a1111_png",
  "parser_version": 5,
  "format": "a1111",
  "model_name": "sd_xl_base_1.0",
  "raw_prompt_length": 256,
  "raw_prompt_preview": "masterpiece, best quality, ...",
  "raw_negative_preview": "lowres, bad anatomy, ...",
  "raw_meta_json_length": 1024,
  "raw_meta_json_preview": "{\"steps\": 20, ...}",
  "has_v4_prompt": false,
  "has_comment": true
}
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | File ID |
| `path` | string | File path |
| `meta_source` | string | Metadata source (`a1111_png`, `novelai_v4_png`, etc.) |
| `parser_version` | int | Parser version |
| `format` | string | Template format |
| `model_name` | string/null | Model name |
| `raw_prompt_length` | int | Character count of the raw prompt |
| `raw_prompt_preview` | string | First 300 characters of the raw prompt |
| `raw_negative_preview` | string | First 300 characters of the negative prompt |
| `raw_meta_json_length` | int | Character count of the raw metadata JSON |
| `raw_meta_json_preview` | string | First 500 characters of the raw metadata JSON |
| `has_v4_prompt` | bool | Whether it contains a NovelAI V4 prompt |
| `has_comment` | bool | Whether it contains a Comment field |

For files inside ZIP archives, a `fresh_extract` field is added with re-extraction results:

```json
{
  "fresh_extract": {
    "meta_source": "a1111_png",
    "format": "a1111",
    "raw_meta_json_length": 1024,
    "raw_meta_json_preview": "{...}",
    "has_v4_prompt": false,
    "success": true,
    "raw_prompt_preview": "masterpiece, ..."
  }
}
```

### Errors

| Status | Description |
|--------|-------------|
| 404 | File not found |

## GET /api/debug/model-check

Check the storage status of `model_name` in the templates table. Returns statistics and samples for records with and without model names.

### Authentication

PIN session or API key

### Parameters

None

### Response

```json
{
  "total_templates": 1000,
  "with_model_name": 850,
  "without_model_name": 150,
  "samples_with_model": [
    {
      "file_id": 1,
      "model_name": "sd_xl_base_1.0",
      "model_hash": "abc123",
      "format": "a1111"
    }
  ],
  "samples_without_model": [
    {
      "file_id": 42,
      "model_name": null,
      "format": "comfy",
      "raw_meta_json_preview": "{...}"
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `total_templates` | int | Total number of templates |
| `with_model_name` | int | Number of records with model name set |
| `without_model_name` | int | Number of records without model name |
| `samples_with_model` | array | Samples with model name (up to 10) |
| `samples_without_model` | array | Samples without model name (up to 5) |

## GET /api/scanned-roots

Extract root directories from files registered in the DB and return them with file counts. Aggregates both configured scan roots and roots of files that don't belong to any configured root.

### Authentication

PIN session or API key

### Parameters

None

### Response

```json
{
  "roots": [
    {
      "path": "C:\\Images\\AI",
      "count": 5000
    },
    {
      "path": "D:\\Archives",
      "count": 1200
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `roots` | array | Array of root directories (sorted by file count descending, max 50) |
| `roots[].path` | string | Directory path |
| `roots[].count` | int | Number of files under this path |

### Errors

| Status | Description |
|--------|-------------|
| 500 | Failed to compute roots summary |

## POST /api/debug/query

Execute a read-only SQL query. Requires the `YU_DEBUG_MODE=1` environment variable and only allows access from localhost.

### Rate Limit

WRITE

### Authentication

PIN session or API key (localhost only + `YU_DEBUG_MODE=1`)

### Request

```json
{
  "sql": "SELECT id, path, meta_source FROM files LIMIT 10",
  "limit": 100
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `sql` | string | Yes | SELECT statement to execute |
| `limit` | int | No | Maximum number of rows to return (default: 100, max: 10000) |

### Constraints

- Only SELECT statements are allowed (INSERT, UPDATE, DELETE, etc. are rejected)
- Multiple statements (semicolon-separated) are not allowed
- Queries containing write keywords (DROP, ALTER, CREATE, etc.) are rejected

### Response

```json
{
  "columns": ["id", "path", "meta_source"],
  "rows": [
    {"id": 1, "path": "/images/test.png", "meta_source": "a1111_png"}
  ],
  "row_count": 1,
  "truncated": false
}
```

| Field | Type | Description |
|-------|------|-------------|
| `columns` | string[] | Array of column names |
| `rows` | object[] | Result rows (each row is an object keyed by column name) |
| `row_count` | int | Number of rows returned |
| `truncated` | bool | `true` if results were truncated by the limit |

### Errors

| Status | Description |
|--------|-------------|
| 400 | Empty SQL, multiple statements, non-SELECT query, contains write operations, SQL syntax error |
| 403 | Debug mode not enabled, or access from non-localhost |

## POST /api/scanned-roots/purge

Permanently delete all file records under the specified path from the DB. Related records (tags, templates, etc.) are cascade-deleted. Unused tags are automatically pruned.

### Rate Limit

DESTRUCTIVE

### Authentication

PIN session or API key

### Request

```json
{
  "path": "C:\\Images\\OldFolder"
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `path` | string | Yes | Root path to purge. All files under this path will be deleted |

### Response

```json
{
  "purged": 150,
  "path": "C:\\Images\\OldFolder"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `purged` | int | Number of file records deleted |
| `path` | string | The specified path |

### Errors

| Status | Description |
|--------|-------------|
| 400 | Path not specified |
| 500 | Purge operation failed |
