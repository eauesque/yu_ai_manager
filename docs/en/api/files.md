# Files API

APIs for retrieving file details, thumbnails, and original media.

## GET /api/file/<id>

Retrieve detailed metadata for a file.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `id` | int | File ID (path parameter) |

### Response

```json
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
  "positive": "1girl, landscape",
  "negative": "low quality",
  "steps": 28,
  "sampler": "Euler a",
  "cfg_scale": 7.0,
  "seed": 1234567890,
  "rating": 4,
  "is_favorite": true,
  "tags": ["landscape"],
  "collections": [1, 3],
  "hash_md5": "abc123...",
  "hash_phash": "def456...",
  "analysis": { "description": "A scenic landscape..." }
}
```

## GET /api/thumbnail/<id>

Thumbnail image (WebP). Supports ETag caching.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `id` | int | File ID |
| `size` | int | Thumbnail size (default 300) |

### Response

- Content-Type: `image/webp`
- ETag / If-None-Match support (304 Not Modified)
- Cache: 24 hours

## GET /api/original/<id>

Stream the original file. Also supports files inside ZIP archives.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `id` | int | File ID |

### Response

- Content-Type: MIME type of the file
- Content-Disposition: `inline`
- Range request support (for video seeking)

## POST /api/convert

Prompt format conversion (A1111 <-> NAI).

### Request

```json
{
  "prompt": "1girl, (masterpiece:1.2)",
  "direction": "a1111_to_nai"
}
```

### Response

```json
{
  "converted": "1girl, {{masterpiece}}",
  "direction": "a1111_to_nai"
}
```

## GET /api/container-thumb-ids

List of thumbnail IDs for a container (folder/ZIP), excluding already-cached entries.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `keys` | string | Container keys (comma-separated) |
