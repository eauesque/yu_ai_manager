# Search API

文件搜索、建议和分组显示的 API。

## GET /api/search

主文件搜索端点。

### 参数

| 参数 | 类型 | 默认值 | 说明 |
|-----------|------|---------|-------------|
| `q` | string | `""` | 搜索查询（提示词中的文本、标签名） |
| `sort` | string | `"date"` | 排序方式：`date`、`name`、`size`、`rating`、`random` |
| `order` | string | `"desc"` | `asc` / `desc` |
| `offset` | int | `0` | 分页起始位置 |
| `limit` | int | `50` | 结果数量（最大 200） |
| `cursor` | string | - | 基于游标的分页令牌 |
| `meta` | string | `"all"` | 元数据类型：`all`、`a1111`、`nai`、`comfy`、`unknown` |
| `tags` | string | - | 标签筛选（逗号分隔） |
| `rating_min` | int | - | 最低评分（0-5） |
| `rating_max` | int | - | 最高评分（0-5） |
| `path` | string | - | 路径前缀筛选 |
| `ext` | string | - | 扩展名筛选（逗号分隔，如 `png,webp`） |
| `has_prompt` | bool | - | 按提示词有无筛选 |
| `collection_id` | int | - | 在合集内搜索 |
| `favorites_only` | bool | `false` | 仅收藏夹 |
| `group_by` | string | - | 分组方式：`folder`、`conversation` |

### 响应

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

按文件夹/ZIP 分组的搜索结果。

### 参数

与 `/api/search` 相同的查询参数，另外增加：

| 参数 | 类型 | 说明 |
|-----------|------|-------------|
| `group_limit` | int | 每组最大显示条目数 |

## GET /api/groups-index

文件夹和 ZIP 容器组的索引。用于搜索结果分组。

### 参数

| 参数 | 类型 | 说明 |
|-----------|------|-------------|
| `sort` | string | 排序方式：`name`、`count`、`date` |
| `order` | string | `asc` / `desc` |
| `offset` | int | 分页起始位置 |
| `limit` | int | 结果数量 |

## GET /api/group-members

指定容器内的文件 ID 列表。

### 参数

| 参数 | 类型 | 说明 |
|-----------|------|-------------|
| `key` | string | 容器键（文件夹路径或 ZIP 路径） |

## GET /api/suggest

标签和提示词自动补全。

### 参数

| 参数 | 类型 | 说明 |
|-----------|------|-------------|
| `q` | string | 输入文本 |
| `limit` | int | 建议数量（默认 10） |

### 响应

```json
{
  "suggestions": [
    { "value": "1girl", "count": 5432 },
    { "value": "1boy", "count": 1234 }
  ]
}
```

## GET /api/suggest/lora

LoRA 模型名建议。

### 参数

| 参数 | 类型 | 说明 |
|-----------|------|-------------|
| `q` | string | 输入文本 |
| `limit` | int | 建议数量 |

## GET /api/server-info

基本服务器信息。

### 响应

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
