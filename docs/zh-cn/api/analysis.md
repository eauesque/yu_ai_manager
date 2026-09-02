# AI Analysis API

AI 驱动的图片分析、提示词趋势分析及服务器管理的 API。

所有 POST/PUT/DELETE 端点都需要 `X-Requested-With` 头（使用 Bearer API Key 时不需要）。

## 速率限制

`/api/analysis/` 下的写入端点使用 **HEAVY** 层级（约 20 次/分钟，突发 5 次）。GET 端点无限制。

---

## 配置

### GET /api/analysis/config

获取当前的 AI 分析配置。API Key 以掩码形式返回。

#### 响应

```json
{
  "engine": "ollama",
  "api_key": "sk-T...xy",
  "model": "claude-sonnet-4-6",
  "ollama_url": "http://localhost:11434",
  "ollama_model": "llava:latest",
  "openai_api_key": "sk-...xy",
  "openai_model": "gpt-4o-mini",
  "openai_compat_url": "http://localhost:8080/v1",
  "openai_compat_api_key": "***...ey",
  "openai_compat_model": "qwen2-vl",
  "hailo_vlm_model": "qwen2-vl-2b-instruct",
  "fallback_local_only": false,
  "language": "ja",
  "is_local": true,
  "has_servers": true,
  "servers": [],
  "active_server": "ollama-main"
}
```

| 字段 | 类型 | 说明 |
|-------|------|-------------|
| `engine` | string | 当前引擎类型（`claude_api`、`openai`、`ollama`、`openai_compat`、`hailo_vlm`） |
| `api_key` | string | Claude API Key（掩码） |
| `model` | string | Claude API 模型名称 |
| `ollama_url` | string | Ollama 服务器 URL |
| `ollama_model` | string | Ollama 模型名称 |
| `openai_api_key` | string | OpenAI API Key（掩码） |
| `openai_model` | string | OpenAI 模型名称 |
| `openai_compat_url` | string | OpenAI 兼容服务器 URL |
| `openai_compat_api_key` | string | OpenAI 兼容 API Key（掩码） |
| `openai_compat_model` | string | OpenAI 兼容模型名称 |
| `hailo_vlm_model` | string | Hailo VLM 模型名称 |
| `fallback_local_only` | boolean | 是否仅限本地引擎 |
| `language` | string | 分析结果的语言（`ja`、`en` 等） |
| `is_local` | boolean | 当前引擎是否为本地（免费） |
| `has_servers` | boolean | 是否已配置服务器注册表 |
| `servers` | array | 服务器列表（仅当 `has_servers` 为 true 时） |
| `active_server` | string | 活动服务器 ID（仅当 `has_servers` 为 true 时） |

### POST /api/analysis/config

保存 AI 分析配置。掩码值（包含 `...` 的字符串）不会被覆盖。API Key 会自动加密。

#### 速率限制

HEAVY

#### 请求

```json
{
  "engine": "ollama",
  "ollama_url": "http://localhost:11434",
  "ollama_model": "llava:latest",
  "language": "ja"
}
```

| 参数 | 类型 | 必须 | 说明 |
|-----------|------|----------|-------------|
| `engine` | string | 否 | 引擎类型 |
| `api_key` | string | 否 | Claude API Key |
| `model` | string | 否 | Claude API 模型 |
| `ollama_url` | string | 否 | Ollama 服务器 URL |
| `ollama_model` | string | 否 | Ollama 模型名称 |
| `openai_api_key` | string | 否 | OpenAI API Key |
| `openai_model` | string | 否 | OpenAI 模型名称 |
| `openai_compat_url` | string | 否 | OpenAI 兼容服务器 URL |
| `openai_compat_api_key` | string | 否 | OpenAI 兼容 API Key |
| `openai_compat_model` | string | 否 | OpenAI 兼容模型名称 |
| `hailo_vlm_model` | string | 否 | Hailo VLM 模型名称 |
| `fallback_local_only` | boolean | 否 | 仅限本地引擎 |
| `language` | string | 否 | 分析结果的语言 |

#### 响应

```json
{
  "success": true
}
```

---

