# API de Inferencia Distribuida

API REST para el registro del servidor de inferencia distribuida. Distribuye cargas de trabajo de indexación semántica CLIP a través de múltiples nodos utilizando una estrategia de cola compartida.

## Endpoints

### GET /api/inference-servers

Devuelve la lista de servidores registrados y el modo de envío actual.

**Respuesta:**

```json
{
  "status": "ok",
  "mode": "single",
  "servers": [
    {
      "id": 1,
      "name": "Hailo Worker 1",
      "endpoint_url": "http://192.168.1.10:9090",
      "inference_types": ["clip"],
      "priority": 50,
      "enabled": true,
      "timeout": 30
    }
  ]
}
```

- `mode`: `"single"` | `"parallel"` | `"idle_first"`
- `servers`: array de objetos de configuración de servidor

---

### POST /api/inference-servers

Registrar un nuevo servidor de inferencia.

**Cuerpo de Solicitud:**

| Campo | Tipo | Requerido | Predeterminado | Descripción |
|---|---|---|---|---|
| `name` | string | ✓ | — | Nombre para mostrar |
| `endpoint_url` | string | ✓ | — | URL base del trabajador |
| `inference_types` | string[] | — | `["clip"]` | Tipos de inferencia soportados |
| `priority` | int | — | `50` | Prioridad (valor menor = mayor prioridad) |
| `bearer_token` | string | — | — | Token de autenticación |
| `timeout` | int | — | `30` | Tiempo de espera de solicitud en segundos |

**Respuesta:**

```json
{
  "status": "ok",
  "server": { ... }
}
```

---

### PUT /api/inference-servers/{server_id}

Actualizar la configuración de un servidor existente. Acepta un cuerpo parcial con los mismos campos que POST.

---

### DELETE /api/inference-servers/{server_id}

Eliminar un servidor del registro.

**Respuesta:**

```json
{ "status": "ok" }
```

---

### POST /api/inference-servers/{server_id}/test

Ejecutar una verificación de salud contra el servidor especificado.

**Respuesta:**

```json
{
  "status": "ok",
  "server_id": 1,
  "healthy": true,
  "latency_ms": 12.5
}
```

---

### GET /api/inference-servers/health

Ejecutar verificaciones de salud contra todos los servidores habilitados simultáneamente.

**Respuesta:**

```json
{
  "status": "ok",
  "results": [
    { "server_id": 1, "healthy": true, "latency_ms": 12.5 },
    { "server_id": 2, "healthy": false, "error": "Connection refused" }
  ]
}
```

---

### POST /api/inference-servers/mode

Establecer el modo de envío.

**Cuerpo de Solicitud:**

| Campo | Tipo | Requerido | Descripción |
|---|---|---|---|
| `mode` | string | ✓ | `"single"` \| `"parallel"` \| `"idle_first"` |

**Respuesta:**

```json
{ "status": "ok", "mode": "parallel" }
```

---

## Modos de Envío

| Modo | Descripción |
|---|---|
| `single` | Usar solo el servidor de mayor prioridad (valor de prioridad más bajo) |
| `parallel` | Distribuir el trabajo a través de todos los servidores habilitados utilizando una cola compartida |
| `idle_first` | Verificar salud primero, luego distribuir a través de servidores receptivos solo |

## Indexación Semántica Distribuida

Añadir `distributed: true` al cuerpo de solicitud `POST /api/index/start` (extensión de búsqueda semántica) para habilitar la indexación distribuida utilizando servidores de trabajadores registrados.

```json
{
  "batch_size": 32,
  "distributed": true
}
```

## Configuración del Servidor Worker

```bash
python deploy/hailo_tagger_server.py --port 9090
```

Endpoints soportados:

| Ruta | Descripción |
|---|---|
| `GET /health` | Verificación de salud |
| `POST /tag` | Inferencia de WD-Tagger |
| `POST /clip-encode` | Codificación de vector CLIP |

## Herramientas MCP

| Herramienta | Descripción |
|---|---|
| `inference-servers-list` | Listar servidores y obtener modo actual |
| `inference-server-add` | Registrar un nuevo servidor |
| `inference-server-update` | Actualizar configuración de servidor |
| `inference-server-remove` | Eliminar un servidor |
| `inference-server-health` | Ejecutar verificaciones de salud |
| `inference-dispatch-mode-set` | Establecer modo de envío |
