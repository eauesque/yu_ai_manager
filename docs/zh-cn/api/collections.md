# Collections API

用于管理收藏集（收藏分组）的 API。

## GET /api/collections

获取所有收藏集的列表。按 `sort_order` 升序、`id` 升序排列。

### 参数

无

### 响应

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

创建新的收藏集。

### 速率限制

WRITE

### 请求

```json
{
  "name": "My Collection",
  "query_json": null
}
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | 是 | 收藏集名称 |
| `query_json` | object/null | 否 | 智能收藏集的查询条件。省略时为普通收藏集 |

### 响应 (201)

```json
{
  "id": 2,
  "name": "My Collection",
  "is_smart": false
}
```

## PUT /api/collections/<id>

重命名收藏集。

### 速率限制

WRITE

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `id` | int | 收藏集 ID（路径参数） |

### 请求

```json
{
  "name": "Renamed Collection"
}
```

### 响应

```json
{
  "id": 2,
  "name": "Renamed Collection"
}
```

## DELETE /api/collections/<id>

删除收藏集。收藏集内的所有收藏条目也会一并删除。

默认收藏集（`id=1`）无法删除。

### 速率限制

WRITE

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `id` | int | 收藏集 ID（路径参数） |

### 响应

```json
{
  "deleted": 2
}
```

## POST /api/collections/reorder

更改收藏集的显示顺序。

### 速率限制

WRITE

### 请求

```json
{
  "ids": [3, 1, 2]
}
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `ids` | int[] | 收藏集 ID 的数组。指定的顺序即为新的排序 |

### 响应

```json
{
  "ok": true
}
```

## POST /api/collections/<id>/batch-add

批量添加文件到收藏集。具有幂等性：已存在的条目会被跳过，并计为成功。

### 速率限制

WRITE

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `id` | int | 收藏集 ID（路径参数） |

### 请求

```json
{
  "file_ids": [1, 2, 3]
}
```

| 参数 | 类型 | 限制 | 说明 |
|------|------|------|------|
| `file_ids` | int[] | 最多 500 条 | 要添加的文件 ID 数组 |

### 响应

```json
{
  "total": 3,
  "succeeded": 3,
  "failed": 0,
  "errors": []
}
```

## POST /api/collections/<id>/batch-remove

从收藏集批量移除文件。

### 速率限制

WRITE

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `id` | int | 收藏集 ID（路径参数） |

### 请求

```json
{
  "file_ids": [1, 2]
}
```

| 参数 | 类型 | 限制 | 说明 |
|------|------|------|------|
| `file_ids` | int[] | 最多 500 条 | 要移除的文件 ID 数组 |

### 响应

```json
{
  "total": 2,
  "succeeded": 2,
  "failed": 0,
  "errors": []
}
```

## GET /api/collections/<id>/export/csv

将收藏集内的文件导出为 CSV 格式。

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `id` | int | 收藏集 ID（路径参数） |

### 响应

- Content-Type: `text/csv; charset=utf-8`
- CSV 列: `id`, `filename`, `folder`, `path`, `meta_source`, `mtime`, `positive`, `negative`
- 收藏集不存在时返回 404
