# API：/api/llm_router（管理）

LLM Router 的管理操作端點群。受一般 WebUI 工作階段認證（PIN/工作階段）保護，與 OpenAI 相容的 `/v1/*` 介面完全分離。

> **注意**：這些是管理用端點，與用於 LLM 推論請求的 `/v1/chat/completions` 等不同。

---

## 共通回應格式

所有端點使用 `api_result` 包裝器。成功時的 body 嵌套於 `data` 鍵下。

```json
{
  "status": "ok",
  "data": { ... }
}
```

錯誤時：

```json
{
  "status": "error",
  "error": "錯誤說明"
}
```

---

## GET /api/llm_router/status

用於以單一請求繪製整個儀表板的快照。回傳所有後端資訊與別名對應。

### 請求

```
GET /api/llm_router/status
```

無參數。

### 回應 `200 OK`

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

### 欄位說明

**`router`**

| 欄位 | 型別 | 說明 |
|---|---|---|
| `version` | string | Router 的 schema 版本（目前為 `"1.0.0"`） |
| `alias_count` | int | 已定義的別名數量 |

**`backends[]`**

| 欄位 | 型別 | 說明 |
|---|---|---|
| `alias` | string | 後端的唯一識別碼 |
| `base_url` | string | OpenAI 相容端點的基礎 URL |
| `source` | string | `"static"`（設定檔）或 `"mdns"`（自動發現） |
| `status` | string | `"ready"` / `"unreachable"` / `"unknown"` |
| `slo_state` | string \| null | `"vision_idle"` / `"vision_active"` / `"unknown"` / `null` |
| `disabled` | bool | `true` 時從路由對象中排除 |
| `model_count` | int | 公開模型數量 |
| `models[]` | array | 模型列表（`name`、`context_window`、`size_b`） |
| `last_seen` | string \| null | 上次正常連線日期時間（ISO 8601） |
| `last_error` | string \| null | 上次錯誤訊息 |

**`aliases`**

邏輯別名 → 實體模型 ID（`後端alias/模型名`）的對應表。

---

## POST /api/llm_router/refresh

對所有後端或指定後端強制執行 probe，更新 `status` 與模型列表。

### 請求

**更新所有後端（無 body）：**

```
POST /api/llm_router/refresh
Content-Type: application/json

{}
```

或不帶 Content-Type 標頭的空 body 亦可。

**僅更新指定後端：**

```json
{
  "alias": "ollama-mac"
}
```

### 回應 `200 OK`

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

`refreshed` 陣列的各元素僅包含輕量的更新結果（完整欄位請透過 `/status` 取得）。

### 錯誤 `404 Not Found`

指定的 `alias` 不存在時：

```json
{
  "status": "error",
  "error": "unknown backend: nonexistent-alias"
}
```

### 備註

- Probe 以同步方式執行（等待完成後才回傳回應）
- `disabled: true` 的後端也會執行 probe（status 會被更新）
- mDNS 來源的後端也是對象

---

## POST /api/llm_router/backends/`<alias>`/disable

停用指定後端。已停用的後端會從路由中排除，並永久化至 `data/llm_router_state.json`。

### 請求

```
POST /api/llm_router/backends/ollama-mac/disable
```

無需 body。

### 回應 `200 OK`

```json
{
  "status": "ok",
  "data": {
    "alias": "ollama-mac",
    "disabled": true
  }
}
```

### 錯誤 `404 Not Found`

```json
{
  "status": "error",
  "error": "unknown backend: nonexistent-alias"
}
```

### 錯誤 `500 Internal Server Error`

磁碟永久化失敗時（權限錯誤、磁碟已滿等）。記憶體狀態會被回滾。

```json
{
  "status": "error",
  "error": "failed to persist disabled state"
}
```

### 永久化機制

1. 將記憶體目錄的 `disabled` 旗標設為 `true`
2. 透過 `.tmp` 以 `os.replace` 原子寫入 `data/llm_router_state.json`
3. 寫入失敗時回滾步驟 1 並回傳 `500`

重啟應用程式後停用狀態仍會保持。透過 mDNS 動態發現的後端在啟動前已被 disable 時，發現後也會自動套用 disabled 狀態。

---

## POST /api/llm_router/backends/`<alias>`/enable

啟用指定後端。為 `disable` 的反向操作。

### 請求

```
POST /api/llm_router/backends/ollama-mac/enable
```

無需 body。

### 回應 `200 OK`

```json
{
  "status": "ok",
  "data": {
    "alias": "ollama-mac",
    "disabled": false
  }
}
```

### 錯誤

與 `disable` 端點相同（`404` / `500`）。以 `disabled: false` 永久化。

---

## 端點一覽

| 方法 | 路徑 | 說明 |
|---|---|---|
| `GET` | `/api/llm_router/status` | 取得所有後端與別名的快照 |
| `POST` | `/api/llm_router/refresh` | 對全體或個別後端強制 probe |
| `POST` | `/api/llm_router/backends/<alias>/disable` | 停用後端（含永久化） |
| `POST` | `/api/llm_router/backends/<alias>/enable` | 啟用後端（含永久化） |

## 相關文件

- [LLM Router WebUI 指南](../llm-router/webui.md)
- [LLM Router 設定](../llm-router/setup.md)
