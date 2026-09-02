# API Registro Server Tagger

API per la gestione di più tag inference worker (Hailo Remote, ONNX Local, Ryzen AI, ecc.) come cluster unificato, con tagging batch distribuito tramite modello di work-stealing con esecuzione parallela a coda condivisa.

## Panoramica

Il Registro dei Server Tagger va oltre un singolo Hailo Remote Tagger gestendo più backend di inferenza eterogenei come cluster. Ogni server ha una priorità configurabile e le attività vengono distribuite secondo la modalità di distribuzione selezionata (singolo / parallelo / idle_first).

### Architettura

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

### Tipi di Server

| Tipo | Descrizione |
|------|-------------|
| `hailo_remote` | Dispositivo Hailo-10H remoto (es. Raspberry Pi 5) |
| `onnx_local` | Inferenza ONNX Runtime locale |
| `onnx_remote` | Server di inferenza ONNX remoto |
| `ryzen_ai` | AMD Ryzen AI NPU |

### Modalità di Distribuzione

| Modalità | Descrizione |
|------|-------------|
| `single` | Utilizza solo il server abilitato con priorità più alta |
| `parallel` | Esegui su tutti i server abilitati in parallelo (work-stealing) |
| `idle_first` | Preferisci prima i server inattivi |

---

## Formato Voce Server

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

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `id` | string | Identificatore del server (auto-generato o specificato manualmente) |
| `name` | string | Nome di visualizzazione |
| `type` | string | Tipo di server (`hailo_remote` / `onnx_local` / `onnx_remote` / `ryzen_ai`) |
| `priority` | int | Priorità (inferiore = priorità superiore, predefinito: 50) |
| `enabled` | bool | Abilitato/disabilitato |
| `config` | object | Configurazione specifica del tipo (vedi sotto) |

### Campi config (per server remoti)

| Campo | Tipo | Obbligatorio | Descrizione |
|-------|------|----------|-------------|
| `endpoint_url` | string | Yes | URL del server remoto |
| `bearer_token` | string | No | Token Bearer (auto-crittografato con prefisso `enc:` al salvataggio) |
| `threshold` | float | No | Soglia di confidenza del tag (predefinito: 0.35) |
| `timeout` | int | No | Timeout della richiesta in secondi (predefinito: 30) |

---

## Autenticazione

La comunicazione con server remoti (`hailo_remote` / `onnx_remote`) supporta l'autenticazione opzionale con token Bearer.

### Host → Server Remoto

Quando `config.bearer_token` è impostato, tutte le richieste HTTP (controlli di salute e tagging) includono automaticamente un'intestazione `Authorization: Bearer <token>`. I token vengono archiviati in `config.json` con crittografia Fernet (prefisso `enc:`) e mascherati nelle risposte API.

### Lato Server Remoto

`deploy/hailo_tagger_server.py` fornisce un'implementazione di riferimento con verifica del token. Imposta il token all'avvio tramite:

```bash
# Argomento della riga di comando
python hailo_tagger_server.py --token "my-secret-token"

# Leggi da file
python hailo_tagger_server.py --token-file /etc/tagger/token

# Variabile di ambiente
TAGGER_BEARER_TOKEN=my-secret-token python hailo_tagger_server.py
```

Quando nessun token è configurato, il server opera in modalità di accesso aperto (modello di trust LAN) per compatibilità all'indietro. I token non validi ricevono risposte 401/403.

---

## GET /api/tagger-servers

Elenca i server registrati e la modalità di distribuzione attuale.

### Limite di Velocità

READ (illimitato)

### Risposta

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

Aggiungi un nuovo server tagger.

### Limite di Velocità

DESTRUCTIVE (~12 req/min, burst 3)

### Corpo della Richiesta

| Campo | Tipo | Obbligatorio | Descrizione |
|-------|------|----------|-------------|
| `name` | string | Yes | Nome di visualizzazione |
| `type` | string | Yes | Tipo di server |
| `config` | object | Yes | Configurazione specifica del tipo |
| `priority` | int | No | Priorità (predefinito: 50) |
| `enabled` | bool | No | Abilitato/disabilitato (predefinito: `true`) |

### Esempio di Richiesta

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

### Risposta

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

### Errori

| Stato | Descrizione |
|--------|-------------|
| 400 | Campi obbligatori mancanti o tipo non valido |

---

## PUT /api/tagger-servers/{server_id}

Aggiorna le impostazioni di un server esistente. Supportati gli aggiornamenti parziali.

### Limite di Velocità

DESTRUCTIVE (~12 req/min, burst 3)

### Parametri di Percorso

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `server_id` | string | ID del server target |

### Corpo della Richiesta

| Campo | Tipo | Obbligatorio | Descrizione |
|-------|------|----------|-------------|
| `name` | string | No | Nome di visualizzazione |
| `type` | string | No | Tipo di server |
| `config` | object | No | Configurazione specifica del tipo |
| `priority` | int | No | Priorità |
| `enabled` | bool | No | Abilitato/disabilitato |

### Risposta

```json
{
  "ok": true,
  "data": {
    "server": { "..." }
  }
}
```

### Errori

| Stato | Descrizione |
|--------|-------------|
| 404 | Server non trovato |

---

## DELETE /api/tagger-servers/{server_id}

Rimuovi un server.

### Limite di Velocità

DESTRUCTIVE (~12 req/min, burst 3)

### Parametri di Percorso

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `server_id` | string | ID del server target |

### Risposta

