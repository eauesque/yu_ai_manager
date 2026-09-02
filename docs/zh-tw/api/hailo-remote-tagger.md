# Hailo Remote Tagger API

透過網路將圖片傳送至遠端 Hailo AI HAT 推論伺服器（如 Raspberry Pi 5），執行 Danbooru 標籤推論並將結果儲存至資料庫的 API。

## 概述

即使本機沒有 GPU 或 ONNX 執行環境，也可以使用區域網路上搭載 Hailo-10H 的裝置作為遠端標記器。圖片以 multipart/form-data 方式傳送，標籤 JSON 作為回應返回。

---

## GET /api/hailo-tagger/config

取得目前設定。

### Rate Limit

READ（無限制）

### 回應

```json
{
  "ok": true,
  "data": {
    "config": {
      "enabled": false,
      "endpoint_url": "",
      "threshold": 0.35,
      "timeout": 30
    }
  }
}
```

| 欄位 | 型別 | 說明 |
|------|------|------|
| `enabled` | bool | Hailo Remote Tagger 是否啟用 |
| `endpoint_url` | string | Pi 端點 URL（例：`http://192.168.1.50:8080`）|
| `threshold` | float | 標籤信賴度閾值（僅儲存高於此值的標籤）|
| `timeout` | int | 請求逾時時間（秒）|

---

## POST /api/hailo-tagger/config

儲存設定。支援部分更新（僅變更指定欄位）。

### Rate Limit

DESTRUCTIVE（~12 req/min, burst 3）

### 請求本體

| 欄位 | 型別 | 必須 | 說明 |
|------|------|------|------|
| `enabled` | bool | 否 | 啟用/停用 |
| `endpoint_url` | string | 否 | Pi 端點 URL |
| `threshold` | float | 否 | 標籤信賴度閾值 |
| `timeout` | int | 否 | 請求逾時時間（秒）|

### 請求範例

```json
{
  "enabled": true,
  "endpoint_url": "http://192.168.1.50:8080",
  "threshold": 0.35
}
```

### 回應

```json
{
  "ok": true,
  "data": {
    "config": {
      "enabled": true,
      "endpoint_url": "http://192.168.1.50:8080",
      "threshold": 0.35,
      "timeout": 30
    }
  }
}
```

### 錯誤

| 狀態碼 | 說明 |
|--------|------|
| 400 | JSON 物件不正確 |

---

## GET /api/hailo-tagger/status

測試與 Hailo 端點的連線。向 `/health` 端點傳送 GET 請求以驗證可達性。

### Rate Limit

READ（無限制）

### 回應（成功）

```json
{
  "ok": true,
  "data": {
    "enabled": true,
    "reachable": true,
    "endpoint_url": "http://192.168.1.50:8080"
  }
}
```

### 回應（未設定/無法到達）

```json
{
  "ok": true,
  "data": {
    "enabled": true,
    "reachable": false,
    "reason": "Connection refused",
    "endpoint_url": "http://192.168.1.50:8080"
  }
}
```

---

## POST /api/hailo-tagger/tag/{file_id}

為單一檔案加上標籤。

### Rate Limit

HEAVY（~20 req/min, burst 5）

### 路徑參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `file_id` | int | 目標檔案的資料庫 ID |

### 請求本體

| 欄位 | 型別 | 必須 | 說明 |
|------|------|------|------|
| `force` | bool | 否 | 覆寫現有標籤（預設：`false`）|

### 回應

```json
{
  "ok": true,
  "data": {
    "file_id": 42,
    "filepath": "/images/test.png",
    "tag_count": 15,
    "tags": [
      {"tag": "1girl", "confidence": 0.95},
      {"tag": "solo", "confidence": 0.88}
    ]
  }
}
```

### 錯誤

| 狀態碼 | 代碼 | 說明 |
|--------|------|------|
| 400 | `disabled` | Hailo Tagger 已停用 |
| 400 | `not_configured` | 端點 URL 未設定 |
| 400 | `file_not_found` | 檔案未找到 |
| 400 | `file_missing` | 磁碟上不存在該檔案 |
| 400 | `unsupported_type` | 不支援此檔案類型的標記 |
| 502 | `request_failed` | 無法連線至遠端伺服器 |

---

## POST /api/hailo-tagger/batch

批次標記多個檔案。作為背景工作執行。

### Rate Limit

HEAVY（~20 req/min, burst 5）

### 請求本體

| 欄位 | 型別 | 必須 | 說明 |
|------|------|------|------|
| `file_ids` | int[] | 否 | 目標檔案 ID 列表（最大 500）。省略時自動選擇未標記檔案 |
| `limit` | int | 否 | 自動選擇時的最大數量（預設：100）|
| `force` | bool | 否 | 覆寫現有標籤（預設：`false`）|

### 請求範例

```json
{
  "file_ids": [1, 2, 3, 4, 5],
  "force": false
}
```

### 回應

```json
{
  "ok": true,
  "data": {
    "started": true,
    "job_id": "hailo_tagger"
  }
}
```

### 錯誤

| 狀態碼 | 代碼 | 說明 |
|--------|------|------|
| 400 | `batch_too_large` | file_ids 超過 500 筆 |
| 409 | `job_running` | 批次工作已在執行中 |

---

## GET /api/hailo-tagger/tags/{file_id}

取得檔案的 Hailo 標籤。

### Rate Limit

READ（無限制）

### 回應

```json
{
  "ok": true,
  "data": {
    "file_id": 42,
    "tags": [
      {"tag_name": "1girl", "confidence": 0.95, "source": "hailo_remote", "created_at": 1710720000},
      {"tag_name": "solo", "confidence": 0.88, "source": "hailo_remote", "created_at": 1710720000}
    ]
  }
}
```

---

## DELETE /api/hailo-tagger/tags/{file_id}

刪除檔案的所有 Hailo 標籤。

### Rate Limit

DESTRUCTIVE（~12 req/min, burst 3）

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

## 資料庫結構

Hailo 標籤儲存在專用的 `file_hailo_tags` 資料表中（獨立於 `file_wd_tags`）。

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
| `file_id` | files 資料表的外部鍵 |
| `tag_name` | Danbooru 標籤名稱（例：`1girl`, `solo`）|
| `confidence` | 推論信賴度（0.0〜1.0）|
| `source` | 標籤來源識別符（固定：`hailo_remote`）|
| `created_at` | UNIX 時間戳記 |

---

## 設定

`config.json` 的 `hailo_tagger` 區段：

```json
{
  "hailo_tagger": {
    "enabled": true,
    "endpoint_url": "http://192.168.1.50:8080",
    "threshold": 0.35,
    "timeout": 30
  }
}
```

也可從設定頁面變更。

> **Note**: 如需管理多個標籤伺服器，請使用 [Tagger Server Registry API](tagger-servers.md)。舊版設定可透過 `/api/tagger-servers/migrate` 自動遷移。Tagger Server Registry 也支援 Bearer 權杖認證。
