# Favorites API

添加、移除、检查及列出收藏文件的 API。

## POST /api/favorites/toggle

切换文件的收藏状态。若尚未收藏则添加，若已收藏则移除。

- **速率限制**: WRITE

### 请求体

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `file_id` | int | 是 | 目标文件 ID（正整数） |
| `collection_id` | int | 否 | 收藏集 ID（默认值: 1） |

```json
{
  "file_id": 42,
  "collection_id": 1
}
```

### 响应

```json
{
  "file_id": 42,
  "collection_id": 1,
  "favorited": true
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `file_id` | int | 目标文件 ID |
| `collection_id` | int | 收藏集 ID |
| `favorited` | bool | 切换后的状态。`true` = 已添加、`false` = 已移除 |

## GET /api/favorites/check

返回指定的文件 ID 中已被收藏的项目。

### 参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `ids` | string | 是 | 以逗号分隔的文件 ID（例如 `1,2,3`） |
| `collection_id` | int | 否 | 筛选特定收藏集 |

### 响应

```json
{
  "favorites": [1, 3]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `favorites` | int[] | 已收藏的文件 ID 数组 |

## GET /api/favorites/check_collections

返回包含指定文件的收藏集 ID 列表。

### 参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `file_id` | int | 是 | 目标文件 ID |

### 响应

```json
{
  "collections": [1, 3]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `collections` | int[] | 包含此文件的收藏集 ID 数组 |

## GET /api/favorites/list

获取收藏文件 ID 的列表。结果按添加日期降序排列，已逻辑删除的文件将被排除。

### 参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `collection_id` | int | 否 | 筛选特定收藏集 |

### 响应

```json
{
  "ids": [42, 55, 67]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `ids` | int[] | 收藏文件 ID 的数组（按 `added_at` 降序排列） |
