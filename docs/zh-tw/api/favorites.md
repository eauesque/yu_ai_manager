# Favorites API

新增、移除、檢查及列出收藏檔案的 API。

## POST /api/favorites/toggle

切換檔案的收藏狀態。若尚未收藏則新增，若已收藏則移除。

- **速率限制**: WRITE

### 請求主體

| 參數 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `file_id` | int | 是 | 目標檔案 ID（正整數） |
| `collection_id` | int | 否 | 收藏集 ID（預設值: 1） |

```json
{
  "file_id": 42,
  "collection_id": 1
}
```

### 回應

```json
{
  "file_id": 42,
  "collection_id": 1,
  "favorited": true
}
```

| 欄位 | 型別 | 說明 |
|------|------|------|
| `file_id` | int | 目標檔案 ID |
| `collection_id` | int | 收藏集 ID |
| `favorited` | bool | 切換後的狀態。`true` = 已新增、`false` = 已移除 |

## GET /api/favorites/check

傳回指定的檔案 ID 中已被收藏的項目。

### 參數

| 參數 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `ids` | string | 是 | 以逗號分隔的檔案 ID（例如 `1,2,3`） |
| `collection_id` | int | 否 | 篩選特定收藏集 |

### 回應

```json
{
  "favorites": [1, 3]
}
```

| 欄位 | 型別 | 說明 |
|------|------|------|
| `favorites` | int[] | 已收藏的檔案 ID 陣列 |

## GET /api/favorites/check_collections

傳回包含指定檔案的收藏集 ID 列表。

### 參數

| 參數 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `file_id` | int | 是 | 目標檔案 ID |

### 回應

```json
{
  "collections": [1, 3]
}
```

| 欄位 | 型別 | 說明 |
|------|------|------|
| `collections` | int[] | 包含此檔案的收藏集 ID 陣列 |

## GET /api/favorites/list

取得收藏檔案 ID 的列表。結果按新增日期降序排列，已邏輯刪除的檔案將被排除。

### 參數

| 參數 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `collection_id` | int | 否 | 篩選特定收藏集 |

### 回應

```json
{
  "ids": [42, 55, 67]
}
```

| 欄位 | 型別 | 說明 |
|------|------|------|
| `ids` | int[] | 收藏檔案 ID 的陣列（依 `added_at` 降序排列） |
