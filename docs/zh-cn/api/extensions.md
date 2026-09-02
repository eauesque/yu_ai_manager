# Extensions API

管理 Extension 的安装、安全性与开发的 API。

---

## GET /api/extensions

列出所有已安装的 Extension。

### 参数

无

### 响应

```json
{
  "extensions": [
    {
      "name": "builtin-sd-webui-bridge",
      "version": "1.0.0",
      "description": "SD WebUI Bridge",
      "enabled": true,
      "trust_level": "trusted",
      "category": "integration",
      "directory": "extensions/builtin_sd_webui_bridge"
    }
  ],
  "total": 5,
  "category_order": ["core", "integration", "tools", "ui", "other"]
}
```

| 字段 | 类型 | 说明 |
|-------|------|-------------|
| `extensions` | array | Extension 信息数组 |
| `total` | int | Extension 总数 |
| `category_order` | string[] | 分类显示顺序 |

## GET /api/extensions/\<name\>

获取特定 Extension 的详细信息。

### 参数

| 参数 | 类型 | 说明 |
|-----------|------|-------------|
| `name` | string | Extension 名称（路径参数） |

### 响应

```json
{
  "name": "builtin-sd-webui-bridge",
  "version": "1.0.0",
  "description": "SD WebUI Bridge",
  "enabled": true,
  "trust_level": "trusted",
  "category": "integration",
  "directory": "extensions/builtin_sd_webui_bridge"
}
```

### 错误

- `404` — 未找到 Extension

## POST /api/extensions/\<name\>/toggle

切换 Extension 的启用/禁用状态。

### Rate Limit

WRITE

### 参数

| 参数 | 类型 | 说明 |
|-----------|------|-------------|
| `name` | string | Extension 名称（路径参数） |

### 请求

```json
{
  "enabled": true
}
```

| 参数 | 类型 | 必填 | 说明 |
|-----------|------|----------|-------------|
| `enabled` | boolean | 否 | `true` 启用、`false` 禁用。省略时切换当前状态（取反） |

### 响应

```json
{
  "name": "builtin-sd-webui-bridge",
  "enabled": true,
  "message": "Extension 'builtin-sd-webui-bridge' enabled"
}
```

### 错误

- `404` — 未找到 Extension

## GET /api/extensions/\<name\>/config

获取 Extension 的配置结构与当前值。

### 参数

| 参数 | 类型 | 说明 |
|-----------|------|-------------|
| `name` | string | Extension 名称（路径参数） |

### 响应

```json
{
  "name": "builtin-sd-webui-bridge",
  "config_schema": {
    "fields": [
      {
        "key": "api_url",
        "label": "API URL",
        "type": "text",
        "default": "http://127.0.0.1:7860",
        "value": "http://127.0.0.1:7860"
      }
    ]
  }
}
```

### 错误

- `404` — 未找到 Extension

## POST /api/extensions/\<name\>/config

保存 Extension 配置值。包含验证功能。

### Rate Limit

WRITE

### 参数

| 参数 | 类型 | 说明 |
|-----------|------|-------------|
| `name` | string | Extension 名称（路径参数） |

### 请求

```json
{
  "values": {
    "api_url": "http://127.0.0.1:7860",
    "timeout": 30
  }
}
```

| 参数 | 类型 | 必填 | 说明 |
|-----------|------|----------|-------------|
| `values` | object | 是 | 字段键与值的映射 |

### 响应

```json
{
  "ok": true,
  "saved": {
    "api_url": "http://127.0.0.1:7860",
    "timeout": 30
  }
}
```

### 错误

- `404` — 未找到 Extension
- `400` — 验证错误

---

## Extension 安装 / 更新 / 卸载

以下端点仅限 **localhost 访问**。远程请求会返回 `403`。

## POST /api/extensions/install

从 Git 仓库安装 Extension。

### Rate Limit

WRITE

### 访问限制

仅限 localhost

### 请求

```json
{
  "url": "https://github.com/user/my-extension.git"
}
```

| 参数 | 类型 | 必填 | 说明 |
|-----------|------|----------|-------------|
| `url` | string | 是 | Git 仓库 URL。`git` 和 `repo` 可作为别名使用 |

