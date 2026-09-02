# Settings API

管理应用程序设置、密钥加密，以及外部密码管理器集成（1Password / Bitwarden）的 API。

密钥值在 GET 响应中一律以掩码形式（`****`）返回。`source` 字段表示该值从哪个后端解析而来。

## 认证

所有端点均需要 PIN 认证或 API Key 认证。

---

## GET /api/settings/schema

获取完整的设置结构定义。返回所有设置的键名、类型、默认值、分类及其他元数据。

### 参数

无

### 响应

```json
{
  "schema": [
    {
      "key": "pin",
      "type": "str",
      "default": "",
      "category": "security",
      "secret": true,
      "label": "PIN Code"
    }
  ]
}
```

| 字段 | 类型 | 说明 |
|-------|------|-------------|
| `key` | string | 设置键（以点号分隔，例如 `github.token`） |
| `type` | string | 值类型（`str`、`int`、`float`、`bool`） |
| `default` | any | 默认值 |
| `category` | string | 分类名称 |
| `secret` | bool | 是否为密钥值 |
| `label` | string | 显示标签 |

---

## GET /api/settings/all

获取所有设置值。密钥值以掩码形式返回。

### 参数

无

### 响应

```json
{
  "settings": [
    {
      "key": "pin",
      "value": "****",
      "source": "encrypted",
      "secret": true,
      "category": "security"
    },
    {
      "key": "theme",
      "value": "dark",
      "source": "config",
      "secret": false,
      "category": "appearance"
    }
  ]
}
```

| 字段 | 类型 | 说明 |
|-------|------|-------------|
| `key` | string | 设置键 |
| `value` | any | 当前值（密钥值会被掩码） |
| `source` | string | 值来源：`default` / `config` / `encrypted` / `1password` / `bitwarden` |
| `secret` | bool | 是否为密钥值 |
| `category` | string | 分类名称 |

---

## GET /api/settings/\<key\>

获取单个设置值。键使用以点号分隔的路径格式（例如 `github.token`）。

### 参数

| 参数 | 类型 | 说明 |
|-----------|------|-------------|
| `key` | string | 设置键（路径参数） |

### 响应

```json
{
  "key": "github.token",
  "value": "****",
  "source": "1password",
  "secret": true,
  "category": "integrations"
}
```

### 错误

| 状态码 | 代码 | 说明 |
|--------|------|-------------|
| 404 | `not_found` | 未知的设置键 |

---

## PUT /api/settings/\<key\>

更新设置值。密钥值会自动加密。可选择指定 1Password URI 以在外部管理密钥。

### Rate Limit

DESTRUCTIVE

### 参数

| 参数 | 类型 | 说明 |
|-----------|------|-------------|
| `key` | string | 设置键（路径参数） |

### 请求

```json
{
  "value": "new-value",
  "op_uri": "op://vault/item/field"
}
```

| 参数 | 类型 | 必填 | 说明 |
|-----------|------|----------|-------------|
| `value` | any | 是 | 要设置的值。自动转换为结构定义中的类型 |
| `op_uri` | string | 否 | 1Password URI。指定时会保存 `op_secrets` 映射而非直接保存值 |

### 响应

```json
{
  "key": "github.token",
  "updated": true
}
```

### 错误

| 状态码 | 代码 | 说明 |
|--------|------|-------------|
| 400 | `bad_request` | 请求主体缺少 `value` |
| 404 | `not_found` | 未知的设置键 |

---

## GET /api/settings/secrets/status

获取加密密钥后端状态。显示当前使用的密钥管理方式。

### 参数

无

### 响应

```json
{
  "backend": "keychain",
  "available": true,
  "keychain_supported": true
}
```

| 字段 | 类型 | 说明 |
|-------|------|-------------|
| `backend` | string | 当前的密钥后端（`keychain` / `passphrase` / `file`） |
| `available` | bool | 加密是否可用 |
| `keychain_supported` | bool | 是否支持 OS keychain |

---

## POST /api/settings/secrets/export

将加密密钥导出为受密码保护的 JSON。用于备份或迁移至其他环境。

### Rate Limit

DESTRUCTIVE

### 请求

```json
{
  "password": "my-export-password"
}
```

| 参数 | 类型 | 必填 | 说明 |
|-----------|------|----------|-------------|
| `password` | string | 是 | 用于保护导出数据的密码 |

### 响应

```json
{
  "success": true,
  "export_data": "base64-encoded-encrypted-key-data"
}
```

### 错误

| 状态码 | 代码 | 说明 |
|--------|------|-------------|
| 400 | `bad_request` | 请求主体缺少 `password` |
| 400 | `export_failed` | 导出操作失败 |

---

## POST /api/settings/secrets/import

从先前导出的数据导入加密密钥。

### Rate Limit

DESTRUCTIVE

### 请求

```json
{
  "export_data": "base64-encoded-encrypted-key-data",
  "password": "my-export-password"
}
```

| 参数 | 类型 | 必填 | 说明 |
|-----------|------|----------|-------------|
| `export_data` | string | 是 | 导出时获取的数据 |
| `password` | string | 是 | 导出时设置的密码 |

### 响应

```json
{
  "success": true,
  "message": "Key imported successfully"
}
```

### 错误

| 状态码 | 代码 | 说明 |
|--------|------|-------------|
| 400 | `bad_request` | 缺少 `export_data` 或 `password` |
| 400 | `import_failed` | 密码错误或数据损坏 |

---

## POST /api/settings/secrets/migrate-keychain

将加密密钥从文件后端迁移至 OS keychain。支持 macOS Keychain、Windows Credential Manager 和 Linux Secret Service。

