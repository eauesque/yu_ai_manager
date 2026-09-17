# Ratings API

用于管理文件评分（1–5 星评分）的 API：设置、获取与统计。

## POST /api/ratings/set

为文件设置评分。指定 `rating=0` 可清除评分。

**速率限制**: WRITE

### 请求

```json
{
  "file_id": 42,
  "rating": 5
}
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `file_id` | int | 是 | 文件 ID（正整数） |
| `rating` | int | 是 | 评分值（0–5）。0 表示清除评分 |

### 响应

```json
{
  "file_id": 42,
  "rating": 5
}
```

## POST /api/ratings/batch-set

一次为多个文件设置评分。

**速率限制**: WRITE

### 请求

```json
{
  "items": [
    { "file_id": 1, "rating": 5 },
    { "file_id": 2, "rating": 3 }
  ]
}
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `items` | array | 是 | 评分设置列表（最多 500 条） |
| `items[].file_id` | int | 是 | 文件 ID（正整数） |
| `items[].rating` | int | 是 | 评分值（0–5） |

### 响应

```json
{
  "total": 2,
  "succeeded": 2,
  "failed": 0,
  "errors": []
}
```

## GET /api/ratings/get

获取文件的评分。未评分的文件会返回 `rating: 0`。

### 参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `file_id` | int | 是 | 文件 ID（查询参数） |

### 响应

```json
{
  "file_id": 42,
  "rating": 5
}
```

> **注意**：未评分的文件会返回 `rating: 0`。

## POST /api/ratings/batch

一次获取多个文件的评分。

### 请求

```json
{
  "file_ids": [1, 2, 3]
}
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `file_ids` | array | 是 | 文件 ID 列表 |

### 响应

```json
{
  "ratings": {
    "1": 5,
    "3": 4
  }
}
```

> **注意**：仅已评分的文件会出现在映射中。未评分的文件不会包含在响应中。

## GET /api/ratings/stats

获取所有文件的评分统计信息。

### 参数

无。

### 响应

```json
{
  "total_rated": 1234,
  "distribution": {
    "1": 50,
    "2": 100,
    "3": 300,
    "4": 500,
    "5": 284
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `total_rated` | int | 已评分文件的总数 |
| `distribution` | object | 各评分值（1–5）的文件数量 |