```json
{
  "ok": true,
  "data": {
    "deleted": "pi-hailo-a"
  }
}
```

### Errori

| Stato | Descrizione |
|--------|-------------|
| 404 | Server non trovato |

---

## POST /api/tagger-servers/reorder

Riordina le priorità dei server in bulk.

### Limite di Velocità

DESTRUCTIVE (~12 req/min, burst 3)

### Corpo della Richiesta

| Campo | Tipo | Obbligatorio | Descrizione |
|-------|------|----------|-------------|
| `order` | string[] | Yes | Array di ID server in ordine di priorità |

### Esempio di Richiesta

```json
{
  "order": ["pi-hailo-a", "local-onnx", "pi-hailo-b"]
}
```

### Risposta

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

Cambia la modalità di distribuzione.

### Limite di Velocità

DESTRUCTIVE (~12 req/min, burst 3)

### Corpo della Richiesta

| Campo | Tipo | Obbligatorio | Descrizione |
|-------|------|----------|-------------|
| `mode` | string | Yes | `single` / `parallel` / `idle_first` |

### Risposta

```json
{
  "ok": true,
  "data": {
    "mode": "parallel"
  }
}
```

### Errori

| Stato | Descrizione |
|--------|-------------|
| 400 | Valore mode non valido |

---

## POST /api/tagger-servers/{server_id}/test

Testa la connettività a un server specifico.

### Limite di Velocità

HEAVY (~20 req/min, burst 5)

### Parametri di Percorso

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `server_id` | string | ID del server target |

### Risposta (successo)

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

### Risposta (non raggiungibile)

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

### Errori

| Stato | Descrizione |
|--------|-------------|
| 404 | Server non trovato |

---

## GET /api/tagger-servers/health

Controllo di salute di tutti i server abilitati.

### Limite di Velocità

READ (illimitato)

### Risposta

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

Esegui il tagging batch distribuito utilizzando il modello di work-stealing a coda condivisa. Esecuzione come lavoro in background con progresso segnalato tramite SSE.

### Limite di Velocità

HEAVY (~20 req/min, burst 5)

### Corpo della Richiesta

| Campo | Tipo | Obbligatorio | Descrizione |
|-------|------|----------|-------------|
| `file_ids` | int[] | No | Elenco degli ID file target. Auto-seleziona file non taggati se omesso |
| `limit` | int | No | Max file per auto-selezione (predefinito: 500) |
| `force` | bool | No | Sovrascrivi i tag esistenti (predefinito: `false`) |
| `threshold` | float | No | Soglia di confidenza del tag override (utilizza la configurazione per-server se omesso) |

### Esempio di Richiesta

```json
{
  "file_ids": [1, 2, 3, 4, 5],
  "force": false,
  "threshold": 0.35
}
```

### Risposta

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

### Errori

| Stato | Codice | Descrizione |
|--------|------|-------------|
| 400 | `no_servers` | Nessun server abilitato disponibile |
| 400 | `batch_too_large` | file_ids supera il limite |
| 409 | `job_running` | Lavoro batch già in esecuzione |

---

## POST /api/tagger-servers/batch/cancel

Cancella un lavoro batch del cluster tagger in esecuzione.

### Risposta

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `status` | string | `"cancelling"` |
| `message` | string | Messaggio di stato |

### Codici di Errore

| Stato | Codice | Descrizione |
|--------|------|-------------|
| 404 | `job_not_running` | Nessun lavoro batch in esecuzione da cancellare |

---

## GET /api/tagger-servers/tags/{file_id}

Recupera i tag tagger per un file.

### Limite di Velocità

READ (illimitato)

### Parametri di Percorso

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `file_id` | int | ID file nel database target |

### Risposta

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

Il campo `source` utilizza il formato `{type}:{server_id}` (es. `hailo_remote:pi-hailo-a`, `onnx_local:local-onnx`).

---

## DELETE /api/tagger-servers/tags/{file_id}

Cancella tutti i tag tagger per un file.

### Limite di Velocità

DESTRUCTIVE (~12 req/min, burst 3)

### Parametri di Percorso

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `file_id` | int | ID file nel database target |

### Risposta

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

Recupera le statistiche del tagger.

### Limite di Velocità

READ (illimitato)

### Risposta

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

Migra la configurazione legacy `hailo_tagger` al formato del Registro dei Server Tagger. Converte la voce `hailo_tagger` esistente in `config.json` in una voce dell'array `tagger_servers`.

### Limite di Velocità

DESTRUCTIVE (~12 req/min, burst 3)

### Risposta

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

### Risposta (nessuna migrazione necessaria)

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

## Configurazione

Chiavi correlate in `config.json`:

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

| Chiave | Tipo | Descrizione |
|-----|------|-------------|
| `tagger_servers` | array | Array di voci server |
| `tagger_servers_mode` | string | Modalità di distribuzione (`single` / `parallel` / `idle_first`) |

Può essere modificato anche dalla pagina Impostazioni.

---

## Schema DB

I tag vengono archiviati nella tabella `file_hailo_tags`. La colonna `source` utilizza il formato `{type}:{server_id}` per identificare quale server ha assegnato il tag.

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

| Colonna | Descrizione |
|--------|-------------|
| `file_id` | Chiave esterna alla tabella files |
| `tag_name` | Nome tag Danbooru (es. `1girl`, `solo`) |
| `confidence` | Confidenza dell'inferenza (0.0-1.0) |
| `source` | Identificatore della sorgente del tag (`{type}:{server_id}` formato, es. `hailo_remote:pi-hailo-a`) |
