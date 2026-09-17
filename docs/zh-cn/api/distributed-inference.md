# 分布式推理 API

分布式推理服务器注册表的 REST API。使用共享队列策略，将 CLIP 语义索引工作负载分散到多个节点。

## 端点列表

### GET /api/inference-servers

获取已注册的服务器列表及当前分派模式。

**响应：**

```json
{
  "status": "ok",
  "mode": "single",
  "servers": [
    {
      "id": 1,
      "name": "Hailo Worker 1",
      "endpoint_url": "http://192.168.1.10:9090",
      "inference_types": ["clip"],
      "priority": 50,
      "enabled": true,
      "timeout": 30
    }
  ]
}
```

- `mode`：`"single"` | `"parallel"` | `"idle_first"`
- `servers`：服务器配置对象的数组

---

### POST /api/inference-servers

新增推理服务器。

**请求体：**

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `name` | string | ✓ | — | 显示名称 |
| `endpoint_url` | string | ✓ | — | Worker 基础 URL |
| `inference_types` | string[] | — | `["clip"]` | 支持的推理类型 |
| `priority` | int | — | `50` | 优先级（数值越小优先级越高） |
| `bearer_token` | string | — | — | 认证 Token |
| `timeout` | int | — | `30` | 请求超时秒数 |

**响应：**

```json
{
  "status": "ok",
  "server": { ... }
}
```

---

### PUT /api/inference-servers/{server_id}

更新已有服务器的配置。请求体可部分指定与 POST 相同的字段。

---

### DELETE /api/inference-servers/{server_id}

从注册表中删除服务器。

**响应：**

```json
{ "status": "ok" }
```

---

### POST /api/inference-servers/{server_id}/test

对指定服务器执行健康检查。

**响应：**

```json
{
  "status": "ok",
  "server_id": 1,
  "healthy": true,
  "latency_ms": 12.5
}
```

---

### GET /api/inference-servers/health

同时对所有启用的服务器执行健康检查。

**响应：**

```json
{
  "status": "ok",
  "results": [
    { "server_id": 1, "healthy": true, "latency_ms": 12.5 },
    { "server_id": 2, "healthy": false, "error": "Connection refused" }
  ]
}
```

---

### POST /api/inference-servers/mode

设置分派模式。

**请求体：**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `mode` | string | ✓ | `"single"` \| `"parallel"` \| `"idle_first"` |

**响应：**

```json
{ "status": "ok", "mode": "parallel" }
```

---

## 分派模式

| 模式 | 说明 |
|---|---|
| `single` | 仅使用优先级最高（priority 值最小）的服务器 |
| `parallel` | 通过共享队列在所有启用的服务器间分散处理 |
| `idle_first` | 先执行健康检查，再仅使用可响应的服务器进行并行处理 |

## 分布式语义索引

在语义搜索扩展的 `POST /api/index/start` 请求体中添加 `distributed: true`，即可启用使用已注册 Worker 服务器的分布式索引。

```json
{
  "batch_size": 32,
  "distributed": true
}
```

## Worker 服务器配置

```bash
python deploy/hailo_tagger_server.py --port 9090
```

支持的端点：

| 路径 | 说明 |
|---|---|
| `GET /health` | 健康检查 |
| `POST /tag` | WD-Tagger 推理 |
| `POST /clip-encode` | CLIP 向量编码 |

## MCP 工具

| 工具名称 | 说明 |
|---|---|
| `inference-servers-list` | 获取服务器列表与当前模式 |
| `inference-server-add` | 新增服务器 |
| `inference-server-update` | 更新服务器配置 |
| `inference-server-remove` | 删除服务器 |
| `inference-server-health` | 执行健康检查 |
| `inference-dispatch-mode-set` | 设置分派模式 |