### 响应

```json
{
  "ok": true,
  "name": "my-extension",
  "message": "Extension installed successfully"
}
```

### 错误

- `400` — 未提供 URL 或 URL 格式无效
- `403` — 非 localhost 访问

## POST /api/extensions/\<name\>/update

将特定 Extension 更新至最新版本（git pull）。

### Rate Limit

WRITE

### 访问限制

仅限 localhost

### 参数

| 参数 | 类型 | 说明 |
|-----------|------|-------------|
| `name` | string | Extension 名称（路径参数） |

### 响应

```json
{
  "ok": true,
  "name": "my-extension",
  "message": "Extension updated successfully"
}
```

### 错误

- `403` — 非 localhost 访问
- `404` — 未找到 Extension

## POST /api/extensions/update-all

批量更新所有通过 Git 安装的 Extension。

### Rate Limit

WRITE

### 访问限制

仅限 localhost

### 响应

```json
{
  "results": [
    {"name": "my-extension", "ok": true, "message": "Updated"},
    {"name": "other-ext", "ok": false, "error": "Git pull failed"}
  ]
}
```

### 错误

- `403` — 非 localhost 访问

## DELETE /api/extensions/\<name\>/uninstall

卸载 Extension（删除目录）。

### Rate Limit

DESTRUCTIVE

### 访问限制

仅限 localhost

### 参数

| 参数 | 类型 | 说明 |
|-----------|------|-------------|
| `name` | string | Extension 名称（路径参数） |

### 响应

```json
{
  "ok": true,
  "name": "my-extension",
  "message": "Extension uninstalled"
}
```

### 错误

- `403` — 非 localhost 访问
- `404` — 未找到 Extension

---

## 安全性与权限

## GET /api/extensions/\<name\>/permissions

获取 Extension 的权限信息与审批状态。

### 参数

| 参数 | 类型 | 说明 |
|-----------|------|-------------|
| `name` | string | Extension 名称（路径参数） |

### 响应

```json
{
  "name": "my-extension",
  "trust_level": "L2",
  "approved": true,
  "permissions": {
    "required": [
      {"name": "network", "reason": "API calls to external service"}
    ],
    "optional": [
      {"name": "filesystem_read", "reason": "Read user images"}
    ]
  },
  "granted": {
    "granted": ["network", "filesystem_read"],
    "denied": [],
    "granted_at": "2025-01-15T10:30:00",
    "auto_approved": false
  }
}
```

| 字段 | 类型 | 说明 |
|-------|------|-------------|
| `trust_level` | string | 信任等级（`trusted`、`L1`、`L2`） |
| `approved` | boolean | 用户是否已审批此 Extension |
| `permissions.required` | array | 必需权限列表 |
| `permissions.optional` | array | 可选权限列表 |
| `granted` | object/null | 已授予权限的详细信息。未审批时为 `null` |

### 错误

- `404` — 未找到 Extension

## POST /api/extensions/\<name\>/permissions

审批或撤销 Extension 权限。

### Rate Limit

WRITE

### 参数

| 参数 | 类型 | 说明 |
|-----------|------|-------------|
| `name` | string | Extension 名称（路径参数） |

### 请求（审批）

```json
{
  "action": "approve",
  "granted": ["network", "filesystem_read"],
  "denied": ["filesystem_write"]
}
```

### 请求（撤销）

```json
{
  "action": "revoke"
}
```

| 参数 | 类型 | 必填 | 说明 |
|-----------|------|----------|-------------|
| `action` | string | 否 | `"approve"`（默认）或 `"revoke"` |
| `granted` | string[] | 否 | 要授予的权限名称列表（用于审批） |
| `denied` | string[] | 否 | 要拒绝的权限名称列表（用于审批） |

### 响应（审批）

```json
{
  "name": "my-extension",
  "action": "approved",
  "granted": ["network", "filesystem_read"],
  "denied": ["filesystem_write"]
}
```

### 响应（撤销）

```json
{
  "name": "my-extension",
  "action": "revoked"
}
```

### 错误