## 引擎发现

### GET /api/analysis/available-engines

获取已配置且可达的引擎列表。启用 `fallback_local_only` 时排除云端引擎。

#### 响应

```json
{
  "engines": [
    {
      "type": "ollama",
      "label": "Ollama",
      "model": "llava:latest",
      "models": ["llava:latest", "llava:13b", "bakllava:latest"]
    },
    {
      "type": "hailo_vlm",
      "label": "Hailo VLM",
      "model": "qwen2-vl-2b-instruct",
      "models": ["qwen2-vl-2b-instruct"]
    }
  ]
}
```

| 字段 | 类型 | 说明 |
|-------|------|-------------|
| `engines[].type` | string | 引擎类型标识符 |
| `engines[].label` | string | 显示标签 |
| `engines[].model` | string | 当前配置的模型 |
| `engines[].models` | string[] | 可用模型列表 |

---

## 单文件分析

### POST /api/analysis/analyze/\<file_id\>

使用 AI 引擎分析单个文件。支持图片、视频及压缩包内的图片。

#### 速率限制

HEAVY

#### 参数

| 参数 | 类型 | 说明 |
|-----------|------|-------------|
| `file_id` | int | 文件 ID（路径参数） |

#### 请求

JSON 体为可选。省略时使用默认设置。

```json
{
  "mode": "full",
  "engine": "ollama",
  "model": "llava:latest",
  "server_id": "ollama-main"
}
```

| 参数 | 类型 | 必须 | 说明 |
|-----------|------|----------|-------------|
| `mode` | string | 否 | 分析模式。默认 `"full"` |
| `engine` | string | 否 | 覆盖引擎类型 |
| `model` | string | 否 | 覆盖模型名称 |
| `server_id` | string | 否 | 指定使用的服务器 ID |

#### 响应 (200)

```json
{
  "success": true,
  "result": {
    "description": "A landscape painting with mountains...",
    "style": "digital art",
    "quality_score": 8,
    "tags": ["landscape", "mountains", "sunset"]
  },
  "engine": "Ollama (llava:latest)"
}
```

#### 错误响应

- `400`：引擎未配置 / 指定的引擎无效
- `404`：找不到文件 / 文件不存在于磁盘上
- `500`：分析过程中发生错误

### GET /api/analysis/result/\<file_id\>

获取文件的已保存分析结果。使用多个引擎/模式时返回所有结果。

#### 参数

| 参数 | 类型 | 说明 |
|-----------|------|-------------|
| `file_id` | int | 文件 ID（路径参数） |

#### 响应 (200) -- 找到结果

```json
{
  "found": true,
  "result": {
    "engine": "Ollama (llava:latest)",
    "description": "A landscape painting...",
    "style": "digital art",
    "quality_score": 8,
    "analyzed_at": 1709500000
  },
  "results": [
    {
      "engine": "Ollama (llava:latest)",
      "description": "A landscape painting...",
      "style": "digital art",
      "quality_score": 8,
      "analyzed_at": 1709500000
    }
  ]
}
```

| 字段 | 类型 | 说明 |
|-------|------|-------------|
| `found` | boolean | 是否存在分析结果 |
| `result` | object | 最新的分析结果（向后兼容用） |
| `results` | array | 所有分析结果的数组 |

#### 响应 (200) -- 无结果

```json
{
  "found": false
}
```

---

## 批量分析

### POST /api/analysis/batch

对未分析的文件启动批量 AI 分析作业。在后台运行。

#### 速率限制

HEAVY

#### 请求

```json
{
  "limit": 10,
  "scan_root": "",
  "file_ids": [],
  "server_ids": ["ollama-main", "openai-compat"]
}
```

| 参数 | 类型 | 必须 | 说明 |
|-----------|------|----------|-------------|
| `limit` | int | 否 | 分析的最大文件数。默认 10。云端引擎上限为 10。本地引擎设为 0 表示全部 |
| `scan_root` | string | 否 | 限制目标为特定扫描根目录 |
| `file_ids` | int[] | 否 | 直接指定要分析的文件 ID |
| `server_ids` | string[] | 否 | 使用的服务器 ID。多个服务器可启用并行分析 |

