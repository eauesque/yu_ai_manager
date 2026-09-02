# API Events (SSE)

Consegna di eventi in tempo reale tramite Server-Sent Events.

## GET /api/events/stream

Il flusso di eventi principale. Tutte le pagine condividono una singola connessione.

### Connessione

```javascript
// Da un modulo TypeScript
import { sseSubscribe } from '../sse';
sseSubscribe('scan.complete', (data) => { ... });

// Da uno script inline del template
window.sseSubscribe('scan.complete', (data) => { ... });
```

**Importante**: Non usare `new EventSource()` direttamente. `window.EventSource` viene sovrascritto da un Proxy, quindi l'utilizzo diretto causa errori.

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `types` | string | Tipi di evento da sottoscrivere (separati da virgola; ometti per tutti gli eventi) |

### Limiti di connessione

- Fino a 10 connessioni simultanee per IP
- Consapevole della visibilità: la connessione entra in uno stato ridotto quando la scheda è nascosta
- Riconnessione automatica con backoff esponenziale

## Tipi di evento

### Scansione

| Evento | Dati | Descrizione |
|-------|------|-------------|
| `scan.progress` | `{ scanned, total, current_file }` | Progresso della scansione |
| `scan.complete` | `{ added_count, updated_count, added_ids?, updated_ids? }` | Scansione completa |
| `config.scan_roots_changed` | `{}` | Notifica di modifica della root di scansione |

### Preferiti e raccolte

| Evento | Dati | Descrizione |
|-------|------|-------------|
| `favorite.add` | `{ file_id, collection_id }` | Preferito aggiunto |
| `favorite.remove` | `{ file_id, collection_id }` | Preferito rimosso |
| `collection.create` | `{ id, name }` | Raccolta creata |
| `collection.delete` | `{ id }` | Raccolta eliminata |

### Analisi AI e tagging

| Evento | Dati | Descrizione |
|-------|------|-------------|
| `semantic_index.start` | `{ total }` | Indicizzazione CLIP avviata |
| `semantic_index.progress` | `{ done, total }` | Progresso dell'indicizzazione CLIP |
| `semantic_index.complete` | `{ indexed }` | Indicizzazione CLIP completa |
| `vlm_caption.start` | `{ total }` | Sottotitolazione VLM avviata |
| `vlm_caption.progress` | `{ done, total }` | Progresso della sottotitolazione VLM |
| `vlm_caption.complete` | `{ processed }` | Sottotitolazione VLM completa |
| `yolo_detect.start` | `{ total }` | Rilevamento YOLO avviato |
| `yolo_detect.progress` | `{ done, total }` | Progresso del rilevamento YOLO |
| `yolo_detect.complete` | `{ detected }` | Rilevamento YOLO completo |

### Freeze e Pull-back

| Evento | Dati | Descrizione |
|-------|------|-------------|
| `fpb.start` | `{ job_id }` | Job avviato |
| `fpb.progress` | `{ job_id, frame, total }` | Progresso del frame |
| `fpb.complete` | `{ job_id, output_path }` | Job completo |
| `fpb.error` | `{ job_id, error }` | Errore del job |

### Chatlog

| Evento | Dati | Descrizione |
|-------|------|-------------|
| `chatlog_reprocess.start` | `{ total }` | Rielaborazione AI avviata |
| `chatlog_reprocess.progress` | `{ done, total }` | Progresso della rielaborazione AI |
| `chatlog_reprocess.complete` | `{ processed }` | Rielaborazione AI completa |
| `chatlog_reprocess.error` | `{ error }` | Errore della rielaborazione AI |

### Pianificatore

| Evento | Dati | Descrizione |
|-------|------|-------------|
| `scheduler.job_executed` | `{ job_id, result }` | Job pianificato completato con successo |
| `scheduler.job_error` | `{ job_id, error }` | Job pianificato non riuscito |

## GET /api/logs/stream

Un flusso SSE dedicato per i log del server. Funziona in modo indipendente dal flusso principale.

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `level` | string | Livello di log minimo (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

### Eventi

| Evento | Dati | Descrizione |
|-------|------|-------------|
| `log.entry` | `{ seq, ts, level, name, message }` | Voce di log |

### Limiti di connessione

- Fino a 3 connessioni simultanee per IP (separate dal flusso principale)
- Intervallo heartbeat di 15 secondi (`: heartbeat\n\n`)
