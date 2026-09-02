# API Keys API

用于创建、列出和删除 API Key 的 API。所有端点都需要 PIN 会话认证。

API Key 以 `sk_` + 32 个十六进制字符（128 位）的格式生成。服务器端仅存储哈希值；原始密钥只在创建时返回一次。

## Scopes

API Key 可以指定 scope 来限制可访问的端点。未指定 scope 的密钥默认为只读访问。

| Scope | 说明 |
|-------|------|
| `read` | 搜索、文件详情、缩略图、统计 |
| `rate` | 评分的获取/设置/批量操作 |
| `tag.write` | 标签的添加/移除 |
| `collection.write` | 收藏集的创建/更新/删除、批量添加、收藏夹 |
| `annotate` | 注解的读取/写入/删除 |
| `scan` | 扫描的启动/取消/恢复 |
| `admin` | API Key 管理、设置、备份/恢复 |

## POST /api/apikeys

创建新的 API Key。

### Rate Limit

WRITE（scope: `admin`）

### Authentication

PIN 会话或具有 `admin` scope 的 API Key

### Request

```json
{
  "label": "My Integration",
  "scopes": ["read", "rate"]
}
```

| 参数 | 类型 | 必须 | 说明 |
|------|------|------|------|
| `label` | string | 否 | 密钥的识别标签。省略时默认为 `Key <timestamp>` |
| `scopes` | string[] | 否 | Scope 数组。省略或传空数组表示只读访问 |

### Response (201)

```json
{
  "id": "ak_1a2b3c4d5e6f7890",
  "key": "sk_abcdef1234567890abcdef1234567890",
  "key_prefix": "sk_abcdef12",
  "label": "My Integration",
  "created_at": 1709500000,
  "scopes": ["read", "rate"]
}
```

> **注意**：`key` 字段仅在创建响应中包含。此值无法再次获取，请保存在安全的位置。

### Errors

| 状态码 | 说明 |
|--------|------|
| 400 | 指定了无效的 scope |

## GET /api/apikeys

列出所有 API Key。不包含哈希值；仅返回前缀。

### Authentication

PIN 会话或具有 `admin` scope 的 API Key

### Parameters

无

### Response

```json
{
  "keys": [
    {
      "id": "ak_1a2b3c4d5e6f7890",
      "key_prefix": "sk_abcdef12",
      "label": "My Integration",
      "created_at": 1709500000,
      "last_used_at": 1709600000,
      "scopes": ["read", "rate"]
    }
  ]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | Key ID（`ak_` 前缀） |
| `key_prefix` | string | 密钥的前 10 个字符（用于识别） |
| `label` | string | 用户定义的标签 |
| `created_at` | int | 创建时间（Unix 时间戳） |
| `last_used_at` | int/null | 最后使用时间。未使用过则为 `null` |
| `scopes` | string[] | 指定的 scope。未设置 scope 时此字段省略 |

## DELETE /api/apikeys/<key_id>

删除（撤销）API Key。

### Rate Limit

WRITE（scope: `admin`）

### Authentication

PIN 会话或具有 `admin` scope 的 API Key

### Parameters

| 参数 | 类型 | 说明 |
|------|------|------|
| `key_id` | string | API Key ID（路径参数） |

### Response

```json
{
  "deleted": "ak_1a2b3c4d5e6f7890"
}
```

### Errors

| 状态码 | 说明 |
|--------|------|
| 404 | 找不到指定 ID 的密钥 |

## 使用 API Key

通过 `Authorization` 标头使用创建的 API Key：

```
Authorization: Bearer sk_abcdef1234567890abcdef1234567890
```

使用 API Key 认证的请求不需要 CSRF 标头（`X-Requested-With`）。
