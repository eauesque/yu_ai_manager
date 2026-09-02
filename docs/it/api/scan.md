# API di scansione

API per la scansione di file e la gestione della root di scansione.

## Controllo della scansione

### POST /api/scan/start

Avvia una scansione.

### Richiesta

```json
{
  "root_indices": [0, 1],
  "force": false
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `root_indices` | int[] | Indici delle root da scansionare (ometti per tutte le root) |
| `force` | bool | Ripeti la scansione dei file esistenti |

### Risposta

```json
{
  "ok": true,
  "message": "Scan started"
}
```

### GET /api/scan/status

Recupera il progresso della scansione.

### Risposta

```json
{
  "scanning": true,
  "progress": 45,
  "total": 1500,
  "current_file": "/images/output/00042.png",
  "errors": 0,
  "started_at": 1709500000
}
```

### POST /api/scan/cancel

Annulla una scansione in esecuzione.

### GET /api/scan/interrupted

Recupera informazioni su una scansione interrotta.

### POST /api/scan/resume

Riprendi una scansione interrotta.

### POST /api/scan/dismiss

Scarta lo stato di scansione interrotta.

## Scansione CLI Worker

Dalla v3.27.0, le scansioni vengono eseguite in un processo separato (worker).
Il worker può essere controllato direttamente dalla CLI oltre all'API WebUI.

```bash
# Avvia una scansione
python -m core.scan.scan_worker start --db ./tags.db --root /path/to/images [--scan-zips] [--force] [--resume]

# Arresta una scansione (SIGTERM -> graceful shutdown)
python -m core.scan.scan_worker stop

# Controlla lo stato
python -m core.scan.scan_worker status
```

### File IPC

| File | Contenuto |
|------|---------|
| `/tmp/yu-scan/worker.pid` | Worker PID |
| `/tmp/yu-scan/progress.json` | Progresso (JSON: running, phase, current, total, percent, message, detail, error) |

La WebUI esegue il polling di questo file di progresso e trasmette i dati tramite `GET /api/scan/status` e gli eventi SSE (`scan.progress`, `scan.complete`).

## Errori di scansione

### GET /api/scan-errors

Elenco degli errori che si sono verificati durante la scansione.

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `type` | string | Filtro tipo di errore |
| `resolved` | bool | Solo errori risolti |
| `limit` | int | Numero di risultati |

### POST /api/scan-errors/<id>/resolve

Contrassegna un errore come risolto.

### POST /api/scan-errors/clear

Elimina tutti gli errori risolti contemporaneamente.

## Gestione della root di scansione

### GET /api/scan-roots

Elenca le root di scansione registrate.

### Risposta

```json
{
  "roots": [
    {
      "path": "O:\\webui\\outputs",
      "enabled": true,
      "file_count": 15000
    }
  ]
}
```

### POST /api/scan-roots

Aggiungi una root di scansione.

```json
{
  "path": "O:\\webui\\outputs"
}
```

### PUT /api/scan-roots/<index>

Aggiorna una root di scansione (cambia percorso, attiva/disattiva abilitato).

### DELETE /api/scan-roots/<index>

Elimina una root di scansione.

## Backfill hash

### POST /api/hash-backfill/start

Avvia il calcolo hash in background per i file esistenti.

### GET /api/hash-backfill/status

Recupera il progresso.

### POST /api/hash-backfill/cancel

Annulla il calcolo.

## Job in background

### GET /api/jobs/status

Stato di tutti i job in background. Utilizzato per la visualizzazione del banner dell'interfaccia utente.

```json
{
  "jobs": [
    {
      "type": "scan",
      "status": "running",
      "progress": 45,
      "total": 1500
    }
  ]
}
```
