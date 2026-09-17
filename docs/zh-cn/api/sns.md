# SNS Share API

用于 SNS 分享、Bluesky 发帖及通知队列管理的 API。

由 `routes/sns_share.py` 提供。所有端点均需要认证（PIN 会话或 API Key）。

## 预览 & X Intent

### GET /api/sns/preview

使用图片元数据展开发帖模板并返回预览。用于分享前确认内容。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `file_id` | int | 是 | 目标图片文件 ID |
| `template` | string | 否 | 自定义模板字符串（省略时使用默认值） |

### 响应

```json
{
  "text": "New artwork: sunset landscape #aiart #stablediffusion",
  "graphemes": 52,
  "meta": {
    "title": "sunset landscape",
    "model": "sd_xl_base_1.0",
    "generator": "a1111"
  }
}
```

### curl 示例

```bash
curl -H "Authorization: Bearer sk_xxxxx" \
  "http://localhost:5000/api/sns/preview?file_id=42"
```

### GET /api/sns/x/intent

生成 X (Twitter) Web Intent URL。打开预填文本的 X 发帖界面。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `file_id` | int | 是 | 目标图片文件 ID |

### 响应

```json
{
  "url": "https://twitter.com/intent/tweet?text=New+artwork%3A+sunset+landscape+%23aiart"
}
```

---

## Bluesky 发帖

### POST /api/sns/bluesky/post

向 Bluesky 发送文本（可选附带图片）。

### 请求

