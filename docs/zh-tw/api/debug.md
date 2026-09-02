# Debug API

用於除錯和診斷的內部 API。用於檢查檔案中繼資料、確認模型資訊以及管理已掃描的根目錄。

這些端點沒有前端 UI，主要用於開發和疑難排解。

## GET /api/debug/file-meta/<file_id>

檢查檔案的詳細中繼資料。回傳儲存在資料庫中的中繼資料，對於 ZIP 壓縮檔內的檔案，還會回傳重新擷取的結果。

### Authentication

PIN 工作階段或 API Key

### Parameters

| 參數 | 型別 | 說明 |
|------|------|------|
| `file_id` | int | 檔案 ID（路徑參數） |

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

| 欄位 | 型別 | 說明 |
|------|------|------|
| `id` | int | 檔案 ID |
| `path` | string | 檔案路徑 |
| `meta_source` | string | 中繼資料來源（`a1111_png`、`novelai_v4_png` 等） |
| `parser_version` | int | 解析器版本 |
| `format` | string | 範本格式 |
| `model_name` | string/null | 模型名稱 |
| `raw_prompt_length` | int | 原始提示詞的字元數 |
| `raw_prompt_preview` | string | 原始提示詞的前 300 個字元 |
| `raw_negative_preview` | string | 負面提示詞的前 300 個字元 |
| `raw_meta_json_length` | int | 原始中繼資料 JSON 的字元數 |
| `raw_meta_json_preview` | string | 原始中繼資料 JSON 的前 500 個字元 |
| `has_v4_prompt` | bool | 是否包含 NovelAI V4 提示詞 |
| `has_comment` | bool | 是否包含 Comment 欄位 |

對於 ZIP 壓縮檔內的檔案，會新增 `fresh_extract` 欄位，包含重新擷取的結果：

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

| 狀態碼 | 說明 |
|--------|------|
| 404 | 找不到檔案 |

## GET /api/debug/model-check

檢查 templates 資料表中 `model_name` 的儲存狀態。回傳有模型名稱和無模型名稱的記錄統計及樣本。

### Authentication

PIN 工作階段或 API Key

### Parameters

無

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

| 欄位 | 型別 | 說明 |
|------|------|------|
| `total_templates` | int | 範本總數 |
| `with_model_name` | int | 已設定模型名稱的記錄數 |
| `without_model_name` | int | 未設定模型名稱的記錄數 |
| `samples_with_model` | array | 有模型名稱的樣本（最多 10 筆） |
| `samples_without_model` | array | 無模型名稱的樣本（最多 5 筆） |

## GET /api/scanned-roots

從資料庫中已註冊的檔案提取根目錄，並回傳包含檔案數量的結果。同時彙整已設定的掃描根目錄和不屬於任何已設定根目錄的檔案所在根目錄。

### Authentication

PIN 工作階段或 API Key

### Parameters

無

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

| 欄位 | 型別 | 說明 |
|------|------|------|
| `roots` | array | 根目錄陣列（按檔案數量降序排列，最多 50 筆） |
| `roots[].path` | string | 目錄路徑 |
| `roots[].count` | int | 該路徑下的檔案數量 |

### Errors

| 狀態碼 | 說明 |
|--------|------|
| 500 | 無法計算根目錄摘要 |

## POST /api/debug/query

執行唯讀 SQL 查詢。需要 `YU_DEBUG_MODE=1` 環境變數，且僅允許從 localhost 存取。

### Rate Limit

WRITE

### Authentication

PIN 工作階段或 API Key（僅限 localhost + `YU_DEBUG_MODE=1`）

### Request

```json
{
  "sql": "SELECT id, path, meta_source FROM files LIMIT 10",
  "limit": 100
}
```

| 參數 | 型別 | 必須 | 說明 |
|------|------|------|------|
| `sql` | string | 是 | 要執行的 SELECT 陳述式 |
| `limit` | int | 否 | 回傳的最大列數（預設：100，最大：10000） |

### 限制條件

- 僅允許 SELECT 陳述式（INSERT、UPDATE、DELETE 等會被拒絕）
- 不允許多個陳述式（以分號分隔的多條查詢）
- 包含寫入關鍵字（DROP、ALTER、CREATE 等）的查詢會被拒絕

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

| 欄位 | 型別 | 說明 |
|------|------|------|
| `columns` | string[] | 欄位名稱陣列 |
| `rows` | object[] | 結果列（每列為以欄位名稱為鍵的物件） |
| `row_count` | int | 回傳的列數 |
| `truncated` | bool | 如果結果被 limit 截斷則為 `true` |

### Errors

| 狀態碼 | 說明 |
|--------|------|
| 400 | SQL 為空、多個陳述式、非 SELECT 查詢、包含寫入操作、SQL 語法錯誤 |
| 403 | Debug 模式未啟用，或非從 localhost 存取 |

## POST /api/scanned-roots/purge

從資料庫永久刪除指定路徑下的所有檔案記錄。相關記錄（標籤、範本等）會被串聯刪除。未使用的標籤會被自動清除。

### Rate Limit

DESTRUCTIVE

### Authentication

PIN 工作階段或 API Key

### Request

```json
{
  "path": "C:\\Images\\OldFolder"
}
```

| 參數 | 型別 | 必須 | 說明 |
|------|------|------|------|
| `path` | string | 是 | 要清除的根路徑。該路徑下的所有檔案將被刪除 |

### Response

```json
{
  "purged": 150,
  "path": "C:\\Images\\OldFolder"
}
```

| 欄位 | 型別 | 說明 |
|------|------|------|
| `purged` | int | 已刪除的檔案記錄數 |
| `path` | string | 指定的路徑 |

### Errors

| 狀態碼 | 說明 |
|--------|------|
| 400 | 未指定路徑 |
| 500 | 清除操作失敗 |
