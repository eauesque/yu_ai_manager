# API de Compartir en SNS

APIs para compartir en SNS, publicar en Bluesky y gestión de cola de notificaciones.

Proporcionado por `routes/sns_share.py`. Todos los endpoints requieren autenticación (sesión PIN o API Key).

## Vista Previa e Intención de X

### GET /api/sns/preview

Expandir una plantilla de publicación con metadatos de imagen y devolver una vista previa. Útil para ver una vista previa de lo que se publicará antes de compartir.

### Parámetros

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `file_id` | int | Sí | ID de archivo de imagen objetivo |
| `template` | string | No | Cadena de plantilla personalizada (usa la predeterminada si se omite) |

### Respuesta

```json
{
  "text": "New artwork: sunset landscape #aiart #stablediffusion",
  "graphemes": 52,
  "meta": {
    "title": "sunset landscape",
    "model": "sd_xl_base_1.0",
    "generator": "a1111"
  }
}
```

### Ejemplo curl

```bash
curl -H "Authorization: Bearer sk_xxxxx" \
  "http://localhost:5000/api/sns/preview?file_id=42"
```

### GET /api/sns/x/intent

Generar una URL de Intención Web de X (Twitter) para compartir. Abre el diálogo de composición de X con texto prerellenado.

### Parámetros

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `file_id` | int | Sí | ID de archivo de imagen objetivo |

### Respuesta

```json
{
  "url": "https://twitter.com/intent/tweet?text=New+artwork%3A+sunset+landscape+%23aiart"
}
```

---

## Publicación en Bluesky

### POST /api/sns/bluesky/post

Publicar texto (e opcionalmente una imagen) en Bluesky.

### Solicitud

```json
{
  "file_id": 42,
  "text": "Check out my new artwork! #aiart",
  "attach_image": true
}
```

| Campo | Tipo | Requerido | Descripción |
|-------|------|----------|-------------|
| `file_id` | int | Sí | ID de archivo de imagen objetivo |
| `text` | string | No | Texto de publicación (usa expansión de plantilla si se omite) |
| `attach_image` | boolean | No | Adjuntar la imagen a la publicación (por defecto: false) |

### Respuesta

```json
{
  "ok": true,
  "uri": "at://did:plc:xxxxx/app.bsky.feed.post/yyyyy"
}
```

### Respuesta de Error

```json
{
  "ok": false,
  "error": "Authentication failed: invalid app password"
}
```

### POST /api/sns/bluesky/test

Probar conexión a Bluesky con credenciales configuradas.

### Respuesta

```json
{
  "ok": true,
  "handle": "user.bsky.social",
  "display_name": "My Display Name"
}
```

### Respuesta de Error

```json
{
  "ok": false,
  "error": "Invalid identifier or password"
}
```

---

## Configuración de SNS

### GET /api/sns/config

Obtener configuración de SNS. Las contraseñas están enmascaradas en la respuesta.

### Respuesta

```json
{
  "bluesky": {
    "handle": "user.bsky.social",
    "app_password": "****...xxxx"
  },
  "post_template": "{title} #aiart #{generator}"
}
```

### POST /api/sns/config

Guardar configuración de SNS.

### Solicitud

```json
{
  "bluesky_handle": "user.bsky.social",
  "bluesky_app_password": "xxxx-xxxx-xxxx-xxxx",
  "post_template": "{title} #aiart #{generator}"
}
```

| Campo | Tipo | Requerido | Descripción |
|-------|------|----------|-------------|
| `bluesky_handle` | string | No | Identificador de Bluesky (ej. `user.bsky.social`) |
| `bluesky_app_password` | string | No | Contraseña de Aplicación de Bluesky |
| `post_template` | string | No | Plantilla de publicación predeterminada con variables `{placeholder}` |

### Ejemplo curl

```bash
curl -X POST -H "Authorization: Bearer sk_xxxxx" \
  -H "Content-Type: application/json" \
  -H "X-Requested-With: XMLHttpRequest" \
  -d '{"bluesky_handle": "user.bsky.social", "bluesky_app_password": "xxxx-xxxx-xxxx-xxxx"}' \
  "http://localhost:5000/api/sns/config"
```

---

## Cola de Notificaciones de Bluesky

### GET /api/sns/bsky/queue

Listar elementos de la cola de notificaciones con filtros opcionales.

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `status` | string | Filtro: `pending`, `notified`, `dismissed`, o vacío para todos |
| `type` | string | Filtro de tipo de notificación (ej. `mention`, `reply`, `quote`, `like`, `repost`, `follow`) |
| `limit` | int | Máx resultados (por defecto 50) |

### Respuesta

```json
{
  "data": {
    "items": [
      {
        "id": 1,
        "type": "mention",
        "author_handle": "someone.bsky.social",
        "author_display_name": "Someone",
        "text": "@user.bsky.social great artwork!",
        "uri": "at://did:plc:xxxxx/app.bsky.feed.post/yyyyy",
        "created_at": "2026-03-15T10:00:00Z",
        "fetched_at": "2026-03-15T12:00:00Z",
        "status": "pending",
        "triage_result": null
      }
    ],
    "stats": { "pending": 3, "notified": 1, "dismissed": 5, "total": 9 }
  }
}
```