- `400` — `granted` 不是列表
- `404` — 未找到 Extension

## GET /api/extensions/\<name\>/scan-results

获取 Extension 代码的静态分析结果。返回 ManifestAuthority 和 CodeVerifier 的结果。

### 参数

| 参数 | 类型 | 说明 |
|-----------|------|-------------|
| `name` | string | Extension 名称（路径参数） |

### 响应

```json
{
  "name": "my-extension",
  "trust_level": "L2",
  "manifest_review": {
    "approved": true,
    "issues": []
  },
  "code_scan": {
    "approved": true,
    "findings": [
      {
        "file": "my_ext.py",
        "line": 15,
        "severity": "warning",
        "message": "Uses subprocess module"
      }
    ]
  }
}
```

| 字段 | 类型 | 说明 |
|-------|------|-------------|
| `manifest_review.approved` | boolean | manifest 是否通过审查 |
| `manifest_review.issues` | array | 问题列表（`severity`、`message`） |
| `code_scan` | object/null | 代码扫描结果。无目录时为 `null` |
| `code_scan.findings` | array | 发现列表 |

### 错误

- `404` — 未找到 Extension

## POST /api/extensions/\<name\>/rescan

重新扫描 Extension 代码。返回格式与 `scan-results` 相同。

### Rate Limit

WRITE

### 参数

| 参数 | 类型 | 说明 |
|-----------|------|-------------|
| `name` | string | Extension 名称（路径参数） |

### 响应

格式与 `GET /api/extensions/<name>/scan-results` 相同。

## GET /api/extensions/\<name\>/tokens

获取 Extension 的 capability token 发行状态。

### 参数

| 参数 | 类型 | 说明 |
|-----------|------|-------------|
| `name` | string | Extension 名称（路径参数） |

### 响应

```json
{
  "name": "my-extension",
  "token_count": 2,
  "tokens": [
    {
      "capability": "network",
      "issued_at": "2025-01-15T10:30:00",
      "expires_at": "2025-01-16T10:30:00"
    }
  ]
}
```

### 错误

- `404` — 未找到 Extension

## GET /api/extensions/\<name\>/integrity

获取 Extension 的文件完整性状态。同时包含 revocation tracker 和 import guard 信息。

### 参数

| 参数 | 类型 | 说明 |
|-----------|------|-------------|
| `name` | string | Extension 名称（路径参数） |

### 响应

```json
{
  "name": "my-extension",
  "integrity": {
    "verified": true,
    "last_check": "2025-01-15T10:30:00",
    "files_changed": 0
  },
  "revocation": {
    "denial_count": 0,
    "last_access": null
  },
  "import_guard": {
    "import_denial_count": 0
  }
}
```

| 字段 | 类型 | 说明 |
|-------|------|-------------|
| `integrity` | object | 文件完整性检查结果 |
| `revocation` | object | Token revocation tracker 信息 |
| `import_guard` | object | Import guard 拒绝次数 |

### 错误

- `404` — 未找到 Extension

---

## Hook 与 Marketplace

## GET /api/extensions/hooks

列出已注册的 Extension hook 和 hook 定义。

### 参数

无

### 响应

```json
{
  "hooks": {
    "after_scan": [
      {"extension": "builtin-tagger", "priority": 100}
    ]
  },
  "definitions": {
    "after_scan": {"mode": "sequential"},
    "before_import": {"mode": "sequential"}
  }
}
```

| 字段 | 类型 | 说明 |
|-------|------|-------------|
| `hooks` | object | hook 名称与已注册 Extension 列表的映射 |
| `definitions` | object | 可用的 hook 定义。`mode` 为执行模式 |

## GET /api/extensions/marketplace

搜索 Marketplace Extension。

### 参数

| 参数 | 类型 | 必填 | 说明 |
|-----------|------|----------|-------------|
| `q` | string | 否 | 搜索查询（查询参数）。空字符串返回全部 |

### 响应

```json
{
  "extensions": [
    {
      "name": "awesome-extension",
      "description": "An awesome extension",
      "author": "developer",
      "version": "1.0.0",
      "installed": false
    }
  ],
  "total": 10
}
```

