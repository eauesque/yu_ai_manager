# Riferimento API YU AI Manager

Questa documentazione REST API copre ogni funzionalità di YU AI Manager, disponibile per interfacce utente personalizzate e script.

## Convenzioni comuni

### URL base

```
http://<host>:<port>
```

Predefinito: `http://127.0.0.1:5000`
Ambiente di test: `http://127.0.0.1:5100` (quando si usa `config_test.json`)

### Autenticazione

Sono supportati quattro metodi di autenticazione:

| Metodo | Caso d'uso | Esempio di intestazione |
|--------|----------|------------|
| PIN Auth | Sessioni del browser | Cookie: `session=...` |
| API Key | Comunicazione machine-to-machine | `Authorization: Bearer sk_...` |
| Trusted Proxy | Dietro un reverse proxy | `X-Remote-User: username` |
| LAN Share Token | Accesso ospite | Percorso URL `/s/<token>/...` |

È possibile saltare completamente l'autenticazione lanciando con `config_test.json` (nessun PIN).

### Protezione CSRF

Tutte le richieste `POST` / `PUT` / `DELETE` agli endpoint `/api/` richiedono l'intestazione `X-Requested-With`:

```
X-Requested-With: XMLHttpRequest
```

**Eccezione**: Le richieste API Key con l'intestazione `Authorization: Bearer` non richiedono CSRF.

### Limitazione della velocità

| Livello | Scope | Velocità | Burst |
|---------|-------|----------|-------|
| READ | Tutti i GET | Illimitato | - |
| WRITE | POST/PUT/DELETE (standard) | ~120 req/min | 30 |
| HEAVY | Ricerca simile, calcolo hash, analisi AI, scansione | ~20 req/min | 5 |
| DESTRUCTIVE | Purge, hard-delete, cache clear, config write | ~12 req/min | 3 |

Un'intestazione `Retry-After` accompagna le risposte 429.

### Formato della risposta

**Successo** (nuove API):
```json
{
  "ok": true,
  "error": null,
  "data": { ... }
}
```

**Errore**:
```json
{
  "ok": false,
  "error": "Error message",
  "code": "ERROR_CODE",
  "detail": "Additional details (optional)"
}
```

Alcune API legacy restituiscono il formato `{ "success": true, "message": "..." }`.

### Paginazione

**Basata su offset** (predefinita):
```
GET /api/search?offset=0&limit=50
```

**Basata su cursore** (per grandi set di dati):
```
GET /api/search?cursor=<opaque_token>&limit=50
```

La risposta include un campo `next_cursor`.

### Operazioni batch

Le API batch supportano fino a 500 operazioni per richiesta. È possibile un successo parziale:

```json
POST /api/ratings/batch-set
{
  "items": [
    { "file_id": 1, "rating": 5 },
    { "file_id": 999, "rating": 3 }
  ]
}
```

## Categorie API

| Documento | Contenuto |
|----------|----------|
| [search.md](search.md) | Ricerca, suggerimenti, gruppi |
| [files.md](files.md) | Dettagli del file, miniature, recupero media |
| [scan.md](scan.md) | Controllo scansione, gestione root scansione |
| [events.md](events.md) | Flusso evento SSE |
| [theming.md](theming.md) | Variabili CSS, personalizzazione tema |
| [source.md](source.md) | Esplorazione codice sorgente (sola lettura per MCP) |
| [github.md](github.md) | Integrazione GitHub (account, issue, PR, notifiche, discussioni, release) |
| [scheduler.md](scheduler.md) | Pianificatore attività (gestione job, cronologia esecuzione) |
| [ratings.md](ratings.md) | Valutazioni (set, batch-set, get, statistiche) |
| [favorites.md](favorites.md) | Preferiti (attiva/disattiva, controlla, elenco) |
| [collections.md](collections.md) | Raccolte (CRUD, riordina, batch aggiungi/rimuovi, esportazione CSV) |
| [tags.md](tags.md) | Tag (batch-set, suggerisci) |
| [sns.md](sns.md) | SNS Share & Bluesky Monitor (posting, notifiche, triage, auto-response) |
| [hailo-remote-tagger.md](hailo-remote-tagger.md) | Hailo Remote Tagger (config, tagging singolo/batch, CRUD tag) |
| [tagger-servers.md](tagger-servers.md) | Registro Tagger Server (cluster di inferenza tag distribuito, gestione server, esecuzione batch) |
| [svg.md](svg.md) | Rasterizzazione SVG (conversione SVG a PNG/WebP, supporto pipeline img2img) |
| [settings.md](settings.md) | Gestione impostazioni (schema, get/update valori, crittografia secret, integrazione 1Password/Bitwarden) |
| [extensions.md](extensions.md) | Estensioni (elenco, attiva/disattiva, config, installazione, sicurezza, marketplace, authoring) |
| [analysis.md](analysis.md) | Analisi AI (config, analisi singolo/batch, analisi trend, statistiche, registro server) |
| [system-update.md](system-update.md) | Aggiornamento sistema (verifica versione, applica aggiornamento, gestore aggiornamento unificato) |
| [tools.md](tools.md) | Strumenti (rilevamento duplicati, calcolo hash, ricerca simile, gestione cache, backup, pulizia archivio, debug log) |
| [agent.md](agent.md) | Agent Safety Gateway (Kill Switch, Circuit Breaker, Budget, Approval, Scope Fence, Undo, Anomaly Detection) |
| [profiles.md](profiles.md) | Gestione profili (CRUD, duplica, esportazione/importazione QR) |
| [wd-tagger.md](wd-tagger.md) | WD-Tagger (auto-tagging Danbooru, gestione modello, VLM, XMP) |
| [ocr.md](ocr.md) | OCR (riconoscimento testo, traduzione, supporto video/PDF, benchmark, profili) |
| [apikeys.md](apikeys.md) | Gestione API Key (crea, elenco, scopi, revoca) |
| [debug.md](debug.md) | Debug (ispezione metadati, query SQL, verifica modello) |
| [ui.md](ui.md) | Gestione UI (elenco, switch, installazione, disinstallazione) |
| [video-analysis.md](video-analysis.md) | Analisi video (config, stato, estrazione keyframe) |

## Quick Start (curl)

```bash
# Ricerca (ambiente senza PIN)
curl "http://localhost:5100/api/search?q=landscape&limit=10"

# Recupera una miniatura
curl "http://localhost:5100/api/thumbnail/42" -o thumb.webp

# Ricerca con API Key
curl -H "Authorization: Bearer sk_your_key_here" \
     "http://localhost:5100/api/search?q=portrait"

# Imposta una valutazione
curl -X POST "http://localhost:5100/api/ratings/set" \
     -H "X-Requested-With: XMLHttpRequest" \
     -H "Content-Type: application/json" \
     -d '{"file_id": 42, "rating": 5}'
```
