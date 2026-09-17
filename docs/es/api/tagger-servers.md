# API de Registro de Servidores de Tagger

API para gestionar múltiples trabajadores de inferencia de etiquetas (Hailo Remoto, ONNX Local, Ryzen AI, etc.) como un clúster unificado, con etiquetado por lotes distribuido a través de un modelo de ejecución paralela con robo de trabajo de cola compartida.

## Descripción General

El Registro de Servidores de Tagger va más allá de un único Tagger Remoto de Hailo al gestionar múltiples backends de inferencia heterogéneos como un clúster. Cada servidor tiene una prioridad configurable, y las tareas se distribuyen de acuerdo con el modo de distribución seleccionado (single / parallel / idle_first).

### Arquitectura

```
┌─────────────────────────────────────────────────────┐
│                   eauesque Host                      │
│  ┌──────────────────────────────────────────────┐   │
│  │         Tagger Orchestrator                  │   │
│  │  - Shared queue (work-stealing)              │   │
│  │  - Progress aggregation -> JobManager -> SSE │   │
│  └──────────┬──────────────┬──────────────────┘   │
│    ┌────────▼───┐   ┌──────▼────────────┐          │
│    │ Local ONNX │   │ Hailo HTTP Client │          │
│    │ Worker     │   │ Worker            │          │
│    └────────────┘   └──────────┬────────┘          │
└────────────────────────────────│────────────────────┘
              ┌──────────────────┼──────────────────┐
     ┌────────▼───┐    ┌────────▼───┐    ┌────────▼───┐
     │ Pi A       │    │ Pi B       │    │ Future     │
     │ Hailo 10H  │    │ Hailo 10H  │    │ NPU Server │
     └────────────┘    └────────────┘    └────────────┘
```

### Tipos de Servidor

| Tipo | Descripción |
|------|-------------|
| `hailo_remote` | Dispositivo Hailo-10H remoto (ej. Raspberry Pi 5) |
| `onnx_local` | Inferencia ONNX Runtime local |
| `onnx_remote` | Servidor de inferencia ONNX remoto |
| `ryzen_ai` | AMD Ryzen AI NPU |

### Modos de Distribución

| Modo | Descripción |
|------|-------------|
| `single` | Usar solo el servidor habilitado de mayor prioridad |
| `parallel` | Ejecutar en todos los servidores habilitados en paralelo (robo de trabajo) |
| `idle_first` | Preferir servidores inactivos primero |

---

## Formato de Entrada de Servidor

```json
{
  "id": "pi-hailo-a",
  "name": "Pi5 Hailo A",
  "type": "hailo_remote",
  "priority": 10,
  "enabled": true,
  "config": {
    "endpoint_url": "http://192.168.1.101:8080",
    "bearer_token": "enc:gAAAAABm...",
    "threshold": 0.35,
    "timeout": 30
  }
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id` | string | Identificador del servidor (auto-generado o especificado manualmente) |
| `name` | string | Nombre mostrado |
| `type` | string | Tipo de servidor (`hailo_remote` / `onnx_local` / `onnx_remote` / `ryzen_ai`) |
| `priority` | int | Prioridad (menor = mayor prioridad, por defecto: 50) |
| `enabled` | bool | Habilitado/deshabilitado |
| `config` | object | Configuración específica del tipo (ver más abajo) |

### Campos config (para servidores remotos)

| Campo | Tipo | Requerido | Descripción |
|-------|------|----------|-------------|
| `endpoint_url` | string | Sí | URL del servidor remoto |
| `bearer_token` | string | No | Token Bearer (encriptado automáticamente con prefijo `enc:` al guardar) |
| `threshold` | float | No | Umbral de confianza de etiqueta (por defecto: 0.35) |
| `timeout` | int | No | Tiempo de espera de solicitud en segundos (por defecto: 30) |

---

## Autenticación

La comunicación con servidores remotos (`hailo_remote` / `onnx_remote`) admite autenticación opcional con token Bearer.

### Host → Servidor Remoto

Cuando `config.bearer_token` está establecido, todas las solicitudes HTTP (comprobaciones de salud y etiquetado) incluyen automáticamente un encabezado `Authorization: Bearer <token>`. Los tokens se almacenan en `config.json` con encriptación Fernet (prefijo `enc:`) y se enmascaran en respuestas de API.

### Lado del Servidor Remoto

