# Events API (SSE)

Echtzeit-Ereignislieferung über Server-Sent Events.

## GET /api/events/stream

Der Hauptereignisstrom. Alle Seiten teilen sich eine einzige Verbindung.

### Verbindung

```javascript
// Aus einem TypeScript-Modul
import { sseSubscribe } from '../sse';
sseSubscribe('scan.complete', (data) => { ... });

// Aus einem Template-Inline-Skript
window.sseSubscribe('scan.complete', (data) => { ... });
```

**Wichtig**: Verwenden Sie `new EventSource()` nicht direkt. `window.EventSource` wird von einem Proxy überschrieben, daher verursacht die direkte Verwendung Fehler.

### Parameter

| Parameter | Typ | Beschreibung |
|-----------|------|-------------|
| `types` | string | Ereignistypen zum Abonnieren (kommagetrennt; weglassen für alle Ereignisse) |

### Verbindungsbeschränkungen

- Bis zu 10 gleichzeitige Verbindungen pro IP
- Sichtbarkeitsbewusst: Die Verbindung geht in einen reduzierten Zustand über, wenn der Tab verborgen ist
- Automatische Wiederverbindung mit exponentiellem Backoff

## Ereignistypen

### Scan

| Ereignis | Daten | Beschreibung |
|-------|------|-------------|
| `scan.progress` | `{ scanned, total, current_file }` | Scan-Fortschritt |
| `scan.complete` | `{ added_count, updated_count, added_ids?, updated_ids? }` | Scan abgeschlossen |
| `config.scan_roots_changed` | `{}` | Scan-Root-Änderungsbenachrichtigung |

### Favoriten & Sammlungen

| Ereignis | Daten | Beschreibung |
|-------|------|-------------|
| `favorite.add` | `{ file_id, collection_id }` | Favorit hinzugefügt |
| `favorite.remove` | `{ file_id, collection_id }` | Favorit entfernt |
| `collection.create` | `{ id, name }` | Sammlung erstellt |
| `collection.delete` | `{ id }` | Sammlung gelöscht |

### AI-Analyse & Tagging

| Ereignis | Daten | Beschreibung |
|-------|------|-------------|
| `semantic_index.start` | `{ total }` | CLIP-Indexierung gestartet |
| `semantic_index.progress` | `{ done, total }` | CLIP-Indexierung Fortschritt |
| `semantic_index.complete` | `{ indexed }` | CLIP-Indexierung abgeschlossen |
| `vlm_caption.start` | `{ total }` | VLM-Bildunterschrift gestartet |
| `vlm_caption.progress` | `{ done, total }` | VLM-Bildunterschrift Fortschritt |
| `vlm_caption.complete` | `{ processed }` | VLM-Bildunterschrift abgeschlossen |
| `yolo_detect.start` | `{ total }` | YOLO-Erkennung gestartet |
| `yolo_detect.progress` | `{ done, total }` | YOLO-Erkennung Fortschritt |
| `yolo_detect.complete` | `{ detected }` | YOLO-Erkennung abgeschlossen |

### Freeze & Pull-back

| Ereignis | Daten | Beschreibung |
|-------|------|-------------|
| `fpb.start` | `{ job_id }` | Job gestartet |
| `fpb.progress` | `{ job_id, frame, total }` | Frame-Fortschritt |
| `fpb.complete` | `{ job_id, output_path }` | Job abgeschlossen |
| `fpb.error` | `{ job_id, error }` | Job-Fehler |

### Chat-Protokolle

| Ereignis | Daten | Beschreibung |
|-------|------|-------------|
| `chatlog_reprocess.start` | `{ total }` | AI-Umarbeitung gestartet |
| `chatlog_reprocess.progress` | `{ done, total }` | AI-Umarbeitung Fortschritt |
| `chatlog_reprocess.complete` | `{ processed }` | AI-Umarbeitung abgeschlossen |
| `chatlog_reprocess.error` | `{ error }` | AI-Umarbeitung Fehler |

### Scheduler

| Ereignis | Daten | Beschreibung |
|-------|------|-------------|
| `scheduler.job_executed` | `{ job_id, result }` | Geplanter Job erfolgreich abgeschlossen |
| `scheduler.job_error` | `{ job_id, error }` | Geplanter Job fehlgeschlagen |

## GET /api/logs/stream

Ein dedizierter SSE-Stream für Server-Protokolle. Er arbeitet unabhängig vom Hauptstrom.

### Parameter

| Parameter | Typ | Beschreibung |
|-----------|------|-------------|
| `level` | string | Minimale Log-Ebene (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

### Ereignisse

| Ereignis | Daten | Beschreibung |
|-------|------|-------------|
| `log.entry` | `{ seq, ts, level, name, message }` | Log-Eintrag |

### Verbindungsbeschränkungen

- Bis zu 3 gleichzeitige Verbindungen pro IP (separat vom Hauptstrom)
- 15-Sekunden-Heartbeat-Intervall (`: heartbeat\n\n`)
