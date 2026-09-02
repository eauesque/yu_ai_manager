# SNS Share API

APIs for SNS sharing, Bluesky posting, and notification queue management.

Provided by `routes/sns_share.py`. All endpoints require authentication (PIN session or API Key).

## Preview & X Intent

### GET /api/sns/preview

Expand a post template with image metadata and return a preview. Useful for previewing what will be posted before sharing.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | Target image file ID |
| `template` | string | No | Custom template string (uses default if omitted) |

### Response

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

### curl Example

```bash
curl -H "Authorization: Bearer sk_xxxxx" \
  "http://localhost:5000/api/sns/preview?file_id=42"
```

### GET /api/sns/x/intent

Generate an X (Twitter) Web Intent URL for sharing. Opens the X compose dialog with pre-filled text.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | Target image file ID |

### Response

```json
{
  "url": "https://twitter.com/intent/tweet?text=New+artwork%3A+sunset+landscape+%23aiart"
}
```

---

## Bluesky Posting

### POST /api/sns/bluesky/post

Post text (and optionally an image) to Bluesky.

### Request

```json
{
  "file_id": 42,
  "text": "Check out my new artwork! #aiart",
  "attach_image": true
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file_id` | int | Yes | Target image file ID |
| `text` | string | No | Post text (uses template expansion if omitted) |
| `attach_image` | boolean | No | Attach the image to the post (default: false) |

### Response

```json
{
  "ok": true,
  "uri": "at://did:plc:xxxxx/app.bsky.feed.post/yyyyy"
}
```

### Error Response

```json
{
  "ok": false,
  "error": "Authentication failed: invalid app password"
}
```

### POST /api/sns/bluesky/test

Test Bluesky connection with configured credentials.

### Response

```json
{
  "ok": true,
  "handle": "user.bsky.social",
  "display_name": "My Display Name"
}
```

### Error Response

```json
{
  "ok": false,
  "error": "Invalid identifier or password"
}
```

---

## SNS Config

### GET /api/sns/config

Get SNS configuration. Passwords are masked in the response.

### Response

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

Save SNS configuration.

### Request

```json
{
  "bluesky_handle": "user.bsky.social",
  "bluesky_app_password": "xxxx-xxxx-xxxx-xxxx",
  "post_template": "{title} #aiart #{generator}"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `bluesky_handle` | string | No | Bluesky handle (e.g. `user.bsky.social`) |
| `bluesky_app_password` | string | No | Bluesky App Password |
| `post_template` | string | No | Default post template with `{placeholder}` variables |

### curl Example

```bash
curl -X POST -H "Authorization: Bearer sk_xxxxx" \
  -H "Content-Type: application/json" \
  -H "X-Requested-With: XMLHttpRequest" \
  -d '{"bluesky_handle": "user.bsky.social", "bluesky_app_password": "xxxx-xxxx-xxxx-xxxx"}' \
  "http://localhost:5000/api/sns/config"
```

---

## Bluesky Notification Queue

### GET /api/sns/bsky/queue

List notification queue items with optional filters.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `status` | string | Filter: `pending`, `notified`, `dismissed`, or empty for all |
| `type` | string | Notification type filter (e.g. `mention`, `reply`, `quote`, `like`, `repost`, `follow`) |
| `limit` | int | Max results (default 50) |

### Response

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

Get pending (unprocessed) notifications for MCP notification.

### Response

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

Set triage result for a queue item.

### Request

```json
{ "result": "valid" }
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `result` | string | Yes | `valid` or `invalid` |

### PUT /api/sns/bsky/queue/<queue_id>/status

Update queue item status.

### Request

```json
{ "status": "notified" }
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `status` | string | Yes | `pending`, `notified`, or `dismissed` |

### POST /api/sns/bsky/queue/<queue_id>/respond

Send an auto-response to a notification.

### Request

```json
{ "text": "Thank you for your kind words!" }
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `text` | string | Yes | Response text to post as a reply |

### POST /api/sns/bsky/queue/poll

Trigger immediate polling for new Bluesky notifications.

### curl Example

```bash
curl -X POST -H "Authorization: Bearer sk_xxxxx" \
  -H "X-Requested-With: XMLHttpRequest" \
  "http://localhost:5000/api/sns/bsky/queue/poll"
```

---

## Bluesky Monitor Config

### GET /api/sns/bsky/monitor/config

Get Bluesky notification monitor settings.

### Response

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

Update Bluesky notification monitor settings. Only provided fields are updated.

### Request

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

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `poll_interval_minutes` | int | No | Polling interval in minutes |
| `auto_dismiss_follow` | boolean | No | Auto-dismiss follow notifications |
| `auto_dismiss_like` | boolean | No | Auto-dismiss like notifications |
| `auto_dismiss_repost` | boolean | No | Auto-dismiss repost notifications |
| `auto_respond_enabled` | boolean | No | Enable auto-responses |
| `notify_on_connect` | boolean | No | Send notification on MCP client connect |

---

## Triage Prompts & Auto-Response Templates

### GET /api/sns/bsky/monitor/triage-prompts

Get editable triage prompts, auto-response templates, and their default values.

### Response

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

Update triage prompts and/or auto-response templates. Only provided fields are updated.

### Request

```json
{
  "triage_prompts": {
    "mention": "Custom mention triage prompt...",
    "reply": "Custom reply triage prompt...",
    "quote": "Custom quote triage prompt..."
  },
  "auto_responses": {
    "mention": "Custom mention auto-response...",
    "reply": "Custom reply auto-response...",
    "quote": "Custom quote auto-response..."
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `triage_prompts` | object | No | Triage prompts keyed by notification type (`mention`, `reply`, `quote`) |
| `auto_responses` | object | No | Auto-response templates keyed by notification type |
