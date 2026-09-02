# Tools API

用于重复检测、哈希计算、相似图片搜索、缓存管理、文件夹选择、数据库备份、压缩包清理及调试日志的工具 API。

---

## 重复 / 哈希 / 扫描

### GET /api/tools/find-duplicates

根据文件哈希或文件名检测重复文件。

#### Rate Limit

HEAVY

#### 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `cross_directory` | string | `"false"` | 设为 `"true"` 以跨不同目录检测重复 |
| `method` | string | `"hash"` | 检测方法：`"hash"` 或 `"name"` |
| `threshold` | int | `5` | 相似度阈值 |

#### 响应

```json
{
  "groups": [
    {
      "hash": "abc123...",
      "files": [
        { "id": 1, "path": "/images/photo.png", "filename": "photo.png" },
        { "id": 2, "path": "/backup/photo.png", "filename": "photo.png" }
      ]
    }
  ],
  "total_groups": 1,
  "total_duplicates": 2
}
```

### POST /api/tools/compute-hashes

为尚无哈希值的文件启动后台哈希计算。

#### Rate Limit

HEAVY

#### 请求

```json
{
  "type": "both",
  "limit": 5000
}
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `type` | string | `"both"` | 哈希类型：`"md5"`、`"sha256"` 或 `"both"` |
| `limit` | int | `5000` | 最大处理文件数 |

#### 响应

```json
{
  "started": true,
  "type": "both",
  "limit": 5000
}
```

### POST /api/tools/delete-duplicates

从重复分组中删除指定文件。

#### Rate Limit

DESTRUCTIVE

#### 请求

```json
{
  "groups": [
    {
      "keep": 1,
      "delete": [2, 3]
    }
  ],
  "mode": "soft"
}
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `groups` | array | 必填 | 删除目标。`keep` = 要保留的文件 ID，`delete` = 要移除的文件 ID 数组 |
| `mode` | string | `"soft"` | `"soft"` = 逻辑删除，`"hard"` = 物理删除 |

#### 响应

```json
{
  "deleted": 2,
  "errors": []
}
```

### GET /api/tools/normalize-tags

规范化标签（合并重复、去除空白等）。

#### 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `dry_run` | string | `"false"` | 设为 `"true"` 以预览变更而不实际应用 |

#### 响应

```json
{
  "normalized": 15,
  "removed": 3,
  "dry_run": false
}
```

### GET /api/tools/find-similar

查找与指定文件相似的图片（基于哈希）。

#### Rate Limit

HEAVY

#### 参数

| 参数 | 类型 | 是否必填 | 说明 |
|------|------|----------|------|
| `file_id` | int | 是 | 参考文件 ID |
| `threshold` | int | 否 | 相似度阈值（1-20，默认 `5`） |

#### 响应

```json
{
  "file_id": 42,
  "threshold": 5,
  "results": [
    {
      "id": 43,
      "filename": "similar.png",
      "distance": 3
    }
  ],
  "count": 1
}
```

#### 错误

- `400` — `file_id` 缺失或无效
- `404` — 找不到指定文件

### POST /api/tools/scan

扫描目录中的文件并注册到数据库。

#### Rate Limit

HEAVY

#### 请求

