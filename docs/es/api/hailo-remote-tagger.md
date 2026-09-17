# API del Tagger Remoto de Hailo

API para enviar imágenes a un servidor de inferencia remoto Hailo AI HAT (ej. Raspberry Pi 5) a través de la red, ejecutar inferencia de etiquetado Danbooru y guardar resultados en la base de datos.

## Descripción General

Incluso sin una GPU local o runtime ONNX, puede utilizar un dispositivo Hailo-10H en su LAN como tagger remoto. Las imágenes se envían como multipart/form-data, y la respuesta JSON de etiquetas se devuelve como respuesta.

---

## GET /api/hailo-tagger/config

Recuperar configuración actual.

### Límite de velocidad

READ (ilimitado)

### Respuesta

```json
{
  "ok": true,
  "data": {
    "config": {
      "enabled": false,
      "endpoint_url": "",
      "threshold": 0.35,
      "timeout": 30
    }
  }
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `enabled` | bool | Si Hailo Remote Tagger está habilitado |
| `endpoint_url` | string | URL del endpoint Pi (ej. `http://192.168.1.50:8080`) |
| `threshold` | float | Umbral de confianza de etiqueta (solo se guardan etiquetas por encima de este) |
| `timeout` | int | Tiempo de espera de solicitud en segundos |

---

## POST /api/hailo-tagger/config

Guardar configuración. Se admiten actualizaciones parciales (solo se cambian los campos especificados).

### Límite de velocidad

DESTRUCTIVE (~12 req/min, ráfaga 3)

### Cuerpo de Solicitud

| Campo | Tipo | Requerido | Descripción |
|-------|------|----------|-------------|
| `enabled` | bool | No | Habilitar/deshabilitar |
| `endpoint_url` | string | No | URL del endpoint Pi |
| `threshold` | float | No | Umbral de confianza de etiqueta |
| `timeout` | int | No | Tiempo de espera de solicitud (segundos) |

### Ejemplo de Solicitud

```json
{
  "enabled": true,
  "endpoint_url": "http://192.168.1.50:8080",
  "threshold": 0.35
}
```

### Respuesta

```json
{
  "ok": true,
  "data": {
    "config": {
      "enabled": true,
      "endpoint_url": "http://192.168.1.50:8080",
      "threshold": 0.35,
      "timeout": 30
    }
  }
}
```

### Errores

| Estado | Descripción |
|--------|-------------|
| 400 | Objeto JSON inválido |

---

## GET /api/hailo-tagger/status

Probar conexión al endpoint de Hailo. Envía una solicitud GET al endpoint `/health` para verificar la accesibilidad.

### Límite de velocidad

READ (ilimitado)

### Respuesta (éxito)

```json
{
  "ok": true,
  "data": {
    "enabled": true,
    "reachable": true,
    "endpoint_url": "http://192.168.1.50:8080"
  }
}
```

### Respuesta (no configurado / no alcanzable)

```json
{
  "ok": true,
  "data": {
    "enabled": true,
    "reachable": false,
    "reason": "Connection refused",
    "endpoint_url": "http://192.168.1.50:8080"
  }
}
```

---

## POST /api/hailo-tagger/tag/{file_id}

Etiquetar un archivo único.

### Límite de velocidad

HEAVY (~20 req/min, ráfaga 5)

### Parámetros de Ruta

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `file_id` | int | ID de base de datos del archivo objetivo |

### Cuerpo de Solicitud

| Campo | Tipo | Requerido | Descripción |
|-------|------|----------|-------------|
| `force` | bool | No | Sobrescribir etiquetas existentes (por defecto: `false`) |

### Respuesta

```json
{
  "ok": true,
  "data": {
    "file_id": 42,
    "filepath": "/images/test.png",
    "tag_count": 15,
    "tags": [
      {"tag": "1girl", "confidence": 0.95},
      {"tag": "solo", "confidence": 0.88}
    ]
  }
}
```

### Errores

| Estado | Código | Descripción |
|--------|--------|-------------|
| 400 | `disabled` | Hailo Tagger está deshabilitado |
| 400 | `not_configured` | URL del endpoint no configurada |
| 400 | `file_not_found` | Archivo no encontrado en la base de datos |
| 400 | `file_missing` | El archivo no existe en el disco |
| 400 | `unsupported_type` | Tipo de archivo no soportado para etiquetado |
| 502 | `request_failed` | Fallo de conexión al servidor remoto |

---

## POST /api/hailo-tagger/batch

Etiquetar múltiples archivos en lote. Se ejecuta como un trabajo en segundo plano.

### Límite de velocidad

HEAVY (~20 req/min, ráfaga 5)

### Cuerpo de Solicitud

| Campo | Tipo | Requerido | Descripción |
|-------|------|----------|-------------|
| `file_ids` | int[] | No | Lista de IDs de archivo objetivo (máx 500). Auto-selecciona archivos sin etiquetar si se omite |
| `limit` | int | No | Máx archivos para auto-selección (por defecto: 100) |
| `force` | bool | No | Sobrescribir etiquetas existentes (por defecto: `false`) |

### Ejemplo de Solicitud

```json
{
  "file_ids": [1, 2, 3, 4, 5],
  "force": false
}
```

### Respuesta

```json
{
  "ok": true,
  "data": {
    "started": true,
    "job_id": "hailo_tagger"
  }
}
```

### Errores

| Estado | Código | Descripción |
|--------|--------|-------------|
| 400 | `batch_too_large` | file_ids excede 500 |
| 409 | `job_running` | Trabajo por lotes ya en ejecución |

---

## GET /api/hailo-tagger/tags/{file_id}

Recuperar etiquetas de Hailo para un archivo.

### Límite de velocidad

READ (ilimitado)

### Respuesta

```json
{
  "ok": true,
  "data": {
    "file_id": 42,
    "tags": [
      {"tag_name": "1girl", "confidence": 0.95, "source": "hailo_remote", "created_at": 1710720000},
      {"tag_name": "solo", "confidence": 0.88, "source": "hailo_remote", "created_at": 1710720000}
    ]
  }
}
```

---

## DELETE /api/hailo-tagger/tags/{file_id}

Eliminar todas las etiquetas de Hailo para un archivo.

### Límite de velocidad

DESTRUCTIVE (~12 req/min, ráfaga 3)

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

## Esquema de BD

Las etiquetas de Hailo se almacenan en una tabla `file_hailo_tags` dedicada (independiente de `file_wd_tags`).

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
| `source` | Identificador de fuente de etiqueta (`hailo_remote` o `hailo_remote:<server_id>` cuando se utiliza el registro) |
| `created_at` | Timestamp UNIX |

---

## Configuración

Sección `hailo_tagger` en `config.json`:

```json
{
  "hailo_tagger": {
    "enabled": true,
    "endpoint_url": "http://192.168.1.50:8080",
    "threshold": 0.35,
    "timeout": 30
  }
}
```

También se puede cambiar desde la página de Configuración.

> **Nota**: Para gestionar múltiples servidores de tagger, utilice la [API del Registro de Servidores de Tagger](tagger-servers.md). La configuración heredada se puede migrar automáticamente a través de `/api/tagger-servers/migrate`. El Registro de Servidores de Tagger también admite autenticación con token Bearer.
