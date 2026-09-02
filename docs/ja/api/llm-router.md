# LLM Router API

YU AI Manager の LLM Router は、複数のローカル LLM バックエンド (Ollama,
hailo-ollama 等) を Anthropic Messages API および OpenAI Chat Completions
API の両プロトコルで統一インターフェイス化する。

ベース URL: `http://localhost:5000/v1`

## エンドポイント

### POST /v1/messages

Anthropic Messages API 互換。Claude Code / Claude Desktop の
`ANTHROPIC_BASE_URL=http://localhost:5000/v1` で接続可能。

リクエスト:
```json
{
  "model": "local-coder-big",
  "messages": [{"role": "user", "content": "..."}],
  "system": "...",
  "max_tokens": 1024,
  "stream": false
}
```

レスポンス: Anthropic Messages 形式。

### POST /v1/chat/completions

OpenAI Chat Completions API 互換。Continue / Aider 等の OpenAI 互換クライアント用。

### GET /v1/models

全バックエンドの全モデル + alias 一覧を OpenAI `/v1/models` 形式で返す。
`yu_metadata` フィールドに context_window / size_b / backend_status 等の独自情報。

### GET /v1/router/health

Router 自身の状態とバックエンドサマリ。診断用。

### POST /v1/router/refresh

`{"backend": "ollama-mac"}` で単一バックエンド、ボディなしで全バックエンドの
discovery を強制再実行。

### POST /v1/router/estimate

トークン数見積もり (tiktoken cl100k 近似)。

### GET /v1/router/capabilities/{target}

モデルの good_at / weak_at / notes 等の curated メタデータ。

## 認証

`config.json` の `llm_router.auth.mode`:

| mode | 動作 |
|---|---|
| `loopback` (default) | 127.0.0.1 / ::1 のみ無認証で許可 |
| `api_key` | `x-api-key` または `Authorization: Bearer` ヘッダ検証 |
| `none` | 認証なし |

詳細は `docs/ja/llm-router/setup.md` 参照。
