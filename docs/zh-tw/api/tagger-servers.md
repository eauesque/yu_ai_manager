# Tagger Server Registry API

用於管理多個標籤推論工作器（Hailo Remote、ONNX Local、Ryzen AI 等）的統一叢集 API，透過共享佇列工作竊取並行執行模型進行分散式批次標記。

## 概述

Tagger Server Registry 超越了單一 Hailo Remote Tagger，可將多個異構推論後端作為叢集管理。每個伺服器都有可設定的優先順序，任務根據所選分散模式（single / parallel / idle_first）進行分配。

### 架構

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

### 伺服器類型

| 類型 | 說明 |
|------|------|
| `hailo_remote` | 搭載 Hailo-10H 的遠端裝置（如 Raspberry Pi 5） |
| `onnx_local` | 本地 ONNX Runtime 推論 |
| `onnx_remote` | 遠端 ONNX 推論伺服器 |
| `ryzen_ai` | AMD Ryzen AI NPU |

### 分散模式

| 模式 | 說明 |
|------|------|
| `single` | 僅使用最高優先順序的已啟用伺服器 |
| `parallel` | 所有已啟用伺服器並行執行（工作竊取） |
| `idle_first` | 優先使用閒置狀態的伺服器 |

---

## 伺服器條目格式

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

| 欄位 | 型別 | 說明 |
|------|------|------|
| `id` | string | 伺服器識別碼（自動產生或手動指定） |
| `name` | string | 顯示名稱 |
| `type` | string | 伺服器類型（`hailo_remote` / `onnx_local` / `onnx_remote` / `ryzen_ai`） |
| `priority` | int | 優先順序（數值越小優先順序越高，預設：50） |
| `enabled` | bool | 啟用/停用 |
| `config` | object | 類型特定設定（參見下方） |

### config 欄位（遠端伺服器用）

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `endpoint_url` | string | 是 | 遠端伺服器 URL |
| `bearer_token` | string | 否 | Bearer 權杖（儲存時自動加密為 `enc:` 前綴）|
| `threshold` | float | 否 | 標籤信賴度閾值（預設：0.35）|
| `timeout` | int | 否 | 請求逾時秒數（預設：30）|

---

## 認證

與遠端伺服器（`hailo_remote` / `onnx_remote`）的通訊支援可選的 Bearer 權杖認證。

### 主機 → 遠端伺服器

當設定了 `config.bearer_token` 時，所有 HTTP 請求（健康檢查和標籤標記）都會自動附帶 `Authorization: Bearer <token>` 標頭。權杖以 Fernet 加密（`enc:` 前綴）儲存在 `config.json` 中，API 回應中會遮罩顯示。

### 遠端伺服器端

`deploy/hailo_tagger_server.py` 提供了帶權杖驗證的參考實作。啟動時可通過以下任一方式設定權杖：

```bash
# 命令列引數
python hailo_tagger_server.py --token "my-secret-token"

# 從檔案讀取
python hailo_tagger_server.py --token-file /etc/tagger/token

# 環境變數
TAGGER_BEARER_TOKEN=my-secret-token python hailo_tagger_server.py
```

未設定權杖時，伺服器以開放存取模式（LAN 內信任模型）運作，保持向後相容。無效權杖將收到 401/403 回應。

---

## GET /api/tagger-servers

列出已註冊的伺服器和目前的分散模式。

### 速率限制

READ（無限制）

### 回應

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

新增標籤伺服器。

### 速率限制

DESTRUCTIVE（~12 req/min, burst 3）

### 請求主體

| 欄位 | 型別 | 必要 | 說明 |
|------|------|------|------|
| `name` | string | 是 | 顯示名稱 |
| `type` | string | 是 | 伺服器類型 |
| `config` | object | 是 | 類型特定設定 |
| `priority` | int | 否 | 優先順序（預設：50） |
| `enabled` | bool | 否 | 啟用/停用（預設：`true`） |

### 請求範例

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

### 回應

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

### 錯誤

| 狀態碼 | 說明 |
|--------|------|
| 400 | 缺少必要欄位或類型無效 |

---

## PUT /api/tagger-servers/{server_id}

更新現有伺服器的設定。支援部分更新。

### 速率限制

DESTRUCTIVE（~12 req/min, burst 3）

### 路徑參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `server_id` | string | 目標伺服器 ID |

### 請求主體

| 欄位 | 型別 | 必要 | 說明 |
|------|------|------|------|
| `name` | string | 否 | 顯示名稱 |
| `type` | string | 否 | 伺服器類型 |
| `config` | object | 否 | 類型特定設定 |
| `priority` | int | 否 | 優先順序 |
| `enabled` | bool | 否 | 啟用/停用 |

### 回應

```json
{
  "ok": true,
  "data": {
    "server": { "..." }
  }
}
```

### 錯誤

| 狀態碼 | 說明 |
|--------|------|
| 404 | 找不到伺服器 |

---

## DELETE /api/tagger-servers/{server_id}

移除伺服器。

### 速率限制

DESTRUCTIVE（~12 req/min, burst 3）

### 路徑參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `server_id` | string | 目標伺服器 ID |

### 回應

```json
{
  "ok": true,
  "data": {
    "deleted": "pi-hailo-a"
  }
}
```