```json
{
  "path": "/path/to/images",
  "recursive": true,
  "scan_zips": false,
  "compute_hash": false
}
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `path` | string | 必填 | 要扫描的目录路径 |
| `recursive` | bool | `true` | 递归扫描子目录 |
| `scan_zips` | bool | `false` | 同时扫描 ZIP 压缩包内部 |
| `compute_hash` | bool | `false` | 扫描时计算文件哈希 |

#### 响应

```json
{
  "scanned": 150,
  "new": 42,
  "updated": 5,
  "errors": []
}
```

---

## 文件搜索 / 元数据检查

### GET /api/tools/file-search

通过关键字搜索数据库中的文件。

#### 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `q` / `query` | string | `""` | 搜索关键字 |
| `meta` / `meta_filter` | string | `"all"` | 按元数据来源筛选（`"all"`、`"a1111_png"`、`"novelai_v4_png"` 等） |
| `limit` / `n` / `page_size` | int | `100` | 结果数量（1-500） |

#### 响应

```json
{
  "results": [
    {
      "id": 1,
      "filename": "image.png",
      "path": "/images/image.png"
    }
  ],
  "count": 1
}
```

### POST /api/inspect

检查上传文件的元数据。提取元数据但不会将文件注册到数据库。

#### Rate Limit

WRITE

#### 请求

`multipart/form-data`：

| 字段 | 类型 | 是否必填 | 说明 |
|------|------|----------|------|
| `file` | file | 是 | 要检查的文件 |
| `zip_entry` | string | 否 | ZIP 压缩包内的路径（用于 ZIP 文件） |

#### 响应

```json
{
  "filename": "image.png",
  "meta_source": "novelai_v4_png",
  "positive": "1girl, landscape",
  "negative": "bad anatomy",
  "parameters": { ... }
}
```

#### 错误

- `400` — 未上传文件

---

## 文件夹选择 / 目录列表

### GET /api/tools/select-folder

打开操作系统原生文件夹选择对话框。**仅限从 localhost 访问。**

#### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `initial` / `path` / `dir` | string | 对话框的初始目录 |

#### 响应

```json
{
  "path": "C:\\Users\\user\\Pictures",
  "cancelled": false
}
```

从远程访问时：

```json
{
  "path": null,
  "error": "remote_client_no_gui",
  "cancelled": false,
  "message": "Native folder dialog is not available for remote access. Please use the server folder browser."
}
```

### GET /api/tools/list-dirs

列出服务器上的目录。**仅限从 localhost 访问。**

#### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `path` / `dir` / `initial` | string | 要列出的目录。留空则返回根目录 |

#### 响应

```json
{
  "current": "C:\\Users",
  "parent": "C:\\",
  "dirs": ["user1", "Public"],
  "roots": ["C:\\", "D:\\"]
}
```

#### 错误

- `403` — 远程访问

---

## 缓存管理

### GET /api/tools/cache-info

获取缩略图缓存状态。

#### 响应

```json
{
  "count": 1234,
  "size_mb": 56.7
}
```

### POST /api/tools/clear-cache

清除所有缩略图缓存。

#### Rate Limit

DESTRUCTIVE

#### 响应

```json
{
  "cleared": 1234
}
```

### POST /api/tools/rebuild-groups

强制重建分组索引缓存。

#### Rate Limit

DESTRUCTIVE

#### 响应

```json
{
  "status": "rebuilt",
  "folders": 42,
  "zips": 5,
  "file_count": 1500
}
```

### POST /api/tools/faststart-prescan

在后台为所有 MP4/MOV 文件预生成 faststart 缓存。立即返回 202。

#### Rate Limit

WRITE

#### 响应 (202)

```json
{
  "ok": true,
  "started": true,
  "message": "faststart prescan started"
}
```

正在运行时 (200)：

```json
{
  "ok": true,
  "started": false,
  "message": "already running"
}
```

---

## 设置

### GET /api/settings/config

获取与默认值合并后的当前配置。

#### 响应

```json
{
  "port": 5000,
  "pin": "",
  "scan_roots": [],
  "theme": "dark",
  "backup": {
    "enabled": true,
    "periodic_interval_hours": 24
  }
}
```

### POST /api/settings/config

部分更新设置。对现有嵌套对象进行深度合并。

#### Rate Limit

DESTRUCTIVE

#### 请求

```json
{
  "theme": "light",
  "backup": {
    "enabled": false
  }
}
```

#### 响应

```json
{
  "status": "saved"
}
```

#### 错误

- `400` — 空数据

---

## 数据库备份 / 恢复

### GET /api/tools/backup-download

直接下载数据库文件。**仅限从 localhost 访问。**

#### 响应

- Content-Type: `application/x-sqlite3`
- Content-Disposition: `attachment; filename="tags_backup_20260322_120000.db"`
- 找不到数据库时返回 404

### POST /api/tools/restore

上传 `.db` 文件以恢复数据库。**仅限从 localhost 访问。** 恢复前会自动创建现有数据库的备份。

#### Rate Limit

WRITE

#### 请求

`multipart/form-data`：

| 字段 | 类型 | 是否必填 | 说明 |
|------|------|----------|------|
| `file` | file | 是 | 扩展名为 `.db` 的 SQLite 文件 |

#### 验证

- 检查 SQLite magic bytes
- 确认 `files` 表存在
- 拒绝包含 trigger 或 view 的数据库

#### 响应

```json
{
  "success": true,
  "message": "Database restored successfully",
  "backup": "tags.db.backup_1711100000"
}
```

#### 错误

- `400` — 未上传文件、扩展名错误或无效的 SQLite
- `403` — 远程访问
- `500` — 备份或恢复失败

### POST /api/tools/backup/create

手动创建受管理的备份。**仅限从 localhost 访问。**

#### Rate Limit

DESTRUCTIVE

#### 响应

```json
{
  "success": true,
  "filename": "tags_backup_20260322_120000.db",
  "reason": "manual"
}
```

### GET /api/tools/backup/list

列出可用的备份。

#### 响应

```json
{
  "backups": [
    {
      "filename": "tags_backup_20260322_120000.db",
      "size": 1048576,
      "created": "2026-03-22T12:00:00"
    }
  ],
  "count": 1
}
```

### POST /api/tools/backup/restore

从指定的备份恢复数据库。**仅限从 localhost 访问。**

#### Rate Limit

DESTRUCTIVE

#### 请求

```json
{
  "filename": "tags_backup_20260322_120000.db"
}
```

| 参数 | 类型 | 是否必填 | 说明 |
|------|------|----------|------|
| `filename` | string | 是 | 要恢复的备份文件名 |

#### 响应

```json
{
  "success": true,
  "message": "Backup restored",
  "filename": "tags_backup_20260322_120000.db"
}
```

#### 错误

- `400` — 缺少文件名或找不到备份
- `403` — 远程访问

### POST /api/tools/backup/delete

删除指定的备份。**仅限从 localhost 访问。**

#### Rate Limit

DESTRUCTIVE

#### 请求

```json
{
  "filename": "tags_backup_20260322_120000.db"
}
```

| 参数 | 类型 | 是否必填 | 说明 |
|------|------|----------|------|
| `filename` | string | 是 | 要删除的备份文件名 |

#### 响应

```json
{
  "success": true,
  "deleted": "tags_backup_20260322_120000.db"
}
```

### GET /api/tools/backup/status

获取备份系统状态。

#### 响应

```json
{
  "enabled": true,
  "backup_on_scan_complete": true,
  "periodic_interval_hours": 24,
  "max_generations": 5,
  "cooldown_minutes": 5,
  "scheduler_running": true,
  "last_backup_time": "2026-03-22T11:00:00",
  "within_cooldown": false
}
```

---

## 调试日志

### GET /api/tools/debug-log

获取调试日志的末尾。调试模式禁用时返回 `enabled: false`。

#### 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `limit` | int | `200` | 要获取的行数（1-5000） |
| `filter` | string | `""` | 行筛选字符串（子字符串匹配） |

#### 响应

```json
{
  "enabled": true,
  "lines": ["2026-03-22 12:00:00 [INFO] Server started", "..."],
  "total_lines": 5000,
  "log_path": "/path/to/debug.log",
  "log_size_kb": 128.5
}
```

### GET /api/tools/debug-log/download

下载调试日志文件。**仅限从 localhost 访问。**

#### 响应

- Content-Type: `text/plain`
- Content-Disposition: `attachment; filename="debug.log"`

#### 错误

- `400` — 调试模式未启用
- `403` — 远程访问
- `404` — 找不到日志文件

### POST /api/tools/debug-log/clear

清除调试日志。**仅限从 localhost 访问。**

#### Rate Limit

WRITE

#### 响应

```json
{
  "success": true,
  "message": "Log cleared"
}
```

#### 错误

- `400` — 调试模式未启用
- `403` — 远程访问
- `404` — 找不到日志文件

---

## 压缩包清理

用于检测和清理重复压缩包及其解压文件夹的工具。所有端点**仅限从 localhost 访问。**

### POST /api/tools/archive-cleanup/scan

扫描压缩包与文件夹配对。

#### Rate Limit

HEAVY

#### 请求

```json
{
  "path": "/path/to/check",
  "recursive": false
}
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `path` | string | 必填 | 要扫描的目录 |
| `recursive` | bool | `false` | 递归扫描子目录 |