#### 响应 (200)

```json
{
  "started": true,
  "count": 10,
  "parallel": false
}
```

| 字段 | 类型 | 说明 |
|-------|------|-------------|
| `started` | boolean | 作业是否已开始 |
| `count` | int | 要分析的文件数 |
| `parallel` | boolean | 是否并行运行（多个 `server_ids`） |
| `worker` | boolean | 若通过推理工作者分派则为 true |
| `subprocess` | boolean | 若以子进程运行（Hailo VLM）则为 true |

#### 错误响应

- `400`：没有要分析的文件
- `409`：AI 分析作业已在运行中

### POST /api/analysis/batch/cancel

取消正在运行的批量 AI 分析作业。

#### 速率限制

HEAVY

#### 请求

不需要体。

#### 响应 (200)

```json
{
  "status": "cancelling",
  "message": "AI analysis cancel requested"
}
```

#### 错误响应

- `404`：没有正在运行的 AI 分析作业

---

## 提示词趋势分析

### POST /api/analysis/trends

对最近 50 个提示词运行趋势分析。结果会自动保存至历史记录。

#### 速率限制

HEAVY

#### 请求

不需要体。

#### 响应 (200)

```json
{
  "success": true,
  "result": {
    "summary": "Recent prompts focus on landscape and character art...",
    "top_themes": ["landscape", "character", "fantasy"],
    "trend_direction": "increasing variety"
  }
}
```

#### 错误响应

- `400`：API Key 未配置（使用云端引擎时）
- `500`：趋势分析过程中发生错误

### GET /api/analysis/trends/history

获取提示词趋势分析历史。按最新排序。最多保留 50 条。

#### 参数

| 参数 | 类型 | 默认 | 说明 |
|-----------|------|---------|-------------|
| `limit` | int | 20 | 获取的条数（最多 50） |
| `offset` | int | 0 | 偏移量 |

#### 响应

```json
{
  "items": [
    {
      "id": 5,
      "engine": "ollama",
      "analyzed_at": 1709500000,
      "prompt_count": 50,
      "result": {
        "summary": "Recent prompts focus on...",
        "top_themes": ["landscape", "character"]
      }
    }
  ]
}
```

| 字段 | 类型 | 说明 |
|-------|------|-------------|
| `items[].id` | int | 历史记录 ID |
| `items[].engine` | string | 使用的引擎类型 |
| `items[].analyzed_at` | int | 分析的 UNIX 时间戳 |
| `items[].prompt_count` | int | 分析的提示词数量 |
| `items[].result` | object | 趋势分析结果 |

### DELETE /api/analysis/trends/history/\<history_id\>

删除单条趋势分析历史记录。

#### 速率限制

HEAVY

#### 参数

| 参数 | 类型 | 说明 |
|-----------|------|-------------|
| `history_id` | int | 历史记录 ID（路径参数） |

#### 响应

```json
{
  "deleted": true
}
```

#### 错误响应

- `404`：找不到历史记录

---

## 统计信息

### GET /api/analysis/stats

获取 AI 分析统计信息。

#### 响应

```json
{
  "total_analyzed": 150,
  "total_files": 1200,
  "styles": [
    { "style": "digital art", "count": 45 },
    { "style": "anime", "count": 30 }
  ],
  "quality_distribution": [
    { "tier": "excellent", "count": 20, "avg_score": 8.5 },
    { "tier": "good", "count": 60, "avg_score": 6.8 },
    { "tier": "average", "count": 50, "avg_score": 4.9 },
    { "tier": "low", "count": 20, "avg_score": 2.3 }
  ]
}
```

| 字段 | 类型 | 说明 |
|-------|------|-------------|
| `total_analyzed` | int | 已分析的文件数 |
| `total_files` | int | 总文件数（不含已删除） |
| `styles` | array | 风格分布（前 10 名） |
| `styles[].style` | string | 风格名称 |
| `styles[].count` | int | 文件数 |
| `quality_distribution` | array | 质量分数分布 |
| `quality_distribution[].tier` | string | 质量等级（`excellent` >= 8、`good` >= 6、`average` >= 4、`low` < 4） |
| `quality_distribution[].count` | int | 文件数 |
| `quality_distribution[].avg_score` | float | 平均分数 |

