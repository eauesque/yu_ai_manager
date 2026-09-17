# OCR API

用於從圖片、影片及 PDF 中提取文字（OCR）的 API，同時提供翻譯、疊加圖片生成、匯出、基準測試及引擎管理功能。

## POST /api/ocr/<file_id>

對單一檔案執行 OCR 並將結果儲存到資料庫。

### Rate Limit

WRITE

### 請求

```json
{
  "task": "ocr",
  "language": "auto",
  "server_id": ""
}
```

| 參數 | 類型 | 是否必填 | 說明 |
|------|------|----------|------|
| `file_id` | int | 是 | 檔案 ID（路徑參數） |
| `task` | string | 否 | OCR 任務類型。`ocr` / `ocr_document` / `ocr_manga` 之一。預設：`ocr` |
| `language` | string | 否 | 語言提示。預設：`auto` |
| `server_id` | string | 否 | 要使用的分析伺服器 ID。省略時自動選擇 |

### 回應 (200)

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

### 錯誤

- `400` — 無效的任務值
- `404` — 找不到檔案
- `500` — 無法解析 OCR 引擎 / OCR 執行錯誤

---

## GET /api/ocr/result/<file_id>

擷取已儲存的 OCR 結果。

### 參數

| 參數 | 類型 | 是否必填 | 說明 |
|------|------|----------|------|
| `file_id` | int | 是 | 檔案 ID（路徑參數） |
| `task` | string | 否 | 依任務類型篩選 |
| `engine` | string | 否 | 依引擎名稱篩選 |
| `all` | string | 否 | 設為任意值時回傳所有結果 |

### 回應（找到結果）

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

### 回應（使用 `?all=1`）

```json
{
  "file_id": 42,
  "results": [
    { "task": "ocr", "engine": "gemini-2.0-flash", "full_text": "..." },
    { "task": "ocr_manga", "engine": "manga-ocr", "full_text": "..." }
  ]
}
```

### 回應（無結果）

```json
{
  "status": "not_found"
}
```

---

## DELETE /api/ocr/result/<file_id>

刪除已儲存的 OCR 結果。

### Rate Limit

WRITE

### 請求

```json
{
  "task": "",
  "engine": ""
}
```

| 參數 | 類型 | 是否必填 | 說明 |
|------|------|----------|------|
| `file_id` | int | 是 | 檔案 ID（路徑參數） |
| `task` | string | 否 | 依任務類型篩選。空字串表示所有任務 |
| `engine` | string | 否 | 依引擎名稱篩選。空字串表示所有引擎 |

### 回應

```json
{
  "deleted": 2
}
```

---

## POST /api/ocr/batch

對多個檔案執行批次 OCR。

### Rate Limit

WRITE

### 請求

```json
{
  "file_ids": [1, 2, 3],
  "task": "ocr",
  "language": "auto",
  "server_id": ""
}
```

| 參數 | 類型 | 是否必填 | 限制 | 說明 |
|------|------|----------|------|------|
| `file_ids` | int[] | 是 | 最多 500 | 目標檔案 ID 陣列 |
| `task` | string | 否 | — | OCR 任務類型。`ocr` / `ocr_document` / `ocr_manga`。預設：`ocr` |
| `language` | string | 否 | — | 語言提示。預設：`auto` |
| `server_id` | string | 否 | — | 要使用的分析伺服器 ID |

### 回應 (200)

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

### 錯誤

- `400` — `file_ids` 為空 / 超過 500 / 無效的任務值
- `500` — 無法解析 OCR 引擎

---

## POST /api/ocr/video/<file_id>

從影片檔案中提取關鍵影格並對每個影格執行 OCR。

### Rate Limit

WRITE

### 請求

```json
{
  "task": "ocr",
  "language": "auto",
  "server_id": "",
  "keyframe_count": 4,
  "strategy": "uniform"
}
```

| 參數 | 類型 | 是否必填 | 說明 |
|------|------|----------|------|
| `file_id` | int | 是 | 檔案 ID（路徑參數） |
| `task` | string | 否 | OCR 任務類型。預設：`ocr` |
| `language` | string | 否 | 語言提示。預設：`auto` |
| `server_id` | string | 否 | 要使用的分析伺服器 ID |
| `keyframe_count` | int | 否 | 要提取的關鍵影格數。範圍：1-16。預設：`4` |
| `strategy` | string | 否 | 關鍵影格提取策略。預設：`uniform` |

### 回應 (200)

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

### 錯誤

- `400` — 檔案不是影片
- `404` — 找不到檔案
- `500` — 無法解析 OCR 引擎 / 影片 OCR 執行錯誤

