# SNS Share API

SNS 共有、Bluesky 投稿、通知キュー管理に関する API。

`routes/sns_share.py` が提供するエンドポイント群。全エンドポイントで認証 (PIN セッションまたは API Key) が必要。

## プレビュー & X Intent

### GET /api/sns/preview

投稿テンプレートを画像メタデータで展開し、プレビューを返す。共有前の内容確認に使用。

### パラメータ

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `file_id` | int | Yes | 対象画像ファイル ID |
| `template` | string | No | カスタムテンプレート文字列 (省略時はデフォルト使用) |

### レスポンス

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

### curl 例

```bash
curl -H "Authorization: Bearer sk_xxxxx" \
  "http://localhost:5000/api/sns/preview?file_id=42"
```

### GET /api/sns/x/intent

X (Twitter) Web Intent URL を生成。X の投稿画面をテキスト入力済みで開く。

### パラメータ

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `file_id` | int | Yes | 対象画像ファイル ID |

### レスポンス

```json
{
  "url": "https://twitter.com/intent/tweet?text=New+artwork%3A+sunset+landscape+%23aiart"
}
```

---

## Bluesky 投稿

### POST /api/sns/bluesky/post

Bluesky にテキスト (およびオプションで画像) を投稿。

### リクエスト

```json
{
  "file_id": 42,
  "text": "Check out my new artwork! #aiart",
  "attach_image": true
}
```

| フィールド | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `file_id` | int | Yes | 対象画像ファイル ID |
| `text` | string | No | 投稿テキスト (省略時はテンプレート展開を使用) |
| `attach_image` | boolean | No | 画像を投稿に添付 (デフォルト: false) |

### レスポンス

```json
{
  "ok": true,
  "uri": "at://did:plc:xxxxx/app.bsky.feed.post/yyyyy"
}
```

### エラーレスポンス

```json
{
  "ok": false,
  "error": "Authentication failed: invalid app password"
}
```

### POST /api/sns/bluesky/test

設定済みの認証情報で Bluesky への接続テストを実行。

### レスポンス

```json
{
  "ok": true,
  "handle": "user.bsky.social",
  "display_name": "My Display Name"
}
```

### エラーレスポンス

```json
{
  "ok": false,
  "error": "Invalid identifier or password"
}
```

---

## SNS 設定

### GET /api/sns/config

SNS 設定を取得。パスワードはマスクされて返却される。

### レスポンス

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

SNS 設定を保存。

### リクエスト

```json
{
  "bluesky_handle": "user.bsky.social",
  "bluesky_app_password": "xxxx-xxxx-xxxx-xxxx",
  "post_template": "{title} #aiart #{generator}"
}
```

| フィールド | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `bluesky_handle` | string | No | Bluesky ハンドル (例: `user.bsky.social`) |
| `bluesky_app_password` | string | No | Bluesky App Password |
| `post_template` | string | No | `{placeholder}` 変数を含むデフォルト投稿テンプレート |

### curl 例

```bash
curl -X POST -H "Authorization: Bearer sk_xxxxx" \
  -H "Content-Type: application/json" \
  -H "X-Requested-With: XMLHttpRequest" \
  -d '{"bluesky_handle": "user.bsky.social", "bluesky_app_password": "xxxx-xxxx-xxxx-xxxx"}' \
  "http://localhost:5000/api/sns/config"
```

---

## Bluesky 通知キュー

### GET /api/sns/bsky/queue

通知キューのアイテムをフィルタ付きで取得。

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `status` | string | フィルタ: `pending`, `notified`, `dismissed`、または空で全件 |
| `type` | string | 通知タイプフィルタ (例: `mention`, `reply`, `quote`, `like`, `repost`, `follow`) |
| `limit` | int | 最大件数 (デフォルト 50) |

### レスポンス

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

MCP 通知用の未処理 (pending) 通知を取得。

### レスポンス

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

キューアイテムのトリアージ結果を設定。

### リクエスト

```json
{ "result": "valid" }
```

| フィールド | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `result` | string | Yes | `valid` または `invalid` |

### PUT /api/sns/bsky/queue/<queue_id>/status

キューアイテムのステータスを更新。

### リクエスト

```json
{ "status": "notified" }
```

| フィールド | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `status` | string | Yes | `pending`, `notified`, または `dismissed` |

### POST /api/sns/bsky/queue/<queue_id>/respond

通知に対して自動返信を送信。

### リクエスト

```json
{ "text": "Thank you for your kind words!" }
```

| フィールド | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `text` | string | Yes | リプライとして投稿する返信テキスト |

### POST /api/sns/bsky/queue/poll

Bluesky の新規通知を即時ポーリング。

### curl 例

```bash
curl -X POST -H "Authorization: Bearer sk_xxxxx" \
  -H "X-Requested-With: XMLHttpRequest" \
  "http://localhost:5000/api/sns/bsky/queue/poll"
```

---

## Bluesky モニター設定

### GET /api/sns/bsky/monitor/config

Bluesky 通知モニターの設定を取得。

### レスポンス

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

Bluesky 通知モニターの設定を更新。指定されたフィールドのみ更新される。

### リクエスト

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

| フィールド | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `poll_interval_minutes` | int | No | ポーリング間隔 (分) |
| `auto_dismiss_follow` | boolean | No | フォロー通知を自動却下 |
| `auto_dismiss_like` | boolean | No | いいね通知を自動却下 |
| `auto_dismiss_repost` | boolean | No | リポスト通知を自動却下 |
| `auto_respond_enabled` | boolean | No | 自動返信を有効化 |
| `notify_on_connect` | boolean | No | MCP クライアント接続時に通知送信 |

---

## トリアージプロンプト & 自動返信テンプレート

### GET /api/sns/bsky/monitor/triage-prompts

編集可能なトリアージプロンプト、自動返信テンプレート、およびデフォルト値を取得。

### レスポンス

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

トリアージプロンプトおよび/または自動返信テンプレートを更新。指定されたフィールドのみ更新される。

### リクエスト

```json
{
  "triage_prompts": {
    "mention": "カスタムメンショントリアージプロンプト...",
    "reply": "カスタムリプライトリアージプロンプト...",
    "quote": "カスタム引用トリアージプロンプト..."
  },
  "auto_responses": {
    "mention": "カスタムメンション自動返信...",
    "reply": "カスタムリプライ自動返信...",
    "quote": "カスタム引用自動返信..."
  }
}
```

| フィールド | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `triage_prompts` | object | No | 通知タイプ (`mention`, `reply`, `quote`) をキーとするトリアージプロンプト |
| `auto_responses` | object | No | 通知タイプをキーとする自動返信テンプレート |
