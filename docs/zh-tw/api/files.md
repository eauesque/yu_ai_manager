# Files API

用於取得檔案詳情、縮圖和原始媒體的 API。

## GET /api/file/<id>

取得檔案的詳細中繼資料。

### 參數

| 參數 | 類型 | 說明 |
|-----------|------|-------------|
| `id` | int | 檔案 ID（路徑參數） |

### 回應

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

縮圖（WebP）。支援 ETag 快取。

### 參數

| 參數 | 類型 | 說明 |
|-----------|------|-------------|
| `id` | int | 檔案 ID |
| `size` | int | 縮圖尺寸（預設 300） |

### 回應

- Content-Type: `image/webp`
- ETag / If-None-Match 支援（304 Not Modified）
- 快取：24 小時

## GET /api/original/<id>

串流傳輸原始檔案。也支援 ZIP 封存檔內的檔案。

### 參數

| 參數 | 類型 | 說明 |
|-----------|------|-------------|
| `id` | int | 檔案 ID |

### 回應

- Content-Type：檔案的 MIME 類型
- Content-Disposition: `inline`
- 支援 Range 請求（用於影片搜尋）

## POST /api/convert

提示詞格式轉換（A1111 <-> NAI）。

### 請求

```json
{
  "prompt": "1girl, (masterpiece:1.2)",
  "direction": "a1111_to_nai"
}
```

### 回應

```json
{
  "converted": "1girl, {{masterpiece}}",
  "direction": "a1111_to_nai"
}
```

## GET /api/container-thumb-ids

容器（資料夾/ZIP）的縮圖 ID 清單，排除已快取的項目。

### 參數

| 參數 | 類型 | 說明 |
|-----------|------|-------------|
| `keys` | string | 容器鍵（逗號分隔） |
