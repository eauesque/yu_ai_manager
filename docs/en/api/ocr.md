# OCR API

API for text extraction (OCR) from images, videos, and PDFs, along with translation, overlay image generation, export, benchmarking, and engine management.

## POST /api/ocr/<file_id>

Execute OCR on a single file and save the result to the database.

### Rate Limit

WRITE

### Request

```json
{
  "task": "ocr",
  "language": "auto",
  "server_id": ""
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | File ID (path parameter) |
| `task` | string | No | OCR task type. One of `ocr` / `ocr_document` / `ocr_manga`. Default: `ocr` |
| `language` | string | No | Language hint. Default: `auto` |
| `server_id` | string | No | Analysis server ID to use. Auto-selected if omitted |

### Response (200)

```json
{
  "file_id": 42,
  "engine": "gemini-2.0-flash",
  "task": "ocr",
  "full_text": "Extracted text...",
  "language": "ja",
  "regions_count": 3,
  "row_id": 1
}
```

### Errors

- `400` — Invalid task value
- `404` — File not found
- `500` — Failed to resolve OCR engine / OCR execution error

---

## GET /api/ocr/result/<file_id>

Retrieve a saved OCR result.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | File ID (path parameter) |
| `task` | string | No | Filter by task type |
| `engine` | string | No | Filter by engine name |
| `all` | string | No | If set to any value, returns all results |

### Response (result found)

```json
{
  "file_id": 42,
  "task": "ocr",
  "engine": "gemini-2.0-flash",
  "full_text": "Extracted text...",
  "language": "ja",
  "regions": [...]
}
```

### Response (with `?all=1`)

```json
{
  "file_id": 42,
  "results": [
    { "task": "ocr", "engine": "gemini-2.0-flash", "full_text": "..." },
    { "task": "ocr_manga", "engine": "manga-ocr", "full_text": "..." }
  ]
}
```

### Response (no result)

```json
{
  "status": "not_found"
}
```

---

## DELETE /api/ocr/result/<file_id>

Delete saved OCR results.

### Rate Limit

WRITE

### Request

```json
{
  "task": "",
  "engine": ""
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | File ID (path parameter) |
| `task` | string | No | Filter by task type. Empty string targets all tasks |
| `engine` | string | No | Filter by engine name. Empty string targets all engines |

### Response

```json
{
  "deleted": 2
}
```

---

## POST /api/ocr/batch

Execute OCR on multiple files in batch.

### Rate Limit

WRITE

### Request

```json
{
  "file_ids": [1, 2, 3],
  "task": "ocr",
  "language": "auto",
  "server_id": ""
}
```

| Parameter | Type | Required | Limit | Description |
|-----------|------|----------|-------|-------------|
| `file_ids` | int[] | Yes | Max 500 | Array of target file IDs |
| `task` | string | No | — | OCR task type. `ocr` / `ocr_document` / `ocr_manga`. Default: `ocr` |
| `language` | string | No | — | Language hint. Default: `auto` |
| `server_id` | string | No | — | Analysis server ID to use |

### Response (200)

```json
{
  "processed": 2,
  "errors": 1,
  "results": [
    { "file_id": 1, "full_text_length": 128, "regions_count": 3 },
    { "file_id": 2, "full_text_length": 256, "regions_count": 5 }
  ],
  "error_details": [
    { "file_id": 3, "error": "File not found" }
  ]
}
```

### Errors

- `400` — `file_ids` is empty / exceeds 500 / invalid task value
- `500` — Failed to resolve OCR engine

---

## POST /api/ocr/video/<file_id>

Extract keyframes from a video file and run OCR on each frame.

### Rate Limit

WRITE

### Request

```json
{
  "task": "ocr",
  "language": "auto",
  "server_id": "",
  "keyframe_count": 4,
  "strategy": "uniform"
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | File ID (path parameter) |
| `task` | string | No | OCR task type. Default: `ocr` |
| `language` | string | No | Language hint. Default: `auto` |
| `server_id` | string | No | Analysis server ID to use |
| `keyframe_count` | int | No | Number of keyframes to extract. Range: 1-16. Default: `4` |
| `strategy` | string | No | Keyframe extraction strategy. Default: `uniform` |

### Response (200)

```json
{
  "file_id": 42,
  "engine": "gemini-2.0-flash",
  "task": "ocr",
  "full_text": "Text extracted from frames...",
  "frame_count": 4,
  "row_id": 5
}
```

### Errors

- `400` — File is not a video
- `404` — File not found
- `500` — Failed to resolve OCR engine / Video OCR execution error

---

## POST /api/ocr/pdf/<file_id>

Convert PDF pages to images and run OCR. Useful for scanned PDFs without a text layer.

### Rate Limit

WRITE

### Request

```json
{
  "task": "ocr_document",
  "language": "auto",
  "server_id": "",
  "page_range": "",
  "dpi": 200
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | File ID (path parameter) |
| `task` | string | No | OCR task type. Default: `ocr_document` |
| `language` | string | No | Language hint. Default: `auto` |
| `server_id` | string | No | Analysis server ID to use |
| `page_range` | string | No | Page range (e.g., `"1-5"`, `"1,3,5"`). Empty string means all pages |
| `dpi` | int | No | Rendering resolution. Range: 72-400. Default: `200` |

### Response (200)

```json
{
  "file_id": 42,
  "engine": "gemini-2.0-flash",
  "task": "ocr_document",
  "full_text": "Text extracted from PDF...",
  "page_count": 10,
  "row_id": 6
}
```

### Errors

- `400` — File is not a PDF
- `404` — File not found
- `500` — Failed to resolve OCR engine / PDF OCR execution error

---

## POST /api/ocr/bbox/<file_id>

Detect text bounding boxes for existing OCR results. Used as a second pass to add position information to previously extracted text regions.

### Rate Limit

WRITE

### Request

```json
{
  "task": "",
  "server_id": ""
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | File ID (path parameter) |
| `task` | string | No | Target OCR task type |
| `server_id` | string | No | Analysis server ID to use |

### Response (200)

```json
{
  "file_id": 42,
  "total_regions": 5,
  "detected_bboxes": 4,
  "regions": [
    {
      "id": 0,
      "text": "Text region",
      "bbox": { "x": 10, "y": 20, "width": 200, "height": 30 }
    }
  ]
}
```

### Errors

- `400` — No text regions found / VLM engine required
- `404` — OCR result not found (run OCR first) / File not found
- `500` — Failed to resolve OCR engine / bbox detection error

---

## GET /api/ocr/engines

List available OCR engines (analysis servers) with per-task scores.

### Parameters

None

### Response

```json
{
  "engines": [
    {
      "server_id": "server-1",
      "server_name": "Gemini Flash",
      "model": "gemini-2.0-flash",
      "type": "google",
      "scores": {
        "ocr": 85,
        "ocr_document": 90,
        "ocr_manga": 60
      }
    }
  ],
  "manga_ocr_available": false
}
```

---

## GET /api/ocr/npu

Get NPU (Neural Processing Unit) device status and recommended optimization settings.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `task` | string | No | Task type for optimization recommendations. Default: `ocr` |

### Response

```json
{
  "npu": {
    "available": true,
    "device": "Hailo-10H",
    "driver_version": "4.20.0"
  },
  "optimization": {
    "recommended_batch_size": 4,
    "use_npu": true
  }
}
```

---

## POST /api/ocr/translate/<file_id>

Translate an existing OCR result into the specified language. The translation is saved to the database.

### Rate Limit

WRITE

### Request

```json
{
  "target_lang": "en",
  "server_id": "",
  "task": ""
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | File ID (path parameter) |
| `target_lang` | string | Yes | Target language code (e.g., `en`, `ja`, `zh`, `ko`) |
| `server_id` | string | No | Analysis server ID to use |
| `task` | string | No | Target OCR task type |

### Response (200)

```json
{
  "file_id": 42,
  "target_lang": "en",
  "translated_text": "Translated full text...",
  "engine": "gemini-2.0-flash",
  "region_translations": [
    { "region_id": 0, "original": "Original text", "translated": "Translated text" }
  ]
}
```

### Errors

- `400` — `target_lang` not specified
- `404` — OCR result not found
- `500` — Translation execution error

---

## GET /api/ocr/translations/<file_id>

Get the list of translation results for a file.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | File ID (path parameter) |
| `target_lang` | string | No | Filter by language code |

### Response

```json
{
  "file_id": 42,
  "translations": [
    {
      "target_lang": "en",
      "translated_text": "Translated text...",
      "engine": "gemini-2.0-flash",
      "region_translations": [...]
    }
  ]
}
```

---

## GET /api/ocr/overlay/<file_id>

Generate an overlay image with OCR results (or translations) rendered on top of the original image.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | File ID (path parameter) |
| `mode` | string | No | Display mode. `translated` / `original` / `both`. Default: `translated` |
| `target_lang` | string | No | Filter by translation language |
| `format` | string | No | Output image format. `png` / `jpeg`. Default: `png` |
| `task` | string | No | Target OCR task type |

### Response

- Content-Type: `image/png` or `image/jpeg`
- Filename: `ocr_overlay_{file_id}.{ext}`

### Errors

- `400` — Invalid mode / format value
- `404` — OCR result not found / File not found
- `500` — Overlay image generation error

---

## GET /api/ocr/export/<file_id>

Export an OCR result in the specified format as a file download.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | File ID (path parameter) |
| `format` | string | No | Export format. `txt` / `md` / `json` / `pdf`. Default: `md` |
| `task` | string | No | Target OCR task type |
| `include_translation` | string | No | If set to any value, includes translations |
| `target_lang` | string | No | Language code of translation to include |

### Response

- Content-Type: Format-appropriate MIME type
- Content-Disposition: `attachment; filename=...`

### Errors

- `400` — Invalid format value
- `404` — OCR result not found

---

## POST /api/ocr/export/batch

Batch export OCR results for multiple files. Supports ZIP download or direct server-side save.

### Rate Limit

WRITE

### Request

```json
{
  "file_ids": [1, 2, 3],
  "format": "md",
  "output_dir": "",
  "overlay_mode": "translated",
  "target_lang": "",
  "include_translation": false
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_ids` | int[] | Yes | Array of target file IDs |
| `format` | string | No | Export format. `txt` / `md` / `json` / `pdf` / `overlay`. Defaults from extension config |
| `output_dir` | string | No | Absolute path for server-side save. If omitted, returns ZIP download |
| `overlay_mode` | string | No | Overlay mode (when `format=overlay`). `translated` / `original` / `both`. Default: `translated` |
| `target_lang` | string | No | Translation language code |
| `include_translation` | bool | No | Whether to include translations. Default: `false` |

### Response (ZIP download)

- Content-Type: `application/zip`
- Filename: `ocr_export_batch.zip` (text formats) or `ocr_overlay_batch.zip` (overlay format)

### Response (server-side save)

```json
{
  "saved": 3,
  "errors": 0,
  "output_dir": "/path/to/output",
  "results": [
    { "file_id": 1, "path": "/path/to/output/ocr_1.md" }
  ],
  "error_details": []
}
```

### Errors

- `400` — `file_ids` is empty / invalid format value / `output_dir` is not an absolute path
- `403` — `output_dir` is a forbidden directory
- `404` — No OCR results found

---

## POST /api/ocr/benchmark

Run an OCR benchmark to measure accuracy and performance. Requires benchmark cases (image + ground truth text pairs).

### Rate Limit

WRITE

### Request

```json
{
  "task": "ocr",
  "server_id": "",
  "benchmark_dir": ""
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `task` | string | No | Task type to benchmark. Default: `ocr` |
| `server_id` | string | No | Analysis server ID to use |
| `benchmark_dir` | string | No | Directory path for benchmark cases. Defaults to `extensions/builtin_ocr/benchmarks/` |

### Response (200)

```json
{
  "total_cases": 10,
  "avg_accuracy": 0.92,
  "avg_time_ms": 1500,
  "results": [
    {
      "image": "test1.png",
      "accuracy": 0.95,
      "time_ms": 1200
    }
  ]
}
```

### Errors

- `404` — No benchmark cases found
- `500` — Failed to resolve OCR engine / Benchmark execution error

---

## GET /api/ocr/benchmark/cases

List available benchmark cases.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `dir` | string | No | Directory path for benchmark cases |

### Response

```json
{
  "cases": [
    {
      "image": "test1.png",
      "task": "ocr",
      "language": "ja",
      "expected_length": 256,
      "tags": ["manga", "vertical"]
    }
  ],
  "total": 10
}
```

---

## GET /api/ocr/profiles

List OCR model profiles with per-task score configurations.

### Parameters

None

### Response

```json
{
  "profiles": [
    {
      "model_prefix": "gemini-2.0-flash",
      "scores": {
        "ocr": 85,
        "ocr_document": 90,
        "ocr_manga": 60
      }
    }
  ]
}
```

---

## POST /api/ocr/profiles/fetch

Fetch and merge community-published model profiles from a URL.

### Rate Limit

WRITE

### Request

```json
{
  "url": "https://example.com/ocr-profiles.json"
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `url` | string | Yes | URL of the profile JSON |

### Response (200)

```json
{
  "added": 3,
  "updated": 1,
  "total": 15
}
```

### Errors

- `400` — `url` not specified
- `500` — Fetch or merge failed

---

## PUT /api/ocr/profiles/<model_prefix>

Manually update scores for a model profile.

### Rate Limit

WRITE

### Request

```json
{
  "scores": {
    "ocr": 90,
    "ocr_document": 85,
    "ocr_manga": 70
  }
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `model_prefix` | string | Yes | Model name prefix (path parameter) |
| `scores` | object | Yes | Object with task types as keys and scores (integers) as values |

### Response

```json
{
  "model": "gemini-2.0-flash",
  "scores": {
    "ocr": 90,
    "ocr_document": 85,
    "ocr_manga": 70
  }
}
```

### Errors

- `400` — `scores` not specified
