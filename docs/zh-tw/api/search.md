# Search API

檔案搜尋、建議和群組顯示的 API。

## GET /api/search

主檔案搜尋端點。

### 參數

| 參數 | 類型 | 預設值 | 說明 |
|-----------|------|---------|-------------|
| `q` | string | `""` | 搜尋查詢（提示詞中的文字、標籤名稱） |
| `sort` | string | `"date"` | 排序方式：`date`、`name`、`size`、`rating`、`random` |
| `order` | string | `"desc"` | `asc` / `desc` |
| `offset` | int | `0` | 分頁起始位置 |
| `limit` | int | `50` | 結果數量（最大 200） |
| `cursor` | string | - | 基於游標的分頁權杖 |
| `meta` | string | `"all"` | 中繼資料類型：`all`、`a1111`、`nai`、`comfy`、`unknown` |
| `tags` | string | - | 標籤篩選（逗號分隔） |
| `rating_min` | int | - | 最低評分（0-5） |
| `rating_max` | int | - | 最高評分（0-5） |
| `path` | string | - | 路徑前綴篩選 |
| `ext` | string | - | 副檔名篩選（逗號分隔，如 `png,webp`） |
| `has_prompt` | bool | - | 按提示詞有無篩選 |
| `collection_id` | int | - | 在合集內搜尋 |
| `favorites_only` | bool | `false` | 僅我的最愛 |
| `group_by` | string | - | 群組方式：`folder`、`conversation` |

### 回應

```json
{
  "results": [
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
      "positive": "1girl, landscape, sunset",
      "negative": "low quality",
      "rating": 4,
      "is_favorite": true,
      "tags": ["landscape", "sunset"]
    }
  ],
  "total": 1500,
  "offset": 0,
  "limit": 50,
  "next_cursor": "eyJtdGltZSI6MTcwOTUwMDAwMCwiaWQiOjQyfQ=="
}
```

## GET /api/search-grouped

按資料夾/ZIP 分組的搜尋結果。

### 參數

與 `/api/search` 相同的查詢參數，另外新增：

| 參數 | 類型 | 說明 |
|-----------|------|-------------|
| `group_limit` | int | 每組最大顯示項目數 |

## GET /api/groups-index

資料夾和 ZIP 容器群組的索引。用於搜尋結果分組。

### 參數

| 參數 | 類型 | 說明 |
|-----------|------|-------------|
| `sort` | string | 排序方式：`name`、`count`、`date` |
| `order` | string | `asc` / `desc` |
| `offset` | int | 分頁起始位置 |
| `limit` | int | 結果數量 |

## GET /api/group-members

指定容器內的檔案 ID 清單。

### 參數

| 參數 | 類型 | 說明 |
|-----------|------|-------------|
| `key` | string | 容器鍵（資料夾路徑或 ZIP 路徑） |

## GET /api/suggest

標籤和提示詞自動補全。

### 參數

| 參數 | 類型 | 說明 |
|-----------|------|-------------|
| `q` | string | 輸入文字 |
| `limit` | int | 建議數量（預設 10） |

### 回應

```json
{
  "suggestions": [
    { "value": "1girl", "count": 5432 },
    { "value": "1boy", "count": 1234 }
  ]
}
```

## GET /api/suggest/lora

LoRA 模型名稱建議。

### 參數

| 參數 | 類型 | 說明 |
|-----------|------|-------------|
| `q` | string | 輸入文字 |
| `limit` | int | 建議數量 |

## GET /api/server-info

基本伺服器資訊。

### 回應

```json
{
  "version": "4.12.1",
  "db_path": "/path/to/tags.db",
  "file_count": 150000,
  "tag_count": 8500,
  "auth_required": false,
  "lan_ip": "192.168.1.100",
  "active_ui": "default"
}
```
