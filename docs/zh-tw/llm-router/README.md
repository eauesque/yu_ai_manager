# LLM Router

> 目標版本：v4.55.0 或更高版本

## LLM Router 是什麼

LLM Router 是內置於 yu_ai_manager 的 **OpenAI 相容 LLM 代理**。  
它彙集 Ollama、LM Studio、llama.cpp 等多個本地 LLM 後端，  
並將其作為**單一端點**提供給 Claude Code、Continue、Open WebUI 等用戶端。

```
用戶端 (Claude Code / Continue 等)
          │  (OpenAI 相容 API)
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
    │   mdns-win01  ─── mDNS 自動發現的後端 (alias: "mdns-<prefix>") │
    └─────────────────────────────────────────┘
```

### 功能

| 功能 | 功能 |
|---|---|
| **多個後端捆綁** | 在區域網路上註冊任意數量的 Ollama 實例 |
| **別名抽象化** | 使用 `"model": "fast"` 隱藏實際模型名稱 |
| **mDNS 自動發現** | 自動註冊同一區域網路上的 yu_ai_manager 節點，無需配置 |
| **Claude Code 整合** | 實現 Anthropic 相容的 `/v1/messages`。無需額外代理 |
| **動態禁用/啟用** | 從 WebUI 立即切換後端。無需重啟 |
| **基於類別的路由** | 透過虛擬後端 `large` / `fast` / `vision` 自動選擇最佳模型 |

---

## 架構

```
用戶端 (Claude Code / Continue 等)
    │
    │ POST /v1/chat/completions
    │ POST /v1/messages          ← Anthropic compatible
    │ GET  /v1/models
    ▼
BackendCatalog  ─── 別名解析 ──► 後端 + 模型名稱
    │
    ├─ 手動註冊的後端 (在 config.json 中編寫)
    └─ mDNS 自動發現的後端 (alias: "mdns-<prefix>")
```

**請求流程：**

1. 用戶端使用 `"model": "claude-opus-4-7"` 傳送請求
2. Router 在 `aliases` 表中將 `"claude-opus-4-7"` → `"large"` 進行解析
3. 從 `large` 類別中選擇有效的後端
4. {trans["flow_step_4"]}
5. {trans["flow_step_5"]}

---

## 文檔索引

| 功能 | 功能 |
|---|---|
| [設置](setup.md) | 如何編寫 config.json、與 Claude Code/Continue 的整合、mDNS 配置 |
| [WebUI](webui.md) | 如何操作 `/llm-router` 儀表板 |
| [Hailo 自動發現](hailo-auto-discovery.md) | 搭載 Hailo NPU 的對等節點的自動註冊 |
| [無法到達對等節點的處理](mdns-peer-unreachable.md) | mDNS 發現的對等節點變為 `unreachable` 的故障排除 |

---

## Gateway 與 Gateway 的區別

| | LLM Router | Gateway |
|---|---|---|
| **範圍** | 僅 LLM (Ollama 等) | SD WebUI、ComfyUI、Ollama 一起 |
| **認證邊界** | 本地可繞過。區域網路外需要 api_key | 為所有後端基於範圍的 Bearer 身份驗證 |
| **端點** | `/v1/*` (OpenAI/Anthropic 相容) | `/v1/*`、`/sd/*`、`/comfy/*` |
| **主要用途** | AI 編碼工具的後端 | 安全地向外部用戶端公開生成工具 |

兩項功能獨立運行。如果僅使用 LLM，LLM Router 就足夠了。

---

## 與 LAN Cowork 的關係

啟用 [LAN Cowork](../lan-cowork/README.md) 時，  
同一區域網路上的對等節點透過 mDNS 自動發現，並自動註冊到  
LLM Router 中，別名為 `mdns-<node_id[:8]>`。  
無需配置即可構建多節點 LLM 環境。