---

## Ollama 连接

### GET /api/analysis/ollama/models

连接至已配置的 Ollama 服务器并列出可用模型。

#### 响应

```json
{
  "available": true,
  "models": [
    { "name": "llava:latest", "size": 4700000000 }
  ]
}
```

#### 错误响应

- `400`：Ollama URL 无效

### POST /api/analysis/ollama/test

测试与指定 URL 的 Ollama 服务器的连接。

#### 速率限制

HEAVY

#### 请求

```json
{
  "ollama_url": "http://localhost:11434"
}
```

| 参数 | 类型 | 必须 | 说明 |
|-----------|------|----------|-------------|
| `ollama_url` | string | 是 | 要测试的 Ollama 服务器 URL |

#### 响应

```json
{
  "available": true,
  "models": [
    { "name": "llava:latest", "size": 4700000000 }
  ]
}
```

#### 错误响应

- `400`：URL 为空 / URL 无效

---

## OpenAI 兼容服务器连接

### GET /api/analysis/openai-compat/models

连接至已配置的 OpenAI 兼容服务器并列出可用模型。

#### 响应

```json
{
  "available": true,
  "models": [
    { "id": "qwen2-vl-7b-instruct" }
  ]
}
```

#### 错误响应

- `400`：URL 未配置 / URL 无效

### POST /api/analysis/openai-compat/test

测试与指定 URL 的 OpenAI 兼容服务器的连接。

#### 速率限制

HEAVY

#### 请求

```json
{
  "url": "http://localhost:8080/v1",
  "api_key": "optional-key"
}
```

| 参数 | 类型 | 必须 | 说明 |
|-----------|------|----------|-------------|
| `url` | string | 是 | 要测试的 URL |
| `api_key` | string | 否 | API Key（如需要） |

#### 响应

```json
{
  "available": true,
  "models": [
    { "id": "qwen2-vl-7b-instruct" }
  ]
}
```

#### 错误响应

- `400`：URL 为空 / URL 无效

---

## AI 服务器注册表

注册和管理多个 AI 服务器，支持基于优先级的回退和并行分析。

### GET /api/analysis/servers

列出所有已注册的服务器及其状态。API Key 会被掩码。

#### 响应

```json
{
  "servers": [
    {
      "id": "ollama-main",
      "name": "Ollama (llava:latest)",
      "type": "ollama",
      "priority": 10,
      "enabled": true,
      "config": {
        "base_url": "http://localhost:11434",
        "model": "llava:latest"
      },
      "is_active": true,
      "status": "unknown"
    }
  ]
}
```

| 字段 | 类型 | 说明 |
|-------|------|-------------|
| `servers[].id` | string | 服务器 ID（不可变更） |
| `servers[].name` | string | 显示名称 |
| `servers[].type` | string | 引擎类型（`claude_api`、`openai`、`ollama`、`openai_compat`、`hailo_vlm`） |
| `servers[].priority` | int | 优先级（数值越低优先级越高） |
| `servers[].enabled` | boolean | 启用/禁用 |
| `servers[].config` | object | 引擎特定配置 |
| `servers[].is_active` | boolean | 是否为当前活动服务器 |
| `servers[].status` | string | 连接状态（列表视图中始终为 `"unknown"`） |

### POST /api/analysis/servers

注册新服务器。第一个服务器会自动设为活动。

#### 速率限制

HEAVY

#### 请求

```json
{
  "name": "Local Ollama",
  "type": "ollama",
  "config": {
    "base_url": "http://localhost:11434",
    "model": "llava:latest"
  }
}
```

| 参数 | 类型 | 必须 | 说明 |
|-----------|------|----------|-------------|
| `name` | string | 是 | 服务器名称 |
| `type` | string | 是 | 引擎类型 |
| `config` | object | 是 | 引擎特定配置 |
| `priority` | int | 否 | 优先级 |
| `enabled` | boolean | 否 | 启用/禁用。默认 true |

