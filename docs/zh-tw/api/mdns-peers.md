# API：/api/mdns（Peer 發現）

> 適用版本：v4.64.0 以後（Hailo 擴充為 v4.66.0 以後）

區域網路上的 yu_ai_manager 節點透過 mDNS（`_yu-ai._tcp.local.`）互相發現的 API。共有 2 個端點。

---

## GET /api/mdns/identity

### 概述

節點的自我介紹端點。其他節點在 peer 驗證時呼叫，確認透過 mDNS advertise 的資訊是否來自真正的 yu_ai_manager 實例。

### 認證

**認證繞過（不需要）。** 由於用於 peer 間的相互驗證，特意不設認證。回應中僅包含已透過 mDNS 公開的資訊。不含任何機密資料。

### 回應

```json
{
  "product": "yu_ai_manager",
  "node_id": "a1b2c3d4-...",
  "version": "4.66.0",
  "capabilities": ["hailo"],
  "hailo_ollama_url": "http://192.168.1.10:11434"
}
```

| 欄位 | 型別 | 說明 |
|---|---|---|
| `product` | string | 固定為 `"yu_ai_manager"` |
| `node_id` | string | 節點的唯一 UUID |
| `version` | string | 應用程式版本（從 VERSION 檔案讀取） |
| `capabilities` | string[] | 可用功能列表。目前僅有 `"hailo"` |
| `hailo_ollama_url` | string（可省略） | Hailo-Ollama 的區域網路存取 URL。無法確定區域網路 IP 時不包含 |

**`capabilities` 包含 `"hailo"` 的條件：** LLM Router 目錄中已註冊 `"hailo-local"` 後端。

**`hailo_ollama_url` 包含的條件：** 目錄中已註冊 `"hailo-ollama-local"`，且可確定區域網路 IP。迴路位址（`127.0.0.1` 等）會被改寫為區域網路 IP。

---

## GET /api/mdns/peers

### 概述

回傳此節點發現的區域網路 peer 列表。供 mDNS 子系統的狀態確認與除錯使用。

### 認證

**認證繞過（不需要）。** 回應中僅包含已透過 mDNS 在區域網路上廣播的資訊。

### 回應（一般狀態）

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

| 欄位 | 型別 | 說明 |
|---|---|---|
| `running` | bool | mDNS 子系統是否正在運行 |
| `status` | string | 子系統的狀態字串 |
| `self_node_id` | string | 本節點的 node_id |
| `peers` | object[] | 已發現的 peer 列表（參見下表） |

**peers 各元素：**

| 欄位 | 型別 | 說明 |
|---|---|---|
| `node_id` | string | peer 的唯一 UUID |
| `hostname` | string | mDNS 主機名稱 |
| `version` | string | peer 的應用程式版本 |
| `llm_base_url` | string \| null | peer 的 LLM 端點 URL |
| `llm_provider` | string \| null | LLM 提供者名稱（例：`"ollama"`） |
| `capabilities` | string[] | peer 的 capability 列表 |
| `web_port` | int \| null | peer 的 Web UI 連接埠 |
| `addresses` | string[] | peer 的區域網路 IP 位址列表 |
| `hailo_ollama_url` | string \| null | peer 的 Hailo-Ollama URL |
| `first_seen` | float \| null | 首次發現時間（Unix 時間戳記） |
| `last_seen` | float \| null | 最後確認時間（Unix 時間戳記） |

### 回應（mDNS 未初始化時）

```json
{
  "running": false,
  "reason": "mdns subsystem not initialised (disabled or init failed)",
  "peers": []
}
```

`running: false` 時表示 mDNS 已停用或初始化失敗。請確認設定與啟動日誌。

---

## 除錯模式

設定環境變數 `TAGDB_DEBUG_TRUSTED_PEERS=1` 後啟動，`/api/mdns/peers` 的回應中會包含額外欄位。

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

| 欄位 | 說明 |
|---|---|
| `trusted_ips` | 已註冊至信任 IP 登錄的 IP 列表 |
| `bridge.managed_aliases` | mDNS bridge 管理的別名列表 |
| `bridge.config_aliases` | 在 config 中靜態定義的別名列表 |
| `bridge.cooldown_seconds_remaining` | 以 node_id 前 8 個字元為鍵的冷卻剩餘秒數 |

**注意：** `trusted_ips` 可能成為攻擊目標清單，因此預設不公開。正式環境請勿設定 `TAGDB_DEBUG_TRUSTED_PEERS=1`。

---

## mDNS 發現流程

```
其他節點啟動
    │
    ▼
mDNS advertise _yu-ai._tcp.local.
    │
    ▼
LlmRouterMdnsBridge 接收 on_peer_added()
    │
    ▼
GET /api/mdns/identity 進行 HTTP 驗證
    │
    ├─ 成功 → 註冊至 PeerRegistry 與 BackendCatalog
    └─ 失敗 → 冷卻後重試
```

---

## 相關檔案

- `routes/mdns_identity.py` — 端點實作
- `core/mdns/` — mDNS 服務、位址工具
- `core/llm_router/state.py` — BackendCatalog
- `core/web/trusted_peer_registry.py` — 信任 IP 登錄
- `docs/zh-tw/mesh-inference/overview.md` — 網狀推論架構全貌