| 字段 | 类型 | 说明 |
|-------|------|-------------|
| `extensions` | array | Marketplace Extension 信息 |
| `extensions[].installed` | boolean | 是否已在本地安装 |
| `total` | int | 搜索结果总数 |

## POST /api/extensions/marketplace/refresh

强制刷新 Marketplace 缓存。

### Rate Limit

WRITE

### 响应

```json
{
  "refreshed": true,
  "total": 25
}
```

---

## 隔离

## GET /api/extensions/isolation

获取进程隔离状态。

### 参数

无

### 响应

```json
{
  "available": true,
  "processes": {
    "my-extension": {
      "pid": 12345,
      "status": "running"
    }
  }
}
```

| 字段 | 类型 | 说明 |
|-------|------|-------------|
| `available` | boolean | 进程隔离是否可用 |
| `processes` | object | Extension 名称与进程状态的映射 |

## GET /api/extensions/os-isolation

获取操作系统级别的隔离状态（Phase D）。同时包含进程隔离信息。

### 参数

无

### 响应

```json
{
  "os_isolation": {
    "platform": "linux",
    "available_backends": ["apparmor"]
  },
  "config": {
    "enabled": true,
    "apparmor": true,
    "macos_sandbox_exec": false,
    "macos_user_isolation": false,
    "windows_restricted_token": false,
    "windows_job_object": false
  },
  "processes": {}
}
```

| 字段 | 类型 | 说明 |
|-------|------|-------------|
| `os_isolation` | object | 操作系统级别隔离信息 |
| `config.enabled` | boolean | 操作系统隔离是否启用 |
| `config.apparmor` | boolean | AppArmor（Linux）使用状态 |
| `config.macos_sandbox_exec` | boolean | macOS sandbox-exec 使用状态 |
| `config.macos_user_isolation` | boolean | macOS 用户隔离使用状态 |
| `config.windows_restricted_token` | boolean | Windows restricted token 使用状态 |
| `config.windows_job_object` | boolean | Windows Job Object 使用状态 |
| `processes` | object | 进程隔离状态 |

---

## Extension 开发

创建与编辑自定义 Extension 的 API。基于 concession 模型，仅 `extensions/custom-{name}/` 目录可写入。

所有端点仅限 **localhost 访问**。

### 安全性约束

- Extension 名称：仅限小写英文字母数字和连字符（`[a-z0-9-]`），最多 50 个字符，禁止使用 `builtin-` 前缀
- 文件类型：仅限白名单（`entrypoint`、`template`、`static_css`、`static_js`、`config`、`readme`）
- 二进制文件：完全禁止
- 文件大小限制：根据类型 10KB 至 50KB

## POST /api/extensions/author/create

创建新的自定义 Extension 并生成脚手架文件。

### Rate Limit

WRITE

### 访问限制

仅限 localhost

### 请求

```json
{
  "name": "my-tool",
  "description": "A useful tool extension"
}
```

| 参数 | 类型 | 必填 | 说明 |
|-----------|------|----------|-------------|
| `name` | string | 是 | Extension 名称（`[a-z0-9-]`，最多 50 个字符） |
| `description` | string | 否 | Extension 说明 |

### 响应

```json
{
  "ok": true,
  "name": "custom-my-tool",
  "path": "extensions/custom-my-tool",
  "files": [
    "extension.json",
    "my_tool_ext.py"
  ]
}
```

### 错误

- `400` — 无效名称或 Extension 已存在
- `403` — 非 localhost 访问

## POST /api/extensions/author/\<name\>/write

写入文件至自定义 Extension。

### Rate Limit

WRITE

### 访问限制

仅限 localhost

### 参数

| 参数 | 类型 | 说明 |
|-----------|------|-------------|
| `name` | string | Extension 名称（路径参数，不含 `custom-` 前缀） |

### 请求

```json
{
  "file_type": "entrypoint",
  "filename": "my_tool_ext",
  "content": "\"\"\"My tool extension.\"\"\"\n\nfrom quart import Blueprint\n..."
}
```

