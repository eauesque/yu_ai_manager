# Tags API

批量标签操作与标签建议/自动补全相关的 API。

## POST /api/tags/batch-set

对多个文件批量添加或移除标签。

### 速率限制

WRITE (约 120 req/min，突发 30)

### 请求体

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `items` | array | 是 | 操作列表 (最多 500 条) |
| `items[].file_id` | int | 是 | 文件 ID (正整数) |
| `items[].add` | string[] | 否 | 要添加的标签名称 |
| `items[].remove` | string[] | 否 | 要移除的标签名称 |

- 每个项目至少需要 `add` 或 `remove` 其中之一
- 不存在的标签会自动创建 (namespace=null)
- 通过 API 添加的标签，其 source 会设为 `"user"`
- 孤立标签 (不再与任何文件关联) 会被自动删除

### 请求示例

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

### 响应

```json
{
  "total": 1,
  "succeeded": 1,
  "failed": 0,
  "errors": []
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `total` | int | 处理的总条数 |
| `succeeded` | int | 成功的条数 |
| `failed` | int | 失败的条数 |
| `errors` | array | 错误详情列表 |

### 错误

| 状态码 | 说明 |
|--------|------|
| 400 | 请求体无效 (items 为空、file_id 无效、add 和 remove 均缺失等) |
| 429 | 超过速率限制 |

---

## GET /api/tags/suggest

返回与搜索字符串部分匹配的标签候选。用于自动补全功能。

### 参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `q` | string | 是 | 搜索字符串 |
| `limit` | int | 否 | 返回结果的上限 (默认：20，最大：100) |

- 搜索不区分大小写 (LIKE %q%)
- 结果按 `file_count` 降序排列
- `q` 为空时返回空数组

### 响应

```json
{
  "data": [
    { "id": 1, "tag": "landscape", "namespace": null, "file_count": 150 },
    { "id": 2, "tag": "1girl", "namespace": null, "file_count": 3420 }
  ]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `data[].id` | int | 标签 ID |
| `data[].tag` | string | 标签名称 |
| `data[].namespace` | string\|null | 命名空间 (通常为 null) |
| `data[].file_count` | int | 与此标签关联的文件数 |
