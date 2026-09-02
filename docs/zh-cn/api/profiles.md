# Profiles API

配置文件管理 API。Profile 是应用程序设置的命名快照，存储为 `profiles/<name>.json`。

所有端点需要 PIN 认证。PIN 认证禁用时返回 403，会话未认证时返回 401。

## Profile 名称规则

- 1 至 64 个字符
- 允许的字符：`a-zA-Z0-9_-`

---

## GET /api/profiles

列出所有 Profile 的元数据。按收藏优先排序，然后按标签字母顺序排列。

### 参数

无

### 响应

```json
{
  "profiles": [
    {
      "name": "default",
      "label": "Default",
      "description": "Standard configuration",
      "favorite": true,
      "last_used_at": "2026-03-20T12:00:00Z",
      "created_at": "2026-01-01T00:00:00Z",
      "db": null,
      "is_active": true
    }
  ]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | string | Profile 名称（用作文件名） |
| `label` | string | 显示标签 |
| `description` | string | 说明文字 |
| `favorite` | boolean | 收藏标志 |
| `last_used_at` | string/null | 最后使用时间戳（ISO 8601） |
| `created_at` | string/null | 创建时间戳（ISO 8601） |
| `db` | string/null | 关联的数据库路径 |
| `is_active` | boolean | 是否为当前使用中的 Profile |

## GET /api/profiles/\<name\>

获取指定 Profile 的完整数据。

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `name` | string | Profile 名称（路径参数） |

### 响应

```json
{
  "profile": {
    "name": "default",
    "label": "Default",
    "description": "Standard configuration",
    "favorite": false,
    "created_at": "2026-01-01T00:00:00Z",
    "last_used_at": "2026-03-20T12:00:00Z",
    "is_active": true
  }
}
```

### 错误

| 代码 | 状态码 | 说明 |
|------|--------|------|
| `invalid_profile_name` | 400 | Profile 名称无效 |
| `profile_not_found` | 404 | Profile 不存在 |

## POST /api/profiles

创建新的 Profile。

### Rate Limit

WRITE

### 请求

```json
{
  "name": "my_profile",
  "label": "My Profile",
  "description": "Custom settings",
  "base_config": {}
}
```

| 参数 | 类型 | 是否必填 | 说明 |
|------|------|----------|------|
| `name` | string | 是 | Profile 名称（`a-zA-Z0-9_-`，1-64 字符） |
| `label` | string | 否 | 显示标签。省略时默认为 `name` |
| `description` | string | 否 | 说明文字 |
| `base_config` | object | 否 | 初始配置值。元数据键（`name`、`label`、`description`、`favorite`、`last_used_at`、`created_at`、`db`）以外的键会被复制到 Profile 中 |

### 响应 (201)

```json
{
  "profile": {
    "name": "my_profile",
    "label": "My Profile",
    "description": "Custom settings",
    "favorite": false,
    "created_at": "2026-03-22T00:00:00Z",
    "last_used_at": null
  }
}
```

### 错误

| 代码 | 状态码 | 说明 |
|------|--------|------|
| `invalid_profile_name` | 400 | Profile 名称无效 |
| `invalid_label` | 400 | 标签为空 |
| `profile_exists` | 409 | 同名的 Profile 已存在 |

## PUT /api/profiles/\<name\>

更新 Profile 元数据。仅可更改 `label`、`description` 和 `favorite`。

### Rate Limit

WRITE

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `name` | string | Profile 名称（路径参数） |

### 请求

```json
{
  "label": "Updated Label",
  "description": "Updated description",
  "favorite": true
}
```

| 参数 | 类型 | 是否必填 | 说明 |
|------|------|----------|------|
| `label` | string | 否 | 显示标签 |
| `description` | string | 否 | 说明文字 |
| `favorite` | boolean | 否 | 收藏标志 |

至少需要提供一个字段。

### 响应

```json
{
  "profile": {
    "name": "my_profile",
    "label": "Updated Label",
    "description": "Updated description",
    "favorite": true,
    "created_at": "2026-03-22T00:00:00Z",
    "last_used_at": null
  }
}
```

### 错误

| 代码 | 状态码 | 说明 |
|------|--------|------|
| `empty_update` | 400 | 未指定要更新的字段 |
| `update_failed` | 400 | 找不到 Profile 等 |

## DELETE /api/profiles/\<name\>

删除 Profile。无法删除当前使用中的 Profile。

### Rate Limit

WRITE

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `name` | string | Profile 名称（路径参数） |

### 响应

```json
{
  "deleted": "my_profile"
}
```

### 错误

| 代码 | 状态码 | 说明 |
|------|--------|------|
| `delete_active` | 400 | 无法删除使用中的 Profile |
| `delete_failed` | 400 | 找不到 Profile 等 |

## POST /api/profiles/\<name\>/duplicate

以新名称复制 Profile。

### Rate Limit

WRITE

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `name` | string | 源 Profile 名称（路径参数） |

### 请求

```json
{
  "new_name": "copied_profile",
  "new_label": "Copied Profile"
}
```

| 参数 | 类型 | 是否必填 | 说明 |
|------|------|----------|------|
| `new_name` | string | 是 | 新的 Profile 名称 |
| `new_label` | string | 否 | 新的显示标签。省略时默认为 `new_name` |

### 响应 (201)

```json
{
  "profile": {
    "name": "copied_profile",
    "label": "Copied Profile",
    "description": "Custom settings",
    "favorite": false,
    "created_at": "2026-03-22T00:00:00Z",
    "last_used_at": null
  }
}
```

### 错误

| 代码 | 状态码 | 说明 |
|------|--------|------|
| `duplicate_failed` | 400 | 找不到源、新名称无效或名称已存在 |

## POST /api/profiles/\<name\>/rename

重命名 Profile。如果重命名的是使用中的 Profile，`config.json` 中的 `active_profile` 会自动更新。

### Rate Limit

WRITE

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `name` | string | 当前的 Profile 名称（路径参数） |

### 请求

```json
{
  "new_name": "renamed_profile"
}
```

| 参数 | 类型 | 是否必填 | 说明 |
|------|------|----------|------|
| `new_name` | string | 是 | 新的 Profile 名称 |

### 响应

```json
{
  "profile": {
    "name": "renamed_profile",
    "label": "My Profile",
    "description": "Custom settings",
    "favorite": false,
    "created_at": "2026-03-22T00:00:00Z",
    "last_used_at": null
  }
}
```

### 错误

| 代码 | 状态码 | 说明 |
|------|--------|------|
| `invalid_profile_name` | 400 | 新的 Profile 名称无效 |
| `rename_failed` | 400 | 找不到源 Profile 或新名称已存在 |

## POST /api/profiles/\<name\>/favorite

切换 Profile 的收藏状态。反转当前的 `favorite` 值。

### Rate Limit

WRITE

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `name` | string | Profile 名称（路径参数） |

### 请求

不需要请求体。

### 响应

```json
{
  "profile": {
    "name": "my_profile",
    "label": "My Profile",
    "favorite": true
  }
}
```

### 错误

| 代码 | 状态码 | 说明 |
|------|--------|------|
| `profile_not_found` | 404 | Profile 不存在 |
| `favorite_failed` | 400 | 更新失败 |

---

## QR 导出 / 导入

将 Profile 导出为 JSON 字符串以供 QR 码使用，或从 QR 码导入 Profile。导出时会自动过滤包含 `pin`、`token`、`secret` 或 `key` 的敏感字段。

## GET /api/profiles/\<name\>/export

将 Profile 导出为 QR 码用的 JSON 字符串。敏感字段会被排除。

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `name` | string | Profile 名称（路径参数） |

### 响应

```json
{
  "qr_data": "{\"schema\":\"yu://profile/1\",\"profile\":{\"name\":\"my_profile\",\"label\":\"My Profile\",\"description\":\"...\"}}"
}
```

`qr_data` 是用于嵌入 QR 码的 JSON 字符串。`schema` 字段标识格式版本。

### 错误

| 代码 | 状态码 | 说明 |
|------|--------|------|
| `profile_not_found` | 404 | Profile 不存在 |

## POST /api/profiles/import-preview

预览 QR 数据的导入。用于检查与现有 Profile 的差异。不会实际执行导入。

### Rate Limit

WRITE

### 请求

```json
{
  "qr_data": "{\"schema\":\"yu://profile/1\",\"profile\":{\"name\":\"my_profile\",\"label\":\"My Profile\"}}"
}
```

| 参数 | 类型 | 是否必填 | 说明 |
|------|------|----------|------|
| `qr_data` | string/object | 是 | QR 码的 JSON 字符串或已解析的对象 |

### 响应（新的 Profile）

```json
{
  "mode": "new",
  "name": "my_profile",
  "label": "My Profile",
  "preview": {
    "name": "my_profile",
    "label": "My Profile",
    "description": "..."
  }
}
```

### 响应（已存在的 Profile）

```json
{
  "mode": "existing",
  "name": "my_profile",
  "label": "My Profile",
  "diff": {
    "description": {
      "old": "Old description",
      "new": "New description"
    }
  }
}
```

### 错误

| 代码 | 状态码 | 说明 |
|------|--------|------|
| `invalid_qr` | 400 | 无效的 QR 数据或缺少 `profile` 键 |
| `invalid_profile_name` | 400 | Profile 名称无效 |

## POST /api/profiles/import

从 QR 数据导入 Profile。支持三种模式：创建新的、差异合并和完整覆写。

### Rate Limit

WRITE

### 请求

```json
{
  "qr_data": "{\"schema\":\"yu://profile/1\",\"profile\":{\"name\":\"my_profile\",\"label\":\"My Profile\"}}",
  "mode": "full"
}
```

| 参数 | 类型 | 是否必填 | 说明 |
|------|------|----------|------|
| `qr_data` | string/object | 是 | QR 码的 JSON 字符串或已解析的对象 |
| `mode` | string | 否 | 导入模式：`full`（完整覆写，默认）、`diff`（仅合并变更的键）、`new`（仅创建新的） |

### 响应

```json
{
  "imported": "my_profile",
  "mode": "full"
}
```

创建新 Profile 时返回状态码 201。

### 错误

| 代码 | 状态码 | 说明 |
|------|--------|------|
| `invalid_qr` | 400 | 无效的 QR 数据 |
| `invalid_profile_name` | 400 | Profile 名称无效 |
| `profile_exists` | 409 | `mode=new` 时 Profile 已存在 |
| `import_failed` | 400 | 导入失败 |
