# OCR API

用于从图片、视频及 PDF 中提取文字（OCR）的 API，同时提供翻译、叠加图片生成、导出、基准测试及引擎管理功能。

## POST /api/ocr/<file_id>

对单个文件执行 OCR 并将结果保存到数据库。

### Rate Limit

WRITE

### 请求

```json
{
  "task": "ocr",
  "language": "auto",
  "server_id": ""
}
```

| 参数 | 类型 | 是否必填 | 说明 |
|------|------|----------|------|
| `file_id` | int | 是 | 文件 ID（路径参数） |
| `task` | string | 否 | OCR 任务类型。`ocr` / `ocr_document` / `ocr_manga` 之一。默认：`ocr` |
| `language` | string | 否 | 语言提示。默认：`auto` |
| `server_id` | string | 否 | 要使用的分析服务器 ID。省略时自动选择 |

### 响应 (200)

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

### 错误

- `400` — 无效的任务值
- `404` — 找不到文件
- `500` — 无法解析 OCR 引擎 / OCR 执行错误

---

## GET /api/ocr/result/<file_id>

获取已保存的 OCR 结果。

### 参数

| 参数 | 类型 | 是否必填 | 说明 |
|------|------|----------|------|
| `file_id` | int | 是 | 文件 ID（路径参数） |
| `task` | string | 否 | 按任务类型筛选 |
| `engine` | string | 否 | 按引擎名称筛选 |
| `all` | string | 否 | 设为任意值时返回所有结果 |

### 响应（找到结果）

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

### 响应（使用 `?all=1`）

```json
{
  "file_id": 42,
  "results": [
    { "task": "ocr", "engine": "gemini-2.0-flash", "full_text": "..." },
    { "task": "ocr_manga", "engine": "manga-ocr", "full_text": "..." }
  ]
}
```

### 响应（无结果）

```json
{
  "status": "not_found"
}
```

---

## DELETE /api/ocr/result/<file_id>

删除已保存的 OCR 结果。

### Rate Limit

WRITE

### 请求

```json
{
  "task": "",
  "engine": ""
}
```

| 参数 | 类型 | 是否必填 | 说明 |
|------|------|----------|------|
| `file_id` | int | 是 | 文件 ID（路径参数） |
| `task` | string | 否 | 按任务类型筛选。空字符串表示所有任务 |
| `engine` | string | 否 | 按引擎名称筛选。空字符串表示所有引擎 |

### 响应

```json
{
  "deleted": 2
}
```

---

## POST /api/ocr/batch

对多个文件执行批量 OCR。

### Rate Limit

WRITE

### 请求

```json
{
  "file_ids": [1, 2, 3],
  "task": "ocr",
  "language": "auto",
  "server_id": ""
}
```

| 参数 | 类型 | 是否必填 | 限制 | 说明 |
|------|------|----------|------|------|
| `file_ids` | int[] | 是 | 最多 500 | 目标文件 ID 数组 |
| `task` | string | 否 | — | OCR 任务类型。`ocr` / `ocr_document` / `ocr_manga`。默认：`ocr` |
| `language` | string | 否 | — | 语言提示。默认：`auto` |
| `server_id` | string | 否 | — | 要使用的分析服务器 ID |

### 响应 (200)

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

### 错误

- `400` — `file_ids` 为空 / 超过 500 / 无效的任务值
- `500` — 无法解析 OCR 引擎

---

## POST /api/ocr/video/<file_id>

从视频文件中提取关键帧并对每帧执行 OCR。

### Rate Limit

WRITE

### 请求

```json
{
  "task": "ocr",
  "language": "auto",
  "server_id": "",
  "keyframe_count": 4,
  "strategy": "uniform"
}
```

| 参数 | 类型 | 是否必填 | 说明 |
|------|------|----------|------|
| `file_id` | int | 是 | 文件 ID（路径参数） |
| `task` | string | 否 | OCR 任务类型。默认：`ocr` |
| `language` | string | 否 | 语言提示。默认：`auto` |
| `server_id` | string | 否 | 要使用的分析服务器 ID |
| `keyframe_count` | int | 否 | 要提取的关键帧数。范围：1-16。默认：`4` |
| `strategy` | string | 否 | 关键帧提取策略。默认：`uniform` |

### 响应 (200)

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

### 错误

- `400` — 文件不是视频
- `404` — 找不到文件
- `500` — 无法解析 OCR 引擎 / 视频 OCR 执行错误

