# Referência da API Gateway

## Autenticação

Todos os endpoints (exceto caminhos de bypass loopback) exigem:
```
Authorization: Bearer <api_key>
```

## Endpoints LLM

| Método | Caminho | Scope | Descrição |
|--------|------|-------|-----------|
| POST | /v1/chat/completions | llm:chat | Chat compatível com OpenAI |
| POST | /v1/messages | llm:messages | Anthropic Messages API |
| GET | /v1/models | llm:models | Listar modelos disponíveis |
| GET | /v1/router/capabilities | (apenas auth) | Capabilities do Gateway |

## Endpoints SD WebUI

| Método | Caminho | Scope |
|--------|------|-------|
| POST | /sd/sdapi/v1/txt2img | sd:generate |
| POST | /sd/sdapi/v1/img2img | sd:generate |
| GET | /sd/sdapi/v1/samplers | sd:query |
| GET | /sd/sdapi/v1/sd-models | sd:query |
| GET | /sd/sdapi/v1/options | sd:admin |
| POST | /sd/sdapi/v1/options | sd:admin |

## Endpoints ComfyUI

| Método | Caminho | Scope |
|--------|------|-------|
| POST | /comfy/api/prompt | comfy:generate |
| GET | /comfy/api/queue | comfy:query |
| GET | /comfy/api/history | comfy:query |
| GET | /comfy/api/view | comfy:query |
| WS | /comfy/ws | comfy:generate |

## Endpoints de Status

| Método | Caminho | Scope |
|--------|------|-------|
| GET | /v1/node/services | node:status |

## API de Administração

| Método | Caminho | Scope | Descrição |
|--------|------|-------|-----------|
| POST | /api/gateway/keys | * | Criar chave (secret exibido uma vez) |
| GET | /api/gateway/keys | * | Listar chaves (sem secrets) |
| PATCH | /api/gateway/keys/{id} | * | Atualizar scopes/modelos |
| DELETE | /api/gateway/keys/{id} | * | Excluir chave |
| POST | /api/gateway/auth/reload | * | Recarregar configuração a quente |

## Formato de Erro

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
