# Riferimento API Gateway

## Autenticazione

Tutti gli endpoint (eccetto i percorsi di bypass loopback) richiedono:
```
Authorization: Bearer <api_key>
```

## Endpoint LLM

| Metodo | Percorso | Scope | Descrizione |
|--------|------|-------|-------------|
| POST | /v1/chat/completions | llm:chat | Chat compatibile OpenAI |
| POST | /v1/messages | llm:messages | Anthropic Messages API |
| GET | /v1/models | llm:models | Elenco modelli disponibili |
| GET | /v1/router/capabilities | (solo auth) | Capabilities del Gateway |

## Endpoint SD WebUI

| Metodo | Percorso | Scope |
|--------|------|-------|
| POST | /sd/sdapi/v1/txt2img | sd:generate |
| POST | /sd/sdapi/v1/img2img | sd:generate |
| GET | /sd/sdapi/v1/samplers | sd:query |
| GET | /sd/sdapi/v1/sd-models | sd:query |
| GET | /sd/sdapi/v1/options | sd:admin |
| POST | /sd/sdapi/v1/options | sd:admin |

## Endpoint ComfyUI

| Metodo | Percorso | Scope |
|--------|------|-------|
| POST | /comfy/api/prompt | comfy:generate |
| GET | /comfy/api/queue | comfy:query |
| GET | /comfy/api/history | comfy:query |
| GET | /comfy/api/view | comfy:query |
| WS | /comfy/ws | comfy:generate |

## Endpoint di Stato

| Metodo | Percorso | Scope |
|--------|------|-------|
| GET | /v1/node/services | node:status |

## API di Amministrazione

| Metodo | Percorso | Scope | Descrizione |
|--------|------|-------|-------------|
| POST | /api/gateway/keys | * | Crea chiave (secret mostrato una volta) |
| GET | /api/gateway/keys | * | Elenco chiavi (senza secret) |
| PATCH | /api/gateway/keys/{id} | * | Aggiorna scope/modelli |
| DELETE | /api/gateway/keys/{id} | * | Elimina chiave |
| POST | /api/gateway/auth/reload | * | Ricarica configurazione a caldo |

## Formato Errore

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
