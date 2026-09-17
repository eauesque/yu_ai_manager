# Collections API

用於管理收藏集（收藏分組）的 API。

## GET /api/collections

取得所有收藏集的清單。依 `sort_order` 升序、`id` 升序排列。

### 參數

無

### 回應

```json
{
  "collections": [
    {
      "id": 1,
      "name": "Favorites",
      "sort_order": 0,
      "created_at": 1709500000,
      "count": 42,
      "is_smart": false,
      "query_json": null
    }
  ]
}
```

## POST /api/collections

建立新的收藏集。

### 速率限制

WRITE

### 請求

```json
{
  "name": "My Collection",
  "query_json": null
}
```

| 參數 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `name` | string | 是 | 收藏集名稱 |
| `query_json` | object/null | 否 | 智慧收藏集的查詢條件。省略時為一般收藏集 |

### 回應 (201)

```json
{
  "id": 2,
  "name": "My Collection",
  "is_smart": false
}
```

## PUT /api/collections/<id>

重新命名收藏集。

### 速率限制

WRITE

### 參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `id` | int | 收藏集 ID（路徑參數） |

### 請求

```json
{
  "name": "Renamed Collection"
}
```

### 回應

```json
{
  "id": 2,
  "name": "Renamed Collection"
}
```

## DELETE /api/collections/<id>

刪除收藏集。收藏集內的所有收藏項目也會一併刪除。

預設收藏集（`id=1`）無法刪除。

### 速率限制

WRITE

### 參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `id` | int | 收藏集 ID（路徑參數） |

### 回應

```json
{
  "deleted": 2
}
```

## POST /api/collections/reorder

變更收藏集的顯示順序。

### 速率限制

WRITE

### 請求

```json
{
  "ids": [3, 1, 2]
}
```

| 參數 | 型別 | 說明 |
|------|------|------|
| `ids` | int[] | 收藏集 ID 的陣列。指定的順序即為新的排序 |

### 回應

```json
{
  "ok": true
}
```

## POST /api/collections/<id>/batch-add

批次新增檔案至收藏集。具冪等性：已存在的項目會被跳過，並計為成功。

### 速率限制

WRITE

### 參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `id` | int | 收藏集 ID（路徑參數） |

### 請求

```json
{
  "file_ids": [1, 2, 3]
}
```

| 參數 | 型別 | 限制 | 說明 |
|------|------|------|------|
| `file_ids` | int[] | 最多 500 筆 | 要新增的檔案 ID 陣列 |

### 回應

```json
{
  "total": 3,
  "succeeded": 3,
  "failed": 0,
  "errors": []
}
```

## POST /api/collections/<id>/batch-remove

從收藏集批次移除檔案。

### 速率限制

WRITE

### 參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `id` | int | 收藏集 ID（路徑參數） |

### 請求

```json
{
  "file_ids": [1, 2]
}
```

| 參數 | 型別 | 限制 | 說明 |
|------|------|------|------|
| `file_ids` | int[] | 最多 500 筆 | 要移除的檔案 ID 陣列 |

### 回應

```json
{
  "total": 2,
  "succeeded": 2,
  "failed": 0,
  "errors": []
}
```

## GET /api/collections/<id>/export/csv

將收藏集內的檔案匯出為 CSV 格式。

### 參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `id` | int | 收藏集 ID（路徑參數） |

### 回應

- Content-Type: `text/csv; charset=utf-8`
- CSV 欄位: `id`, `filename`, `folder`, `path`, `meta_source`, `mtime`, `positive`, `negative`
- 收藏集不存在時回傳 404
