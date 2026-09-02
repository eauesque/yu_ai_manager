# Referencia de API de Gateway

## Autenticación

Todos los endpoints (excepto rutas de bypass de loopback) requieren:
```
Authorization: Bearer <api_key>
```

## Endpoints LLM

| Método | Ruta | Scope | Descripción |
|--------|------|-------|-------------|
| POST | /v1/chat/completions | llm:chat | Chat compatible con OpenAI |
| POST | /v1/messages | llm:messages | Anthropic Messages API |
| GET | /v1/models | llm:models | Listar modelos disponibles |
| GET | /v1/router/capabilities | (solo auth) | Capacidades del Gateway |

## Endpoints SD WebUI

| Método | Ruta | Scope |
|--------|------|-------|
| POST | /sd/sdapi/v1/txt2img | sd:generate |
| POST | /sd/sdapi/v1/img2img | sd:generate |
| GET | /sd/sdapi/v1/samplers | sd:query |
| GET | /sd/sdapi/v1/sd-models | sd:query |
| GET | /sd/sdapi/v1/options | sd:admin |
| POST | /sd/sdapi/v1/options | sd:admin |

## Endpoints ComfyUI

| Método | Ruta | Scope |
|--------|------|-------|
| POST | /comfy/api/prompt | comfy:generate |
| GET | /comfy/api/queue | comfy:query |
| GET | /comfy/api/history | comfy:query |
| GET | /comfy/api/view | comfy:query |
| WS | /comfy/ws | comfy:generate |

## Endpoints de Estado

| Método | Ruta | Scope |
|--------|------|-------|
| GET | /v1/node/services | node:status |

## API de Administración

| Método | Ruta | Scope | Descripción |
|--------|------|-------|-------------|
| POST | /api/gateway/keys | * | Crear clave (secret se muestra una vez) |
| GET | /api/gateway/keys | * | Listar claves (sin secrets) |
| PATCH | /api/gateway/keys/{id} | * | Actualizar scopes/modelos |
| DELETE | /api/gateway/keys/{id} | * | Eliminar clave |
| POST | /api/gateway/auth/reload | * | Recargar configuración en caliente |

## Formato de Error

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