```json
{
  "file_id": 42,
  "text": "Check out my new artwork! #aiart",
  "attach_image": true
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `file_id` | int | 是 | 目标图片文件 ID |
| `text` | string | 否 | 发帖文本（省略时使用模板展开） |
| `attach_image` | boolean | 否 | 在帖子中附带图片（默认: false） |

### 响应

```json
{
  "ok": true,
  "uri": "at://did:plc:xxxxx/app.bsky.feed.post/yyyyy"
}
```

### 错误响应

```json
{
  "ok": false,
  "error": "Authentication failed: invalid app password"
}
```

### POST /api/sns/bluesky/test

使用已配置的认证信息测试 Bluesky 连接。

### 响应

```json
{
  "ok": true,
  "handle": "user.bsky.social",
  "display_name": "My Display Name"
}
```

### 错误响应

```json
{
  "ok": false,
  "error": "Invalid identifier or password"
}
```

---

## SNS 配置

### GET /api/sns/config

获取 SNS 配置。密码以掩码方式显示。

### 响应

```json
{
  "bluesky": {
    "handle": "user.bsky.social",
    "app_password": "****...xxxx"
  },
  "post_template": "{title} #aiart #{generator}"
}
```

### POST /api/sns/config

保存 SNS 配置。

### 请求

```json
{
  "bluesky_handle": "user.bsky.social",
  "bluesky_app_password": "xxxx-xxxx-xxxx-xxxx",
  "post_template": "{title} #aiart #{generator}"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `bluesky_handle` | string | 否 | Bluesky 句柄（例: `user.bsky.social`） |
| `bluesky_app_password` | string | 否 | Bluesky App Password |
| `post_template` | string | 否 | 包含 `{placeholder}` 变量的默认发帖模板 |

### curl 示例

```bash
curl -X POST -H "Authorization: Bearer sk_xxxxx" \
  -H "Content-Type: application/json" \
  -H "X-Requested-With: XMLHttpRequest" \
  -d '{"bluesky_handle": "user.bsky.social", "bluesky_app_password": "xxxx-xxxx-xxxx-xxxx"}' \
  "http://localhost:5000/api/sns/config"
```

---

## Bluesky 通知队列

### GET /api/sns/bsky/queue

使用可选筛选条件获取通知队列项目。

| 参数 | 类型 | 说明 |
|------|------|------|
| `status` | string | 筛选: `pending`、`notified`、`dismissed`，或留空获取全部 |
| `type` | string | 通知类型筛选（例: `mention`、`reply`、`quote`、`like`、`repost`、`follow`） |
| `limit` | int | 最大结果数（默认 50） |

### 响应

```json
{
  "data": {
    "items": [
      {
        "id": 1,
        "type": "mention",
        "author_handle": "someone.bsky.social",
        "author_display_name": "Someone",
        "text": "@user.bsky.social great artwork!",
        "uri": "at://did:plc:xxxxx/app.bsky.feed.post/yyyyy",
        "created_at": "2026-03-15T10:00:00Z",
        "fetched_at": "2026-03-15T12:00:00Z",
        "status": "pending",
        "triage_result": null
      }
    ],
    "stats": { "pending": 3, "notified": 1, "dismissed": 5, "total": 9 }
  }
}
```

### GET /api/sns/bsky/queue/pending

获取用于 MCP 通知的待处理（pending）通知。

### 响应

```json
{
  "data": {
    "items": [...],
    "count": 3,
    "stats": { "pending": 3, "notified": 1, "dismissed": 5, "total": 9 }
  }
}
```

### POST /api/sns/bsky/queue/<queue_id>/triage

设置队列项目的分类结果。

### 请求

```json
{ "result": "valid" }
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `result` | string | 是 | `valid` 或 `invalid` |

### PUT /api/sns/bsky/queue/<queue_id>/status

更新队列项目状态。

### 请求

```json
{ "status": "notified" }
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `status` | string | 是 | `pending`、`notified` 或 `dismissed` |

### POST /api/sns/bsky/queue/<queue_id>/respond

对通知发送自动回复。

### 请求

```json
{ "text": "Thank you for your kind words!" }
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `text` | string | 是 | 作为回复发送的响应文本 |

### POST /api/sns/bsky/queue/poll

立即轮询 Bluesky 新通知。

### curl 示例

```bash
curl -X POST -H "Authorization: Bearer sk_xxxxx" \
  -H "X-Requested-With: XMLHttpRequest" \
  "http://localhost:5000/api/sns/bsky/queue/poll"
```

---

## Bluesky 监控配置

### GET /api/sns/bsky/monitor/config

获取 Bluesky 通知监控设置。

### 响应

```json
{
  "data": {
    "poll_interval_minutes": 15,
    "auto_dismiss_follow": false,
    "auto_dismiss_like": true,
    "auto_dismiss_repost": true,
    "auto_respond_enabled": false,
    "notify_on_connect": true
  }
}
```

### PUT /api/sns/bsky/monitor/config

更新 Bluesky 通知监控设置。仅更新提供的字段。

### 请求

```json
{
  "poll_interval_minutes": 30,
  "auto_dismiss_follow": false,
  "auto_dismiss_like": true,
  "auto_dismiss_repost": true,
  "auto_respond_enabled": false,
  "notify_on_connect": true
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `poll_interval_minutes` | int | 否 | 轮询间隔（分钟） |
| `auto_dismiss_follow` | boolean | 否 | 自动忽略关注通知 |
| `auto_dismiss_like` | boolean | 否 | 自动忽略点赞通知 |
| `auto_dismiss_repost` | boolean | 否 | 自动忽略转发通知 |
| `auto_respond_enabled` | boolean | 否 | 启用自动回复 |
| `notify_on_connect` | boolean | 否 | MCP 客户端连接时发送通知 |

---

## 分类提示词 & 自动回复模板

### GET /api/sns/bsky/monitor/triage-prompts

获取可编辑的分类提示词、自动回复模板及其默认值。

### 响应

```json
{
  "data": {
    "triage_prompts": {
      "mention": "Evaluate this mention for relevance...",
      "reply": "Evaluate this reply...",
      "quote": "Evaluate this quote post..."
    },
    "auto_responses": {
      "mention": "Thanks for the mention!",
      "reply": "Thank you for your reply!",
      "quote": "Thanks for sharing!"
    },
    "defaults": {
      "triage_prompts": {
        "mention": "Evaluate this mention for relevance...",
        "reply": "Evaluate this reply...",
        "quote": "Evaluate this quote post..."
      },
      "auto_responses": {
        "mention": "Thanks for the mention!",
        "reply": "Thank you for your reply!",
        "quote": "Thanks for sharing!"
      }
    }
  }
}
```

### PUT /api/sns/bsky/monitor/triage-prompts

更新分类提示词和/或自动回复模板。仅更新提供的字段。

### 请求

```json
{
  "triage_prompts": {
    "mention": "自定义提及分类提示词...",
    "reply": "自定义回复分类提示词...",
    "quote": "自定义引用分类提示词..."
  },
  "auto_responses": {
    "mention": "自定义提及自动回复...",
    "reply": "自定义回复自动回复...",
    "quote": "自定义引用自动回复..."
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `triage_prompts` | object | 否 | 以通知类型（`mention`、`reply`、`quote`）为键的分类提示词 |
| `auto_responses` | object | 否 | 以通知类型为键的自动回复模板 |
