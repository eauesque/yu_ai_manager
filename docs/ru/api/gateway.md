# Справочник API Gateway

## Аутентификация

Все эндпоинты (кроме путей обхода loopback) требуют:
```
Authorization: Bearer <api_key>
```

## LLM Эндпоинты

| Метод | Путь | Scope | Описание |
|--------|------|-------|----------|
| POST | /v1/chat/completions | llm:chat | Чат, совместимый с OpenAI |
| POST | /v1/messages | llm:messages | Anthropic Messages API |
| GET | /v1/models | llm:models | Список доступных моделей |
| GET | /v1/router/capabilities | (только auth) | Capabilities Gateway |

## Эндпоинты SD WebUI

| Метод | Путь | Scope |
|--------|------|-------|
| POST | /sd/sdapi/v1/txt2img | sd:generate |
| POST | /sd/sdapi/v1/img2img | sd:generate |
| GET | /sd/sdapi/v1/samplers | sd:query |
| GET | /sd/sdapi/v1/sd-models | sd:query |
| GET | /sd/sdapi/v1/options | sd:admin |
| POST | /sd/sdapi/v1/options | sd:admin |

## Эндпоинты ComfyUI

| Метод | Путь | Scope |
|--------|------|-------|
| POST | /comfy/api/prompt | comfy:generate |
| GET | /comfy/api/queue | comfy:query |
| GET | /comfy/api/history | comfy:query |
| GET | /comfy/api/view | comfy:query |
| WS | /comfy/ws | comfy:generate |

## Эндпоинты статуса

| Метод | Путь | Scope |
|--------|------|-------|
| GET | /v1/node/services | node:status |

## Admin API

| Метод | Путь | Scope | Описание |
|--------|------|-------|----------|
| POST | /api/gateway/keys | * | Создать ключ (secret показывается один раз) |
| GET | /api/gateway/keys | * | Список ключей (без secret) |
| PATCH | /api/gateway/keys/{id} | * | Обновить scope/модели |
| DELETE | /api/gateway/keys/{id} | * | Удалить ключ |
| POST | /api/gateway/auth/reload | * | Горячая перезагрузка конфигурации |

## Формат ошибки

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
