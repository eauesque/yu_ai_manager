# 系统更新 API

用于在 GitHub 上检查新版本及应用程序更新的 API。
自动检测安装方式（git / tauri / docker / portable），并提供相应的更新方法。

## GET /api/system/update/check

检查 GitHub 仓库是否有新版本可用。

- **速率限制**：无 (GET)
- **认证**：PIN 会话或 API Key

### 响应

```json
{
  "current": "4.21.0",
  "latest": "4.22.0",
  "update_available": true,
  "release_url": "https://github.com/...",
  "release_notes": "## What's New\n...",
  "published_at": "2026-03-20T12:00:00Z",
  "install_type": "git",
  "docker_command": null,
  "portable_download_url": null
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `current` | string | 当前版本 |
| `latest` | string | GitHub 上的最新版本 |
| `update_available` | bool | 是否有新版本可用 |
| `release_url` | string | GitHub Release 页面 URL |
| `release_notes` | string | 发行说明 (Markdown) |
| `published_at` | string | 发布日期 (ISO 8601) |
| `install_type` | string | 安装方式 (`"git"`, `"tauri"`, `"docker"`, `"portable"`) |
| `docker_command` | string \| null | 仅 Docker 环境：更新命令 |
| `portable_download_url` | string \| null | 仅 Portable 环境：下载 URL |

---

## GET /api/system/update/status

获取当前安装方式和版本信息。

- **速率限制**：无 (GET)
- **认证**：PIN 会话或 API Key

### 响应

```json
{
  "version": "4.21.0",
  "install_type": "git",
  "update_in_progress": false
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `version` | string | 当前版本 |
| `install_type` | string | 安装方式 (`"git"` \| `"tauri"` \| `"docker"` \| `"portable"`) |
| `update_in_progress` | bool | 更新是否正在进行中 |

---

## POST /api/system/update/apply

应用可用的更新。仅支持 git clone 和 portable 安装。

- **速率限制**：DESTRUCTIVE
- **认证**：PIN 会话 (localhost) 或重启令牌
- **CSRF**：需要 `X-Requested-With: XMLHttpRequest`

### 请求体

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `confirm` | string | 是 | 确认字符串。必须为 `"update"` |

### 请求示例

```json
{
  "confirm": "update"
}
```

### 响应

```json
{
  "ok": true,
  "message": "Update started"
}
```

### SSE 事件

更新过程中会通过 SSE 推送 `update.progress` 事件。

```
event: update.progress
data: {"step": "backup", "status": "running", "detail": "Creating backup..."}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `step` | string | 进度步骤（见下方） |
| `status` | string | `"running"` \| `"done"` \| `"error"` |
| `detail` | string | 步骤详细信息 |

#### 步骤一览

| 步骤 | 说明 |
|------|------|
| `backup` | 创建备份 |
| `fetch` | 执行 git fetch |
| `pull` | 执行 git pull |
| `download` | 下载文件 (portable) |
| `extract` | 解压归档 (portable) |
| `replace` | 替换文件 (portable) |
| `pip_install` | 安装 Python 依赖包 |
| `ts_build` | TypeScript 构建 |
| `complete` | 更新完成 |

### 错误响应

**Docker 环境** (400)：
```json
{
  "ok": false,
  "error": "Docker installs cannot be updated from the web UI. Pull the latest image instead.",
  "code": "DOCKER_UPDATE_NOT_SUPPORTED"
}
```

**Tauri 环境** (400)：
```json
{
  "ok": false,
  "error": "Tauri updates are handled by the desktop app's built-in updater.",
  "code": "TAURI_UPDATE_NOT_SUPPORTED"
}
```

---

## 注意事项

- Docker 环境无法使用 `/api/system/update/apply`，请使用 `docker pull` 获取最新镜像
- Tauri 桌面应用的更新由应用内置的更新程序处理
- 仅 git 和 portable 安装支持通过 Web UI 进行更新
- 更新过程中可能会发生服务器重启

---

## GET /api/system/update/unified-check

一次性检查系统本体和所有 Extension 的更新状态。

- **速率限制**：无 (GET)
- **认证**：PIN 会话或 API Key

### 查询参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `force` | string | `"1"` 忽略缓存并重新检查 |

### 响应

```json
{
  "system": {
    "current": "4.22.0",
    "latest": "4.23.0",
    "update_available": true,
    "install_type": "git"
  },
  "extensions": [
    {
      "name": "builtin-backup",
      "version": "1.0.0",
      "source": "builtin",
      "status": "builtin",
      "enabled": true,
      "description": "..."
    },
    {
      "name": "my-custom-ext",
      "version": "0.3.0",
      "source": "git",
      "status": "update_available",
      "enabled": true,
      "description": "...",
      "local_head": "abc12345",
      "remote_head": "def67890",
      "commits_behind": 3
    }
  ],
  "summary": {
    "total": 45,
    "up_to_date": 1,
    "update_available": 1,
    "unknown": 0,
    "builtin": 43
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `system` | object | 系统本体的更新信息（与 `check_for_update` 格式相同） |
| `extensions` | array | 各 Extension 的更新状态 |
| `extensions[].status` | string | `"up_to_date"` \| `"update_available"` \| `"unknown"` \| `"builtin"` |
| `extensions[].source` | string | `"builtin"` \| `"git"` \| `"local"` |
| `extensions[].commits_behind` | int | 有可用更新时，与远程的提交差异数 |
| `summary` | object | 各分类的统计汇总 |

---

## POST /api/system/update/unified-apply

一次性更新系统本体和 Extension。更新前会自动备份 Extension 配置。

- **速率限制**：DESTRUCTIVE
- **认证**：PIN 会话 (localhost) 或重启令牌
- **CSRF**：需要 `X-Requested-With: XMLHttpRequest`

### 请求体

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `update_system` | bool | 否 | 是否更新系统本体（默认：true） |
| `update_extensions` | bool | 否 | 是否更新 Extension（默认：true） |
| `extension_names` | array | 否 | 要更新的 Extension 名称列表（省略时更新所有 git Extension） |

### 请求示例

```json
{
  "update_system": true,
  "update_extensions": true,
  "extension_names": ["my-custom-ext"]
}
```

### 响应

```json
{
  "ok": true,
  "accepted": true,
  "message": "統合更新を開始しました。進捗は SSE イベント (update.progress) で通知されます。",
  "update_system": true,
  "update_extensions": true
}
```

### SSE 事件

统合更新过程中，`update.progress` 事件会附带 `"unified": true` 标记。

```
event: update.progress
data: {"step": "ext_config_backup", "status": "done", "detail": "...", "unified": true}
event: update.progress
data: {"step": "ext_update_my-custom-ext", "status": "running", "detail": "(1/1)", "unified": true}
```

#### 额外步骤

| 步骤 | 说明 |
|------|------|
| `ext_config_backup` | Extension 配置的备份 |
| `ext_update_<name>` | 单个 Extension 的更新 |

---

## MCP 工具集成

可从 Claude Desktop 管理系统更新。

```
# Step 1: 检查新版本
check_for_update()

# Step 2: 检查更新状态
get_update_status()

# Step 3: 应用更新 (仅 git/portable)
apply_system_update(confirm="update")

# 统合检查：一次性确认系统 + 所有 Extension 的更新
check_unified_updates()

# 统合更新：一次性更新系统 + Extension
apply_unified_updates(update_system=True, update_extensions=True)
```

### MCP 工具一览

| 工具 | 说明 |
|------|------|
| `check_for_update` | 检查 GitHub 是否有新版本可用 |
| `get_update_status` | 获取当前安装方式和版本 |
| `apply_system_update` | 应用可用的更新 (仅 git/portable) |
| `check_unified_updates` | 一次性检查系统 + 所有 Extension 的更新状态 |
| `apply_unified_updates` | 一次性更新系统 + Extension（自动备份配置） |