#### 响应 (201)

```json
{
  "success": true,
  "server": {
    "id": "local-ollama",
    "name": "Local Ollama",
    "type": "ollama",
    "priority": 10,
    "enabled": true,
    "config": { "base_url": "http://localhost:11434", "model": "llava:latest" }
  }
}
```

#### 错误响应

- `400`：验证错误 / 已达服务器上限

### PUT /api/analysis/servers/\<server_id\>

更新服务器设置。`id` 字段无法变更。

#### 速率限制

HEAVY

#### 参数

| 参数 | 类型 | 说明 |
|-----------|------|-------------|
| `server_id` | string | 服务器 ID（路径参数） |

#### 请求

```json
{
  "name": "Updated Name",
  "type": "ollama",
  "priority": 20,
  "enabled": true,
  "config": { "base_url": "http://192.168.1.100:11434", "model": "llava:13b" }
}
```

所有字段均为可选。仅更新指定的字段。

#### 响应

```json
{
  "success": true,
  "server": { "id": "ollama-main", "name": "Updated Name", "..." : "..." }
}
```

#### 错误响应

- `400`：类型无效 / 找不到服务器

### DELETE /api/analysis/servers/\<server_id\>

删除服务器。若删除的是活动服务器，会自动切换至下一个最高优先级的服务器。

#### 速率限制

HEAVY

#### 参数

| 参数 | 类型 | 说明 |
|-----------|------|-------------|
| `server_id` | string | 服务器 ID（路径参数） |

#### 响应

```json
{
  "success": true
}
```

#### 错误响应

- `400`：找不到服务器

### POST /api/analysis/servers/\<server_id\>/activate

切换活动服务器。

#### 速率限制

HEAVY

#### 参数

| 参数 | 类型 | 说明 |
|-----------|------|-------------|
| `server_id` | string | 服务器 ID（路径参数） |

#### 响应

```json
{
  "success": true,
  "active": "ollama-main"
}
```

#### 错误响应

- `400`：找不到服务器

### POST /api/analysis/servers/\<server_id\>/test

对服务器运行连接测试。同时测量响应时间。

#### 速率限制

HEAVY

#### 参数

| 参数 | 类型 | 说明 |
|-----------|------|-------------|
| `server_id` | string | 服务器 ID（路径参数） |

#### 响应

```json
{
  "success": true,
  "available": true,
  "elapsed_ms": 45,
  "server": {
    "id": "ollama-main",
    "name": "Local Ollama",
    "type": "ollama",
    "config": { "..." : "..." }
  }
}
```

| 字段 | 类型 | 说明 |
|-------|------|-------------|
| `available` | boolean | 服务器是否可达 |
| `elapsed_ms` | int | 连接测试响应时间（毫秒） |
| `server` | object | 服务器信息 |

#### 错误响应

- `400`：找不到服务器

### PUT /api/analysis/servers/reorder

批量更新服务器优先级。

#### 速率限制

HEAVY

#### 请求

```json
{
  "server_ids": ["ollama-main", "openai-compat", "claude-api"]
}
```

| 参数 | 类型 | 必须 | 说明 |
|-----------|------|----------|-------------|
| `server_ids` | string[] | 是 | 服务器 ID 数组。指定的顺序成为新的优先级顺序 |

#### 响应

```json
{
  "success": true
}
```

#### 错误响应

- `400`：`server_ids` 不是数组

### POST /api/analysis/servers/migrate

从旧版 `ai_analysis` 配置自动迁移至新的服务器注册表格式。若已存在服务器则失败。

#### 速率限制

HEAVY

#### 请求

不需要体。

#### 响应

```json
{
  "success": true,
  "servers": [
    { "id": "ollama", "name": "Ollama (llava:latest)", "type": "ollama", "..." : "..." }
  ],
  "migrated": 3
}
```

| 字段 | 类型 | 说明 |
|-------|------|-------------|
| `servers` | array | 迁移创建的服务器 |
| `migrated` | int | 创建的服务器数量 |

#### 错误响应

- `400`：`ai_servers` 已存在
