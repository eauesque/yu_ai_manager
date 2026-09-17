# Debug API

用于调试和诊断的内部 API。用于检查文件元数据、确认模型信息以及管理已扫描的根目录。

这些端点没有前端 UI，主要用于开发和故障排查。

## GET /api/debug/file-meta/<file_id>

检查文件的详细元数据。返回存储在数据库中的元数据，对于 ZIP 压缩包内的文件，还会返回重新提取的结果。

### Authentication

PIN 会话或 API Key

### Parameters

| 参数 | 类型 | 说明 |
|------|------|------|
| `file_id` | int | 文件 ID（路径参数） |

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

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | int | 文件 ID |
| `path` | string | 文件路径 |
| `meta_source` | string | 元数据来源（`a1111_png`、`novelai_v4_png` 等） |
| `parser_version` | int | 解析器版本 |
| `format` | string | 模板格式 |
| `model_name` | string/null | 模型名称 |
| `raw_prompt_length` | int | 原始提示词的字符数 |
| `raw_prompt_preview` | string | 原始提示词的前 300 个字符 |
| `raw_negative_preview` | string | 负面提示词的前 300 个字符 |
| `raw_meta_json_length` | int | 原始元数据 JSON 的字符数 |
| `raw_meta_json_preview` | string | 原始元数据 JSON 的前 500 个字符 |
| `has_v4_prompt` | bool | 是否包含 NovelAI V4 提示词 |
| `has_comment` | bool | 是否包含 Comment 字段 |

对于 ZIP 压缩包内的文件，会添加 `fresh_extract` 字段，包含重新提取的结果：

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

| 状态码 | 说明 |
|--------|------|
| 404 | 找不到文件 |

## GET /api/debug/model-check

检查 templates 表中 `model_name` 的存储状态。返回有模型名称和无模型名称的记录统计及样本。

### Authentication

PIN 会话或 API Key

### Parameters

无

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

| 字段 | 类型 | 说明 |
|------|------|------|
| `total_templates` | int | 模板总数 |
| `with_model_name` | int | 已设置模型名称的记录数 |
| `without_model_name` | int | 未设置模型名称的记录数 |
| `samples_with_model` | array | 有模型名称的样本（最多 10 条） |
| `samples_without_model` | array | 无模型名称的样本（最多 5 条） |

## GET /api/scanned-roots

从数据库中已注册的文件提取根目录，并返回包含文件数量的结果。同时汇总已配置的扫描根目录和不属于任何已配置根目录的文件所在根目录。

### Authentication

PIN 会话或 API Key

### Parameters

无

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

| 字段 | 类型 | 说明 |
|------|------|------|
| `roots` | array | 根目录数组（按文件数量降序排列，最多 50 条） |
| `roots[].path` | string | 目录路径 |
| `roots[].count` | int | 该路径下的文件数量 |

### Errors

| 状态码 | 说明 |
|--------|------|
| 500 | 无法计算根目录摘要 |

## POST /api/debug/query

执行只读 SQL 查询。需要 `YU_DEBUG_MODE=1` 环境变量，且仅允许从 localhost 访问。

### Rate Limit

WRITE

### Authentication

PIN 会话或 API Key（仅限 localhost + `YU_DEBUG_MODE=1`）

### Request

```json
{
  "sql": "SELECT id, path, meta_source FROM files LIMIT 10",
  "limit": 100
}
```

| 参数 | 类型 | 必须 | 说明 |
|------|------|------|------|
| `sql` | string | 是 | 要执行的 SELECT 语句 |
| `limit` | int | 否 | 返回的最大行数（默认：100，最大：10000） |

### 限制条件

- 仅允许 SELECT 语句（INSERT、UPDATE、DELETE 等会被拒绝）
- 不允许多个语句（以分号分隔的多条查询）
- 包含写入关键字（DROP、ALTER、CREATE 等）的查询会被拒绝

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

| 字段 | 类型 | 说明 |
|------|------|------|
| `columns` | string[] | 列名数组 |
| `rows` | object[] | 结果行（每行为以列名为键的对象） |
| `row_count` | int | 返回的行数 |
| `truncated` | bool | 如果结果被 limit 截断则为 `true` |

### Errors

| 状态码 | 说明 |
|--------|------|
| 400 | SQL 为空、多个语句、非 SELECT 查询、包含写入操作、SQL 语法错误 |
| 403 | Debug 模式未启用，或非从 localhost 访问 |

## POST /api/scanned-roots/purge

从数据库永久删除指定路径下的所有文件记录。相关记录（标签、模板等）会被级联删除。未使用的标签会被自动清理。

### Rate Limit

DESTRUCTIVE

### Authentication

PIN 会话或 API Key

### Request

```json
{
  "path": "C:\\Images\\OldFolder"
}
```

| 参数 | 类型 | 必须 | 说明 |
|------|------|------|------|
| `path` | string | 是 | 要清除的根路径。该路径下的所有文件将被删除 |

### Response

```json
{
  "purged": 150,
  "path": "C:\\Images\\OldFolder"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `purged` | int | 已删除的文件记录数 |
| `path` | string | 指定的路径 |

### Errors

| 状态码 | 说明 |
|--------|------|
| 400 | 未指定路径 |
| 500 | 清除操作失败 |
