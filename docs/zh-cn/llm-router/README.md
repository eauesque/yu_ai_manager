# LLM Router

> 目标版本：v4.55.0 或更高版本

## LLM Router 是什么

LLM Router 是内置于 yu_ai_manager 的 **OpenAI 兼容 LLM 代理**。  
它汇集 Ollama、LM Studio、llama.cpp 等多个本地 LLM 后端，  
并将其作为**单一端点**提供给 Claude Code、Continue、Open WebUI 等客户端。

```
客户端 (Claude Code / Continue 等)
          │  (OpenAI 兼容 API)
          ▼
    yu_ai_manager
    ┌─────────────────────────────────────────┐
    │           LLM Router                   │
    │                                         │
    │  alias: "claude-opus-4-7" ──► large    │
    │  alias: "local-coder" ──► ollama-mac/…│
    │                                         │
    │  [BackendCatalog]                       │
    │   ollama-mac  ─── 192.168.1.10:11434   │
    │   ollama-pi5  ─── 192.168.1.20:11434   │
    │   mdns-win01  ─── mDNS 自动发现的后端 (alias: "mdns-<prefix>") │
    └─────────────────────────────────────────┘
```

### 功能

| 功能 | 功能 |
|---|---|
| **多个后端捆绑** | 在局域网上注册任意数量的 Ollama 实例 |
| **别名抽象化** | 使用 `"model": "fast"` 隐藏实际模型名称 |
| **mDNS 自动发现** | 自动注册同一局域网上的 yu_ai_manager 节点，无需配置 |
| **Claude Code 集成** | 实现 Anthropic 兼容的 `/v1/messages`。无需额外代理 |
| **动态禁用/启用** | 从 WebUI 立即切换后端。无需重启 |
| **基于类别的路由** | 通过虚拟后端 `large` / `fast` / `vision` 自动选择最优模型 |

---

## 架构

```
客户端 (Claude Code / Continue 等)
    │
    │ POST /v1/chat/completions
    │ POST /v1/messages          ← Anthropic compatible
    │ GET  /v1/models
    ▼
BackendCatalog  ─── 别名解析 ──► 后端 + 模型名称
    │
    ├─ 手动注册的后端 (在 config.json 中编写)
    └─ mDNS 自动发现的后端 (alias: "mdns-<prefix>")
```

**请求流程：**

1. 客户端使用 `"model": "claude-opus-4-7"` 发送请求
2. Router 在 `aliases` 表中将 `"claude-opus-4-7"` → `"large"` 进行解析
3. 从 `large` 类别中选择有效的后端
4. {trans["flow_step_4"]}
5. {trans["flow_step_5"]}

---

## 文档索引

| 功能 | 功能 |
|---|---|
| [设置](setup.md) | 如何编写 config.json、与 Claude Code/Continue 的集成、mDNS 配置 |
| [WebUI](webui.md) | 如何操作 `/llm-router` 仪表板 |
| [Hailo 自动发现](hailo-auto-discovery.md) | 搭载 Hailo NPU 的对等节点的自动注册 |
| [无法到达对等节点的处理](mdns-peer-unreachable.md) | mDNS 发现的对等节点变为 `unreachable` 的故障排除 |

---

## Gateway 与 Gateway 的区别

| | LLM Router | Gateway |
|---|---|---|
| **范围** | 仅 LLM (Ollama 等) | SD WebUI、ComfyUI、Ollama 一起 |
| **认证边界** | 本地可绕过。局域网外需要 api_key | 为所有后端基于作用域的 Bearer 身份验证 |
| **端点** | `/v1/*` (OpenAI/Anthropic 兼容) | `/v1/*`、`/sd/*`、`/comfy/*` |
| **主要用途** | AI 编码工具的后端 | 安全地向外部客户端公开生成工具 |

两项功能独立运行。如果仅使用 LLM，LLM Router 就足够了。

---

## 与 LAN Cowork 的关系

启用 [LAN Cowork](../lan-cowork/README.md) 时，  
同一局域网上的对等节点通过 mDNS 自动发现，并自动注册到  
LLM Router 中，别名为 `mdns-<node_id[:8]>`。  
无需配置即可构建多节点 LLM 环境。