### Rate Limit

DESTRUCTIVE

### 请求

无（不需要请求主体）

### 响应

```json
{
  "success": true,
  "message": "Key migrated to OS keychain"
}
```

### 错误

| 状态码 | 代码 | 说明 |
|--------|------|-------------|
| 400 | `migration_failed` | keychain 不可用或迁移失败 |

---

## GET /api/settings/op-status

获取 1Password CLI（`op`）连接状态。

### 参数

无

### 响应

```json
{
  "available": true,
  "signed_in": true,
  "version": "2.24.0"
}
```

| 字段 | 类型 | 说明 |
|-------|------|-------------|
| `available` | bool | `op` 命令是否存在于 PATH |
| `signed_in` | bool | 是否已登录 1Password |
| `version` | string | `op` CLI 版本 |

---

## GET /api/settings/secrets/op-vaults

列出可用的 1Password vault。

### 参数

无

### 响应

```json
{
  "vaults": [
    {
      "id": "abc123",
      "name": "Personal"
    }
  ]
}
```

### 错误

| 状态码 | 代码 | 说明 |
|--------|------|-------------|
| 503 | `op_unavailable` | 1Password CLI 不可用 |

---

## POST /api/settings/secrets/push-to-op

将所有密钥设置批量写入 1Password，并在 config.json 中保存 `op_secrets` 映射。

### Rate Limit

DESTRUCTIVE

### 请求

```json
{
  "vault": "Personal",
  "item_title": "YU AI Manager",
  "remove_local": false
}
```

| 参数 | 类型 | 必填 | 说明 |
|-----------|------|----------|-------------|
| `vault` | string | 是 | 目标 1Password vault 名称 |
| `item_title` | string | 否 | 1Password 项目标题。默认：`YU AI Manager` |
| `remove_local` | bool | 否 | 若为 `true`，推送后从 config.json 移除本地加密值。默认：`false` |

### 响应

```json
{
  "message": "2 secrets pushed to 1Password",
  "pushed_keys": ["github.token", "pin"],
  "uris": {
    "github.token": "op://Personal/YU AI Manager/github.token",
    "pin": "op://Personal/YU AI Manager/pin"
  },
  "remove_local": false
}
```

### 错误

| 状态码 | 代码 | 说明 |
|--------|------|-------------|
| 400 | `bad_request` | 缺少 `vault` |
| 400 | `no_secrets` | 无密钥可推送 |
| 500 | `op_push_failed` | 写入 1Password 失败 |
| 503 | `op_unavailable` | 1Password CLI 不可用 |

---

## DELETE /api/settings/op-mapping/\<key\>

移除 1Password URI 映射，恢复为本地加密。

### Rate Limit

WRITE

### 参数

| 参数 | 类型 | 说明 |
|-----------|------|-------------|
| `key` | string | 设置键（路径参数） |

### 响应

```json
{
  "key": "github.token",
  "unlinked": true
}
```

### 错误

| 状态码 | 代码 | 说明 |
|--------|------|-------------|
| 404 | `not_found` | 在 `op_secrets` 映射中未找到该键 |

---

## GET /api/settings/bw-status

获取 Bitwarden CLI（`bw`）连接状态。

### 参数

无

### 响应

```json
{
  "available": true,
  "status": "unlocked"
}
```

| 字段 | 类型 | 说明 |
|-------|------|-------------|
| `available` | bool | `bw` 命令是否存在于 PATH |
| `status` | string | Bitwarden 会话状态 |

---

## GET /api/settings/secrets/bw-folders

列出可用的 Bitwarden 文件夹。

### 参数

无

### 响应

```json
{
  "folders": [
    {
      "id": "folder-uuid",
      "name": "Development"
    }
  ]
}
```

### 错误

| 状态码 | 代码 | 说明 |
|--------|------|-------------|
| 503 | `bw_unavailable` | Bitwarden CLI 不可用 |

---

## POST /api/settings/secrets/push-to-bw

将所有密钥设置批量写入 Bitwarden，并在 config.json 中保存 `bw_secrets` 映射。

### Rate Limit

WRITE

### 请求

```json
{
  "folder_id": "folder-uuid",
  "item_name": "YU AI Manager"
}
```

| 参数 | 类型 | 必填 | 说明 |
|-----------|------|----------|-------------|
| `folder_id` | string/null | 否 | 目标 Bitwarden 文件夹 ID。省略则不指定文件夹 |
| `item_name` | string | 否 | Bitwarden 项目名称。默认：`YU AI Manager` |

### 响应

```json
{
  "message": "2 secrets pushed to Bitwarden",
  "pushed_keys": ["github.token", "pin"],
  "mappings": {
    "github.token": {"item_id": "item-uuid", "field": "github.token"},
    "pin": {"item_id": "item-uuid", "field": "pin"}
  }
}
```

### 错误

| 状态码 | 代码 | 说明 |
|--------|------|-------------|
| 400 | `no_secrets` | 无密钥可推送 |
| 500 | `bw_push_failed` | 写入 Bitwarden 失败 |
| 503 | `bw_unavailable` | Bitwarden CLI 不可用 |

---

## DELETE /api/settings/bw-mapping/\<key\>

移除 Bitwarden 映射，恢复为本地加密。

### Rate Limit

WRITE

### 参数

| 参数 | 类型 | 说明 |
|-----------|------|-------------|
| `key` | string | 设置键（路径参数） |

### 响应

```json
{
  "key": "github.token",
  "unlinked": true
}
```

### 错误

| 状态码 | 代码 | 说明 |
|--------|------|-------------|
| 404 | `not_found` | 在 `bw_secrets` 映射中未找到该键 |
