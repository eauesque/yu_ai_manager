# API Tools

API di utilità per il rilevamento di duplicati, il calcolo dell'hash, la ricerca di immagini simili, la gestione della cache, la selezione delle cartelle, il backup del database, la pulizia dell'archivio e il debug logging.

---

## Duplicati / Hash / Scansione

### GET /api/tools/find-duplicates

Rilevare file duplicati in base all'hash del file o al nome del file.

#### Rate Limit

HEAVY

#### Parametri

| Parametro | Tipo | Predefinito | Descrizione |
|-----------|------|---------|-------------|
| `cross_directory` | string | `"false"` | Impostare su `"true"` per rilevare duplicati in directory diverse |
| `method` | string | `"hash"` | Metodo di rilevamento: `"hash"` o `"name"` |
| `threshold` | int | `5` | Soglia di somiglianza |

#### Risposta

```json
{
  "groups": [
    {
      "hash": "abc123...",
      "files": [
        { "id": 1, "path": "/images/photo.png", "filename": "photo.png" },
        { "id": 2, "path": "/backup/photo.png", "filename": "photo.png" }
      ]
    }
  ],
  "total_groups": 1,
  "total_duplicates": 2
}
```

### POST /api/tools/compute-hashes

Avvia il calcolo dell'hash in background per i file senza hash.

#### Rate Limit

HEAVY

#### Richiesta

```json
{
  "type": "both",
  "limit": 5000
}
```

| Parametro | Tipo | Predefinito | Descrizione |
|-----------|------|---------|-------------|
| `type` | string | `"both"` | Tipo di hash: `"md5"`, `"sha256"`, o `"both"` |
| `limit` | int | `5000` | Numero massimo di file da elaborare |

#### Risposta

```json
{
  "started": true,
  "type": "both",
  "limit": 5000
}
```

### POST /api/tools/delete-duplicates

Elimina i file specificati dai gruppi di duplicati.

#### Rate Limit

DESTRUCTIVE

#### Richiesta

```json
{
  "groups": [
    {
      "keep": 1,
      "delete": [2, 3]
    }
  ],
  "mode": "soft"
}
```

| Parametro | Tipo | Predefinito | Descrizione |
|-----------|------|---------|-------------|
| `groups` | array | Richiesto | Bersagli di eliminazione. `keep` = ID del file da mantenere, `delete` = array di ID dei file da rimuovere |
| `mode` | string | `"soft"` | `"soft"` = eliminazione logica, `"hard"` = eliminazione fisica |

#### Risposta

```json
{
  "deleted": 2,
  "errors": []
}
```

### GET /api/tools/normalize-tags

Normalizza i tag (unisci duplicati, taglia spazi bianchi, ecc.).

#### Parametri

| Parametro | Tipo | Predefinito | Descrizione |
|-----------|------|---------|-------------|
| `dry_run` | string | `"false"` | Impostare su `"true"` per visualizzare in anteprima i cambiamenti senza applicarli |

#### Risposta

```json
{
  "normalized": 15,
  "removed": 3,
  "dry_run": false
}
```

### GET /api/tools/find-similar

Trova immagini simili a un file specificato (basato su hash).

#### Rate Limit

HEAVY

#### Parametri

| Parametro | Tipo | Richiesto | Descrizione |
|-----------|------|----------|-------------|
| `file_id` | int | Sì | ID del file di riferimento |
| `threshold` | int | No | Soglia di somiglianza (1-20, predefinito `5`) |

#### Risposta

```json
{
  "file_id": 42,
  "threshold": 5,
  "results": [
    {
      "id": 43,
      "filename": "similar.png",
      "distance": 3
    }
  ],
  "count": 1
}
```

#### Errori

- `400` — `file_id` mancante o non valido
- `404` — File specificato non trovato

### POST /api/tools/scan

Scansiona i file in una directory e registrali nel database.

#### Rate Limit

HEAVY

#### Richiesta

```json
{
  "path": "/path/to/images",
  "recursive": true,
  "scan_zips": false,
  "compute_hash": false
}
```

| Parametro | Tipo | Predefinito | Descrizione |
|-----------|------|---------|-------------|
| `path` | string | Richiesto | Percorso della directory da scansionare |
| `recursive` | bool | `true` | Scansiona ricorsivamente le sottodirectory |
| `scan_zips` | bool | `false` | Scansiona anche dentro gli archivi ZIP |
| `compute_hash` | bool | `false` | Calcola gli hash dei file durante la scansione |

#### Risposta

```json
{
  "scanned": 150,
  "new": 42,
  "updated": 5,
  "errors": []
}
```

---

## Ricerca file / Ispezione metadati

