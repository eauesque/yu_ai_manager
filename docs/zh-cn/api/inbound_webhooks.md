# Inbound Webhook API

从外部服务向 yu_ai_manager 的 event_bus 发送事件的接收端点。

## 接收端点（无需认证 — 基于 token）

`POST /api/webhooks/receive/{token}`

### 请求主体

| 字段 | 类型 | 说明 |
|------|------|------|
| event | string | 触发的 event_type（省略时: `webhook.received`） |
| data | object | 事件数据 |

### 响应

```json
{"ok": true, "event": "scan.start"}
```

### 错误

| 代码 | 说明 |
|------|------|
| 403 | token 无效 / HMAC 不匹配 / event 不在 allowed_events 内 |

## 管理 API（需要 PIN 会话）

### 创建

`POST /api/webhooks/inbound`

```json
{"label": "n8n trigger", "allowed_events": ["scan.start"]}
```

响应:

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

### 删除

`DELETE /api/webhooks/inbound/{id}`

## 认证

- URL 中的 token 匹配即接受
- 若有 `X-Webhook-Signature` 标头，则进行 HMAC-SHA256 额外验证（可选）

## 安全性

- token 为 64 字符 hex（256 bit）
- `allowed_events` 限制可触发的事件
- `allowed_events` 为空数组 = 允许所有事件
