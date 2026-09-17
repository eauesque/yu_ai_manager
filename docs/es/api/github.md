# API de Integración de GitHub

APIs para gestión de cuentas de GitHub, problemas, solicitudes de extracción, notificaciones y lanzamientos.

Proporcionado por la extensión `builtin-github`. Todos los endpoints requieren autenticación (sesión PIN o API Key).

## Gestión de Cuentas

### GET /api/github/accounts

Listar cuentas de GitHub registradas. Los tokens están enmascarados en la respuesta.

### Respuesta

```json
{
  "data": [
    {
      "label": "my-account",
      "token": "ghp_****...xxxx",
      "repos": ["owner/repo1", "owner/repo2"],
      "enabled": true
    }
  ]
}
```

### POST /api/github/accounts

Registrar una nueva cuenta de GitHub.

### Solicitud

```json
{
  "label": "my-account",
  "token": "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "repos": ["owner/repo1", "owner/repo2"]
}
```

| Campo | Tipo | Requerido | Descripción |
|-------|------|----------|-------------|
| `label` | string | Sí | Etiqueta de identificador de cuenta única |
| `token` | string | Sí | Token de Acceso Personal de GitHub |
| `repos` | string[] | Sí | Repositorios a monitorear (formato `owner/repo`) |

### Respuesta

```json
{
  "data": { "label": "my-account", "status": "created" }
}
```

### PUT /api/github/accounts/<label>

Actualizar configuración de una cuenta existente.

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `label` | string | Etiqueta de cuenta (parámetro de ruta) |

### Solicitud

```json
{
  "token": "ghp_new_token_value",
  "repos": ["owner/repo1", "owner/repo3"],
  "enabled": false
}
```

| Campo | Tipo | Requerido | Descripción |
|-------|------|----------|-------------|
| `token` | string | No | Nuevo valor de token |
| `repos` | string[] | No | Lista de repositorio actualizada |
| `enabled` | boolean | No | Habilitar o deshabilitar la cuenta |

### DELETE /api/github/accounts/<label>

Eliminar una cuenta.

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `label` | string | Etiqueta de cuenta (parámetro de ruta) |

---

## Problemas

### GET /api/github/issues/<label>

Obtener problemas de los repositorios de la cuenta.

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `label` | string | Etiqueta de cuenta (parámetro de ruta) |
| `state` | string | Filtro de estado de problema (`open`, `closed`, `all`) |
| `labels` | string | Filtro de etiqueta (separado por comas) |
| `since` | string | Problemas actualizados después de esta fecha (ISO 8601) |
| `repo` | string | Filtrar a un repositorio específico (`owner/repo`) |

### Ejemplo curl

```bash
curl -H "Authorization: Bearer sk_xxxxx" \
  "http://localhost:5000/api/github/issues/my-account?state=open&repo=owner/repo1"
```

### POST /api/github/issues/<label>

Crear un nuevo problema.

### Solicitud

```json
{
  "repo": "owner/repo1",
  "title": "Bug: crash on login screen",
  "body": "Steps to reproduce:\n1. ...\n2. ...",
  "labels": ["bug", "priority:high"]
}
```

| Campo | Tipo | Requerido | Descripción |
|-------|------|----------|-------------|
| `repo` | string | Sí | Repositorio objetivo (`owner/repo`) |
| `title` | string | Sí | Título del problema |
| `body` | string | No | Cuerpo del problema (Markdown) |
| `labels` | string[] | No | Etiquetas a aplicar |

### GET /api/github/issue/<label>/<repo>/<number>

Recuperar detalles de problema incluidos comentarios.

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `label` | string | Etiqueta de cuenta |
| `repo` | string | Nombre de repositorio (`owner/repo`) |
| `number` | int | Número de problema |

### POST /api/github/triage/<label>

Ejecutar clasificación de problema (clasificación y priorización).

### Solicitud

```json
{
  "state": "open",
  "since": "2026-03-01T00:00:00Z"
}
```

| Campo | Tipo | Requerido | Descripción |
|-------|------|----------|-------------|
| `state` | string | No | Filtro de estado para problemas objetivo |
| `since` | string | No | Solo clasificar problemas actualizados después de esta fecha (ISO 8601) |

---

## Solicitudes de Extracción

### GET /api/github/pulls/<label>

Listar solicitudes de extracción.

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `label` | string | Etiqueta de cuenta (parámetro de ruta) |
| `state` | string | Estado de PR (`open`, `closed`, `all`) |
| `repo` | string | Filtrar a un repositorio específico (`owner/repo`) |

### GET /api/github/pull/<label>/<repo>/<number>

Recuperar detalles de PR incluidos archivos cambiados.

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `label` | string | Etiqueta de cuenta |
| `repo` | string | Nombre de repositorio (`owner/repo`) |
| `number` | int | Número de PR |

---

## Notificaciones

### GET /api/github/notifications/<label>

Listar notificaciones.

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `label` | string | Etiqueta de cuenta (parámetro de ruta) |
| `all` | string | Establecer en `true` para incluir notificaciones leídas (por defecto: solo no leídas) |

### PATCH /api/github/notifications/<label>/<thread_id>

Marcar un hilo de notificación específico como leído.

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `label` | string | Etiqueta de cuenta |
| `thread_id` | string | ID del hilo de notificación |

### POST /api/github/notifications/<label>/mark-all-read

Marcar todas las notificaciones como leídas.

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `label` | string | Etiqueta de cuenta (parámetro de ruta) |