#### 路径验证

- 以 `~` 开头的路径会被拒绝
- 包含 `..` 的路径会被拒绝

#### 响应

```json
{
  "pairs": [
    {
      "archive_path": "/data/images.zip",
      "folder_path": "/data/images",
      "archive_size": 10485760,
      "folder_size": 12582912,
      "file_count": 42
    }
  ],
  "count": 1
}
```

### POST /api/tools/archive-cleanup/execute

对扫描到的配对执行清理操作。

#### Rate Limit

DESTRUCTIVE

#### 请求

```json
{
  "actions": [
    { "action": "delete_archive", "archive_path": "/data/images.zip" },
    { "action": "delete_folder", "folder_path": "/data/images" },
    { "action": "skip" }
  ]
}
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `actions` | array | 操作数组 |
| `actions[].action` | string | `"delete_archive"`、`"delete_folder"` 或 `"skip"` 之一 |
| `actions[].archive_path` | string | 操作为 `delete_archive` 时必填 |
| `actions[].folder_path` | string | 操作为 `delete_folder` 时必填 |

#### 响应

```json
{
  "results": [
    { "action": "delete_archive", "success": true },
    { "action": "delete_folder", "success": true },
    { "action": "skip", "success": true }
  ]
}
```

### POST /api/tools/archive-cleanup/llm-verify

使用 LLM 验证压缩包与文件夹配对的一致性（单个配对）。

#### Rate Limit

HEAVY

#### 请求

```json
{
  "archive_path": "/data/images.zip",
  "folder_path": "/data/images",
  "pair_info": {
    "archive_size": 10485760,
    "folder_size": 12582912
  }
}
```

| 参数 | 类型 | 是否必填 | 说明 |
|------|------|----------|------|
| `archive_path` | string | 是 | 压缩包路径 |
| `folder_path` | string | 是 | 解压文件夹路径 |
| `pair_info` | object | 否 | 额外的配对元数据 |

#### 响应

```json
{
  "verdict": "same",
  "confidence": 0.95,
  "reasoning": "File counts and sizes match exactly."
}
```

### POST /api/tools/archive-cleanup/llm-verify-batch

使用 LLM 批量验证多个配对。最多 50 个配对。

#### Rate Limit

HEAVY

#### 请求

```json
{
  "pairs": [
    {
      "archive_path": "/data/a.zip",
      "folder_path": "/data/a",
      "pair_info": {}
    }
  ]
}
```

| 参数 | 类型 | 限制 | 说明 |
|------|------|------|------|
| `pairs` | array | 最多 50 | 要验证的配对数组 |

#### 响应

```json
{
  "results": [
    { "result": { "verdict": "same", "confidence": 0.95, "reasoning": "..." } }
  ]
}
```

### GET /api/tools/archive-cleanup/llm-config

获取压缩包清理的 LLM 配置。

#### 响应

```json
{
  "engine": "ollama",
  "base_url": "http://localhost:11434",
  "model": "llama3",
  "api_key": ""
}
```

### POST /api/tools/archive-cleanup/llm-config

保存压缩包清理的 LLM 配置。

#### Rate Limit

WRITE

#### 请求

```json
{
  "engine": "ollama",
  "base_url": "http://localhost:11434",
  "model": "llama3"
}
```

#### 响应

```json
{
  "success": true
}
```

### POST /api/tools/archive-cleanup/list-models

列出指定引擎的可用模型。

#### 请求

```json
{
  "engine": "ollama",
  "base_url": "http://localhost:11434"
}
```

| 参数 | 类型 | 是否必填 | 说明 |
|------|------|----------|------|
| `engine` | string | 是 | `"ollama"` 或 `"openai_compat"` |
| `base_url` | string | 是 | 引擎 API URL |
| `api_key` | string | 否 | `openai_compat` 的 API Key |

#### 响应

```json
{
  "models": ["llama3", "mistral", "codellama"]
}
```

#### 错误

- `400` — 无效的引擎或缺少 `base_url`
