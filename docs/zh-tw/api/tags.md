# Tags API

批次標籤操作與標籤建議/自動完成相關的 API。

## POST /api/tags/batch-set

對多個檔案批次新增或移除標籤。

### 速率限制

WRITE (約 120 req/min，突發 30)

### 請求主體

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `items` | array | 是 | 操作清單 (最多 500 筆) |
| `items[].file_id` | int | 是 | 檔案 ID (正整數) |
| `items[].add` | string[] | 否 | 要新增的標籤名稱 |
| `items[].remove` | string[] | 否 | 要移除的標籤名稱 |

- 每個項目至少需要 `add` 或 `remove` 其中之一
- 不存在的標籤會自動建立 (namespace=null)
- 透過 API 新增的標籤，其 source 會設為 `"user"`
- 孤立標籤 (不再與任何檔案關聯) 會被自動刪除

### 請求範例

```json
{
  "items": [
    {
      "file_id": 42,
      "add": ["landscape", "sunset"],
      "remove": ["lowres"]
    }
  ]
}
```

### 回應

```json
{
  "total": 1,
  "succeeded": 1,
  "failed": 0,
  "errors": []
}
```

| 欄位 | 型別 | 說明 |
|------|------|------|
| `total` | int | 處理的總筆數 |
| `succeeded` | int | 成功的筆數 |
| `failed` | int | 失敗的筆數 |
| `errors` | array | 錯誤詳情清單 |

### 錯誤

| 狀態碼 | 說明 |
|--------|------|
| 400 | 請求主體無效 (items 為空、file_id 無效、add 和 remove 皆缺失等) |
| 429 | 超過速率限制 |

---

## GET /api/tags/suggest

回傳與搜尋字串部分匹配的標籤候選。用於自動完成功能。

### 參數

| 參數 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `q` | string | 是 | 搜尋字串 |
| `limit` | int | 否 | 回傳結果的上限 (預設：20，最大：100) |

- 搜尋不區分大小寫 (LIKE %q%)
- 結果依 `file_count` 降序排列
- `q` 為空時回傳空陣列

### 回應

```json
{
  "data": [
    { "id": 1, "tag": "landscape", "namespace": null, "file_count": 150 },
    { "id": 2, "tag": "1girl", "namespace": null, "file_count": 3420 }
  ]
}
```

| 欄位 | 型別 | 說明 |
|------|------|------|
| `data[].id` | int | 標籤 ID |
| `data[].tag` | string | 標籤名稱 |
| `data[].namespace` | string\|null | 命名空間 (通常為 null) |
| `data[].file_count` | int | 與此標籤關聯的檔案數 |