### GET /api/tools/file-search

Ricerca file nel database per parola chiave.

#### Parametri

| Parametro | Tipo | Predefinito | Descrizione |
|-----------|------|---------|-------------|
| `q` / `query` | string | `""` | Parola chiave di ricerca |
| `meta` / `meta_filter` | string | `"all"` | Filtra per fonte dei metadati (`"all"`, `"a1111_png"`, `"novelai_v4_png"`, ecc.) |
| `limit` / `n` / `page_size` | int | `100` | Numero di risultati (1-500) |

#### Risposta

```json
{
  "results": [
    {
      "id": 1,
      "filename": "image.png",
      "path": "/images/image.png"
    }
  ],
  "count": 1
}
```

### POST /api/inspect

Ispeziona i metadati di un file caricato. Estrae i metadati senza registrare il file nel database.

#### Rate Limit

WRITE

#### Richiesta

`multipart/form-data`:

| Campo | Tipo | Richiesto | Descrizione |
|-------|------|----------|-------------|
| `file` | file | Sì | File da ispezionare |
| `zip_entry` | string | No | Percorso all'interno dell'archivio ZIP (per file ZIP) |

#### Risposta

```json
{
  "filename": "image.png",
  "meta_source": "novelai_v4_png",
  "positive": "1girl, landscape",
  "negative": "bad anatomy",
  "parameters": { ... }
}
```

#### Errori

- `400` — Nessun file caricato

---

## Selezione cartella / Elenco directory

### GET /api/tools/select-folder

Apri la finestra di dialogo del selezionatore di cartelle nativo del sistema operativo. **Disponibile solo da localhost.**

#### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `initial` / `path` / `dir` | string | Directory iniziale per la finestra di dialogo |

#### Risposta

```json
{
  "path": "C:\\Users\\user\\Pictures",
  "cancelled": false
}
```

Quando accesso remoto:

```json
{
  "path": null,
  "error": "remote_client_no_gui",
  "cancelled": false,
  "message": "Native folder dialog is not available for remote access. Please use the server folder browser."
}
```

### GET /api/tools/list-dirs

Elenca le directory sul server. **Disponibile solo da localhost.**

#### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `path` / `dir` / `initial` | string | Directory da elencare. Vuoto restituisce le directory root |

#### Risposta

```json
{
  "current": "C:\\Users",
  "parent": "C:\\",
  "dirs": ["user1", "Public"],
  "roots": ["C:\\", "D:\\"]
}
```

#### Errori

- `403` — Accesso remoto

---

## Gestione cache

### GET /api/tools/cache-info

Ottieni lo stato della cache delle miniature.

#### Risposta

```json
{
  "count": 1234,
  "size_mb": 56.7
}
```

### POST /api/tools/clear-cache

Cancella tutta la cache delle miniature.

#### Rate Limit

DESTRUCTIVE

#### Risposta

```json
{
  "cleared": 1234
}
```

### POST /api/tools/rebuild-groups

Forza la ricostruzione della cache dell'indice dei gruppi.

#### Rate Limit

DESTRUCTIVE

#### Risposta

```json
{
  "status": "rebuilt",
  "folders": 42,
  "zips": 5,
  "file_count": 1500
}
```

### POST /api/tools/faststart-prescan

Pre-genera la cache faststart per tutti i file MP4/MOV in background. Restituisce 202 immediatamente.

#### Rate Limit

WRITE

#### Risposta (202)

```json
{
  "ok": true,
  "started": true,
  "message": "faststart prescan started"
}
```

Quando già in esecuzione (200):

```json
{
  "ok": true,
  "started": false,
  "message": "already running"
}
```

---

## Impostazioni

### GET /api/settings/config

Ottieni la configurazione attuale unita ai valori predefiniti.

#### Risposta

```json
{
  "port": 5000,
  "pin": "",
  "scan_roots": [],
  "theme": "dark",
  "backup": {
    "enabled": true,
    "periodic_interval_hours": 24
  }
}
```

### POST /api/settings/config

Aggiorna parzialmente le impostazioni. Viene applicato l'unione profonda agli oggetti annidati esistenti.

#### Rate Limit

DESTRUCTIVE

#### Richiesta

```json
{
  "theme": "light",
  "backup": {
    "enabled": false
  }
}
```

#### Risposta

```json
{
  "status": "saved"
}
```

#### Errori

- `400` — Dati vuoti

---

## Backup / Ripristino del database

### GET /api/tools/backup-download

Scarica il file del database direttamente. **Disponibile solo da localhost.**

#### Risposta

- Content-Type: `application/x-sqlite3`
- Content-Disposition: `attachment; filename="tags_backup_20260322_120000.db"`
- Restituisce 404 se il database non è trovato

