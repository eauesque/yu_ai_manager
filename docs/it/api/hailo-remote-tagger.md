# API Hailo Remote Tagger

API per l'invio di immagini a un server di inferenza Hailo AI HAT remoto (es. Raspberry Pi 5) sulla rete, l'esecuzione dell'inferenza tag Danbooru e il salvataggio dei risultati nel database.

## Panoramica

Anche senza una GPU locale o runtime ONNX, puoi utilizzare un dispositivo Hailo-10H sulla tua LAN come tagger remoto. Le immagini vengono inviate come multipart/form-data e il JSON dei tag viene restituito come risposta.

---

## GET /api/hailo-tagger/config

Recupera la configurazione attuale.

### Limite di Velocità

READ (illimitato)

### Risposta

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

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `enabled` | bool | Se Hailo Remote Tagger è abilitato |
| `endpoint_url` | string | URL dell'endpoint Pi (es. `http://192.168.1.50:8080`) |
| `threshold` | float | Soglia di confidenza del tag (solo i tag sopra questo vengono salvati) |
| `timeout` | int | Timeout della richiesta in secondi |

---

## POST /api/hailo-tagger/config

Salva la configurazione. Supportati gli aggiornamenti parziali (solo i campi specificati vengono modificati).

### Limite di Velocità

DESTRUCTIVE (~12 req/min, burst 3)

### Corpo della Richiesta

| Campo | Tipo | Obbligatorio | Descrizione |
|-------|------|----------|-------------|
| `enabled` | bool | No | Abilita/disabilita |
| `endpoint_url` | string | No | URL dell'endpoint Pi |
| `threshold` | float | No | Soglia di confidenza del tag |
| `timeout` | int | No | Timeout della richiesta (secondi) |

### Esempio di Richiesta

```json
{
  "enabled": true,
  "endpoint_url": "http://192.168.1.50:8080",
  "threshold": 0.35
}
```

### Risposta

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

### Errori

| Stato | Descrizione |
|--------|-------------|
| 400 | Oggetto JSON non valido |

---

## GET /api/hailo-tagger/status

Testa la connessione all'endpoint Hailo. Invia una richiesta GET all'endpoint `/health` per verificare la raggiungibilità.

### Limite di Velocità

READ (illimitato)

### Risposta (successo)

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

### Risposta (non configurato / non raggiungibile)

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

Tagga un file singolo.

### Limite di Velocità

HEAVY (~20 req/min, burst 5)

### Parametri di Percorso

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `file_id` | int | ID file nel database target |

### Corpo della Richiesta

| Campo | Tipo | Obbligatorio | Descrizione |
|-------|------|----------|-------------|
| `force` | bool | No | Sovrascrivi i tag esistenti (predefinito: `false`) |

### Risposta

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

### Errori

| Stato | Codice | Descrizione |
|--------|------|-------------|
| 400 | `disabled` | Hailo Tagger è disabilitato |
| 400 | `not_configured` | URL dell'endpoint non configurato |
| 400 | `file_not_found` | File non trovato nel database |
| 400 | `file_missing` | File non esiste su disco |
| 400 | `unsupported_type` | Tipo di file non supportato per il tagging |
| 502 | `request_failed` | Errore di connessione al server remoto |

---

## POST /api/hailo-tagger/batch

Tagga più file in batch. Esecuzione come lavoro in background.

### Limite di Velocità

HEAVY (~20 req/min, burst 5)

### Corpo della Richiesta

| Campo | Tipo | Obbligatorio | Descrizione |
|-------|------|----------|-------------|
| `file_ids` | int[] | No | Elenco degli ID file target (max 500). Auto-seleziona i file non taggati se omesso |
| `limit` | int | No | Max file per auto-selezione (predefinito: 100) |
| `force` | bool | No | Sovrascrivi i tag esistenti (predefinito: `false`) |

### Esempio di Richiesta

```json
{
  "file_ids": [1, 2, 3, 4, 5],
  "force": false
}
```

### Risposta

```json
{
  "ok": true,
  "data": {
    "started": true,
    "job_id": "hailo_tagger"
  }
}
```

### Errori

| Stato | Codice | Descrizione |
|--------|------|-------------|
| 400 | `batch_too_large` | file_ids supera 500 |
| 409 | `job_running` | Lavoro batch già in esecuzione |

---

## GET /api/hailo-tagger/tags/{file_id}

Recupera i tag Hailo per un file.

### Limite di Velocità

READ (illimitato)

### Risposta

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

Cancella tutti i tag Hailo per un file.

### Limite di Velocità

DESTRUCTIVE (~12 req/min, burst 3)

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

## Schema DB

I tag Hailo vengono archiviati in una tabella dedicata `file_hailo_tags` (indipendente da `file_wd_tags`).

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
| `source` | Identificatore della sorgente del tag (`hailo_remote` o `hailo_remote:<server_id>` quando si utilizza il registro) |
| `created_at` | Timestamp UNIX |

---

## Configurazione

Sezione `hailo_tagger` in `config.json`:

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

Può essere modificato anche dalla pagina Impostazioni.

> **Nota**: Per gestire più server tagger, utilizza l'[API Registro dei Server Tagger](tagger-servers.md). La configurazione legacy può essere auto-migrata tramite `/api/tagger-servers/migrate`. Il Registro dei Server Tagger supporta anche l'autenticazione con token Bearer.