---

## POST /api/ocr/pdf/<file_id>

将 PDF 页面转换为图片并执行 OCR。适用于没有文字层的扫描 PDF。

### Rate Limit

WRITE

### 请求

```json
{
  "task": "ocr_document",
  "language": "auto",
  "server_id": "",
  "page_range": "",
  "dpi": 200
}
```

| 参数 | 类型 | 是否必填 | 说明 |
|------|------|----------|------|
| `file_id` | int | 是 | 文件 ID（路径参数） |
| `task` | string | 否 | OCR 任务类型。默认：`ocr_document` |
| `language` | string | 否 | 语言提示。默认：`auto` |
| `server_id` | string | 否 | 要使用的分析服务器 ID |
| `page_range` | string | 否 | 页面范围（例如 `"1-5"`、`"1,3,5"`）。空字符串表示所有页面 |
| `dpi` | int | 否 | 渲染分辨率。范围：72-400。默认：`200` |

### 响应 (200)

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

### 错误

- `400` — 文件不是 PDF
- `404` — 找不到文件
- `500` — 无法解析 OCR 引擎 / PDF OCR 执行错误

---

## POST /api/ocr/bbox/<file_id>

检测现有 OCR 结果的文字边界框。作为第二阶段处理，为之前提取的文字区域添加位置信息。

### Rate Limit

WRITE

### 请求

```json
{
  "task": "",
  "server_id": ""
}
```

| 参数 | 类型 | 是否必填 | 说明 |
|------|------|----------|------|
| `file_id` | int | 是 | 文件 ID（路径参数） |
| `task` | string | 否 | 目标 OCR 任务类型 |
| `server_id` | string | 否 | 要使用的分析服务器 ID |

### 响应 (200)

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

### 错误

- `400` — 找不到文字区域 / 需要 VLM 引擎
- `404` — 找不到 OCR 结果（请先执行 OCR）/ 找不到文件
- `500` — 无法解析 OCR 引擎 / 边界框检测错误

---

## GET /api/ocr/engines

列出可用的 OCR 引擎（分析服务器）及各任务的评分。

### 参数

无

### 响应

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

获取 NPU（Neural Processing Unit）设备状态及推荐的优化设置。

### 参数

| 参数 | 类型 | 是否必填 | 说明 |
|------|------|----------|------|
| `task` | string | 否 | 优化建议的任务类型。默认：`ocr` |

### 响应

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

将现有的 OCR 结果翻译为指定语言。翻译结果会保存到数据库。

### Rate Limit

WRITE

### 请求

```json
{
  "target_lang": "en",
  "server_id": "",
  "task": ""
}
```

| 参数 | 类型 | 是否必填 | 说明 |
|------|------|----------|------|
| `file_id` | int | 是 | 文件 ID（路径参数） |
| `target_lang` | string | 是 | 目标语言代码（例如 `en`、`ja`、`zh`、`ko`） |
| `server_id` | string | 否 | 要使用的分析服务器 ID |
| `task` | string | 否 | 目标 OCR 任务类型 |

### 响应 (200)

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

### 错误

- `400` — 未指定 `target_lang`
- `404` — 找不到 OCR 结果
- `500` — 翻译执行错误

---

## GET /api/ocr/translations/<file_id>

获取文件的翻译结果列表。

### 参数

| 参数 | 类型 | 是否必填 | 说明 |
|------|------|----------|------|
| `file_id` | int | 是 | 文件 ID（路径参数） |
| `target_lang` | string | 否 | 按语言代码筛选 |

### 响应

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

生成将 OCR 结果（或翻译）渲染在原始图片上的叠加图片。

### 参数

| 参数 | 类型 | 是否必填 | 说明 |
|------|------|----------|------|
| `file_id` | int | 是 | 文件 ID（路径参数） |
| `mode` | string | 否 | 显示模式。`translated` / `original` / `both`。默认：`translated` |
| `target_lang` | string | 否 | 按翻译语言筛选 |
| `format` | string | 否 | 输出图片格式。`png` / `jpeg`。默认：`png` |
| `task` | string | 否 | 目标 OCR 任务类型 |

### 响应

- Content-Type: `image/png` 或 `image/jpeg`
- Filename: `ocr_overlay_{file_id}.{ext}`

### 错误

- `400` — 无效的模式 / 格式值
- `404` — 找不到 OCR 结果 / 找不到文件
- `500` — 叠加图片生成错误

---

