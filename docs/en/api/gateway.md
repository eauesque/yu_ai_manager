# Gateway API Reference

## Authentication

All endpoints (except loopback bypass paths) require:
```
Authorization: Bearer <api_key>
```

## LLM Endpoints

| Method | Path | Scope | Description |
|--------|------|-------|-------------|
| POST | /v1/chat/completions | llm:chat | OpenAI-compatible chat |
| POST | /v1/messages | llm:messages | Anthropic Messages API |
| GET | /v1/models | llm:models | List available models |
| GET | /v1/router/capabilities | (auth only) | Gateway capabilities |

## SD WebUI Endpoints

| Method | Path | Scope |
|--------|------|-------|
| POST | /sd/sdapi/v1/txt2img | sd:generate |
| POST | /sd/sdapi/v1/img2img | sd:generate |
| GET | /sd/sdapi/v1/samplers | sd:query |
| GET | /sd/sdapi/v1/sd-models | sd:query |
| GET | /sd/sdapi/v1/options | sd:admin |
| POST | /sd/sdapi/v1/options | sd:admin |

## ComfyUI Endpoints

| Method | Path | Scope |
|--------|------|-------|
| POST | /comfy/api/prompt | comfy:generate |
| GET | /comfy/api/queue | comfy:query |
| GET | /comfy/api/history | comfy:query |
| GET | /comfy/api/view | comfy:query |
| WS | /comfy/ws | comfy:generate |

## Status Endpoints

| Method | Path | Scope |
|--------|------|-------|
| GET | /v1/node/services | node:status |

## Admin API

| Method | Path | Scope | Description |
|--------|------|-------|-------------|
| POST | /api/gateway/keys | * | Create key (returns secret once) |
| GET | /api/gateway/keys | * | List keys (no secrets) |
| PATCH | /api/gateway/keys/{id} | * | Update scopes/models |
| DELETE | /api/gateway/keys/{id} | * | Delete key |
| POST | /api/gateway/auth/reload | * | Hot reload config |

## Error Format

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
