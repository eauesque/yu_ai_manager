# API YOLO Stream

API per l'elaborazione del flusso YOLO in tempo reale. Fornisce gestione delle sorgenti di flusso, distribuzione MJPEG, regole di rilevamento e funzionalità di registrazione/snapshot.

Tutti gli endpoint POST/PUT/DELETE richiedono l'intestazione `X-Requested-With` (eccetto quando si utilizza la chiave API Bearer).

---

## Gestione Sorgente

### GET /ext/hailo-yolo/api/stream/sources

Elenca tutte le sorgenti di flusso registrate.

#### Risposta

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

Aggiungi una nuova sorgente di flusso.

#### Richiesta

```json
{
  "id": "cam2",
  "url": "rtsp://192.168.1.101:554/stream",
  "name": "Back Camera"
}
```

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|----------|-------------|
| `id` | string | Yes | Identificatore univoco della sorgente |
| `url` | string | Yes | URL RTSP o indice del dispositivo |
| `name` | string | No | Nome di visualizzazione |

#### Risposta (201)

```json
{ "status": "ok", "source": { "id": "cam2", "..." : "..." } }
```

### DELETE /ext/hailo-yolo/api/stream/sources/\<id\>

Rimuovi la sorgente specificata.

#### Risposta

```json
{ "status": "ok" }
```

### POST /ext/hailo-yolo/api/stream/sources/\<id\>/start

Avvia la cattura per la sorgente specificata.

#### Risposta

```json
{ "status": "ok", "source": { "id": "cam1", "state": "running", "..." : "..." } }
```

### POST /ext/hailo-yolo/api/stream/sources/\<id\>/stop

Ferma la cattura per la sorgente specificata.

#### Risposta

```json
{ "status": "ok", "source": { "id": "cam1", "state": "stopped", "..." : "..." } }
```

### POST /ext/hailo-yolo/api/stream/sources/\<id\>/test

Testa la connessione a una sorgente. Se un URL viene fornito nel corpo della richiesta, tale URL viene testato; altrimenti viene utilizzato l'URL della sorgente esistente.

#### Richiesta

```json
{ "url": "rtsp://192.168.1.100:554/stream" }
```

#### Risposta

```json
{ "ok": true, "resolution": { "width": 1920, "height": 1080 } }
```

### GET /ext/hailo-yolo/api/stream/devices

Rileva le fotocamere USB collegate.

#### Risposta

```json
{
  "status": "ok",
  "devices": [
    { "index": 0, "name": "USB Camera", "resolution": null }
  ]
}
```

> **Nota:** La risposta nativa Rust elenca le fotocamere USB solo su Linux e non le apre mai; `resolution` è sempre `null`. Windows e macOS restituiscono `devices: []` e non supportano la registrazione tramite indice numerico della fotocamera.
>
> Anche il fan-out degli eventi viene ridotto: nessuna consegna wildcard implicita alle estensioni webhook configurate, nessun relay LAN quando un nome evento personalizzato corrisponde a `RELAY_TYPES` e nessun ricevitore MCP dedicato. `mcp_event` viene consegnato tramite l'hub SSE condiviso.

---

## Flusso Video

### GET /ext/hailo-yolo/api/stream/\<id\>/mjpeg

Restituisce un flusso MJPEG con overlay di rilevamento YOLO. Massimo 4 visualizzatori simultanei per sorgente.

- **Content-Type**: `multipart/x-mixed-replace; boundary=frame`

---

## Gestione Regola

### GET /ext/hailo-yolo/api/stream/rules

Elenca tutte le regole.

#### Risposta

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

Aggiungi una nuova regola. Passa il JSON della regola completa nel corpo della richiesta.

#### Risposta (201)

```json
{ "status": "ok", "rule": { "..." : "..." } }
```

### PUT /ext/hailo-yolo/api/stream/rules/\<id\>

Aggiorna una regola esistente.

#### Risposta

```json
{ "status": "ok", "rule": { "..." : "..." } }
```

### DELETE /ext/hailo-yolo/api/stream/rules/\<id\>

Cancella una regola.

#### Risposta

```json
{ "status": "ok" }
```

---

## Registrazioni e Snapshot

### GET /ext/hailo-yolo/api/stream/recordings

Elenca i file registrati.

#### Risposta

```json
{
  "status": "ok",
  "recordings": [
    { "filename": "cam1_20260328_220500.mp4", "path": "./detections/videos/cam1_20260328_220500.mp4", "size_bytes": 5242880, "created_at": "2026-03-28T22:05:00" }
  ]
}
```

### GET /ext/hailo-yolo/api/stream/snapshot/\<filename\>

Distribuisci un file di immagine snapshot.

---

## Stato

### GET /ext/hailo-yolo/api/stream/status

Ottieni lo stato complessivo della pipeline e della sorgente.

#### Risposta

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

## Struttura JSON della Regola

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `id` | string | Identificatore univoco della regola |
| `name` | string | Nome della regola |
| `enabled` | boolean | Se la regola è attiva |
| `conditions.classes` | string[] | Classi di rilevamento target (es. `["person"]`) |
| `conditions.min_confidence` | number | Soglia di confidenza minima (0.0-1.0) |
| `conditions.sources` | string[] | ID sorgente target. Tutte le sorgenti se omesso |
| `conditions.schedule` | object | Programma (`start`, `end`, `days`) |
| `cooldown_sec` | number | Cooldown in secondi |
| `actions` | object[] | Array di azioni |

### Tipi di Azione

| type | Descrizione |
|------|-------------|
| `snapshot` | Salva uno snapshot al rilevamento |
| `record` | Avvia la registrazione al rilevamento |
| `webhook` | Invia notifica all'URL webhook (con firma HMAC) |
| `sse` | Invia evento al canale SSE |
| `mcp_event` | Attiva un evento MCP |
