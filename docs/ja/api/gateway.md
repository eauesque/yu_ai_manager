# Gateway API リファレンス

## 認証

ループバックバイパスパスを除く全エンドポイントで以下が必要です:
```
Authorization: Bearer <api_key>
```

## LLM エンドポイント

| メソッド | パス | Scope | 説明 |
|--------|------|-------|-------------|
| POST | /v1/chat/completions | llm:chat | OpenAI 互換チャット |
| POST | /v1/messages | llm:messages | Anthropic Messages API |
| GET | /v1/models | llm:models | 利用可能なモデル一覧 |
| GET | /v1/router/capabilities | (認証のみ) | Gateway の capabilities |

## SD WebUI エンドポイント

| メソッド | パス | Scope |
|--------|------|-------|
| POST | /sd/sdapi/v1/txt2img | sd:generate |
| POST | /sd/sdapi/v1/img2img | sd:generate |
| GET | /sd/sdapi/v1/samplers | sd:query |
| GET | /sd/sdapi/v1/sd-models | sd:query |
| GET | /sd/sdapi/v1/options | sd:admin |
| POST | /sd/sdapi/v1/options | sd:admin |

## ComfyUI エンドポイント

| メソッド | パス | Scope |
|--------|------|-------|
| POST | /comfy/api/prompt | comfy:generate |
| GET | /comfy/api/queue | comfy:query |
| GET | /comfy/api/history | comfy:query |
| GET | /comfy/api/view | comfy:query |
| WS | /comfy/ws | comfy:generate |

## ステータスエンドポイント

| メソッド | パス | Scope |
|--------|------|-------|
| GET | /v1/node/services | node:status |

## 管理 API

| メソッド | パス | Scope | 説明 |
|--------|------|-------|-------------|
| POST | /api/gateway/keys | * | キー作成（secret は一度のみ表示） |
| GET | /api/gateway/keys | * | キー一覧（secret なし） |
| PATCH | /api/gateway/keys/{id} | * | scope/models 更新 |
| DELETE | /api/gateway/keys/{id} | * | キー削除 |
| POST | /api/gateway/auth/reload | * | 設定のホットリロード |

## エラー形式

```json
{
  "error": {
    "message": "...",
    "type": "authentication_error | invalid_request_error | server_error",
    "code": "invalid_api_key | insufficient_scope | model_not_found | backend_unavailable | path_traversal | body_too_large",
    "param": "..."
  }
}
```
