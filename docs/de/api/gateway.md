# Gateway API-Referenz

## Authentifizierung

Alle Endpunkte (außer Loopback-Bypass-Pfaden) erfordern:
```
Authorization: Bearer <api_key>
```

## LLM-Endpunkte

| Methode | Pfad | Scope | Beschreibung |
|--------|------|-------|--------------|
| POST | /v1/chat/completions | llm:chat | OpenAI-kompatibler Chat |
| POST | /v1/messages | llm:messages | Anthropic Messages API |
| GET | /v1/models | llm:models | Verfügbare Modelle auflisten |
| GET | /v1/router/capabilities | (nur Auth) | Gateway-Capabilities |

## SD WebUI-Endpunkte

| Methode | Pfad | Scope |
|--------|------|-------|
| POST | /sd/sdapi/v1/txt2img | sd:generate |
| POST | /sd/sdapi/v1/img2img | sd:generate |
| GET | /sd/sdapi/v1/samplers | sd:query |
| GET | /sd/sdapi/v1/sd-models | sd:query |
| GET | /sd/sdapi/v1/options | sd:admin |
| POST | /sd/sdapi/v1/options | sd:admin |

## ComfyUI-Endpunkte

| Methode | Pfad | Scope |
|--------|------|-------|
| POST | /comfy/api/prompt | comfy:generate |
| GET | /comfy/api/queue | comfy:query |
| GET | /comfy/api/history | comfy:query |
| GET | /comfy/api/view | comfy:query |
| WS | /comfy/ws | comfy:generate |

## Status-Endpunkte

| Methode | Pfad | Scope |
|--------|------|-------|
| GET | /v1/node/services | node:status |

## Admin-API

| Methode | Pfad | Scope | Beschreibung |
|--------|------|-------|--------------|
| POST | /api/gateway/keys | * | Schlüssel erstellen (secret wird einmalig angezeigt) |
| GET | /api/gateway/keys | * | Schlüssel auflisten (ohne secret) |
| PATCH | /api/gateway/keys/{id} | * | Scopes/Modelle aktualisieren |
| DELETE | /api/gateway/keys/{id} | * | Schlüssel löschen |
| POST | /api/gateway/auth/reload | * | Konfiguration neu laden |

## Fehlerformat

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
