# Référence de l'API Gateway

## Authentification

Tous les endpoints (sauf les chemins de bypass loopback) nécessitent :
```
Authorization: Bearer <api_key>
```

## Endpoints LLM

| Méthode | Chemin | Scope | Description |
|--------|------|-------|-------------|
| POST | /v1/chat/completions | llm:chat | Chat compatible OpenAI |
| POST | /v1/messages | llm:messages | Anthropic Messages API |
| GET | /v1/models | llm:models | Lister les modèles disponibles |
| GET | /v1/router/capabilities | (auth uniquement) | Capabilities du Gateway |

## Endpoints SD WebUI

| Méthode | Chemin | Scope |
|--------|------|-------|
| POST | /sd/sdapi/v1/txt2img | sd:generate |
| POST | /sd/sdapi/v1/img2img | sd:generate |
| GET | /sd/sdapi/v1/samplers | sd:query |
| GET | /sd/sdapi/v1/sd-models | sd:query |
| GET | /sd/sdapi/v1/options | sd:admin |
| POST | /sd/sdapi/v1/options | sd:admin |

## Endpoints ComfyUI

| Méthode | Chemin | Scope |
|--------|------|-------|
| POST | /comfy/api/prompt | comfy:generate |
| GET | /comfy/api/queue | comfy:query |
| GET | /comfy/api/history | comfy:query |
| GET | /comfy/api/view | comfy:query |
| WS | /comfy/ws | comfy:generate |

## Endpoints de Statut

| Méthode | Chemin | Scope |
|--------|------|-------|
| GET | /v1/node/services | node:status |

## API d'Administration

| Méthode | Chemin | Scope | Description |
|--------|------|-------|-------------|
| POST | /api/gateway/keys | * | Créer une clé (secret affiché une fois) |
| GET | /api/gateway/keys | * | Lister les clés (sans secrets) |
| PATCH | /api/gateway/keys/{id} | * | Mettre à jour scopes/modèles |
| DELETE | /api/gateway/keys/{id} | * | Supprimer une clé |
| POST | /api/gateway/auth/reload | * | Rechargement à chaud de la config |

## Format d'Erreur

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
