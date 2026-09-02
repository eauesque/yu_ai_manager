# Gateway API 參考

## 驗證

除回送繞過路徑外，所有端點均需要：
```
Authorization: Bearer <api_key>
```

## LLM 端點

| 方法 | 路徑 | Scope | 說明 |
|--------|------|-------|-------------|
| POST | /v1/chat/completions | llm:chat | OpenAI 相容聊天 |
| POST | /v1/messages | llm:messages | Anthropic Messages API |
| GET | /v1/models | llm:models | 列出可用模型 |
| GET | /v1/router/capabilities | （僅驗證） | Gateway capabilities |

## SD WebUI 端點

| 方法 | 路徑 | Scope |
|--------|------|-------|
| POST | /sd/sdapi/v1/txt2img | sd:generate |
| POST | /sd/sdapi/v1/img2img | sd:generate |
| GET | /sd/sdapi/v1/samplers | sd:query |
| GET | /sd/sdapi/v1/sd-models | sd:query |
| GET | /sd/sdapi/v1/options | sd:admin |
| POST | /sd/sdapi/v1/options | sd:admin |

## ComfyUI 端點

| 方法 | 路徑 | Scope |
|--------|------|-------|
| POST | /comfy/api/prompt | comfy:generate |
| GET | /comfy/api/queue | comfy:query |
| GET | /comfy/api/history | comfy:query |
| GET | /comfy/api/view | comfy:query |
| WS | /comfy/ws | comfy:generate |

## 狀態端點

| 方法 | 路徑 | Scope |
|--------|------|-------|
| GET | /v1/node/services | node:status |

## 管理 API

| 方法 | 路徑 | Scope | 說明 |
|--------|------|-------|-------------|
| POST | /api/gateway/keys | * | 建立金鑰（secret 僅顯示一次） |
| GET | /api/gateway/keys | * | 列出金鑰（無 secret） |
| PATCH | /api/gateway/keys/{id} | * | 更新 scope/models |
| DELETE | /api/gateway/keys/{id} | * | 刪除金鑰 |
| POST | /api/gateway/auth/reload | * | 熱重載設定 |

## 錯誤格式

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