### POST /api/tools/restore

Ripristina il database caricando un file `.db`. **Disponibile solo da localhost.** Crea automaticamente un backup del database esistente prima del ripristino.

#### Rate Limit

WRITE

#### Richiesta

`multipart/form-data`:

| Campo | Tipo | Richiesto | Descrizione |
|-------|------|----------|-------------|
| `file` | file | Sì | File SQLite con estensione `.db` |

#### Convalidazione

- Verifica i byte magici SQLite
- Controlla la tabella `files`
- Rifiuta i database contenenti trigger o view

#### Risposta

```json
{
  "success": true,
  "message": "Database restored successfully",
  "backup": "tags.db.backup_1711100000"
}
```

#### Errori

- `400` — Nessun file caricato, estensione sbagliata, o SQLite non valido
- `403` — Accesso remoto
- `500` — Errore di backup o ripristino

### POST /api/tools/backup/create

Crea manualmente un backup gestito. **Disponibile solo da localhost.**

#### Rate Limit

DESTRUCTIVE

#### Risposta

```json
{
  "success": true,
  "filename": "tags_backup_20260322_120000.db",
  "reason": "manual"
}
```

### GET /api/tools/backup/list

Elenca i backup disponibili.

#### Risposta

```json
{
  "backups": [
    {
      "filename": "tags_backup_20260322_120000.db",
      "size": 1048576,
      "created": "2026-03-22T12:00:00"
    }
  ],
  "count": 1
}
```

### POST /api/tools/backup/restore

Ripristina il database da un backup denominato. **Disponibile solo da localhost.**

#### Rate Limit

DESTRUCTIVE

#### Richiesta

```json
{
  "filename": "tags_backup_20260322_120000.db"
}
```

| Parametro | Tipo | Richiesto | Descrizione |
|-----------|------|----------|-------------|
| `filename` | string | Sì | Nome file del backup da cui ripristinare |

#### Risposta

```json
{
  "success": true,
  "message": "Backup restored",
  "filename": "tags_backup_20260322_120000.db"
}
```

#### Errori

- `400` — Nome file mancante o backup non trovato
- `403` — Accesso remoto

### POST /api/tools/backup/delete

Elimina un backup specifico. **Disponibile solo da localhost.**

#### Rate Limit

DESTRUCTIVE

#### Richiesta

```json
{
  "filename": "tags_backup_20260322_120000.db"
}
```

| Parametro | Tipo | Richiesto | Descrizione |
|-----------|------|----------|-------------|
| `filename` | string | Sì | Nome file del backup da eliminare |

#### Risposta

```json
{
  "success": true,
  "deleted": "tags_backup_20260322_120000.db"
}
```

### GET /api/tools/backup/status

Ottieni lo stato del sistema di backup.

#### Risposta

```json
{
  "enabled": true,
  "backup_on_scan_complete": true,
  "periodic_interval_hours": 24,
  "max_generations": 5,
  "cooldown_minutes": 5,
  "scheduler_running": true,
  "last_backup_time": "2026-03-22T11:00:00",
  "within_cooldown": false
}
```

---

## Debug Log

### GET /api/tools/debug-log

Ottieni la coda del debug log. Restituisce `enabled: false` quando la modalità debug è disabilitata.

#### Parametri

| Parametro | Tipo | Predefinito | Descrizione |
|-----------|------|---------|-------------|
| `limit` | int | `200` | Numero di righe da recuperare (1-5000) |
| `filter` | string | `""` | Stringa filtro linea (corrispondenza substring) |

#### Risposta

```json
{
  "enabled": true,
  "lines": ["2026-03-22 12:00:00 [INFO] Server started", "..."],
  "total_lines": 5000,
  "log_path": "/path/to/debug.log",
  "log_size_kb": 128.5
}
```

### GET /api/tools/debug-log/download

Scarica il file di debug log. **Disponibile solo da localhost.**

#### Risposta

- Content-Type: `text/plain`
- Content-Disposition: `attachment; filename="debug.log"`

#### Errori

- `400` — Modalità debug non abilitata
- `403` — Accesso remoto
- `404` — File di log non trovato

### POST /api/tools/debug-log/clear

Cancella il debug log. **Disponibile solo da localhost.**

#### Rate Limit

WRITE

#### Risposta

```json
{
  "success": true,
  "message": "Log cleared"
}
```

#### Errori

- `400` — Modalità debug non abilitata
- `403` — Accesso remoto
- `404` — File di log non trovato

---

## Archive Cleanup

Strumenti per il rilevamento e la pulizia di archivi duplicati e delle loro cartelle estratte. Tutti gli endpoint sono **disponibili solo da localhost.**

