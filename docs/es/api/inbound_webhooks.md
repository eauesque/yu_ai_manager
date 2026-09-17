# API de Webhook de Entrada

Un endpoint de recepción para enviar eventos desde servicios externos al event_bus de yu_ai_manager.

## Endpoint de Recepción (Sin autenticación requerida — basada en token)

`POST /api/webhooks/receive/{token}`

### Cuerpo de Solicitud

| Campo | Tipo | Descripción |
|-------|------|-------------|
| event | string | event_type a disparar (predeterminado: `webhook.received`) |
| data | object | Datos del evento |

### Respuesta

```json
{"ok": true, "event": "scan.start"}
```

### Errores

| Código | Descripción |
|------|-------------|
| 403 | Token inválido / desajuste HMAC / evento no en allowed_events |

## API de Gestión (Sesión PIN requerida)

### Crear

`POST /api/webhooks/inbound`

```json
{"label": "n8n trigger", "allowed_events": ["scan.start"]}
```

Respuesta:

```json
{
  "id": "iwh_a1b2c3...",
  "token": "64char_hex...",
  "label": "n8n trigger",
  "allowed_events": ["scan.start"],
  "active": true,
  "created_at": 1712188800
}
```

### Listar

`GET /api/webhooks/inbound`

### Actualizar

`PUT /api/webhooks/inbound/{id}`

```json
{"label": "updated", "allowed_events": ["scan.start", "tag.add"], "active": true}
```

### Eliminar

`DELETE /api/webhooks/inbound/{id}`

## Autenticación

- Aceptado si el token en la URL coincide
- Si el encabezado `X-Webhook-Signature` está presente, se realiza verificación adicional de HMAC-SHA256 (opcional)

## Seguridad

- El token es hexadecimal de 64 caracteres (256 bits)
- `allowed_events` restringe qué eventos se pueden desencadenar
- Array `allowed_events` vacío = todos los eventos permitidos