---

## Discusiones

### GET /api/github/discussions/<label>

Obtener Discusiones de GitHub (a través de API GraphQL).

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `label` | string | Etiqueta de cuenta (parámetro de ruta) |
| `repo` | string | Filtrar a un repositorio específico (`owner/repo`) |

---

## Lanzamientos

### GET /api/github/releases/<label>

Listar lanzamientos.

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `label` | string | Etiqueta de cuenta (parámetro de ruta) |
| `repo` | string | Filtrar a un repositorio específico (`owner/repo`) |

---

## Estadísticas de Repositorio

### GET /api/github/repo-stats/<label>/<repo>

Recuperar estadísticas para un repositorio único.

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `label` | string | Etiqueta de cuenta |
| `repo` | string | Nombre de repositorio (`owner/repo`) |

### GET /api/github/repo-stats-all/<label>

Recuperar estadísticas para todos los repositorios registrados a la vez.

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `label` | string | Etiqueta de cuenta (parámetro de ruta) |

---

## Límite de Velocidad

### GET /api/github/rate-limit/<label>

Verificar estado del límite de velocidad de API de GitHub.

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `label` | string | Etiqueta de cuenta (parámetro de ruta) |

### Ejemplo de Respuesta

```json
{
  "data": {
    "rate": {
      "limit": 5000,
      "remaining": 4832,
      "reset": 1710500000
    }
  }
}
```

---

## Indicaciones de Clasificación

### GET /api/github/triage-prompts

Obtener indicaciones de clasificación editables para problema/PR/discusión, junto con sus valores predeterminados.

### Respuesta

```json
{
  "data": {
    "prompts": {
      "issue": "Review the following GitHub issue...",
      "pr": "Do not accept pull requests. Close automatically.",
      "discussion": "Discussions are closed. No action required."
    },
    "defaults": {
      "issue": "Review the following GitHub issue...",
      "pr": "Do not accept pull requests. Close automatically.",
      "discussion": "Discussions are closed. No action required."
    }
  }
}
```

### PUT /api/github/triage-prompts

Actualizar indicaciones de clasificación. Solo se actualizan los campos proporcionados.

### Solicitud

```json
{
  "issue": "Custom issue triage prompt...",
  "pr": "Custom PR prompt...",
  "discussion": "Custom discussion prompt..."
}
```

| Campo | Tipo | Requerido | Descripción |
|-------|------|----------|-------------|
| `issue` | string | No | Indicación de clasificación para problemas |
| `pr` | string | No | Indicación de clasificación para solicitudes de extracción |
| `discussion` | string | No | Indicación de clasificación para discusiones |

---

## Cola de Problemas

### GET /api/github/queue

Obtener elementos de cola de problemas con filtro de estado opcional.

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `status` | string | Filtro: `pending`, `notified`, `dismissed`, o vacío para todos |
| `limit` | int | Máx resultados (por defecto 50, máx 200) |

### Respuesta

```json
{
  "data": {
    "items": [
      {
        "id": 1,
        "repo": "owner/repo",
        "issue_number": 42,
        "title": "Bug report title",
        "body": "Issue body...",
        "created_at": "2026-03-15T10:00:00Z",
        "fetched_at": "2026-03-15T12:00:00Z",
        "status": "pending",
        "triage_result": "pending"
      }
    ],
    "stats": { "pending": 3, "notified": 1, "dismissed": 5, "total": 9 }
  }
}
```

### GET /api/github/queue/pending

Obtener problemas pendientes (no leídos) para notificación MCP.

### Respuesta

```json
{
  "data": {
    "items": [...],
    "count": 3
  }
}
```

### POST /api/github/queue/<queue_id>/triage

Establecer resultado de clasificación para un elemento de cola.

### Solicitud

```json
{ "result": "valid" }
```

| Campo | Tipo | Requerido | Descripción |
|-------|------|----------|-------------|
| `result` | string | Sí | `valid` o `invalid` |

### POST /api/github/queue/<queue_id>/dismiss

Descartar un elemento de cola. Opcionalmente auto-cerrar el problema en GitHub.

### Solicitud

```json
{
  "auto_close": true,
  "account_label": "my-account"
}
```

| Campo | Tipo | Requerido | Descripción |
|-------|------|----------|-------------|
| `auto_close` | boolean | No | Cerrar el problema en GitHub con comentario de plantilla |
| `account_label` | string | No | Requerido si `auto_close` es verdadero |

### PUT /api/github/queue/<queue_id>/status

Actualizar estado del elemento de cola.

### Solicitud

```json
{ "status": "notified" }
```

| Campo | Tipo | Requerido | Descripción |
|-------|------|----------|-------------|
| `status` | string | Sí | `pending`, `notified`, o `dismissed` |

### GET /api/github/queue/config

Obtener configuración de cola de problemas.

### Respuesta

```json
{
  "data": {
    "poll_interval_minutes": 60,
    "auto_close_invalid": false,
    "notify_on_connect": true
  }
}
```

### PUT /api/github/queue/config

Actualizar configuración de cola de problemas.

### Solicitud

```json
{
  "poll_interval_minutes": 30,
  "auto_close_invalid": true,
  "notify_on_connect": true
}
```

### POST /api/github/queue/poll

Desencadenar sondeo inmediato de todas las cuentas para nuevos problemas.

---

## WebUI

### GET /ext/github

Página WebUI de Integración de GitHub. Acceder directamente en el navegador.

Requiere una sesión PIN autenticada.
