# SNS Share API

用於 SNS 分享、Bluesky 發文及通知佇列管理的 API。

由 `routes/sns_share.py` 提供。所有端點皆需要驗證（PIN 工作階段或 API Key）。

## 預覽 & X Intent

### GET /api/sns/preview

使用圖片中繼資料展開發文範本並回傳預覽。用於分享前確認內容。

| 參數 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `file_id` | int | 是 | 目標圖片檔案 ID |
| `template` | string | 否 | 自訂範本字串（省略時使用預設值） |

### 回應

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

### curl 範例

```bash
curl -H "Authorization: Bearer sk_xxxxx" \
  "http://localhost:5000/api/sns/preview?file_id=42"
```

### GET /api/sns/x/intent

產生 X (Twitter) Web Intent URL。開啟預填文字的 X 發文介面。

| 參數 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `file_id` | int | 是 | 目標圖片檔案 ID |

### 回應

```json
{
  "url": "https://twitter.com/intent/tweet?text=New+artwork%3A+sunset+landscape+%23aiart"
}
```

---

## Bluesky 發文

### POST /api/sns/bluesky/post

向 Bluesky 發送文字（可選附帶圖片）。

### 請求

```json
{
  "file_id": 42,
  "text": "Check out my new artwork! #aiart",
  "attach_image": true
}
```

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `file_id` | int | 是 | 目標圖片檔案 ID |
| `text` | string | 否 | 發文文字（省略時使用範本展開） |
| `attach_image` | boolean | 否 | 在貼文中附帶圖片（預設: false） |

### 回應

```json
{
  "ok": true,
  "uri": "at://did:plc:xxxxx/app.bsky.feed.post/yyyyy"
}
```

### 錯誤回應

```json
{
  "ok": false,
  "error": "Authentication failed: invalid app password"
}
```

### POST /api/sns/bluesky/test

使用已設定的驗證資訊測試 Bluesky 連線。

### 回應

```json
{
  "ok": true,
  "handle": "user.bsky.social",
  "display_name": "My Display Name"
}
```

### 錯誤回應

```json
{
  "ok": false,
  "error": "Invalid identifier or password"
}
```

---

## SNS 設定

### GET /api/sns/config

取得 SNS 設定。密碼以遮罩方式顯示。

### 回應

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

儲存 SNS 設定。

### 請求

```json
{
  "bluesky_handle": "user.bsky.social",
  "bluesky_app_password": "xxxx-xxxx-xxxx-xxxx",
  "post_template": "{title} #aiart #{generator}"
}
```

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `bluesky_handle` | string | 否 | Bluesky 帳號代碼（例: `user.bsky.social`） |
| `bluesky_app_password` | string | 否 | Bluesky App Password |
| `post_template` | string | 否 | 包含 `{placeholder}` 變數的預設發文範本 |

### curl 範例

```bash
curl -X POST -H "Authorization: Bearer sk_xxxxx" \
  -H "Content-Type: application/json" \
  -H "X-Requested-With: XMLHttpRequest" \
  -d '{"bluesky_handle": "user.bsky.social", "bluesky_app_password": "xxxx-xxxx-xxxx-xxxx"}' \
  "http://localhost:5000/api/sns/config"
```

---

## Bluesky 通知佇列

### GET /api/sns/bsky/queue

使用可選篩選條件取得通知佇列項目。

| 參數 | 型別 | 說明 |
|------|------|------|
| `status` | string | 篩選: `pending`、`notified`、`dismissed`，或留空取得全部 |
| `type` | string | 通知類型篩選（例: `mention`、`reply`、`quote`、`like`、`repost`、`follow`） |
| `limit` | int | 最大結果數（預設 50） |

### 回應

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

取得用於 MCP 通知的待處理（pending）通知。

### 回應

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

設定佇列項目的分類結果。

### 請求

```json
{ "result": "valid" }
```

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `result` | string | 是 | `valid` 或 `invalid` |

### PUT /api/sns/bsky/queue/<queue_id>/status

更新佇列項目狀態。

### 請求

```json
{ "status": "notified" }
```

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `status` | string | 是 | `pending`、`notified` 或 `dismissed` |

### POST /api/sns/bsky/queue/<queue_id>/respond

對通知發送自動回覆。

### 請求

```json
{ "text": "Thank you for your kind words!" }
```

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `text` | string | 是 | 作為回覆發送的回應文字 |

### POST /api/sns/bsky/queue/poll

立即輪詢 Bluesky 新通知。

### curl 範例

```bash
curl -X POST -H "Authorization: Bearer sk_xxxxx" \
  -H "X-Requested-With: XMLHttpRequest" \
  "http://localhost:5000/api/sns/bsky/queue/poll"
```

---

## Bluesky 監控設定

### GET /api/sns/bsky/monitor/config

取得 Bluesky 通知監控設定。

### 回應

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

更新 Bluesky 通知監控設定。僅更新提供的欄位。

### 請求

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

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `poll_interval_minutes` | int | 否 | 輪詢間隔（分鐘） |
| `auto_dismiss_follow` | boolean | 否 | 自動忽略追蹤通知 |
| `auto_dismiss_like` | boolean | 否 | 自動忽略按讚通知 |
| `auto_dismiss_repost` | boolean | 否 | 自動忽略轉發通知 |
| `auto_respond_enabled` | boolean | 否 | 啟用自動回覆 |
| `notify_on_connect` | boolean | 否 | MCP 用戶端連線時傳送通知 |

---

## 分類提示詞 & 自動回覆範本

### GET /api/sns/bsky/monitor/triage-prompts

取得可編輯的分類提示詞、自動回覆範本及其預設值。

### 回應

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

更新分類提示詞及/或自動回覆範本。僅更新提供的欄位。

### 請求

```json
{
  "triage_prompts": {
    "mention": "自訂提及分類提示詞...",
    "reply": "自訂回覆分類提示詞...",
    "quote": "自訂引用分類提示詞..."
  },
  "auto_responses": {
    "mention": "自訂提及自動回覆...",
    "reply": "自訂回覆自動回覆...",
    "quote": "自訂引用自動回覆..."
  }
}
```

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `triage_prompts` | object | 否 | 以通知類型（`mention`、`reply`、`quote`）為鍵的分類提示詞 |
| `auto_responses` | object | 否 | 以通知類型為鍵的自動回覆範本 |
