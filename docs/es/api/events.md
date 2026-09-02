# API de Eventos (SSE)

Entrega de eventos en tiempo real a través de Server-Sent Events.

## GET /api/events/stream

El flujo de eventos principal. Todas las páginas comparten una única conexión.

### Conectando

```javascript
// Desde un módulo TypeScript
import { sseSubscribe } from '../sse';
sseSubscribe('scan.complete', (data) => { ... });

// Desde un script en línea de plantilla
window.sseSubscribe('scan.complete', (data) => { ... });
```

**Importante**: No use `new EventSource()` directamente. `window.EventSource` se sobrescribe por un Proxy, por lo que el uso directo causa errores.

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `types` | string | Tipos de eventos a los que suscribirse (separados por comas; omitir para todos los eventos) |

### Límites de Conexión

- Hasta 10 conexiones simultáneas por IP
- Consciente de visibilidad: la conexión entra en un estado reducido cuando la pestaña está oculta
- Reconexión automática con retroceso exponencial

## Tipos de Eventos

### Escaneo

| Evento | Datos | Descripción |
|-------|------|-------------|
| `scan.progress` | `{ scanned, total, current_file }` | Progreso de escaneo |
| `scan.complete` | `{ added_count, updated_count, added_ids?, updated_ids? }` | Escaneo completo |
| `config.scan_roots_changed` | `{}` | Notificación de cambio de raíz de escaneo |

### Favoritos y Colecciones

| Evento | Datos | Descripción |
|-------|------|-------------|
| `favorite.add` | `{ file_id, collection_id }` | Favorito agregado |
| `favorite.remove` | `{ file_id, collection_id }` | Favorito eliminado |
| `collection.create` | `{ id, name }` | Colección creada |
| `collection.delete` | `{ id }` | Colección eliminada |

### Análisis de IA y Etiquetado

| Evento | Datos | Descripción |
|-------|------|-------------|
| `semantic_index.start` | `{ total }` | Indexación CLIP iniciada |
| `semantic_index.progress` | `{ done, total }` | Progreso de indexación CLIP |
| `semantic_index.complete` | `{ indexed }` | Indexación CLIP completa |
| `vlm_caption.start` | `{ total }` | Subtítulos VLM iniciados |
| `vlm_caption.progress` | `{ done, total }` | Progreso de subtítulos VLM |
| `vlm_caption.complete` | `{ processed }` | Subtítulos VLM completos |
| `yolo_detect.start` | `{ total }` | Detección YOLO iniciada |
| `yolo_detect.progress` | `{ done, total }` | Progreso de detección YOLO |
| `yolo_detect.complete` | `{ detected }` | Detección YOLO completa |

### Congelación y Recuperación

| Evento | Datos | Descripción |
|-------|------|-------------|
| `fpb.start` | `{ job_id }` | Trabajo iniciado |
| `fpb.progress` | `{ job_id, frame, total }` | Progreso de fotograma |
| `fpb.complete` | `{ job_id, output_path }` | Trabajo completo |
| `fpb.error` | `{ job_id, error }` | Error de trabajo |

### Registros de Chat

| Evento | Datos | Descripción |
|-------|------|-------------|
| `chatlog_reprocess.start` | `{ total }` | Reprocesamiento de IA iniciado |
| `chatlog_reprocess.progress` | `{ done, total }` | Progreso de reprocesamiento de IA |
| `chatlog_reprocess.complete` | `{ processed }` | Reprocesamiento de IA completo |
| `chatlog_reprocess.error` | `{ error }` | Error de reprocesamiento de IA |

### Programador

| Evento | Datos | Descripción |
|-------|------|-------------|
| `scheduler.job_executed` | `{ job_id, result }` | Trabajo programado completado exitosamente |
| `scheduler.job_error` | `{ job_id, error }` | Trabajo programado fallido |

## GET /api/logs/stream

Un flujo SSE dedicado para registros del servidor. Funciona de forma independiente del flujo principal.

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `level` | string | Nivel de registro mínimo (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

### Eventos

| Evento | Datos | Descripción |
|-------|------|-------------|
| `log.entry` | `{ seq, ts, level, name, message }` | Entrada de registro |

### Límites de Conexión

- Hasta 3 conexiones simultáneas por IP (separadas del flujo principal)
- Intervalo de latido de 15 segundos (`: heartbeat\n\n`)