### POST /api/tools/archive-cleanup/scan

Scansiona le coppie archivio-cartella.

#### Rate Limit

HEAVY

#### Richiesta

```json
{
  "path": "/path/to/check",
  "recursive": false
}
```

| Parametro | Tipo | Predefinito | Descrizione |
|-----------|------|---------|-------------|
| `path` | string | Richiesto | Directory da scansionare |
| `recursive` | bool | `false` | Scansiona ricorsivamente le sottodirectory |

#### Convalidazione del percorso

- I percorsi che iniziano con `~` sono rifiutati
- I percorsi contenenti `..` sono rifiutati

#### Risposta

```json
{
  "pairs": [
    {
      "archive_path": "/data/images.zip",
      "folder_path": "/data/images",
      "archive_size": 10485760,
      "folder_size": 12582912,
      "file_count": 42
    }
  ],
  "count": 1
}
```

### POST /api/tools/archive-cleanup/execute

Esegui azioni di pulizia sulle coppie scansionate.

#### Rate Limit

DESTRUCTIVE

#### Richiesta

```json
{
  "actions": [
    { "action": "delete_archive", "archive_path": "/data/images.zip" },
    { "action": "delete_folder", "folder_path": "/data/images" },
    { "action": "skip" }
  ]
}
```

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `actions` | array | Array di azioni |
| `actions[].action` | string | Uno di `"delete_archive"`, `"delete_folder"`, `"skip"` |
| `actions[].archive_path` | string | Richiesto quando l'azione è `delete_archive` |
| `actions[].folder_path` | string | Richiesto quando l'azione è `delete_folder` |

#### Risposta

```json
{
  "results": [
    { "action": "delete_archive", "success": true },
    { "action": "delete_folder", "success": true },
    { "action": "skip", "success": true }
  ]
}
```

### POST /api/tools/archive-cleanup/llm-verify

Verifica l'identità della coppia archivio-cartella usando LLM (singola coppia).

#### Rate Limit

HEAVY

#### Richiesta

```json
{
  "archive_path": "/data/images.zip",
  "folder_path": "/data/images",
  "pair_info": {
    "archive_size": 10485760,
    "folder_size": 12582912
  }
}
```

| Parametro | Tipo | Richiesto | Descrizione |
|-----------|------|----------|-------------|
| `archive_path` | string | Sì | Percorso del file archivio |
| `folder_path` | string | Sì | Percorso della cartella estratta |
| `pair_info` | object | No | Metadati della coppia aggiuntivi |

#### Risposta

```json
{
  "verdict": "same",
  "confidence": 0.95,
  "reasoning": "File counts and sizes match exactly."
}
```

### POST /api/tools/archive-cleanup/llm-verify-batch

Verifica in batch più coppie usando LLM. Massimo 50 coppie.

#### Rate Limit

HEAVY

#### Richiesta

```json
{
  "pairs": [
    {
      "archive_path": "/data/a.zip",
      "folder_path": "/data/a",
      "pair_info": {}
    }
  ]
}
```

| Parametro | Tipo | Limite | Descrizione |
|-----------|------|-------|-------------|
| `pairs` | array | Max 50 | Array di coppie da verificare |

#### Risposta

```json
{
  "results": [
    { "result": { "verdict": "same", "confidence": 0.95, "reasoning": "..." } }
  ]
}
```

### GET /api/tools/archive-cleanup/llm-config

Ottieni la configurazione LLM di archive cleanup.

#### Risposta

```json
{
  "engine": "ollama",
  "base_url": "http://localhost:11434",
  "model": "llama3",
  "api_key": ""
}
```

### POST /api/tools/archive-cleanup/llm-config

Salva la configurazione LLM di archive cleanup.

#### Rate Limit

WRITE

#### Richiesta

```json
{
  "engine": "ollama",
  "base_url": "http://localhost:11434",
  "model": "llama3"
}
```

#### Risposta

```json
{
  "success": true
}
```

### POST /api/tools/archive-cleanup/list-models

Elenca i modelli disponibili per il motore specificato.

#### Richiesta

```json
{
  "engine": "ollama",
  "base_url": "http://localhost:11434"
}
```

| Parametro | Tipo | Richiesto | Descrizione |
|-----------|------|----------|-------------|
| `engine` | string | Sì | `"ollama"` o `"openai_compat"` |
| `base_url` | string | Sì | URL API del motore |
| `api_key` | string | No | Chiave API per `openai_compat` |

#### Risposta

```json
{
  "models": ["llama3", "mistral", "codellama"]
}
```

#### Errori

- `400` — Motore non valido o `base_url` mancante