### 錯誤

| 狀態碼 | 說明 |
|--------|------|
| 404 | 找不到伺服器 |

---

## POST /api/tagger-servers/reorder

批次重新排列伺服器優先順序。

### 速率限制

DESTRUCTIVE（~12 req/min, burst 3）

### 請求主體

| 欄位 | 型別 | 必要 | 說明 |
|------|------|------|------|
| `order` | string[] | 是 | 按優先順序排列的伺服器 ID 陣列 |

### 請求範例

```json
{
  "order": ["pi-hailo-a", "local-onnx", "pi-hailo-b"]
}
```

### 回應

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

變更分散模式。

### 速率限制

DESTRUCTIVE（~12 req/min, burst 3）

### 請求主體

| 欄位 | 型別 | 必要 | 說明 |
|------|------|------|------|
| `mode` | string | 是 | `single` / `parallel` / `idle_first` |

### 回應

```json
{
  "ok": true,
  "data": {
    "mode": "parallel"
  }
}
```

### 錯誤

| 狀態碼 | 說明 |
|--------|------|
| 400 | 無效的模式值 |

---

## POST /api/tagger-servers/{server_id}/test

測試與指定伺服器的連線。

### 速率限制

HEAVY（~20 req/min, burst 5）

### 路徑參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `server_id` | string | 目標伺服器 ID |

### 回應（成功）

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

### 回應（無法到達）

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

### 錯誤

| 狀態碼 | 說明 |
|--------|------|
| 404 | 找不到伺服器 |

---

## GET /api/tagger-servers/health

檢查所有已啟用伺服器的健康狀態。

### 速率限制

READ（無限制）

### 回應

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

使用共享佇列工作竊取模型執行分散式批次標記。以背景任務執行，進度透過 SSE 通知。

### 速率限制

HEAVY（~20 req/min, burst 5）

### 請求主體

| 欄位 | 型別 | 必要 | 說明 |
|------|------|------|------|
| `file_ids` | int[] | 否 | 目標檔案 ID 列表。省略時自動選擇未標記檔案 |
| `limit` | int | 否 | 自動選擇時的最大數量（預設：500） |
| `force` | bool | 否 | 覆寫現有標籤（預設：`false`） |
| `threshold` | float | 否 | 覆寫標籤信心度閾值（省略時使用各伺服器設定） |

### 請求範例

```json
{
  "file_ids": [1, 2, 3, 4, 5],
  "force": false,
  "threshold": 0.35
}
```

### 回應

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

### 錯誤

| 狀態碼 | 代碼 | 說明 |
|--------|------|------|
| 400 | `no_servers` | 沒有可用的已啟用伺服器 |
| 400 | `batch_too_large` | file_ids 超過上限 |
| 409 | `job_running` | 批次任務正在執行中 |

---

## POST /api/tagger-servers/batch/cancel

取消正在執行的標籤伺服器叢集批次任務。

### Response

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | `"cancelling"` |
| `message` | string | 狀態訊息 |

### Error Codes

| Status | Code | Description |
|--------|------|-------------|
| 404 | `job_not_running` | 沒有正在執行的批次任務可取消 |

---

## GET /api/tagger-servers/tags/{file_id}

取得檔案的標籤器標籤。

### 速率限制

READ（無限制）

### 路徑參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `file_id` | int | 目標檔案的資料庫 ID |

### 回應

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

`source` 欄位使用 `{type}:{server_id}` 格式（例如 `hailo_remote:pi-hailo-a`、`onnx_local:local-onnx`）。

---

## DELETE /api/tagger-servers/tags/{file_id}

刪除檔案的所有標籤器標籤。

### 速率限制

DESTRUCTIVE（~12 req/min, burst 3）

### 路徑參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `file_id` | int | 目標檔案的資料庫 ID |

### 回應

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

取得標籤器統計資訊。

### 速率限制

READ（無限制）

### 回應

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

將舊版 `hailo_tagger` 設定遷移至 Tagger Server Registry 格式。將 `config.json` 中現有的 `hailo_tagger` 條目轉換為 `tagger_servers` 陣列條目。

### 速率限制

DESTRUCTIVE（~12 req/min, burst 3）

### 回應

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

### 回應（無需遷移）

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

## 設定

`config.json` 中的相關鍵值：

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

| 鍵 | 型別 | 說明 |
|----|------|------|
| `tagger_servers` | array | 伺服器條目陣列 |
| `tagger_servers_mode` | string | 分散模式（`single` / `parallel` / `idle_first`） |

也可從設定頁面（Settings）變更。

---

## DB 結構

標籤儲存在 `file_hailo_tags` 表中。`source` 欄位使用 `{type}:{server_id}` 格式來識別哪個伺服器指派了該標籤。

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

| 欄位 | 說明 |
|------|------|
| `file_id` | files 表的外鍵 |
| `tag_name` | Danbooru 標籤名稱（例如 `1girl`、`solo`） |
| `confidence` | 推論信心度（0.0〜1.0） |
| `source` | 標籤來源識別碼（`{type}:{server_id}` 格式，例如 `hailo_remote:pi-hailo-a`） |
| `created_at` | UNIX 時間戳 |
