# Tagger Server Registry API

用于管理多个标签推理工作器（Hailo Remote、ONNX Local、Ryzen AI 等）的统一集群 API，通过共享队列工作窃取并行执行模型进行分布式批量标记。

## 概述

Tagger Server Registry 超越了单一 Hailo Remote Tagger，可将多个异构推理后端作为集群管理。每个服务器都有可配置的优先级，任务根据所选分布模式（single / parallel / idle_first）进行分配。

### 架构

```
┌─────────────────────────────────────────────────────┐
│                   eauesque Host                      │
│  ┌──────────────────────────────────────────────┐   │
│  │         Tagger Orchestrator                  │   │
│  │  - Shared queue (work-stealing)              │   │
│  │  - Progress aggregation -> JobManager -> SSE │   │
│  └──────────┬──────────────┬──────────────────┘   │
│    ┌────────▼───┐   ┌──────▼────────────┐          │
│    │ Local ONNX │   │ Hailo HTTP Client │          │
│    │ Worker     │   │ Worker            │          │
│    └────────────┘   └──────────┬────────┘          │
└────────────────────────────────│────────────────────┘
              ┌──────────────────┼──────────────────┐
     ┌────────▼───┐    ┌────────▼───┐    ┌────────▼───┐
     │ Pi A       │    │ Pi B       │    │ Future     │
     │ Hailo 10H  │    │ Hailo 10H  │    │ NPU Server │
     └────────────┘    └────────────┘    └────────────┘
```

### 服务器类型

| 类型 | 说明 |
|------|------|
| `hailo_remote` | 搭载 Hailo-10H 的远程设备（如 Raspberry Pi 5） |
| `onnx_local` | 本地 ONNX Runtime 推理 |
| `onnx_remote` | 远程 ONNX 推理服务器 |
| `ryzen_ai` | AMD Ryzen AI NPU |

### 分布模式

| 模式 | 说明 |
|------|------|
| `single` | 仅使用最高优先级的已启用服务器 |
| `parallel` | 所有已启用服务器并行执行（工作窃取） |
| `idle_first` | 优先使用空闲状态的服务器 |

---

## 服务器条目格式

```json
{
  "id": "pi-hailo-a",
  "name": "Pi5 Hailo A",
  "type": "hailo_remote",
  "priority": 10,
  "enabled": true,
  "config": {
    "endpoint_url": "http://192.168.1.101:8080",
    "bearer_token": "enc:gAAAAABm...",
    "threshold": 0.35,
    "timeout": 30
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 服务器标识符（自动生成或手动指定） |
| `name` | string | 显示名称 |
| `type` | string | 服务器类型（`hailo_remote` / `onnx_local` / `onnx_remote` / `ryzen_ai`） |
| `priority` | int | 优先级（数值越小优先级越高，默认：50） |
| `enabled` | bool | 启用/禁用 |
| `config` | object | 类型特定配置（参见下方） |

### config 字段（远程服务器用）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `endpoint_url` | string | 是 | 远程服务器 URL |
| `bearer_token` | string | 否 | Bearer 令牌（保存时自动加密为 `enc:` 前缀）|
| `threshold` | float | 否 | 标签置信度阈值（默认：0.35）|
| `timeout` | int | 否 | 请求超时秒数（默认：30）|

---

## 认证

与远程服务器（`hailo_remote` / `onnx_remote`）的通信支持可选的 Bearer 令牌认证。

### 主机 → 远程服务器

当设置了 `config.bearer_token` 时，所有 HTTP 请求（健康检查和标签标记）都会自动附带 `Authorization: Bearer <token>` 头。令牌以 Fernet 加密（`enc:` 前缀）存储在 `config.json` 中，API 响应中会脱敏显示。

### 远程服务器端

`deploy/hailo_tagger_server.py` 提供了带令牌验证的参考实现。启动时可通过以下任一方式设置令牌：

```bash
# 命令行参数
python hailo_tagger_server.py --token "my-secret-token"

