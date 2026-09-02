# API: /api/mdns（节点发现）

> 适用版本: v4.64.0 及以上（Hailo 扩展为 v4.66.0 及以上）

局域网上的 yu_ai_manager 节点通过 mDNS（`_yu-ai._tcp.local.`）相互发现的 API。共有 2 个端点。

---

## GET /api/mdns/identity

### 概述

节点自我介绍端点。其他节点在验证节点时调用此端点，确认 mDNS 广播的信息是否来自真正的 yu_ai_manager 实例。

### 认证

**认证旁路（不需要）。** 由于用于节点间的相互验证，因此故意不设认证。响应中仅包含已通过 mDNS 公开的信息，不包含任何秘密或敏感信息。

### 响应

```json
{
  "product": "yu_ai_manager",
  "node_id": "a1b2c3d4-...",
  "version": "4.66.0",
  "capabilities": ["hailo"],
  "hailo_ollama_url": "http://192.168.1.10:11434"
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `product` | string | 始终为 `"yu_ai_manager"` |
| `node_id` | string | 节点的唯一 UUID |
| `version` | string | 应用版本（从 VERSION 文件读取）|
| `capabilities` | string[] | 可用功能列表。目前仅有 `"hailo"` |
| `hailo_ollama_url` | string（可选） | Hailo-Ollama 的局域网访问 URL。无法确定局域网 IP 时不包含 |

**`capabilities` 包含 `"hailo"` 的条件:** LLM Router catalog 中注册了 `"hailo-local"` 后端时。

**`hailo_ollama_url` 包含的条件:** catalog 中注册了 `"hailo-ollama-local"` 且能确定局域网 IP 时。回环地址（`127.0.0.1` 等）会被替换为局域网 IP。

---

## GET /api/mdns/peers

### 概述

返回该节点发现的局域网节点列表。用于 mDNS 子系统的状态确认和调试。

### 认证

**认证旁路（不需要）。** 响应中仅包含已通过 mDNS 在局域网上广播的信息。

### 响应（正常时）

```json
{
  "running": true,
  "status": "browsing",
  "self_node_id": "a1b2c3d4-...",
  "peers": [
    {
      "node_id": "e5f6a7b8-...",
      "hostname": "raspberrypi.local",
      "version": "4.66.0",
      "llm_base_url": "http://192.168.1.20:11434",
      "llm_provider": "ollama",
      "capabilities": ["hailo"],
      "web_port": 5000,
      "addresses": ["192.168.1.20"],
      "hailo_ollama_url": "http://192.168.1.20:11434",
      "first_seen": 1712600000.0,
      "last_seen": 1712603600.0
    }
  ]
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `running` | bool | mDNS 子系统是否正在运行 |
| `status` | string | 子系统的状态字符串 |
| `self_node_id` | string | 本节点的 node_id |
| `peers` | object[] | 已发现的节点列表（见下表）|

**peers 各元素:**

| 字段 | 类型 | 说明 |
|---|---|---|
| `node_id` | string | 节点的唯一 UUID |
| `hostname` | string | mDNS 主机名 |
| `version` | string | 节点的应用版本 |
| `llm_base_url` | string \| null | 节点的 LLM 端点 URL |
| `llm_provider` | string \| null | LLM 提供商名称（例: `"ollama"`）|
| `capabilities` | string[] | 节点的 capability 列表 |
| `web_port` | int \| null | 节点的 Web UI 端口 |
| `addresses` | string[] | 节点的局域网 IP 地址列表 |
| `hailo_ollama_url` | string \| null | 节点的 Hailo-Ollama URL |
| `first_seen` | float \| null | 首次发现时间（Unix 时间戳）|
| `last_seen` | float \| null | 最后确认时间（Unix 时间戳）|

### 响应（mDNS 未初始化时）

```json
{
  "running": false,
  "reason": "mdns subsystem not initialised (disabled or init failed)",
  "peers": []
}
```

`running: false` 表示 mDNS 被禁用或初始化失败。请检查配置和启动日志。

---

## 调试模式

设置环境变量 `TAGDB_DEBUG_TRUSTED_PEERS=1` 启动后，`/api/mdns/peers` 的响应会包含额外字段。

```json
{
  "running": true,
  "peers": [...],
  "trusted_ips": ["192.168.1.20", "192.168.1.30"],
  "bridge": {
    "managed_aliases": ["ollama-192.168.1.20"],
    "config_aliases": ["my-nas"],
    "cooldown_seconds_remaining": {
      "e5f6a7b8": 12.3
    }
  }
}
```

| 字段 | 说明 |
|---|---|
| `trusted_ips` | 信任 IP 注册表中已注册的 IP 列表 |
| `bridge.managed_aliases` | mDNS 桥接管理的别名列表 |
| `bridge.config_aliases` | 配置中静态定义的别名列表 |
| `bridge.cooldown_seconds_remaining` | 以 node_id 前 8 位为键的冷却剩余秒数 |

**注意:** `trusted_ips` 可能成为攻击目标列表，因此默认不公开。生产环境中请勿设置 `TAGDB_DEBUG_TRUSTED_PEERS=1`。

---

## mDNS 发现流程

```
其他节点启动
    │
    ▼
mDNS 广播 _yu-ai._tcp.local.
    │
    ▼
LlmRouterMdnsBridge 接收 on_peer_added()
    │
    ▼
通过 GET /api/mdns/identity 进行 HTTP 验证
    │
    ├─ 成功 → 注册到 PeerRegistry 和 BackendCatalog
    └─ 失败 → 冷却后重试
```

---

## 相关文件

- `routes/mdns_identity.py` — 端点实现
- `core/mdns/` — mDNS 服务和地址工具
- `core/llm_router/state.py` — BackendCatalog
- `core/web/trusted_peer_registry.py` — 信任 IP 注册表
- `docs/zh-cn/mesh-inference/overview.md` — 网状推理架构全貌
