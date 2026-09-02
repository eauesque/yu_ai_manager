# Inbound Webhook API

外部サービスから yu_ai_manager の event_bus にイベントを送信するための受信エンドポイント。

## 受信エンドポイント（認証不要 — token ベース）

`POST /api/webhooks/receive/{token}`

### リクエストボディ

| フィールド | 型 | 説明 |
|-----------|------|------|
| event | string | 発火する event_type（省略時: `webhook.received`） |
| data | object | イベントデータ |

### レスポンス

```json
{"ok": true, "event": "scan.start"}
```

### エラー

| コード | 説明 |
|--------|------|
| 403 | token 無効 / HMAC 不一致 / event が allowed_events 外 |

## 管理 API（PIN セッション必須）

### 作成

`POST /api/webhooks/inbound`

```json
{"label": "n8n trigger", "allowed_events": ["scan.start"]}
```

レスポンス:

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

### 一覧

`GET /api/webhooks/inbound`

### 更新

`PUT /api/webhooks/inbound/{id}`

```json
{"label": "updated", "allowed_events": ["scan.start", "tag.add"], "active": true}
```

### 削除

`DELETE /api/webhooks/inbound/{id}`

## 認証

- URL 内の token が一致すれば受け入れ
- `X-Webhook-Signature` ヘッダがあれば HMAC-SHA256 で追加検証（オプション）

## セキュリティ

- token は 64 文字 hex（256 bit）
- `allowed_events` でトリガー可能なイベントを制限
- `allowed_events` が空配列 = 全イベント許可