`deploy/hailo_tagger_server.py` proporciona una implementación de referencia con verificación de token. Establezca el token al iniciar mediante cualquiera de:

```bash
# Argumento de línea de comandos
python hailo_tagger_server.py --token "my-secret-token"

# Leer desde archivo
python hailo_tagger_server.py --token-file /etc/tagger/token

# Variable de entorno
TAGGER_BEARER_TOKEN=my-secret-token python hailo_tagger_server.py
```

Cuando no se configura token, el servidor opera en modo de acceso abierto (modelo de confianza LAN) para compatibilidad hacia atrás. Los tokens inválidos reciben respuestas 401/403.

---

## GET /api/tagger-servers

Listar servidores registrados y el modo de distribución actual.

### Límite de velocidad

READ (ilimitado)

### Respuesta

```json
{
  "ok": true,
  "data": {
    "servers": [
      {
        "id": "pi-hailo-a",
        "name": "Pi5 Hailo A",
        "type": "hailo_remote",
        "priority": 10,
        "enabled": true,
        "config": {
          "endpoint_url": "http://192.168.1.101:8080",
          "threshold": 0.35,
          "timeout": 30
        }
      }
    ],
    "mode": "parallel"
  }
}
```

---

## POST /api/tagger-servers

Agregar un nuevo servidor de tagger.

### Límite de velocidad

DESTRUCTIVE (~12 req/min, ráfaga 3)

### Cuerpo de Solicitud

| Campo | Tipo | Requerido | Descripción |
|-------|------|----------|-------------|
| `name` | string | Sí | Nombre mostrado |
| `type` | string | Sí | Tipo de servidor |
| `config` | object | Sí | Configuración específica del tipo |
| `priority` | int | No | Prioridad (por defecto: 50) |
| `enabled` | bool | No | Habilitado/deshabilitado (por defecto: `true`) |

### Ejemplo de Solicitud

```json
{
  "name": "Pi5 Hailo A",
  "type": "hailo_remote",
  "config": {
    "endpoint_url": "http://192.168.1.101:8080",
    "threshold": 0.35,
    "timeout": 30
  },
  "priority": 10
}
```

### Respuesta

```json
{
  "ok": true,
  "data": {
    "server": {
      "id": "pi-hailo-a",
      "name": "Pi5 Hailo A",
      "type": "hailo_remote",
      "priority": 10,
      "enabled": true,
      "config": {
        "endpoint_url": "http://192.168.1.101:8080",
        "threshold": 0.35,
        "timeout": 30
      }
    }
  }
}
```

### Errores

| Estado | Descripción |
|--------|-------------|
| 400 | Campos requeridos faltantes o tipo inválido |

---

## PUT /api/tagger-servers/{server_id}

Actualizar la configuración de un servidor existente. Se admiten actualizaciones parciales.

### Límite de velocidad

DESTRUCTIVE (~12 req/min, ráfaga 3)

### Parámetros de Ruta

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `server_id` | string | ID de servidor objetivo |

### Cuerpo de Solicitud

| Campo | Tipo | Requerido | Descripción |
|-------|------|----------|-------------|
| `name` | string | No | Nombre mostrado |
| `type` | string | No | Tipo de servidor |
| `config` | object | No | Configuración específica del tipo |
| `priority` | int | No | Prioridad |
| `enabled` | bool | No | Habilitado/deshabilitado |

### Respuesta

```json
{
  "ok": true,
  "data": {
    "server": { "..." }
  }
}
```

### Errores

| Estado | Descripción |
|--------|-------------|
| 404 | Servidor no encontrado |

---

## DELETE /api/tagger-servers/{server_id}

Eliminar un servidor.

### Límite de velocidad

DESTRUCTIVE (~12 req/min, ráfaga 3)

### Parámetros de Ruta

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `server_id` | string | ID de servidor objetivo |

### Respuesta

```json
{
  "ok": true,
  "data": {
    "deleted": "pi-hailo-a"
  }
}
```

### Errores

| Estado | Descripción |
|--------|-------------|
| 404 | Servidor no encontrado |

---

## POST /api/tagger-servers/reorder

Reordenar prioridades de servidor en masa.

### Límite de velocidad

DESTRUCTIVE (~12 req/min, ráfaga 3)

### Cuerpo de Solicitud

| Campo | Tipo | Requerido | Descripción |
|-------|------|----------|-------------|
| `order` | string[] | Sí | Array de IDs de servidor en orden de prioridad |

### Ejemplo de Solicitud

