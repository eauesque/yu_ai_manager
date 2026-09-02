# API: /api/llm_router（管理）

LLM Router 的管理操作端点组。受常规 WebUI 会话认证（PIN/会话）保护，与 OpenAI 兼容的 `/v1/*` 接口完全分离。

> **注意**: 这些是管理端点，与用于 LLM 推理请求的 `/v1/chat/completions` 等不同。

---

## 通用响应格式

所有端点使用 `api_result` 包装。成功时的响应体嵌套在 `data` 键下。

```json
{
  "status": "ok",
  "data": { ... }
}
```

错误时:

```json
{
  "status": "error",
  "error": "错误描述"
}
```

---

## GET /api/llm_router/status

用于单个请求绘制整个仪表盘的快照。返回所有后端信息和别名映射。

### 请求

```
GET /api/llm_router/status
```

无参数。

### 响应 `200 OK`

```json
{
  "status": "ok",
  "data": {
    "router": {
      "version": "1.0.0",
      "alias_count": 2
    },
    "backends": [
      {
        "alias": "ollama-mac",
        "base_url": "http://192.168.1.10:11434",
        "source": "static",
        "status": "ready",
        "slo_state": null,
        "disabled": false,
        "model_count": 3,
        "models": [
          {
            "name": "qwen2.5:7b",
            "context_window": 32768,
            "size_b": 7.6
          },
          {
            "name": "llama3.2:3b",
            "context_window": 128000,
            "size_b": 3.2
          }
        ],
        "last_seen": "2026-04-09T12:34:56.789123",
        "last_error": null
      },
      {
        "alias": "mdns-pi5-hailo",
        "base_url": "http://192.168.1.20:8080",
        "source": "mdns",
        "status": "unreachable",
        "slo_state": "unknown",
        "disabled": false,
        "model_count": 0,
        "models": [],
        "last_seen": null,
        "last_error": "Connection refused"
      }
    ],
    "aliases": {
      "default-llm": "ollama-mac/qwen2.5:7b",
      "fast-chat": "ollama-mac/llama3.2:3b"
    }
  }
}
```

### 字段说明

**`router`**

| 字段 | 类型 | 说明 |
|---|---|---|
| `version` | string | Router 的 schema 版本（当前为 `"1.0.0"`） |
| `alias_count` | int | 已定义的别名数量 |

**`backends[]`**

| 字段 | 类型 | 说明 |
|---|---|---|
| `alias` | string | 后端的唯一标识符 |
| `base_url` | string | OpenAI 兼容端点的基础 URL |
| `source` | string | `"static"`（配置文件）或 `"mdns"`（自动发现） |
| `status` | string | `"ready"` / `"unreachable"` / `"unknown"` |
| `slo_state` | string \| null | `"vision_idle"` / `"vision_active"` / `"unknown"` / `null` |
| `disabled` | bool | 为 `true` 时从路由目标中排除 |
| `model_count` | int | 公开模型数量 |
| `models[]` | array | 模型列表（`name`, `context_window`, `size_b`） |
| `last_seen` | string \| null | 最后正常连通时间（ISO 8601） |
| `last_error` | string \| null | 最后的错误消息 |

**`aliases`**

逻辑别名 → 物理模型 ID（`后端alias/模型名`）的映射。

---

## POST /api/llm_router/refresh

对所有后端或指定后端强制执行探测，更新 `status` 和模型列表。

### 请求

**更新所有后端（无请求体）:**

```
POST /api/llm_router/refresh
Content-Type: application/json

{}
```

或无 Content-Type 头的空请求体也可。

**仅更新指定后端:**

```json
{
  "alias": "ollama-mac"
}
```

### 响应 `200 OK`

```json
{
  "status": "ok",
  "data": {
    "refreshed": [
      {
        "alias": "ollama-mac",
        "status": "ready",
        "model_count": 3,
        "disabled": false,
        "last_error": null
      },
      {
        "alias": "mdns-pi5-hailo",
        "status": "unreachable",
        "model_count": 0,
        "disabled": false,
        "last_error": "Connection refused"
      }
    ]
  }
}
```

`refreshed` 数组的每个元素仅包含轻量的更新结果（完整字段请通过 `/status` 获取）。

### 错误 `404 Not Found`

指定了不存在的 `alias` 时:

```json
{
  "status": "error",
  "error": "unknown backend: nonexistent-alias"
}
```

### 备注

- 探测同步执行（等待完成后再返回响应）
- 对 `disabled: true` 的后端也会执行探测（状态会更新）
- mDNS 来源的后端也在范围内

---

## POST /api/llm_router/backends/`<alias>`/disable

禁用指定后端。被禁用的后端从路由中排除，并持久化到 `data/llm_router_state.json`。

### 请求

```
POST /api/llm_router/backends/ollama-mac/disable
```

无需请求体。

### 响应 `200 OK`

```json
{
  "status": "ok",
  "data": {
    "alias": "ollama-mac",
    "disabled": true
  }
}
```

### 错误 `404 Not Found`

```json
{
  "status": "error",
  "error": "unknown backend: nonexistent-alias"
}
```

### 错误 `500 Internal Server Error`

磁盘持久化失败时（权限错误、磁盘空间不足等）。内存状态会回滚。

```json
{
  "status": "error",
  "error": "failed to persist disabled state"
}
```

### 持久化机制

1. 将内存 catalog 的 `disabled` 标志设为 `true`
2. 原子写入 `data/llm_router_state.json`（通过 `.tmp` 和 `os.replace`）
3. 写入失败时回滚步骤 1 并返回 `500`

应用重启后禁用状态仍保留。通过 mDNS 动态发现的后端如果在启动前已被 disable，发现后也会自动应用 disabled 状态。

---

## POST /api/llm_router/backends/`<alias>`/enable

启用指定后端。`disable` 的逆操作。

### 请求

```
POST /api/llm_router/backends/ollama-mac/enable
```

无需请求体。

### 响应 `200 OK`

```json
{
  "status": "ok",
  "data": {
    "alias": "ollama-mac",
    "disabled": false
  }
}
```

### 错误

与 `disable` 端点相同（`404` / `500`）。以 `disabled: false` 持久化。

---

## 端点一览

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/llm_router/status` | 获取所有后端和别名的快照 |
| `POST` | `/api/llm_router/refresh` | 全体或单个后端的强制探测 |
| `POST` | `/api/llm_router/backends/<alias>/disable` | 禁用后端（带持久化） |
| `POST` | `/api/llm_router/backends/<alias>/enable` | 启用后端（带持久化） |

## 相关文档

- [LLM Router WebUI 指南](../llm-router/webui.md)
- [LLM Router 设置](../llm-router/setup.md)