### GET /api/sns/bsky/queue/pending

Obtener notificaciones pendientes (sin procesar) para notificación MCP.

### Respuesta

```json
{
  "data": {
    "items": [...],
    "count": 3,
    "stats": { "pending": 3, "notified": 1, "dismissed": 5, "total": 9 }
  }
}
```

### POST /api/sns/bsky/queue/<queue_id>/triage

Establecer resultado de clasificación para un elemento de cola.

### Solicitud

```json
{ "result": "valid" }
```

| Campo | Tipo | Requerido | Descripción |
|-------|------|----------|-------------|
| `result` | string | Sí | `valid` o `invalid` |

### PUT /api/sns/bsky/queue/<queue_id>/status

Actualizar estado del elemento de cola.

### Solicitud

```json
{ "status": "notified" }
```

| Campo | Tipo | Requerido | Descripción |
|-------|------|----------|-------------|
| `status` | string | Sí | `pending`, `notified`, o `dismissed` |

### POST /api/sns/bsky/queue/<queue_id>/respond

Enviar una respuesta automática a una notificación.

### Solicitud

```json
{ "text": "Thank you for your kind words!" }
```

| Campo | Tipo | Requerido | Descripción |
|-------|------|----------|-------------|
| `text` | string | Sí | Texto de respuesta a publicar como respuesta |

### POST /api/sns/bsky/queue/poll

Desencadenar sondeo inmediato de nuevas notificaciones de Bluesky.

### Ejemplo curl

```bash
curl -X POST -H "Authorization: Bearer sk_xxxxx" \
  -H "X-Requested-With: XMLHttpRequest" \
  "http://localhost:5000/api/sns/bsky/queue/poll"
```

---

## Configuración del Monitor de Bluesky

### GET /api/sns/bsky/monitor/config

Obtener configuración del monitor de notificaciones de Bluesky.

### Respuesta

```json
{
  "data": {
    "poll_interval_minutes": 15,
    "auto_dismiss_follow": false,
    "auto_dismiss_like": true,
    "auto_dismiss_repost": true,
    "auto_respond_enabled": false,
    "notify_on_connect": true
  }
}
```

### PUT /api/sns/bsky/monitor/config

Actualizar configuración del monitor de notificaciones de Bluesky. Solo se actualizan los campos proporcionados.

### Solicitud

```json
{
  "poll_interval_minutes": 30,
  "auto_dismiss_follow": false,
  "auto_dismiss_like": true,
  "auto_dismiss_repost": true,
  "auto_respond_enabled": false,
  "notify_on_connect": true
}
```

| Campo | Tipo | Requerido | Descripción |
|-------|------|----------|-------------|
| `poll_interval_minutes` | int | No | Intervalo de sondeo en minutos |
| `auto_dismiss_follow` | boolean | No | Auto-descartar notificaciones de seguimiento |
| `auto_dismiss_like` | boolean | No | Auto-descartar notificaciones de "me gusta" |
| `auto_dismiss_repost` | boolean | No | Auto-descartar notificaciones de re-publicación |
| `auto_respond_enabled` | boolean | No | Habilitar respuestas automáticas |
| `notify_on_connect` | boolean | No | Enviar notificación al conectarse cliente MCP |

---

## Indicaciones de Clasificación y Plantillas de Respuesta Automática

### GET /api/sns/bsky/monitor/triage-prompts

Obtener indicaciones de clasificación editables, plantillas de respuesta automática y sus valores predeterminados.

### Respuesta

```json
{
  "data": {
    "triage_prompts": {
      "mention": "Evaluate this mention for relevance...",
      "reply": "Evaluate this reply...",
      "quote": "Evaluate this quote post..."
    },
    "auto_responses": {
      "mention": "Thanks for the mention!",
      "reply": "Thank you for your reply!",
      "quote": "Thanks for sharing!"
    },
    "defaults": {
      "triage_prompts": {
        "mention": "Evaluate this mention for relevance...",
        "reply": "Evaluate this reply...",
        "quote": "Evaluate this quote post..."
      },
      "auto_responses": {
        "mention": "Thanks for the mention!",
        "reply": "Thank you for your reply!",
        "quote": "Thanks for sharing!"
      }
    }
  }
}
```

### PUT /api/sns/bsky/monitor/triage-prompts

Actualizar indicaciones de clasificación y/o plantillas de respuesta automática. Solo se actualizan los campos proporcionados.

### Solicitud

```json
{
  "triage_prompts": {
    "mention": "Custom mention triage prompt...",
    "reply": "Custom reply triage prompt...",
    "quote": "Custom quote triage prompt..."
  },
  "auto_responses": {
    "mention": "Custom mention auto-response...",
    "reply": "Custom reply auto-response...",
    "quote": "Custom quote auto-response..."
  }
}
```

| Campo | Tipo | Requerido | Descripción |
|-------|------|----------|-------------|
| `triage_prompts` | object | No | Indicaciones de clasificación indexadas por tipo de notificación (`mention`, `reply`, `quote`) |
| `auto_responses` | object | No | Plantillas de respuesta automática indexadas por tipo de notificación |
