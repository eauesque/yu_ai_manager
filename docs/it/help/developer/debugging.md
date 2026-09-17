# Manuale di Debug

Manuale completo per il debug di YU AI Manager. Guida per sviluppatori e agenti AI per investigare e correggere bug in modo efficiente.

---

## Indice

1. [Avvio del Server](#avvio-del-server)
2. [Log di Debug](#log-di-debug)
3. [Esecuzione Test](#esecuzione-test)
4. [Debug DB](#debug-db)
5. [Bypass e Test Autenticazione](#bypass-e-test-autenticazione)
6. [Debug MCP](#debug-mcp)
7. [Debug Frontend](#debug-frontend)
8. [Elenco Variabili d'Ambiente](#elenco-variabili-dampiente)
9. [Errori Comuni e Soluzioni](#errori-comuni-e-soluzioni)
10. [Debug Prestazioni](#debug-prestazioni)

---

## Avvio del Server

### Per Verifica (Consigliato)

Avvia senza PIN e in binding locale. La forma base per test e debug.

```bash
source venv/Scripts/activate  # Windows Git Bash
python web_ui.py --db ./tags.db --config config_test.json --port 5100
```

Se `config_test.json` non esiste, crearlo con:

```json
{
  "scan_roots": [],
  "server": {
    "host": "127.0.0.1",
    "port": 5100,
    "lan": false
  },
  "extract_a1111": true,
  "extract_comfyui": true,
  "lowercase_tags": true,
  "compute_hash": false,
  "enable_fts": true,
  "extensions": {}
}
```

### Equivalente Produzione (Accesso LAN)

```bash
python web_ui.py --db ./tags.db --host 0.0.0.0 --port 5000 --pin 1234
```

> **Nota**: Con binding `0.0.0.0` il PIN è obbligatorio. Dalla v4.8.1 il flag `--debug` viene ignorato con accesso LAN (prevenzione leak stack trace).

### Regola Selezione Porte

5100 → 5200 → 5300 → incrementi di 100. Verificare prima dell'avvio:

```bash
# Windows
netstat -ano | grep :5100

# Linux/macOS
ss -tlnp | grep :5100
```

### Opzioni CLI

| Opzione | Tipo | Default | Descrizione |
|---------|------|---------|-------------|
| `--db` | path | `data/tags.db` | Percorso file SQLite DB |
| `--config` | path | `config.json` | Percorso file configurazione |
| `--host` | str | `127.0.0.1` | Indirizzo di binding |
| `--port` | int | 5000 | Porta di binding |
| `--lan` | flag | - | Binding `0.0.0.0` (accesso LAN) |
| `--pin` | str | - | Abilitazione autenticazione PIN |
| `--debug` | flag | - | Abilitazione modalità debug Quart |
| `--debug-log` | `on`/`off` | - | Abilitazione/disabilitazione log debug strutturati |
| `--debug-log-file` | path | `logs/debug.log` | Destinazione file log |
| `--debug-log-max-mb` | int | 10 | Dimensione rotazione file log (MB) |
| `--debug-log-backups` | int | 5 | Numero generazioni backup log |
| `--debug-log-stdout` | `on`/`off` | `on` | Output log anche su stderr |
| `--allow-restart` | flag | - | Abilitazione `/api/server/restart` |
| `--trusted-proxy-auth` | flag | - | Abilitazione autenticazione Trusted Proxy |
| `--profile` | str | - | Nome profilo di avvio |

---

## Log di Debug

### Abilitazione

```bash
# Abilitazione da CLI
python web_ui.py --db ./tags.db --debug-log on

# Abilitazione tramite variabile d'ambiente
export TAGDB_DEBUG=1
python web_ui.py --db ./tags.db
```

### Formato Log

Log di debug strutturati (funzione `dlog()` in `core/infra_core/debug_log.py`):

```
[DEBUG] 2026-03-15 12:34:56 | scan:prepare | counting_start | root=/path/to/dir, recursive=True
```

Formato: `[DEBUG] timestamp | sorgente | nome_evento | key=value, ...`

### Monitoraggio in Tempo Reale

```bash
# Tail del file
tail -f logs/debug.log

# Recupero via API
curl http://127.0.0.1:5100/api/debug/logs

# Streaming SSE
curl -N "http://127.0.0.1:5100/api/debug/logs?stream=1"
```

---

## Esecuzione Test

### Unit Test

```bash
source venv/Scripts/activate

# Esecuzione tutti i test
python -m pytest tests/test_basic.py -v

# Solo test specifici
python -m pytest tests/test_basic.py::TestImports -v

# Fermati al primo fallimento
python -m pytest tests/test_basic.py -x
```

### Test di Integrazione API

```bash
python -m pytest tests/api/ -v
```

### Test Browser Playwright

```bash
# 1. Avviare il server di verifica
python web_ui.py --db ./tags.db --config config_test.json --port 5100 &

# 2. Eseguire i test
TARGET_URL=http://localhost:5100 python -m pytest tests/test_webui_browser.py -v
```

---

## Debug DB

### Verifica Versione Schema

```bash
python -c "
import sqlite3
con = sqlite3.connect('data/tags.db')
v = con.execute('SELECT MAX(version) FROM schema_version').fetchone()[0]
print(f'Schema version: {v}')
"
```

### Controllo Integrità DB

```bash
python db_health.py --db ./tags.db
```

### Separazione Connessioni DB

| Funzione | Utilizzo | Quando Usarla |
|----------|----------|---------------|
| `get_readonly_db()` | Solo lettura | GET API, ricerca, riferimento thumbnail, statistiche |
| `get_db()` | Scrittura (con Row factory) | POST/PUT/DELETE API |
| `get_raw_db()` | Scrittura (senza Row factory) | Elaborazione batch, scansione, migrazione |

> **Importante**: Usare `get_db()` in API di sola lettura causa conflitti di write lock durante la scansione. Usare sempre `get_readonly_db()`.

---

## Bypass e Test Autenticazione

### Skip Autenticazione PIN

Avviando con `config_test.json` (senza PIN impostato) si salta tutta l'autenticazione.

### Test API Key

```bash
# Richiesta API con Bearer token (header CSRF non necessario)
curl -H "Authorization: Bearer sk_xxxxxxxxxxxxxx" \
  http://127.0.0.1:5000/api/stats/all
```

### Scope API Key

Dalla v4.8.1, le key senza scope permettono **solo lettura**. Le operazioni di scrittura richiedono key con scope espliciti.

| Scope | Operazioni Permesse |
|-------|---------------------|
| `read` | Ricerca, dettagli file, thumbnail, statistiche |
| `rate` | Impostazione/recupero/batch rating |
| `tag.write` | Aggiunta/rimozione tag |
| `collection.write` | CRUD collezioni, preferiti |
| `annotate` | Lettura/scrittura annotazioni |
| `scan` | Avvio/interruzione/ripresa scansione |
| `admin` | Gestione API Key, modifica impostazioni, backup/ripristino |

---

## Debug MCP

### Avvio Server MCP

```bash
source venv/Scripts/activate
python -m mcp_server
```

### Abilitazione Strumenti di Debug

```bash
export YU_DEBUG_MODE=1
export YU_BASE_URL=http://127.0.0.1:5100
export YU_API_KEY=sk_...
python -m mcp_server
```

### Configurazione Claude Desktop

`claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "yu-ai-manager": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "<radice progetto>",
      "env": {
        "YU_API_KEY": "sk_...",
        "YU_BASE_URL": "http://127.0.0.1:5000",
        "YU_DEBUG_MODE": "1"
      }
    }
  }
}
```

### Strumenti di Debug MCP

Con `YU_DEBUG_MODE=1` vengono registrati 9 strumenti di debug aggiuntivi:

| Strumento | Utilizzo |
|-----------|----------|
| `debug_health_check` | Verifica sopravvivenza server, DB, tabelle |
| `debug_validate_counts` | Confronto statistiche API e conteggi reali DB |
| `debug_validate_search` | Verifica regressione API di ricerca |
| `debug_validate_collection` | Coerenza interna conteggi collezione |
| `debug_validate_annotations` | Coerenza tabella annotazioni |
| `debug_sample_files` | Analisi campi con campionamento casuale |
| `debug_roundtrip_test` | Test di andata e ritorno annotation/rating/tag |
| `debug_readonly_query` | Esecuzione query SELECT arbitrarie |
| `debug_full_report` | Report integrato di tutti gli strumenti di osservazione (1-5) |

---

## Debug Frontend

### Build TypeScript

```bash
pnpm run build        # Bundle con esbuild
pnpm run typecheck    # Solo controllo tipi con tsc --noEmit
```

Output: `ui/default/static/dist/`

### Interceptor CSRF

`src/ts/nav/csrf-fetch.ts` wrappa il `fetch` globale con un Proxy e inietta automaticamente l'header `X-Requested-With` in tutte le richieste POST/PUT/DELETE.

### Motore SSE Condiviso

`window.EventSource` è sovrascritto da un Proxy, quindi chiamare direttamente `new EventSource()` genera un errore.

```javascript
// Utilizzo corretto
window.sseSubscribe('scan.progress', (d) => console.log(d.data));

// Errato (errore runtime)
// new EventSource('/api/events/...')
```

### Debug i18n

```javascript
// Cambio lingua
window.setLang('en');

// Verifica chiave traduzione
console.log(window.tr('search.count.normal', { count: 5 }));
```

---

## Elenco Variabili d'Ambiente

### Debug e Log

| Variabile | Valori | Default | Descrizione |
|-----------|--------|---------|-------------|
| `TAGDB_DEBUG` | `1`/`0` | `0` | Abilitazione/disabilitazione log debug strutturati |
| `TAGDB_DEBUG_LOG` | path | `logs/debug.log` | Percorso file log |
| `TAGDB_DEBUG_LOG_MAX_MB` | int | `10` | Dimensione rotazione log (MB) |
| `TAGDB_DEBUG_LOG_BACKUPS` | int | `5` | Numero generazioni backup |
| `TAGDB_DEBUG_STDOUT` | `1`/`0` | `1` | Output log su stderr |

### Server

| Variabile | Valori | Descrizione |
|-----------|--------|-------------|
| `TAGDB_DB` | path | Percorso file DB |
| `TAGDB_CONFIG` | path | Percorso config.json |
| `TAGDB_PROFILE` | str | Nome profilo di avvio |
| `TAGDB_ALLOW_RESTART` | `1`/`0` | Abilitazione API di riavvio |

### MCP

| Variabile | Valori | Descrizione |
|-----------|--------|-------------|
| `YU_DEBUG_MODE` | `1` | Registrazione 9 strumenti di debug aggiuntivi |
| `YU_BASE_URL` | URL | BASE URL per client MCP |
| `YU_API_KEY` | `sk_...` | API Key per client MCP |

---

## Errori Comuni e Soluzioni

### Avvio Server

| Errore | Causa | Soluzione |
|--------|-------|-----------|
| `Address already in use` | Porta occupata | Specificare porta diversa con `--port 5200` |
| `database is locked` | Conflitto lock DB | Verificare che il DB non sia su percorso di rete |
| `--pin is required` | PIN non impostato con binding LAN | Impostare con `--pin <digit>` |
| `ModuleNotFoundError` | venv non attivato o pacchetti mancanti | `source venv/Scripts/activate && uv pip install -r requirements.txt` |

### Autenticazione

| Errore | Causa | Soluzione |
|--------|-------|-----------|
| Schermata PIN si ripete | Errore impostazione Cookie | Verificare Cookie del browser (DevTools → Application) |
| `CSRF header missing` (403) | Header `X-Requested-With` mancante | Aggiungere `-H "X-Requested-With: XMLHttpRequest"` alla fetch |
| API Key rifiutata | Scope insufficiente | Dalla v4.8.1, le key senza scope sono solo lettura. Assegnare lo scope necessario |

### DB

| Errore | Causa | Soluzione |
|--------|-------|-----------|
| `no such table: schema_version` | Primo avvio | Viene generato automaticamente, ignorare |
| Fallimento migrazione | Bug script | Verificare integrità con `db_health.py` → correzione manuale |
| `SQLITE_BUSY` (timeout) | Transazione di lunga durata | Verificare che le API di lettura non usino `get_db()` |

### Windows Specifici

| Errore | Causa | Soluzione |
|--------|-------|-----------|
| `UnicodeEncodeError` (in print) | em dash ecc. non stampabili con cp932 | Usare solo caratteri ASCII |
| `pkill` non funziona | Limitazione Git Bash | `tasklist \| grep python` → `taskkill //F //PID <pid>` |
| Fallimento `os.replace()` | File handle aperto | Chiudere il processo e riprovare |

---

## Debug Prestazioni

### Blocco del Viewer Durante la Scansione

**Sintomo**: La visualizzazione immagini si blocca per 5-10 secondi durante la scansione

**Causa**: Le API di lettura usavano `get_db()` (connessione scrivibile)

**Soluzione**: Usare sempre `get_readonly_db()` per le API di sola lettura

### Verifica Rate Limit

Sistema a bucket token con 3 tier:

| Tier | Target | Limite |
|------|--------|--------|
| **HEAVY** | Ricerca simile, calcolo hash, analisi AI, scansione | ~20 req/min (burst 5) |
| **DESTRUCTIVE** | purge, hard-delete, cache clear, scrittura config | ~12 req/min (burst 3) |
| **WRITE** | Altri POST/PUT/DELETE | ~120 req/min (burst 30) |
| GET | Lettura | Illimitato |

In caso di risposta 429, verificare l'header `Retry-After`.

---

## Documenti Correlati

| Documento | Posizione |
|-----------|-----------|
| Separazione lettura/scrittura DB | `docs/development/development_docs/SQLITE_READONLY_SEPARATION.md` |
| Gestione errori unificata | `docs/development/development_docs/ERROR_HANDLING.md` |
| Cross-platform | `docs/development/development_docs/CROSS_PLATFORM_ISSUES.md` |
| Specifiche strumenti debug MCP | `docs/development/development_docs/MCP_DEBUG_TOOLS.md` |
| QA handoff | `docs/development/development_docs/QA_HANDOFF.md` |
