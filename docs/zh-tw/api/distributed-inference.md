# 分散式推論 API

分散式推論伺服器登錄表的 REST API。使用共享佇列策略，將 CLIP 語意索引工作負載分散至多個節點。

## 端點列表

### GET /api/inference-servers

取得已登錄的伺服器清單及目前的分派模式。

**回應：**

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
- `servers`：伺服器設定物件的陣列

---

### POST /api/inference-servers

新增推論伺服器。

**請求主體：**

| 欄位 | 類型 | 必填 | 預設值 | 說明 |
|---|---|---|---|---|
| `name` | string | ✓ | — | 顯示名稱 |
| `endpoint_url` | string | ✓ | — | Worker 基礎 URL |
| `inference_types` | string[] | — | `["clip"]` | 支援的推論類型 |
| `priority` | int | — | `50` | 優先度（數值越小優先度越高） |
| `bearer_token` | string | — | — | 認證 Token |
| `timeout` | int | — | `30` | 請求逾時秒數 |

**回應：**

```json
{
  "status": "ok",
  "server": { ... }
}
```

---

### PUT /api/inference-servers/{server_id}

更新既有伺服器的設定。請求主體可部分指定與 POST 相同的欄位。

---

### DELETE /api/inference-servers/{server_id}

從登錄表中移除伺服器。

**回應：**

```json
{ "status": "ok" }
```

---

### POST /api/inference-servers/{server_id}/test

對指定伺服器執行健康檢查。

**回應：**

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

同時對所有啟用的伺服器執行健康檢查。

**回應：**

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

設定分派模式。

**請求主體：**

| 欄位 | 類型 | 必填 | 說明 |
|---|---|---|---|
| `mode` | string | ✓ | `"single"` \| `"parallel"` \| `"idle_first"` |

**回應：**

```json
{ "status": "ok", "mode": "parallel" }
```

---

## 分派模式

| 模式 | 說明 |
|---|---|
| `single` | 僅使用優先度最高（priority 值最小）的伺服器 |
| `parallel` | 透過共享佇列在所有啟用的伺服器間分散處理 |
| `idle_first` | 先執行健康檢查，再僅使用可回應的伺服器進行並列處理 |

## 分散式語意索引

在語意搜尋擴充功能的 `POST /api/index/start` 請求主體中加入 `distributed: true`，即可啟用使用已登錄 Worker 伺服器的分散式索引。

```json
{
  "batch_size": 32,
  "distributed": true
}
```

## Worker 伺服器設定

```bash
python deploy/hailo_tagger_server.py --port 9090
```

支援的端點：

| 路徑 | 說明 |
|---|---|
| `GET /health` | 健康檢查 |
| `POST /tag` | WD-Tagger 推論 |
| `POST /clip-encode` | CLIP 向量編碼 |

## MCP 工具

| 工具名稱 | 說明 |
|---|---|
| `inference-servers-list` | 取得伺服器清單與目前模式 |
| `inference-server-add` | 新增伺服器 |
| `inference-server-update` | 更新伺服器設定 |
| `inference-server-remove` | 移除伺服器 |
| `inference-server-health` | 執行健康檢查 |
| `inference-dispatch-mode-set` | 設定分派模式 |