---

## POST /api/ocr/pdf/<file_id>

將 PDF 頁面轉換為圖片並執行 OCR。適用於沒有文字層的掃描 PDF。

### Rate Limit

WRITE

### 請求

```json
{
  "task": "ocr_document",
  "language": "auto",
  "server_id": "",
  "page_range": "",
  "dpi": 200
}
```

| 參數 | 類型 | 是否必填 | 說明 |
|------|------|----------|------|
| `file_id` | int | 是 | 檔案 ID（路徑參數） |
| `task` | string | 否 | OCR 任務類型。預設：`ocr_document` |
| `language` | string | 否 | 語言提示。預設：`auto` |
| `server_id` | string | 否 | 要使用的分析伺服器 ID |
| `page_range` | string | 否 | 頁面範圍（例如 `"1-5"`、`"1,3,5"`）。空字串表示所有頁面 |
| `dpi` | int | 否 | 渲染解析度。範圍：72-400。預設：`200` |

### 回應 (200)

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

### 錯誤

- `400` — 檔案不是 PDF
- `404` — 找不到檔案
- `500` — 無法解析 OCR 引擎 / PDF OCR 執行錯誤

---

## POST /api/ocr/bbox/<file_id>

偵測現有 OCR 結果的文字邊界框。作為第二階段處理，為先前提取的文字區域新增位置資訊。

### Rate Limit

WRITE

### 請求

```json
{
  "task": "",
  "server_id": ""
}
```

| 參數 | 類型 | 是否必填 | 說明 |
|------|------|----------|------|
| `file_id` | int | 是 | 檔案 ID（路徑參數） |
| `task` | string | 否 | 目標 OCR 任務類型 |
| `server_id` | string | 否 | 要使用的分析伺服器 ID |

### 回應 (200)

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

### 錯誤

- `400` — 找不到文字區域 / 需要 VLM 引擎
- `404` — 找不到 OCR 結果（請先執行 OCR）/ 找不到檔案
- `500` — 無法解析 OCR 引擎 / 邊界框偵測錯誤

---

## GET /api/ocr/engines

列出可用的 OCR 引擎（分析伺服器）及各任務的評分。

### 參數

無

### 回應

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

取得 NPU（Neural Processing Unit）裝置狀態及建議的最佳化設定。

### 參數

| 參數 | 類型 | 是否必填 | 說明 |
|------|------|----------|------|
| `task` | string | 否 | 最佳化建議的任務類型。預設：`ocr` |

### 回應

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

將現有的 OCR 結果翻譯為指定語言。翻譯結果會儲存到資料庫。

### Rate Limit

WRITE

### 請求

```json
{
  "target_lang": "en",
  "server_id": "",
  "task": ""
}
```

| 參數 | 類型 | 是否必填 | 說明 |
|------|------|----------|------|
| `file_id` | int | 是 | 檔案 ID（路徑參數） |
| `target_lang` | string | 是 | 目標語言代碼（例如 `en`、`ja`、`zh`、`ko`） |
| `server_id` | string | 否 | 要使用的分析伺服器 ID |
| `task` | string | 否 | 目標 OCR 任務類型 |

### 回應 (200)

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

### 錯誤

- `400` — 未指定 `target_lang`
- `404` — 找不到 OCR 結果
- `500` — 翻譯執行錯誤

---

## GET /api/ocr/translations/<file_id>

取得檔案的翻譯結果列表。

### 參數

| 參數 | 類型 | 是否必填 | 說明 |
|------|------|----------|------|
| `file_id` | int | 是 | 檔案 ID（路徑參數） |
| `target_lang` | string | 否 | 依語言代碼篩選 |

### 回應

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

生成將 OCR 結果（或翻譯）渲染在原始圖片上的疊加圖片。

### 參數

| 參數 | 類型 | 是否必填 | 說明 |
|------|------|----------|------|
| `file_id` | int | 是 | 檔案 ID（路徑參數） |
| `mode` | string | 否 | 顯示模式。`translated` / `original` / `both`。預設：`translated` |
| `target_lang` | string | 否 | 依翻譯語言篩選 |
| `format` | string | 否 | 輸出圖片格式。`png` / `jpeg`。預設：`png` |
| `task` | string | 否 | 目標 OCR 任務類型 |

### 回應

- Content-Type: `image/png` 或 `image/jpeg`
- Filename: `ocr_overlay_{file_id}.{ext}`

### 錯誤

- `400` — 無效的模式 / 格式值
- `404` — 找不到 OCR 結果 / 找不到檔案
- `500` — 疊加圖片生成錯誤

