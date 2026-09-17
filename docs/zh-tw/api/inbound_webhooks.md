# Inbound Webhook API

從外部服務向 yu_ai_manager 的 event_bus 發送事件的接收端點。

## 接收端點（無需認證 — 基於 token）

`POST /api/webhooks/receive/{token}`

### 請求主體

| 欄位 | 型別 | 說明 |
|------|------|------|
| event | string | 觸發的 event_type（省略時: `webhook.received`） |
| data | object | 事件資料 |

### 回應

```json
{"ok": true, "event": "scan.start"}
```

### 錯誤

| 代碼 | 說明 |
|------|------|
| 403 | token 無效 / HMAC 不符 / event 不在 allowed_events 內 |

## 管理 API（需要 PIN 工作階段）

### 建立

`POST /api/webhooks/inbound`

```json
{"label": "n8n trigger", "allowed_events": ["scan.start"]}
```

回應:

```json
{
  "id": "iwh_a1b2c3...",
  "token": "64char_hex...",
  "label": "n8n trigger",
  "allowed_events": ["scan.start"],
  "active": true,
  "created_at": 1712188800
}
```

### 列表

`GET /api/webhooks/inbound`

### 更新

`PUT /api/webhooks/inbound/{id}`

```json
{"label": "updated", "allowed_events": ["scan.start", "tag.add"], "active": true}
```

### 刪除

`DELETE /api/webhooks/inbound/{id}`

## 認證

- URL 中的 token 相符即接受
- 若有 `X-Webhook-Signature` 標頭，則進行 HMAC-SHA256 額外驗證（選用）

## 安全性

- token 為 64 字元 hex（256 bit）
- `allowed_events` 限制可觸發的事件
- `allowed_events` 為空陣列 = 允許所有事件