| 参数 | 类型 | 必填 | 说明 |
|-----------|------|----------|-------------|
| `file_type` | string | 是 | 文件类型。可选：`entrypoint`、`template`、`static_css`、`static_js`、`config`、`readme` |
| `filename` | string | 是 | 不含扩展名的文件名称。仅限英文字母数字、连字符和下划线 |
| `content` | string | 是 | 文件内容（仅限文本） |

### 文件类型约束

| file_type | 扩展名 | 最大大小 | 备注 |
|-----------|-----------|----------|-------|
| `entrypoint` | `.py` | 50KB | Extension 入口点 |
| `template` | `.html` | 50KB | 放置于 `templates/{name}/` |
| `static_css` | `.css` | 50KB | 放置于 `static/` |
| `static_js` | `.js` | 50KB | 放置于 `static/` |
| `config` | `.json` | 10KB | 文件名必须为 `extension` |
| `readme` | `.md` | 20KB | 文件名必须为 `README` |

### 响应

```json
{
  "ok": true,
  "file": "my_tool_ext.py",
  "size": 256
}
```

### 错误

- `400` — 验证错误（无效名称、文件类型、超过大小限制、检测到二进制文件）
- `403` — 非 localhost 访问

## GET /api/extensions/author/\<name\>/read

读取自定义 Extension 的文件。

### 访问限制

仅限 localhost

### 参数

| 参数 | 类型 | 说明 |
|-----------|------|-------------|
| `name` | string | Extension 名称（路径参数） |

### 查询参数

| 参数 | 类型 | 必填 | 说明 |
|-----------|------|----------|-------------|
| `file_type` | string | 是 | 文件类型 |
| `filename` | string | 是 | 不含扩展名的文件名称 |

### 响应

```json
{
  "ok": true,
  "file": "my_tool_ext.py",
  "content": "\"\"\"My tool extension.\"\"\"\n...",
  "size": 256
}
```

### 错误

- `400` — 验证错误
- `403` — 非 localhost 访问

## GET /api/extensions/author/\<name\>/files

列出自定义 Extension 的所有文件。

### 访问限制

仅限 localhost

### 参数

| 参数 | 类型 | 说明 |
|-----------|------|-------------|
| `name` | string | Extension 名称（路径参数） |

### 响应

```json
{
  "ok": true,
  "name": "custom-my-tool",
  "files": [
    {"path": "extension.json", "size": 320},
    {"path": "my_tool_ext.py", "size": 256},
    {"path": "templates/my_tool/index.html", "size": 1024}
  ],
  "total_size": 1600
}
```

### 错误

- `400` — 无效的 Extension 名称
- `403` — 非 localhost 访问

## POST /api/extensions/author/\<name\>/validate

验证自定义 Extension 的 extension.json 和代码。执行 CodeVerifier 但不会注册 Extension。

### Rate Limit

WRITE

### 访问限制

仅限 localhost

### 参数

| 参数 | 类型 | 说明 |
|-----------|------|-------------|
| `name` | string | Extension 名称（路径参数） |

### 响应（成功）

```json
{
  "ok": true,
  "name": "custom-my-tool",
  "issues": [],
  "code_findings": [],
  "manifest": {
    "name": "custom-my-tool",
    "version": "0.1.0",
    "entrypoint": "my_tool_ext.py"
  }
}
```

### 响应（发现问题）

```json
{
  "ok": false,
  "name": "custom-my-tool",
  "issues": [
    "Missing required field: version",
    "CodeVerifier rejected: dangerous patterns detected"
  ],
  "code_findings": [
    {
      "severity": "critical",
      "message": "Uses eval()",
      "file": "my_tool_ext.py",
      "line": 42
    }
  ],
  "manifest": {}
}
```

| 字段 | 类型 | 说明 |
|-------|------|-------------|
| `ok` | boolean | 所有检查是否通过 |
| `issues` | string[] | manifest 和代码验证问题 |
| `code_findings` | array | CodeVerifier 发现 |
| `manifest` | object | 解析后的 extension.json 内容 |

### 错误

- `400` — 无效的 Extension 名称或 Extension 不存在
- `403` — 非 localhost 访问
