# Gateway API 参考

## 认证

除回环绕过路径外，所有端点均需要：
```
Authorization: Bearer <api_key>
```

## LLM 端点

| 方法 | 路径 | Scope | 说明 |
|--------|------|-------|-------------|
| POST | /v1/chat/completions | llm:chat | OpenAI 兼容聊天 |
| POST | /v1/messages | llm:messages | Anthropic Messages API |
| GET | /v1/models | llm:models | 列出可用模型 |
| GET | /v1/router/capabilities | （仅认证） | Gateway capabilities |

## SD WebUI 端点

| 方法 | 路径 | Scope |
|--------|------|-------|
| POST | /sd/sdapi/v1/txt2img | sd:generate |
| POST | /sd/sdapi/v1/img2img | sd:generate |
| GET | /sd/sdapi/v1/samplers | sd:query |
| GET | /sd/sdapi/v1/sd-models | sd:query |
| GET | /sd/sdapi/v1/options | sd:admin |
| POST | /sd/sdapi/v1/options | sd:admin |

## ComfyUI 端点

| 方法 | 路径 | Scope |
|--------|------|-------|
| POST | /comfy/api/prompt | comfy:generate |
| GET | /comfy/api/queue | comfy:query |
| GET | /comfy/api/history | comfy:query |
| GET | /comfy/api/view | comfy:query |
| WS | /comfy/ws | comfy:generate |

## 状态端点

| 方法 | 路径 | Scope |
|--------|------|-------|
| GET | /v1/node/services | node:status |

## 管理 API

| 方法 | 路径 | Scope | 说明 |
|--------|------|-------|-------------|
| POST | /api/gateway/keys | * | 创建密钥（secret 仅显示一次） |
| GET | /api/gateway/keys | * | 列出密钥（无 secret） |
| PATCH | /api/gateway/keys/{id} | * | 更新 scope/models |
| DELETE | /api/gateway/keys/{id} | * | 删除密钥 |
| POST | /api/gateway/auth/reload | * | 热重载配置 |

## 错误格式

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