# 从文件读取
python hailo_tagger_server.py --token-file /etc/tagger/token

# 环境变量
TAGGER_BEARER_TOKEN=my-secret-token python hailo_tagger_server.py
```

未设置令牌时，服务器以开放访问模式（LAN 内信任模型）运行，保持向后兼容。无效令牌将收到 401/403 响应。

---

## GET /api/tagger-servers

列出已注册的服务器和当前的分布模式。

### 速率限制

READ（无限制）

### 响应

```json
{
  "ok": true,
  "data": {
    "servers": [
      {
        "id": "pi-hailo-a",
        "name": "Pi5 Hailo A",
        "type": "hailo_remote",
        "priority": 10,
        "enabled": true,
        "config": {
          "endpoint_url": "http://192.168.1.101:8080",
          "threshold": 0.35,
          "timeout": 30
        }
      }
    ],
    "mode": "parallel"
  }
}
```

---

## POST /api/tagger-servers

新增标签服务器。

### 速率限制

DESTRUCTIVE（~12 req/min, burst 3）

### 请求体

| 字段 | 类型 | 必须 | 说明 |
|------|------|------|------|
| `name` | string | 是 | 显示名称 |
| `type` | string | 是 | 服务器类型 |
| `config` | object | 是 | 类型特定配置 |
| `priority` | int | 否 | 优先级（默认：50） |
| `enabled` | bool | 否 | 启用/禁用（默认：`true`） |

### 请求示例

```json
{
  "name": "Pi5 Hailo A",
  "type": "hailo_remote",
  "config": {
    "endpoint_url": "http://192.168.1.101:8080",
    "threshold": 0.35,
    "timeout": 30
  },
  "priority": 10
}
```

### 响应

```json
{
  "ok": true,
  "data": {
    "server": {
      "id": "pi-hailo-a",
      "name": "Pi5 Hailo A",
      "type": "hailo_remote",
      "priority": 10,
      "enabled": true,
      "config": {
        "endpoint_url": "http://192.168.1.101:8080",
        "threshold": 0.35,
        "timeout": 30
      }
    }
  }
}
```

### 错误

| 状态码 | 说明 |
|--------|------|
| 400 | 缺少必须字段或类型无效 |

---

## PUT /api/tagger-servers/{server_id}

更新现有服务器的设置。支持部分更新。

### 速率限制

DESTRUCTIVE（~12 req/min, burst 3）

### 路径参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `server_id` | string | 目标服务器 ID |

### 请求体

| 字段 | 类型 | 必须 | 说明 |
|------|------|------|------|
| `name` | string | 否 | 显示名称 |
| `type` | string | 否 | 服务器类型 |
| `config` | object | 否 | 类型特定配置 |
| `priority` | int | 否 | 优先级 |
| `enabled` | bool | 否 | 启用/禁用 |

### 响应

```json
{
  "ok": true,
  "data": {
    "server": { "..." }
  }
}
```

### 错误

| 状态码 | 说明 |
|--------|------|
| 404 | 找不到服务器 |

---

## DELETE /api/tagger-servers/{server_id}

删除服务器。

### 速率限制

DESTRUCTIVE（~12 req/min, burst 3）

### 路径参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `server_id` | string | 目标服务器 ID |

### 响应

```json
{
  "ok": true,
  "data": {
    "deleted": "pi-hailo-a"
  }
}
```

### 错误

| 状态码 | 说明 |
|--------|------|
| 404 | 找不到服务器 |

---

## POST /api/tagger-servers/reorder

批量重新排列服务器优先级。

### 速率限制

DESTRUCTIVE（~12 req/min, burst 3）

### 请求体

| 字段 | 类型 | 必须 | 说明 |
|------|------|------|------|
| `order` | string[] | 是 | 按优先级排列的服务器 ID 数组 |

### 请求示例

```json
{
  "order": ["pi-hailo-a", "local-onnx", "pi-hailo-b"]
}
```

### 响应

```json
{
  "ok": true,
  "data": {
    "servers": [ "..." ]
  }
}
```

---

## POST /api/tagger-servers/mode

变更分布模式。

### 速率限制

DESTRUCTIVE（~12 req/min, burst 3）

### 请求体

| 字段 | 类型 | 必须 | 说明 |
|------|------|------|------|
| `mode` | string | 是 | `single` / `parallel` / `idle_first` |

### 响应

```json
{
  "ok": true,
  "data": {
    "mode": "parallel"
  }
}
```

### 错误

| 状态码 | 说明 |
|--------|------|
| 400 | 无效的模式值 |

---

## POST /api/tagger-servers/{server_id}/test

测试与指定服务器的连接。

### 速率限制

HEAVY（~20 req/min, burst 5）

### 路径参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `server_id` | string | 目标服务器 ID |

### 响应（成功）

```json
{
  "ok": true,
  "data": {
    "server_id": "pi-hailo-a",
    "reachable": true,
    "latency_ms": 45
  }
}
```

### 响应（无法到达）

```json
{
  "ok": true,
  "data": {
    "server_id": "pi-hailo-a",
    "reachable": false,
    "reason": "Connection refused"
  }
}
```

### 错误

| 状态码 | 说明 |
|--------|------|
| 404 | 找不到服务器 |

---

## GET /api/tagger-servers/health

检查所有已启用服务器的健康状态。

### 速率限制

READ（无限制）

### 响应

```json
{
  "ok": true,
  "data": {
    "results": [
      {
        "server_id": "pi-hailo-a",
        "name": "Pi5 Hailo A",
        "type": "hailo_remote",
        "reachable": true,
        "latency_ms": 45
      },
      {
        "server_id": "local-onnx",
        "name": "Local ONNX",
        "type": "onnx_local",
        "reachable": true,
        "latency_ms": 2
      }
    ]
  }
}
```

---

## POST /api/tagger-servers/batch

使用共享队列工作窃取模型执行分布式批量标记。以后台任务执行，进度通过 SSE 通知。

### 速率限制

HEAVY（~20 req/min, burst 5）

### 请求体

| 字段 | 类型 | 必须 | 说明 |
|------|------|------|------|
| `file_ids` | int[] | 否 | 目标文件 ID 列表。省略时自动选择未标记文件 |
| `limit` | int | 否 | 自动选择时的最大数量（默认：500） |
| `force` | bool | 否 | 覆盖现有标签（默认：`false`） |
| `threshold` | float | 否 | 覆盖标签置信度阈值（省略时使用各服务器配置） |

### 请求示例

```json
{
  "file_ids": [1, 2, 3, 4, 5],
  "force": false,
  "threshold": 0.35
}
```

### 响应

```json
{
  "ok": true,
  "data": {
    "started": true,
    "job_id": "tagger_servers_batch",
    "total_files": 5,
    "active_servers": ["pi-hailo-a", "local-onnx"]
  }
}
```

### 错误

| 状态码 | 代码 | 说明 |
|--------|------|------|
| 400 | `no_servers` | 没有可用的已启用服务器 |
| 400 | `batch_too_large` | file_ids 超过上限 |
| 409 | `job_running` | 批量任务正在执行中 |

---

## POST /api/tagger-servers/batch/cancel

取消正在运行的标签服务器集群批处理任务。

### Response

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | `"cancelling"` |
| `message` | string | 状态消息 |

### Error Codes

| Status | Code | Description |
|--------|------|-------------|
| 404 | `job_not_running` | 没有正在运行的批处理任务可取消 |

---

## GET /api/tagger-servers/tags/{file_id}

获取文件的标签器标签。

### 速率限制

READ（无限制）

### 路径参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `file_id` | int | 目标文件的数据库 ID |

### 响应

```json
{
  "ok": true,
  "data": {
    "file_id": 42,
    "tags": [
      {"tag_name": "1girl", "confidence": 0.95, "source": "hailo_remote:pi-hailo-a", "created_at": 1710720000},
      {"tag_name": "solo", "confidence": 0.88, "source": "hailo_remote:pi-hailo-a", "created_at": 1710720000}
    ]
  }
}
```

`source` 字段使用 `{type}:{server_id}` 格式（例如 `hailo_remote:pi-hailo-a`、`onnx_local:local-onnx`）。

---

## DELETE /api/tagger-servers/tags/{file_id}

删除文件的所有标签器标签。

### 速率限制

DESTRUCTIVE（~12 req/min, burst 3）

### 路径参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `file_id` | int | 目标文件的数据库 ID |

### 响应

```json
{
  "ok": true,
  "data": {
    "file_id": 42,
    "deleted": 15
  }
}
```

---

## GET /api/tagger-servers/stats

获取标签器统计信息。

### 速率限制

READ（无限制）

### 响应

```json
{
  "ok": true,
  "data": {
    "total_files": 10000,
    "tagged_files": 8500,
    "untagged_files": 1500,
    "servers": {
      "pi-hailo-a": {"tagged": 5000, "type": "hailo_remote"},
      "local-onnx": {"tagged": 3500, "type": "onnx_local"}
    }
  }
}
```

---

## POST /api/tagger-servers/migrate

将旧版 `hailo_tagger` 配置迁移至 Tagger Server Registry 格式。将 `config.json` 中现有的 `hailo_tagger` 条目转换为 `tagger_servers` 数组条目。

### 速率限制

DESTRUCTIVE（~12 req/min, burst 3）

### 响应

```json
{
  "ok": true,
  "data": {
    "migrated": true,
    "server": {
      "id": "legacy-hailo",
      "name": "Hailo Remote (migrated)",
      "type": "hailo_remote",
      "priority": 50,
      "enabled": true,
      "config": {
        "endpoint_url": "http://192.168.1.50:8080",
        "threshold": 0.35,
        "timeout": 30
      }
    }
  }
}
```

### 响应（无需迁移）

```json
{
  "ok": true,
  "data": {
    "migrated": false,
    "reason": "No legacy config found"
  }
}
```

---

## 配置

`config.json` 中的相关键值：

```json
{
  "tagger_servers": [
    {
      "id": "pi-hailo-a",
      "name": "Pi5 Hailo A",
      "type": "hailo_remote",
      "priority": 10,
      "enabled": true,
      "config": {
        "endpoint_url": "http://192.168.1.101:8080",
        "bearer_token": "enc:gAAAAABm...",
        "threshold": 0.35,
        "timeout": 30
      }
    },
    {
      "id": "local-onnx",
      "name": "Local ONNX",
      "type": "onnx_local",
      "priority": 20,
      "enabled": true,
      "config": {
        "threshold": 0.35
      }
    }
  ],
  "tagger_servers_mode": "parallel"
}
```

| 键 | 类型 | 说明 |
|----|------|------|
| `tagger_servers` | array | 服务器条目数组 |
| `tagger_servers_mode` | string | 分布模式（`single` / `parallel` / `idle_first`） |

也可从设置页面（Settings）变更。

---

## DB 结构

标签存储在 `file_hailo_tags` 表中。`source` 列使用 `{type}:{server_id}` 格式来识别哪个服务器分配了该标签。

```sql
CREATE TABLE file_hailo_tags (
    id         INTEGER PRIMARY KEY,
    file_id    INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    tag_name   TEXT NOT NULL,
    confidence REAL NOT NULL,
    source     TEXT NOT NULL DEFAULT 'hailo_remote',
    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    UNIQUE(file_id, tag_name)
);
```

| 列 | 说明 |
|----|------|
| `file_id` | files 表的外键 |
| `tag_name` | Danbooru 标签名称（例如 `1girl`、`solo`） |
| `confidence` | 推理置信度（0.0〜1.0） |
| `source` | 标签来源标识符（`{type}:{server_id}` 格式，例如 `hailo_remote:pi-hailo-a`） |
| `created_at` | UNIX 时间戳 |