---

## GET /api/ocr/export/<file_id>

以指定格式匯出 OCR 結果並下載。

### 參數

| 參數 | 類型 | 是否必填 | 說明 |
|------|------|----------|------|
| `file_id` | int | 是 | 檔案 ID（路徑參數） |
| `format` | string | 否 | 匯出格式。`txt` / `md` / `json` / `pdf`。預設：`md` |
| `task` | string | 否 | 目標 OCR 任務類型 |
| `include_translation` | string | 否 | 設為任意值時包含翻譯 |
| `target_lang` | string | 否 | 要包含的翻譯語言代碼 |

### 回應

- Content-Type: 對應格式的 MIME 類型
- Content-Disposition: `attachment; filename=...`

### 錯誤

- `400` — 無效的格式值
- `404` — 找不到 OCR 結果

---

## POST /api/ocr/export/batch

批次匯出多個檔案的 OCR 結果。支援 ZIP 下載或直接儲存到伺服器端。

### Rate Limit

WRITE

### 請求

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

| 參數 | 類型 | 是否必填 | 說明 |
|------|------|----------|------|
| `file_ids` | int[] | 是 | 目標檔案 ID 陣列 |
| `format` | string | 否 | 匯出格式。`txt` / `md` / `json` / `pdf` / `overlay`。預設從 Extension 設定取得 |
| `output_dir` | string | 否 | 伺服器端儲存的絕對路徑。省略時回傳 ZIP 下載 |
| `overlay_mode` | string | 否 | 疊加模式（`format=overlay` 時）。`translated` / `original` / `both`。預設：`translated` |
| `target_lang` | string | 否 | 翻譯語言代碼 |
| `include_translation` | bool | 否 | 是否包含翻譯。預設：`false` |

### 回應（ZIP 下載）

- Content-Type: `application/zip`
- Filename: `ocr_export_batch.zip`（文字格式）或 `ocr_overlay_batch.zip`（疊加格式）

### 回應（伺服器端儲存）

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

### 錯誤

- `400` — `file_ids` 為空 / 無效的格式值 / `output_dir` 不是絕對路徑
- `403` — `output_dir` 是禁止的目錄
- `404` — 找不到 OCR 結果

---

## POST /api/ocr/benchmark

執行 OCR 基準測試以衡量準確度和效能。需要基準測試案例（圖片 + 正確答案文字配對）。

### Rate Limit

WRITE

### 請求

```json
{
  "task": "ocr",
  "server_id": "",
  "benchmark_dir": ""
}
```

| 參數 | 類型 | 是否必填 | 說明 |
|------|------|----------|------|
| `task` | string | 否 | 要測試的任務類型。預設：`ocr` |
| `server_id` | string | 否 | 要使用的分析伺服器 ID |
| `benchmark_dir` | string | 否 | 基準測試案例目錄路徑。預設為 `extensions/builtin_ocr/benchmarks/` |

### 回應 (200)

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

### 錯誤

- `404` — 找不到基準測試案例
- `500` — 無法解析 OCR 引擎 / 基準測試執行錯誤

---

## GET /api/ocr/benchmark/cases

列出可用的基準測試案例。

### 參數

| 參數 | 類型 | 是否必填 | 說明 |
|------|------|----------|------|
| `dir` | string | 否 | 基準測試案例目錄路徑 |

### 回應

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

列出包含各任務評分設定的 OCR 模型 Profile。

### 參數

無

### 回應

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

從 URL 取得並合併社群發布的模型 Profile。

### Rate Limit

WRITE

### 請求

```json
{
  "url": "https://example.com/ocr-profiles.json"
}
```

| 參數 | 類型 | 是否必填 | 說明 |
|------|------|----------|------|
| `url` | string | 是 | Profile JSON 的 URL |

### 回應 (200)

```json
{
  "added": 3,
  "updated": 1,
  "total": 15
}
```

### 錯誤

- `400` — 未指定 `url`
- `500` — 取得或合併失敗

---

## PUT /api/ocr/profiles/<model_prefix>

手動更新模型 Profile 的評分。

### Rate Limit

WRITE

### 請求

```json
{
  "scores": {
    "ocr": 90,
    "ocr_document": 85,
    "ocr_manga": 70
  }
}
```

| 參數 | 類型 | 是否必填 | 說明 |
|------|------|----------|------|
| `model_prefix` | string | 是 | 模型名稱前綴（路徑參數） |
| `scores` | object | 是 | 以任務類型為鍵、評分（整數）為值的物件 |

### 回應

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

### 錯誤

- `400` — 未指定 `scores`
