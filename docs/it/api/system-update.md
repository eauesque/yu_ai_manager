# API Aggiornamento di Sistema

API per verificare le nuove versioni su GitHub e applicare gli aggiornamenti dell'applicazione.
Rileva automaticamente il tipo di installazione (git / tauri / docker / portable) e fornisce il metodo di aggiornamento appropriato.

## GET /api/system/update/check

Verifica se una nuova versione è disponibile sul repository GitHub.

- **Limite di velocità**: Nessuno (GET)
- **Autenticazione**: Sessione PIN o chiave API

### Risposta

```json
{
  "current": "4.21.0",
  "latest": "4.22.0",
  "update_available": true,
  "release_url": "https://github.com/...",
  "release_notes": "## What's New\n...",
  "published_at": "2026-03-20T12:00:00Z",
  "install_type": "git",
  "docker_command": null,
  "portable_download_url": null
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `current` | string | Versione attuale |
| `latest` | string | Ultima versione su GitHub |
| `update_available` | bool | Se una nuova versione è disponibile |
| `release_url` | string | URL della pagina Release su GitHub |
| `release_notes` | string | Note di rilascio (Markdown) |
| `published_at` | string | Data di pubblicazione della release (ISO 8601) |
| `install_type` | string | Tipo di installazione (`"git"`, `"tauri"`, `"docker"`, `"portable"`) |
| `docker_command` | string \| null | Solo Docker: comando per aggiornare |
| `portable_download_url` | string \| null | Solo Portable: URL di download |

---

## GET /api/system/update/status

Ottieni il tipo di installazione attuale e le informazioni sulla versione.

- **Limite di velocità**: Nessuno (GET)
- **Autenticazione**: Sessione PIN o chiave API

### Risposta

```json
{
  "version": "4.21.0",
  "install_type": "git",
  "update_in_progress": false
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `version` | string | Versione attuale |
| `install_type` | string | Tipo di installazione (`"git"` \| `"tauri"` \| `"docker"` \| `"portable"`) |
| `update_in_progress` | bool | Se un aggiornamento è attualmente in corso |

---

## POST /api/system/update/apply

Applica un aggiornamento disponibile. Supportato solo per installazioni con clonaggio git e portable.

- **Limite di velocità**: DESTRUCTIVE
- **Autenticazione**: Sessione PIN (localhost) o token di riavvio
- **CSRF**: Intestazione `X-Requested-With: XMLHttpRequest` richiesta

### Corpo della Richiesta

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|----------|-------------|
| `confirm` | string | Yes | Stringa di conferma. Deve essere `"update"` |

### Esempio di Richiesta

```json
{
  "confirm": "update"
}
```

### Risposta

```json
{
  "ok": true,
  "message": "Update started"
}
```

### Eventi SSE

Durante l'aggiornamento, gli eventi `update.progress` vengono forniti tramite SSE.

```
event: update.progress
data: {"step": "backup", "status": "running", "detail": "Creating backup..."}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `step` | string | Passaggio di progresso (vedi sotto) |
| `status` | string | `"running"` \| `"done"` \| `"error"` |
| `detail` | string | Dettagli del passaggio |

#### Riferimento Passaggi

| Passaggio | Descrizione |
|------|-------------|
| `backup` | Creazione di un backup |
| `fetch` | Esecuzione di git fetch |
| `pull` | Esecuzione di git pull |
| `download` | Download dei file (portable) |
| `extract` | Estrazione dell'archivio (portable) |
| `replace` | Sostituzione dei file (portable) |
| `pip_install` | Installazione delle dipendenze Python |
| `ts_build` | Creazione di TypeScript |
| `complete` | Aggiornamento completo |

### Risposte di Errore

**Installazioni Docker** (400):
```json
{
  "ok": false,
  "error": "Docker installs cannot be updated from the web UI. Pull the latest image instead.",
  "code": "DOCKER_UPDATE_NOT_SUPPORTED"
}
```

**Installazioni Tauri** (400):
```json
{
  "ok": false,
  "error": "Tauri updates are handled by the desktop app's built-in updater.",
  "code": "TAURI_UPDATE_NOT_SUPPORTED"
}
```

---

## Note

- Le installazioni Docker non possono utilizzare `/api/system/update/apply`. Utilizza `docker pull` per ottenere l'ultima immagine
- Gli aggiornamenti dell'app desktop Tauri vengono gestiti dall'updater integrato dell'app
- Solo le installazioni git e portable supportano l'aggiornamento tramite l'interfaccia Web
- Un riavvio del server può verificarsi durante il processo di aggiornamento

---

## GET /api/system/update/unified-check

Verifica lo stato di aggiornamento per il sistema e tutte le estensioni contemporaneamente.

- **Limite di velocità**: Nessuno (GET)
- **Autenticazione**: Sessione PIN o chiave API

### Parametri di Query

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `force` | string | `"1"` per bypassare la cache e ri-verificare |

### Risposta

```json
{
  "system": {
    "current": "4.22.0",
    "latest": "4.23.0",
    "update_available": true,
    "install_type": "git"
  },
  "extensions": [
    {
      "name": "builtin-backup",
      "version": "1.0.0",
      "source": "builtin",
      "status": "builtin",
      "enabled": true,
      "description": "..."
    },
    {
      "name": "my-custom-ext",
      "version": "0.3.0",
      "source": "git",
      "status": "update_available",
      "enabled": true,
      "description": "...",
      "local_head": "abc12345",
      "remote_head": "def67890",
      "commits_behind": 3
    }
  ],
  "summary": {
    "total": 45,
    "up_to_date": 1,
    "update_available": 1,
    "unknown": 0,
    "builtin": 43
  }
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `system` | object | Info di aggiornamento del sistema (stesso formato di `check_for_update`) |
| `extensions` | array | Stato di aggiornamento per-estensione |
| `extensions[].status` | string | `"up_to_date"` \| `"update_available"` \| `"unknown"` \| `"builtin"` |
| `extensions[].source` | string | `"builtin"` \| `"git"` \| `"local"` |
| `extensions[].commits_behind` | int | Numero di commit dietro il remote (quando l'aggiornamento è disponibile) |
| `summary` | object | Ripartizione del conteggio per categoria |

---

## POST /api/system/update/unified-apply

Applica gli aggiornamenti per il sistema e/o le estensioni in un'unica operazione. I file di configurazione delle estensioni vengono automaticamente sottoposti a backup prima dell'aggiornamento.

- **Limite di velocità**: DESTRUCTIVE
- **Autenticazione**: Sessione PIN (localhost) o token di riavvio
- **CSRF**: Intestazione `X-Requested-With: XMLHttpRequest` richiesta

### Corpo della Richiesta

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|----------|-------------|
| `update_system` | bool | No | Aggiorna il sistema (predefinito: true) |
| `update_extensions` | bool | No | Aggiorna le estensioni (predefinito: true) |
| `extension_names` | array | No | Elenco dei nomi delle estensioni da aggiornare (omettere per tutte le estensioni git) |

### Esempio di Richiesta

```json
{
  "update_system": true,
  "update_extensions": true,
  "extension_names": ["my-custom-ext"]
}
```

### Risposta

```json
{
  "ok": true,
  "accepted": true,
  "message": "Unified update started. Progress via SSE (update.progress).",
  "update_system": true,
  "update_extensions": true
}
```

### Eventi SSE

Durante gli aggiornamenti unificati, gli eventi `update.progress` includono il flag `"unified": true`.

```
event: update.progress
data: {"step": "ext_config_backup", "status": "done", "detail": "...", "unified": true}
event: update.progress
data: {"step": "ext_update_my-custom-ext", "status": "running", "detail": "(1/1)", "unified": true}
```

#### Passaggi Aggiuntivi

| Passaggio | Descrizione |
|------|-------------|
| `ext_config_backup` | Backup della configurazione dell'estensione |
| `ext_update_<name>` | Aggiornamento della singola estensione |

---

## Integrazione MCP

Gestisci gli aggiornamenti del sistema da Claude Desktop.

```
# Passaggio 1: Verifica la nuova versione
check_for_update()

# Passaggio 2: Verifica lo stato dell'aggiornamento
get_update_status()

# Passaggio 3: Applica l'aggiornamento (solo git/portable)
apply_system_update(confirm="update")

# Verifica unificata: sistema + tutte le estensioni
check_unified_updates()

# Applicazione unificata: aggiorna il sistema + le estensioni contemporaneamente
apply_unified_updates(update_system=True, update_extensions=True)
```

### Strumenti MCP

| Strumento | Descrizione |
|------|-------------|
| `check_for_update` | Verifica se una nuova versione è disponibile su GitHub |
| `get_update_status` | Ottieni il tipo di installazione attuale e la versione |
| `apply_system_update` | Applica l'aggiornamento disponibile (solo git/portable) |
| `check_unified_updates` | Verifica lo stato di aggiornamento per il sistema + tutte le estensioni |
| `apply_unified_updates` | Aggiorna il sistema + le estensioni contemporaneamente (backup automatico delle configurazioni) |
