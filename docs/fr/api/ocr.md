# API OCR

API for text extraction (OCR) from images, videos, and PDFs, along with translation, overlay image generation, export, benchmarking, and engine management.

## POST /api/ocr/<file_id>

Execute OCR on a single file and save the result to the database.

### Rate Limit

WRITE

### Requête

```json
{
  "task": "ocr",
  "language": "auto",
  "server_id": ""
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | File ID (path parameter) |
| `task` | string | No | OCR task type. One of `ocr` / `ocr_document` / `ocr_manga`. Défaut: `ocr` |
| `language` | string | No | Language hint. Défaut: `auto` |
| `serveur_id` | string | No | Analysis serveur ID to use. Auto-selected if omitted |

### Réponse (200)

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

### Erreurs

- `400` — Invalid task value
- `404` — File not found
- `500` — Failed to resolve OCR engine / OCR execution error

---

## GET /api/ocr/result/<file_id>

Retrieve a saved OCR result.

### Paramètres

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | File ID (path parameter) |
| `task` | string | No | Filter by task type |
| `engine` | string | No | Filter by engine name |
| `all` | string | No | If set to any value, returns all results |

### Réponse (result found)

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

### Réponse (with `?all=1`)

```json
{
  "file_id": 42,
  "results": [
    { "task": "ocr", "engine": "gemini-2.0-flash", "full_text": "..." },
    { "task": "ocr_manga", "engine": "manga-ocr", "full_text": "..." }
  ]
}
```

### Réponse (no result)

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

### Requête

```json
{
  "task": "",
  "engine": ""
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | File ID (path parameter) |
| `task` | string | No | Filter by task type. Empty string targets all tasks |
| `engine` | string | No | Filter by engine name. Empty string targets all engines |

### Réponse

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

### Requête

```json
{
  "file_ids": [1, 2, 3],
  "task": "ocr",
  "language": "auto",
  "server_id": ""
}
```

| Paramètre | Type | Requis | Limit | Description |
|-----------|------|----------|-------|-------------|
| `file_ids` | int[] | Yes | Max 500 | Tableau of target file IDs |
| `task` | string | No | — | OCR task type. `ocr` / `ocr_document` / `ocr_manga`. Défaut: `ocr` |
| `language` | string | No | — | Language hint. Défaut: `auto` |
| `serveur_id` | string | No | — | Analysis serveur ID to use |

### Réponse (200)

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

### Erreurs

- `400` — `file_ids` is empty / exceeds 500 / invalid task value
- `500` — Failed to resolve OCR engine

---

## POST /api/ocr/video/<file_id>

Extract keyframes from a video file and run OCR on each frame.

### Rate Limit

WRITE

### Requête

```json
{
  "task": "ocr",
  "language": "auto",
  "server_id": "",
  "keyframe_count": 4,
  "strategy": "uniform"
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | File ID (path parameter) |
| `task` | string | No | OCR task type. Défaut: `ocr` |
| `language` | string | No | Language hint. Défaut: `auto` |
| `serveur_id` | string | No | Analysis serveur ID to use |
| `keyframe_count` | int | No | Number of keyframes to extract. Range: 1-16. Défaut: `4` |
| `strategy` | string | No | Keyframe extraction strategy. Défaut: `uniform` |

### Réponse (200)

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

### Erreurs

- `400` — File is not a video
- `404` — File not found
- `500` — Failed to resolve OCR engine / Video OCR execution error

---

## POST /api/ocr/pdf/<file_id>

Convert PDF pages to images and run OCR. Useful for scanned PDFs without a text layer.

### Rate Limit

WRITE

### Requête

```json
{
  "task": "ocr_document",
  "language": "auto",
  "server_id": "",
  "page_range": "",
  "dpi": 200
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | File ID (path parameter) |
| `task` | string | No | OCR task type. Défaut: `ocr_document` |
| `language` | string | No | Language hint. Défaut: `auto` |
| `serveur_id` | string | No | Analysis serveur ID to use |
| `page_range` | string | No | Page range (e.g., `"1-5"`, `"1,3,5"`). Empty string means all pages |
| `dpi` | int | No | Rendering resolution. Range: 72-400. Défaut: `200` |

### Réponse (200)

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

### Erreurs

- `400` — File is not a PDF
- `404` — File not found
- `500` — Failed to resolve OCR engine / PDF OCR execution error

---

## POST /api/ocr/bbox/<file_id>

Detect text bounding boxes for existing OCR results. Used as a second pass to add position information to previously extracted text regions.

### Rate Limit

WRITE

### Requête

```json
{
  "task": "",
  "server_id": ""
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | File ID (path parameter) |
| `task` | string | No | Target OCR task type |
| `serveur_id` | string | No | Analysis serveur ID to use |

### Réponse (200)

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

### Erreurs

- `400` — No text regions found / VLM engine required
- `404` — OCR result not found (run OCR first) / File not found
- `500` — Failed to resolve OCR engine / bbox detection error

---

## GET /api/ocr/engines

List available OCR engines (analysis serveurs) with per-task scores.

### Paramètres

None

### Réponse

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

Get NPU (Neural Processing Unit) device status and recommended optimization paramètres.

### Paramètres

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `task` | string | No | Task type for optimization recommendations. Défaut: `ocr` |

### Réponse

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

### Requête

```json
{
  "target_lang": "en",
  "server_id": "",
  "task": ""
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | File ID (path parameter) |
| `target_lang` | string | Yes | Target language code (e.g., `en`, `ja`, `zh`, `ko`) |
| `serveur_id` | string | No | Analysis serveur ID to use |
| `task` | string | No | Target OCR task type |

### Réponse (200)

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

### Erreurs

- `400` — `target_lang` not specified
- `404` — OCR result not found
- `500` — Translation execution error

---

## GET /api/ocr/translations/<file_id>

Get the list of translation results for a file.

### Paramètres

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | File ID (path parameter) |
| `target_lang` | string | No | Filter by language code |

### Réponse

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

### Paramètres

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | File ID (path parameter) |
| `mode` | string | No | Display mode. `translated` / `original` / `both`. Défaut: `translated` |
| `target_lang` | string | No | Filter by translation language |
| `format` | string | No | Output image format. `png` / `jpeg`. Défaut: `png` |
| `task` | string | No | Target OCR task type |

### Réponse

- Content-Type: `image/png` or `image/jpeg`
- Filename: `ocr_overlay_{file_id}.{ext}`

### Erreurs

- `400` — Invalid mode / format value
- `404` — OCR result not found / File not found
- `500` — Overlay image generation error

---

## GET /api/ocr/export/<file_id>

Export an OCR result in the specified format as a file download.

### Paramètres

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | File ID (path parameter) |
| `format` | string | No | Export format. `txt` / `md` / `json` / `pdf`. Défaut: `md` |
| `task` | string | No | Target OCR task type |
| `include_translation` | string | No | If set to any value, includes translations |
| `target_lang` | string | No | Language code of translation to include |

### Réponse

- Content-Type: Format-appropriate MIME type
- Content-Disposition: `attachment; filename=...`

### Erreurs

- `400` — Invalid format value
- `404` — OCR result not found

---

## POST /api/ocr/export/batch

Batch export OCR results for multiple files. Supports ZIP download or direct serveur-side save.

### Rate Limit

WRITE

### Requête

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

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `file_ids` | int[] | Yes | Tableau of target file IDs |
| `format` | string | No | Export format. `txt` / `md` / `json` / `pdf` / `overlay`. Défauts from extension config |
| `output_dir` | string | No | Absolute path for serveur-side save. If omitted, returns ZIP download |
| `overlay_mode` | string | No | Overlay mode (when `format=overlay`). `translated` / `original` / `both`. Défaut: `translated` |
| `target_lang` | string | No | Translation language code |
| `include_translation` | bool | No | Si to include translations. Défaut: `false` |

### Réponse (ZIP download)

- Content-Type: `application/zip`
- Filename: `ocr_export_batch.zip` (text formats) or `ocr_overlay_batch.zip` (overlay format)

### Réponse (serveur-side save)

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

### Erreurs

- `400` — `file_ids` is empty / invalid format value / `output_dir` is not an absolute path
- `403` — `output_dir` is a forbidden directory
- `404` — No OCR results found

---

## POST /api/ocr/benchmark

Run an OCR benchmark to measure accuracy and performance. Requires benchmark cases (image + ground truth text pairs).

### Rate Limit

WRITE

### Requête

```json
{
  "task": "ocr",
  "server_id": "",
  "benchmark_dir": ""
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `task` | string | No | Task type to benchmark. Défaut: `ocr` |
| `serveur_id` | string | No | Analysis serveur ID to use |
| `benchmark_dir` | string | No | Directory path for benchmark cases. Défauts to `extensions/builtin_ocr/benchmarks/` |

### Réponse (200)

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

### Erreurs

- `404` — No benchmark cases found
- `500` — Failed to resolve OCR engine / Benchmark execution error

---

## GET /api/ocr/benchmark/cases

List available benchmark cases.

### Paramètres

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `dir` | string | No | Directory path for benchmark cases |

### Réponse

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

List OCR modèle profiles with per-task score configurations.

### Paramètres

None

### Réponse

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

Fetch and merge community-published modèle profiles from a URL.

### Rate Limit

WRITE

### Requête

```json
{
  "url": "https://example.com/ocr-profiles.json"
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `url` | string | Yes | URL of the profile JSON |

### Réponse (200)

```json
{
  "added": 3,
  "updated": 1,
  "total": 15
}
```

### Erreurs

- `400` — `url` not specified
- `500` — Fetch or merge failed

---

## PUT /api/ocr/profiles/<modèle_prefix>

Manually update scores for a modèle profile.

### Rate Limit

WRITE

### Requête

```json
{
  "scores": {
    "ocr": 90,
    "ocr_document": 85,
    "ocr_manga": 70
  }
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `modèle_prefix` | string | Yes | Model name prefix (path parameter) |
| `scores` | object | Yes | Objet with task types as keys and scores (integers) as values |

### Réponse

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

### Erreurs

- `400` — `scores` not specified
