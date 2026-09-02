# Inbound Webhook API

A receive endpoint for sending events from external services to the yu_ai_manager event_bus.

## Receive Endpoint (No auth required — token-based)

`POST /api/webhooks/receive/{token}`

### Request Body

| Field | Type | Description |
|-------|------|-------------|
| event | string | event_type to fire (default: `webhook.received`) |
| data | object | Event data |

### Response

```json
{"ok": true, "event": "scan.start"}
```

### Errors

| Code | Description |
|------|-------------|
| 403 | Invalid token / HMAC mismatch / event not in allowed_events |

## Management API (PIN session required)

### Create

`POST /api/webhooks/inbound`

```json
{"label": "n8n trigger", "allowed_events": ["scan.start"]}
```

Response:

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

### List

`GET /api/webhooks/inbound`

### Update

`PUT /api/webhooks/inbound/{id}`

```json
{"label": "updated", "allowed_events": ["scan.start", "tag.add"], "active": true}
```

### Delete

`DELETE /api/webhooks/inbound/{id}`

## Authentication

- Accepted if the token in the URL matches
- If `X-Webhook-Signature` header is present, additional HMAC-SHA256 verification is performed (optional)

## Security

- Token is 64-character hex (256 bit)
- `allowed_events` restricts which events can be triggered
- Empty `allowed_events` array = all events allowed
