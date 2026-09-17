# API Keys API

用於建立、列出和刪除 API Key 的 API。所有端點都需要 PIN 工作階段認證。

API Key 以 `sk_` + 32 個十六進位字元（128 位元）的格式產生。伺服器端僅儲存雜湊值；原始金鑰只在建立時回傳一次。

## Scopes

API Key 可以指定 scope 來限制可存取的端點。未指定 scope 的金鑰預設為唯讀存取。

| Scope | 說明 |
|-------|------|
| `read` | 搜尋、檔案詳情、縮圖、統計 |
| `rate` | 評分的取得/設定/批次操作 |
| `tag.write` | 標籤的新增/移除 |
| `collection.write` | 收藏集的建立/更新/刪除、批次新增、我的最愛 |
| `annotate` | 註解的讀取/寫入/刪除 |
| `scan` | 掃描的啟動/取消/恢復 |
| `admin` | API Key 管理、設定、備份/還原 |

## POST /api/apikeys

建立新的 API Key。

### Rate Limit

WRITE（scope: `admin`）

### Authentication

PIN 工作階段或具有 `admin` scope 的 API Key

### Request

```json
{
  "label": "My Integration",
  "scopes": ["read", "rate"]
}
```

| 參數 | 型別 | 必須 | 說明 |
|------|------|------|------|
| `label` | string | 否 | 金鑰的識別標籤。省略時預設為 `Key <timestamp>` |
| `scopes` | string[] | 否 | Scope 陣列。省略或傳空陣列表示唯讀存取 |

### Response (201)

```json
{
  "id": "ak_1a2b3c4d5e6f7890",
  "key": "sk_abcdef1234567890abcdef1234567890",
  "key_prefix": "sk_abcdef12",
  "label": "My Integration",
  "created_at": 1709500000,
  "scopes": ["read", "rate"]
}
```

> **注意**：`key` 欄位僅在建立回應中包含。此值無法再次取得，請儲存在安全的位置。

### Errors

| 狀態碼 | 說明 |
|--------|------|
| 400 | 指定了無效的 scope |

## GET /api/apikeys

列出所有 API Key。不包含雜湊值；僅回傳前綴。

### Authentication

PIN 工作階段或具有 `admin` scope 的 API Key

### Parameters

無

### Response

```json
{
  "keys": [
    {
      "id": "ak_1a2b3c4d5e6f7890",
      "key_prefix": "sk_abcdef12",
      "label": "My Integration",
      "created_at": 1709500000,
      "last_used_at": 1709600000,
      "scopes": ["read", "rate"]
    }
  ]
}
```

| 欄位 | 型別 | 說明 |
|------|------|------|
| `id` | string | Key ID（`ak_` 前綴） |
| `key_prefix` | string | 金鑰的前 10 個字元（用於識別） |
| `label` | string | 使用者定義的標籤 |
| `created_at` | int | 建立時間（Unix 時間戳） |
| `last_used_at` | int/null | 最後使用時間。未使用過則為 `null` |
| `scopes` | string[] | 指定的 scope。未設定 scope 時此欄位省略 |

## DELETE /api/apikeys/<key_id>

刪除（撤銷）API Key。

### Rate Limit

WRITE（scope: `admin`）

### Authentication

PIN 工作階段或具有 `admin` scope 的 API Key

### Parameters

| 參數 | 型別 | 說明 |
|------|------|------|
| `key_id` | string | API Key ID（路徑參數） |

### Response

```json
{
  "deleted": "ak_1a2b3c4d5e6f7890"
}
```

### Errors

| 狀態碼 | 說明 |
|--------|------|
| 404 | 找不到指定 ID 的金鑰 |

## 使用 API Key

透過 `Authorization` 標頭使用建立的 API Key：

```
Authorization: Bearer sk_abcdef1234567890abcdef1234567890
```

使用 API Key 認證的請求不需要 CSRF 標頭（`X-Requested-With`）。