## GET /api/ocr/export/<file_id>

以指定格式导出 OCR 结果并下载。

### 参数

| 参数 | 类型 | 是否必填 | 说明 |
|------|------|----------|------|
| `file_id` | int | 是 | 文件 ID（路径参数） |
| `format` | string | 否 | 导出格式。`txt` / `md` / `json` / `pdf`。默认：`md` |
| `task` | string | 否 | 目标 OCR 任务类型 |
| `include_translation` | string | 否 | 设为任意值时包含翻译 |
| `target_lang` | string | 否 | 要包含的翻译语言代码 |

### 响应

- Content-Type: 对应格式的 MIME 类型
- Content-Disposition: `attachment; filename=...`

### 错误

- `400` — 无效的格式值
- `404` — 找不到 OCR 结果

---

## POST /api/ocr/export/batch

批量导出多个文件的 OCR 结果。支持 ZIP 下载或直接保存到服务器端。

### Rate Limit

WRITE

### 请求

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

| 参数 | 类型 | 是否必填 | 说明 |
|------|------|----------|------|
| `file_ids` | int[] | 是 | 目标文件 ID 数组 |
| `format` | string | 否 | 导出格式。`txt` / `md` / `json` / `pdf` / `overlay`。默认从 Extension 配置获取 |
| `output_dir` | string | 否 | 服务器端保存的绝对路径。省略时返回 ZIP 下载 |
| `overlay_mode` | string | 否 | 叠加模式（`format=overlay` 时）。`translated` / `original` / `both`。默认：`translated` |
| `target_lang` | string | 否 | 翻译语言代码 |
| `include_translation` | bool | 否 | 是否包含翻译。默认：`false` |

### 响应（ZIP 下载）

- Content-Type: `application/zip`
- Filename: `ocr_export_batch.zip`（文本格式）或 `ocr_overlay_batch.zip`（叠加格式）

### 响应（服务器端保存）

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

### 错误

- `400` — `file_ids` 为空 / 无效的格式值 / `output_dir` 不是绝对路径
- `403` — `output_dir` 是禁止的目录
- `404` — 找不到 OCR 结果

---

## POST /api/ocr/benchmark

执行 OCR 基准测试以衡量准确度和性能。需要基准测试用例（图片 + 正确答案文字配对）。

### Rate Limit

WRITE

### 请求

```json
{
  "task": "ocr",
  "server_id": "",
  "benchmark_dir": ""
}
```

| 参数 | 类型 | 是否必填 | 说明 |
|------|------|----------|------|
| `task` | string | 否 | 要测试的任务类型。默认：`ocr` |
| `server_id` | string | 否 | 要使用的分析服务器 ID |
| `benchmark_dir` | string | 否 | 基准测试用例目录路径。默认为 `extensions/builtin_ocr/benchmarks/` |

### 响应 (200)

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

### 错误

- `404` — 找不到基准测试用例
- `500` — 无法解析 OCR 引擎 / 基准测试执行错误

---

## GET /api/ocr/benchmark/cases

列出可用的基准测试用例。

### 参数

| 参数 | 类型 | 是否必填 | 说明 |
|------|------|----------|------|
| `dir` | string | 否 | 基准测试用例目录路径 |

### 响应

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

列出包含各任务评分配置的 OCR 模型 Profile。

### 参数

无

### 响应

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

从 URL 获取并合并社区发布的模型 Profile。

### Rate Limit

WRITE

### 请求

```json
{
  "url": "https://example.com/ocr-profiles.json"
}
```

| 参数 | 类型 | 是否必填 | 说明 |
|------|------|----------|------|
| `url` | string | 是 | Profile JSON 的 URL |

### 响应 (200)

```json
{
  "added": 3,
  "updated": 1,
  "total": 15
}
```

### 错误

- `400` — 未指定 `url`
- `500` — 获取或合并失败

---

## PUT /api/ocr/profiles/<model_prefix>

手动更新模型 Profile 的评分。

### Rate Limit

WRITE

### 请求

```json
{
  "scores": {
    "ocr": 90,
    "ocr_document": 85,
    "ocr_manga": 70
  }
}
```

| 参数 | 类型 | 是否必填 | 说明 |
|------|------|----------|------|
| `model_prefix` | string | 是 | 模型名称前缀（路径参数） |
| `scores` | object | 是 | 以任务类型为键、评分（整数）为值的对象 |

### 响应

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

### 错误

- `400` — 未指定 `scores`
