# API de Stream YOLO

APIs para procesamiento de stream en tiempo real de YOLO. Proporciona gestión de fuentes de stream, entrega MJPEG, reglas de detección y funcionalidad de grabación/captura.

Todos los endpoints POST/PUT/DELETE requieren el encabezado `X-Requested-With` (excepto cuando se utiliza API Key Bearer).

---

## Gestión de Fuentes

### GET /ext/hailo-yolo/api/stream/sources

Listar todas las fuentes de stream registradas.

#### Respuesta

```json
{
  "status": "ok",
  "sources": [
    {
      "id": "cam1",
      "name": "Front Camera",
      "url": "rtsp://192.168.1.100:554/stream",
      "type": "rtsp",
      "state": "running",
      "resolution": { "width": 1920, "height": 1080 },
      "fps": 25.0,
      "frame_count": 15420,
      "error": null,
      "viewers": 1
    }
  ]
}
```

### POST /ext/hailo-yolo/api/stream/sources

Agregar una nueva fuente de stream.

#### Solicitud

```json
{
  "id": "cam2",
  "url": "rtsp://192.168.1.101:554/stream",
  "name": "Back Camera"
}
```

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `id` | string | Sí | Identificador único de fuente |
| `url` | string | Sí | URL RTSP o índice de dispositivo |
| `name` | string | No | Nombre para mostrar |

#### Respuesta (201)

```json
{ "status": "ok", "source": { "id": "cam2", "..." : "..." } }
```

### DELETE /ext/hailo-yolo/api/stream/sources/\<id\>

Eliminar la fuente especificada.

#### Respuesta

```json
{ "status": "ok" }
```

### POST /ext/hailo-yolo/api/stream/sources/\<id\>/start

Iniciar captura para la fuente especificada.

#### Respuesta

```json
{ "status": "ok", "source": { "id": "cam1", "state": "running", "..." : "..." } }
```

### POST /ext/hailo-yolo/api/stream/sources/\<id\>/stop

Detener captura para la fuente especificada.

#### Respuesta

```json
{ "status": "ok", "source": { "id": "cam1", "state": "stopped", "..." : "..." } }
```

### POST /ext/hailo-yolo/api/stream/sources/\<id\>/test

Probar conexión a una fuente. Si se proporciona una URL en el cuerpo de la solicitud, esa URL se prueba; de lo contrario se utiliza la URL de fuente existente.

#### Solicitud

```json
{ "url": "rtsp://192.168.1.100:554/stream" }
```

#### Respuesta

```json
{ "ok": true, "resolution": { "width": 1920, "height": 1080 } }
```

### GET /ext/hailo-yolo/api/stream/devices

Detectar cámaras USB conectadas.

#### Respuesta

```json
{
  "status": "ok",
  "devices": [
    { "index": 0, "name": "USB Camera", "resolution": null }
  ]
}
```

> **Nota:** La respuesta nativa de Rust enumera cámaras USB solo en Linux y nunca las abre; `resolution` siempre es `null`. Windows y macOS devuelven `devices: []` y no admiten el registro mediante un índice numérico de cámara.
>
> También se reduce la distribución de eventos: no hay entrega wildcard implícita a extensiones webhook configuradas, ni retransmisión LAN cuando un nombre de evento personalizado coincide con `RELAY_TYPES`, ni receptor MCP dedicado. `mcp_event` se entrega mediante el hub SSE compartido.

---

## Stream de Video

### GET /ext/hailo-yolo/api/stream/\<id\>/mjpeg

Devuelve un stream MJPEG con superposición de detección YOLO. Máximo 4 espectadores concurrentes por fuente.

- **Content-Type**: `multipart/x-mixed-replace; boundary=frame`

---

## Gestión de Reglas

### GET /ext/hailo-yolo/api/stream/rules

Listar todas las reglas.

#### Respuesta

```json
{
  "status": "ok",
  "rules": [
    {
      "id": "rule1",
      "name": "Person detection",
      "enabled": true,
      "conditions": {
        "classes": ["person"],
        "min_confidence": 0.7,
        "sources": ["cam1"],
        "schedule": { "start": "22:00", "end": "06:00", "days": ["mon","tue","wed","thu","fri","sat","sun"] }
      },
      "cooldown_sec": 60,
      "actions": [
        { "type": "snapshot", "save_dir": "./detections/snapshots" },
        { "type": "record", "save_dir": "./detections/videos", "duration_sec": 30, "extend_mode": "fixed" },
        { "type": "webhook", "url": "https://example.com/hook", "secret": "hmac-key" },
        { "type": "sse", "channel": "yolo_stream" },
        { "type": "mcp_event", "event": "yolo_stream.detection" }
      ]
    }
  ]
}
```

### POST /ext/hailo-yolo/api/stream/rules

Agregar una nueva regla. Pasar el JSON completo de la regla en el cuerpo de la solicitud.

#### Respuesta (201)

```json
{ "status": "ok", "rule": { "..." : "..." } }
```

### PUT /ext/hailo-yolo/api/stream/rules/\<id\>

Actualizar una regla existente.

#### Respuesta

```json
{ "status": "ok", "rule": { "..." : "..." } }
```

### DELETE /ext/hailo-yolo/api/stream/rules/\<id\>

Eliminar una regla.

#### Respuesta

```json
{ "status": "ok" }
```

---

## Grabaciones y Capturas

### GET /ext/hailo-yolo/api/stream/recordings

Listar archivos de grabación.

#### Respuesta

```json
{
  "status": "ok",
  "recordings": [
    { "filename": "cam1_20260328_220500.mp4", "path": "./detections/videos/cam1_20260328_220500.mp4", "size_bytes": 5242880, "created_at": "2026-03-28T22:05:00" }
  ]
}
```

### GET /ext/hailo-yolo/api/stream/snapshot/\<filename\>

Servir un archivo de imagen de captura.

---

## Estado

### GET /ext/hailo-yolo/api/stream/status

Obtener estado general de pipeline y fuentes.

#### Respuesta

```json
{
  "status": "ok",
  "pipeline": { "running": true, "queue_size": 2, "fps": 24.8 },
  "sources": [ { "id": "cam1", "state": "running" } ],
  "rules_count": 3,
  "recorder": { "active_recordings": 1 }
}
```

---

## Estructura JSON de Regla

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id` | string | Identificador único de regla |
| `name` | string | Nombre de la regla |
| `enabled` | boolean | Si la regla está activa |
| `conditions.classes` | string[] | Clases de detección objetivo (ej. `["person"]`) |
| `conditions.min_confidence` | number | Umbral de confianza mínimo (0.0-1.0) |
| `conditions.sources` | string[] | IDs de fuente objetivo. Todas las fuentes si se omite |
| `conditions.schedule` | object | Cronograma (`start`, `end`, `days`) |
| `cooldown_sec` | number | Enfriamiento en segundos |
| `actions` | object[] | Array de acciones |

### Tipos de Acción

| type | Descripción |
|------|-------------|
| `snapshot` | Guardar una captura en detección |
| `record` | Iniciar grabación en detección |
| `webhook` | Enviar notificación a URL de webhook (con firma HMAC) |
| `sse` | Enviar evento a canal SSE |
| `mcp_event` | Disparar un evento MCP |
