# LLM Router

> Target version: v4.55.0 or later

## What is LLM Router

LLM Router is an **OpenAI-compatible LLM proxy** built into yu_ai_manager.  
It bundles multiple local LLM backends such as Ollama, LM Studio, and llama.cpp,  
and provides them as a **single endpoint** to clients like Claude Code, Continue, and Open WebUI.

```
Client (Claude Code / Continue, etc.)
          │  (OpenAI-compatible API)
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
    │   mdns-win01  ─── mDNS auto-discovered backends (alias: "mdns-<prefix>") │
    └─────────────────────────────────────────┘
```

### Capabilities

| Feature | Feature |
|---|---|
| **Multiple backends bundling** | Register any number of Ollama instances on the LAN |
| **Abstraction with aliases** | Hide actual model names with `"model": "fast"` |
| **mDNS auto-discovery** | Automatically register yu_ai_manager nodes on the same LAN without configuration |
| **Claude Code integration** | Implement Anthropic-compatible `/v1/messages`. No additional proxy needed |
| **Dynamic disable/enable** | Switch backends immediately from WebUI. No restart required |
| **Category-based routing** | Automatically select optimal models via virtual backends `large` / `fast` / `vision` |

---

## Architecture

```
Client (Claude Code / Continue, etc.)
    │
    │ POST /v1/chat/completions
    │ POST /v1/messages          ← Anthropic compatible
    │ GET  /v1/models
    ▼
BackendCatalog  ─── Alias resolution ──► Backend + Model name
    │
    ├─ Manually registered backends (written in config.json)
    └─ mDNS auto-discovered backends (alias: "mdns-<prefix>")
```

**Request flow:**

1. Client requests with `"model": "claude-opus-4-7"`
2. Router resolves `"claude-opus-4-7"` → `"large"` in the `aliases` table
3. Select a valid backend from the `large` category
4. {trans["flow_step_4"]}
5. {trans["flow_step_5"]}

---

## Documentation index

| Feature | Feature |
|---|---|
| [Setup](setup.md) | How to write config.json, integrate with Claude Code/Continue, mDNS configuration |
| [WebUI](webui.md) | How to operate the `/llm-router` dashboard |
| [Hailo auto-discovery](hailo-auto-discovery.md) | Automatic registration of peers with Hailo NPU |
| [Handling unreachable peers](mdns-peer-unreachable.md) | Troubleshooting when mDNS-discovered peers become `unreachable` |

---

## Gateway Difference from Gateway

| | LLM Router | Gateway |
|---|---|---|
| **Scope** | LLM (Ollama, etc.) only | SD WebUI, ComfyUI, Ollama together |
| **Authentication boundary** | Local can bypass. api_key required outside LAN | Bearer authentication based on scope for all backends |
| **Endpoints** | `/v1/*` (OpenAI/Anthropic-compatible) | `/v1/*`, `/sd/*`, `/comfy/*` |
| **Primary use case** | Backend for AI coding tools | Safely expose generation tools to external clients |

Both features operate independently. If you only use LLM, LLM Router alone is sufficient.

---

## Relationship with LAN Cowork

When [LAN Cowork](../lan-cowork/README.md) is enabled,  
peers on the same LAN are auto-discovered via mDNS and automatically registered  
in LLM Router with aliases like `mdns-<node_id[:8]>`.  
A multi-node LLM environment is set up without configuration.
