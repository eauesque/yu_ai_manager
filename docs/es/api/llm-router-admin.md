# API: /api/llm_router (Admin)

Endpoints administrativos para operaciones de gestión del Router LLM. Protegidos por autenticación de sesión estándar de WebUI (PIN/sesión), y completamente separados de la superficie `/v1/*` compatible con OpenAI.

> **Nota**: Estos son endpoints administrativos y son distintos de los endpoints de inferencia como `/v1/chat/completions`.

---

## Formato de Respuesta Común

Todos los endpoints utilizan el envoltorio `api_result`. En caso de éxito, el cuerpo se anida bajo la clave `data`.

```json
{
  "status": "ok",
  "data": { ... }
}
```

En caso de error:

```json
{
  "status": "error",
  "error": "Error description"
}
```

---

## GET /api/llm_router/status

Una instantánea para renderizar el panel completo en una única solicitud. Devuelve toda la información del backend y el mapa de alias.

### Solicitud

```
GET /api/llm_router/status
```

Sin parámetros.

### Respuesta `200 OK`

```json
{
  "status": "ok",
  "data": {
    "router": {
      "version": "1.0.0",
      "alias_count": 2
    },
    "backends": [
      {
        "alias": "ollama-mac",
        "base_url": "http://192.168.1.10:11434",
        "source": "static",
        "status": "ready",
        "slo_state": null,
        "disabled": false,
        "model_count": 3,
        "models": [
          {
            "name": "qwen2.5:7b",
            "context_window": 32768,
            "size_b": 7.6
          },
          {
            "name": "llama3.2:3b",
            "context_window": 128000,
            "size_b": 3.2
          }
        ],
        "last_seen": "2026-04-09T12:34:56.789123",
        "last_error": null
      },
      {
        "alias": "mdns-pi5-hailo",
        "base_url": "http://192.168.1.20:8080",
        "source": "mdns",
        "status": "unreachable",
        "slo_state": "unknown",
        "disabled": false,
        "model_count": 0,
        "models": [],
        "last_seen": null,
        "last_error": "Connection refused"
      }
    ],
    "aliases": {
      "default-llm": "ollama-mac/qwen2.5:7b",
      "fast-chat": "ollama-mac/llama3.2:3b"
    }
  }
}
```

### Descripciones de Campo

**`router`**

| Campo | Tipo | Descripción |
|---|---|---|
| `version` | string | Versión del esquema del Router (actualmente `"1.0.0"`) |
| `alias_count` | int | Número de alias definidos |

**`backends[]`**

| Campo | Tipo | Descripción |
|---|---|---|
| `alias` | string | Identificador único del backend |
| `base_url` | string | URL base del endpoint compatible con OpenAI |
| `source` | string | `"static"` (archivo de configuración) o `"mdns"` (detectado automáticamente) |
| `status` | string | `"ready"` / `"unreachable"` / `"unknown"` |
| `slo_state` | string \| null | `"vision_idle"` / `"vision_active"` / `"unknown"` / `null` |
| `disabled` | bool | `true` si se excluye del enrutamiento |
| `model_count` | int | Número de modelos expuestos |
| `models[]` | array | Lista de modelos (`name`, `context_window`, `size_b`) |
| `last_seen` | string \| null | Última verificación de conectividad exitosa (ISO 8601) |
| `last_error` | string \| null | Último mensaje de error |

**`aliases`**

Un mapa de nombres de alias lógicos a IDs de modelo físico (`backend-alias/model-name`).

---

## POST /api/llm_router/refresh

Fuerza un sondeo en todos los backends o en un backend especificado, actualizando `status` y la lista de modelos.

### Solicitud

**Para actualizar todos los backends (sin cuerpo):**

```
POST /api/llm_router/refresh
Content-Type: application/json

{}
```

También se acepta un cuerpo vacío sin encabezado Content-Type.

**Para actualizar un backend específico solamente:**

```json
{
  "alias": "ollama-mac"
}
```

### Respuesta `200 OK`

```json
{
  "status": "ok",
  "data": {
    "refreshed": [
      {
        "alias": "ollama-mac",
        "status": "ready",
        "model_count": 3,
        "disabled": false,
        "last_error": null
      },
      {
        "alias": "mdns-pi5-hailo",
        "status": "unreachable",
        "model_count": 0,
        "disabled": false,
        "last_error": "Connection refused"
      }
    ]
  }
}
```

El array `refreshed` contiene solo resultados de actualización ligeros (use `/status` para detalles completos).

### Error `404 Not Found`

Cuando se especifica un `alias` pero no existe:

```json
{
  "status": "error",
  "error": "unknown backend: nonexistent-alias"
}
```

### Notas

- Los sondeos se ejecutan de forma sincrónica (la respuesta se devuelve después de la finalización)
- Los sondeos también se ejecutan para backends con `disabled: true` (el estado aún se actualiza)
- Los backends descubiertos por mDNS se incluyen

---

## POST /api/llm_router/backends/`<alias>`/disable

Deshabilita el backend especificado. Los backends deshabilitados se excluyen del enrutamiento y el estado se persiste en `data/llm_router_state.json`.

### Solicitud

```
POST /api/llm_router/backends/ollama-mac/disable
```

No se requiere cuerpo.

### Respuesta `200 OK`

```json
{
  "status": "ok",
  "data": {
    "alias": "ollama-mac",
    "disabled": true
  }
}
```

### Error `404 Not Found`

```json
{
  "status": "error",
  "error": "unknown backend: nonexistent-alias"
}
```

### Error `500 Internal Server Error`

Cuando la persistencia en disco falla (error de permiso, disco lleno, etc.). El estado en memoria se revierte.

```json
{
  "status": "error",
  "error": "failed to persist disabled state"
}
```

### Mecanismo de Persistencia

1. Establecer la bandera `disabled` a `true` en el catálogo en memoria
2. Escribir atómicamente a `data/llm_router_state.json` (a través del archivo `.tmp` y `os.replace`)
3. Si la escritura falla, el paso 1 se revierte y se devuelve un `500`

El estado deshabilitado se preserva entre reinicios de aplicación. Si un backend descubierto por mDNS fue deshabilitado antes del inicio, el estado deshabilitado se aplica automáticamente después del descubrimiento.

---

## POST /api/llm_router/backends/`<alias>`/enable

Habilita el backend especificado. Lo opuesto a `disable`.

### Solicitud

```
POST /api/llm_router/backends/ollama-mac/enable
```

No se requiere cuerpo.

### Respuesta `200 OK`

```json
{
  "status": "ok",
  "data": {
    "alias": "ollama-mac",
    "disabled": false
  }
}
```

### Errores

Lo mismo que el endpoint `disable` (`404` / `500`). Persistido con `disabled: false`.

---

## Resumen de Endpoint

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/api/llm_router/status` | Obtener una instantánea de todos los backends y alias |
| `POST` | `/api/llm_router/refresh` | Forzar sondeo en todos los backends o individuales |
| `POST` | `/api/llm_router/backends/<alias>/disable` | Deshabilitar un backend (persistido) |
| `POST` | `/api/llm_router/backends/<alias>/enable` | Habilitar un backend (persistido) |

## Documentación Relacionada

- [Guía de WebUI del Router LLM](../llm-router/webui.md)
- [Configuración del Router LLM](../llm-router/setup.md)