```json
{
  "order": ["pi-hailo-a", "local-onnx", "pi-hailo-b"]
}
```

### Respuesta

```json
{
  "ok": true,
  "data": {
    "servers": [ "..." ]
  }
}
```

---

## POST /api/tagger-servers/mode

Cambiar el modo de distribución.

### Límite de velocidad

DESTRUCTIVE (~12 req/min, ráfaga 3)

### Cuerpo de Solicitud

| Campo | Tipo | Requerido | Descripción |
|-------|------|----------|-------------|
| `mode` | string | Sí | `single` / `parallel` / `idle_first` |

### Respuesta

```json
{
  "ok": true,
  "data": {
    "mode": "parallel"
  }
}
```

### Errores

| Estado | Descripción |
|--------|-------------|
| 400 | Valor de modo inválido |

---

## POST /api/tagger-servers/{server_id}/test

Probar conectividad a un servidor específico.

### Límite de velocidad

HEAVY (~20 req/min, ráfaga 5)

### Parámetros de Ruta

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `server_id` | string | ID de servidor objetivo |

### Respuesta (éxito)

```json
{
  "ok": true,
  "data": {
    "server_id": "pi-hailo-a",
    "reachable": true,
    "latency_ms": 45
  }
}
```

### Respuesta (no alcanzable)

```json
{
  "ok": true,
  "data": {
    "server_id": "pi-hailo-a",
    "reachable": false,
    "reason": "Connection refused"
  }
}
```

### Errores

| Estado | Descripción |
|--------|-------------|
| 404 | Servidor no encontrado |

---

## GET /api/tagger-servers/health

Comprobación de salud de todos los servidores habilitados.

### Límite de velocidad

READ (ilimitado)

### Respuesta

```json
{
  "ok": true,
  "data": {
    "results": [
      {
        "server_id": "pi-hailo-a",
        "name": "Pi5 Hailo A",
        "type": "hailo_remote",
        "reachable": true,
        "latency_ms": 45
      },
      {
        "server_id": "local-onnx",
        "name": "Local ONNX",
        "type": "onnx_local",
        "reachable": true,
        "latency_ms": 2
      }
    ]
  }
}
```

---

## POST /api/tagger-servers/batch

Ejecutar etiquetado por lotes distribuido usando el modelo de robo de trabajo de cola compartida. Se ejecuta como un trabajo en segundo plano con progreso informado a través de SSE.

### Límite de velocidad

HEAVY (~20 req/min, ráfaga 5)

### Cuerpo de Solicitud

| Campo | Tipo | Requerido | Descripción |
|-------|------|----------|-------------|
| `file_ids` | int[] | No | Lista de ID de archivo objetivo. Auto-selecciona archivos no etiquetados si se omite |
| `limit` | int | No | Máx archivos para auto-selección (por defecto: 500) |
| `force` | bool | No | Sobrescribir etiquetas existentes (por defecto: `false`) |
| `threshold` | float | No | Anular umbral de confianza de etiqueta (usa configuración por servidor si se omite) |

### Ejemplo de Solicitud

```json
{
  "file_ids": [1, 2, 3, 4, 5],
  "force": false,
  "threshold": 0.35
}
```

### Respuesta

```json
{
  "ok": true,
  "data": {
    "started": true,
    "job_id": "tagger_servers_batch",
    "total_files": 5,
    "active_servers": ["pi-hailo-a", "local-onnx"]
  }
}
```

### Errores

| Estado | Código | Descripción |
|--------|--------|-------------|
| 400 | `no_servers` | Sin servidores habilitados disponibles |
| 400 | `batch_too_large` | file_ids excede límite |
| 409 | `job_running` | Trabajo por lotes ya en ejecución |

---

## POST /api/tagger-servers/batch/cancel

Cancelar un trabajo por lotes en ejecución del clúster de tagger.

### Respuesta

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `status` | string | `"cancelling"` |
| `message` | string | Mensaje de estado |

### Códigos de Error

| Estado | Código | Descripción |
|--------|--------|-------------|
| 404 | `job_not_running` | Sin trabajo por lotes en ejecución para cancelar |

---

## GET /api/tagger-servers/tags/{file_id}

Recuperar etiquetas de tagger para un archivo.

### Límite de velocidad

READ (ilimitado)

### Parámetros de Ruta

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `file_id` | int | ID de base de datos del archivo objetivo |

### Respuesta

```json
{
  "ok": true,
  "data": {
    "file_id": 42,
    "tags": [
      {"tag_name": "1girl", "confidence": 0.95, "source": "hailo_remote:pi-hailo-a", "created_at": 1710720000},
      {"tag_name": "solo", "confidence": 0.88, "source": "hailo_remote:pi-hailo-a", "created_at": 1710720000}
    ]
  }
}
```

El campo `source` utiliza el formato `{type}:{server_id}` (ej. `hailo_remote:pi-hailo-a`, `onnx_local:local-onnx`).

---

## DELETE /api/tagger-servers/tags/{file_id}

Eliminar todas las etiquetas de tagger para un archivo.

### Límite de velocidad

DESTRUCTIVE (~12 req/min, ráfaga 3)

### Parámetros de Ruta

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `file_id` | int | ID de base de datos del archivo objetivo |

### Respuesta

```json
{
  "ok": true,
  "data": {
    "file_id": 42,
    "deleted": 15
  }
}
```

---

## GET /api/tagger-servers/stats

Recuperar estadísticas de tagger.

### Límite de velocidad

READ (ilimitado)

### Respuesta

```json
{
  "ok": true,
  "data": {
    "total_files": 10000,
    "tagged_files": 8500,
    "untagged_files": 1500,
    "servers": {
      "pi-hailo-a": {"tagged": 5000, "type": "hailo_remote"},
      "local-onnx": {"tagged": 3500, "type": "onnx_local"}
    }
  }
}
```

---

## POST /api/tagger-servers/migrate

Migrar configuración heredada `hailo_tagger` al formato de Registro de Servidores de Tagger. Convierte la entrada existente `hailo_tagger` en `config.json` a una entrada de array `tagger_servers`.

### Límite de velocidad

DESTRUCTIVE (~12 req/min, ráfaga 3)

### Respuesta

```json
{
  "ok": true,
  "data": {
    "migrated": true,
    "server": {
      "id": "legacy-hailo",
      "name": "Hailo Remote (migrated)",
      "type": "hailo_remote",
      "priority": 50,
      "enabled": true,
      "config": {
        "endpoint_url": "http://192.168.1.50:8080",
        "threshold": 0.35,
        "timeout": 30
      }
    }
  }
}
```

### Respuesta (sin migración necesaria)

```json
{
  "ok": true,
  "data": {
    "migrated": false,
    "reason": "No legacy config found"
  }
}
```

---

## Configuración

Claves relacionadas en `config.json`:

```json
{
  "tagger_servers": [
    {
      "id": "pi-hailo-a",
      "name": "Pi5 Hailo A",
      "type": "hailo_remote",
      "priority": 10,
      "enabled": true,
      "config": {
        "endpoint_url": "http://192.168.1.101:8080",
        "bearer_token": "enc:gAAAAABm...",
        "threshold": 0.35,
        "timeout": 30
      }
    },
    {
      "id": "local-onnx",
      "name": "Local ONNX",
      "type": "onnx_local",
      "priority": 20,
      "enabled": true,
      "config": {
        "threshold": 0.35
      }
    }
  ],
  "tagger_servers_mode": "parallel"
}
```

| Clave | Tipo | Descripción |
|-------|------|-------------|
| `tagger_servers` | array | Array de entradas de servidor |
| `tagger_servers_mode` | string | Modo de distribución (`single` / `parallel` / `idle_first`) |

También se puede cambiar desde la página de Configuración.

---

## Esquema de BD

Las etiquetas se almacenan en la tabla `file_hailo_tags`. La columna `source` utiliza el formato `{type}:{server_id}` para identificar qué servidor asignó la etiqueta.

```sql
CREATE TABLE file_hailo_tags (
    id         INTEGER PRIMARY KEY,
    file_id    INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    tag_name   TEXT NOT NULL,
    confidence REAL NOT NULL,
    source     TEXT NOT NULL DEFAULT 'hailo_remote',
    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    UNIQUE(file_id, tag_name)
);
```

| Columna | Descripción |
|--------|-------------|
| `file_id` | Clave externa a tabla de archivos |
| `tag_name` | Nombre de etiqueta Danbooru (ej. `1girl`, `solo`) |
| `confidence` | Confianza de inferencia (0.0-1.0) |
| `source` | Identificador de fuente de etiqueta (formato `{type}:{server_id}`, ej. `hailo_remote:pi-hailo-a`) |
| `created_at` | Timestamp UNIX |
