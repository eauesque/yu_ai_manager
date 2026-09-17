# Panoramica API

YU AI Manager fornisce una REST API, con cui è possibile eseguire programmaticamente tutte le operazioni dell'interfaccia WebUI. Offre oltre 320 endpoint, coprendo una vasta gamma di operazioni dalla gestione immagini all'analisi AI.

> **Suggerimento**: Per le convenzioni comuni in dettaglio (autenticazione, CSRF, rate limit, formato risposte) consultare la sezione "Riferimento API".

## Autenticazione

Sono supportati 4 metodi di autenticazione.

| Metodo | Utilizzo | Header/Parametro |
|--------|----------|-----------------|
| Autenticazione PIN | Sessione browser | Login su `/_pin` → cookie di sessione |
| API Key | Comunicazione machine-to-machine, MCP | `Authorization: Bearer sk_xxxx` |
| Trusted Proxy | Reverse proxy | Header `X-Remote-User` |
| Token LAN Share | Accesso guest | Percorso `/s/<token>` |

### Esempi di Test con curl

```bash
# Autenticazione API Key (header CSRF non necessario)
curl -H "Authorization: Bearer sk_your_key" \
     http://localhost:5000/api/search?tags=1girl

# Per ambiente con autenticazione PIN sono necessari 2 passaggi
# 1. Ottenere token CSRF
curl -c cookies.txt http://localhost:5000/_pin
# 2. Invio PIN
curl -b cookies.txt -X POST \
     -H "X-Requested-With: XMLHttpRequest" \
     -d "pin=1234" http://localhost:5000/_pin_check
```

### Protezione CSRF

L'header `X-Requested-With` è obbligatorio per tutti gli endpoint `/api/` con POST/PUT/DELETE.
Non è richiesto per le richieste con Bearer API Key.

## Endpoint Principali

### Ricerca e Navigazione Immagini

| Metodo | Percorso | Descrizione |
|--------|----------|-------------|
| GET | `/api/search` | Ricerca con filtri per tag, data, rating ecc. |
| GET | `/api/search-grouped` | Ricerca raggruppata per cartella/ZIP |
| GET | `/api/file/<id>` | Recupero metadati dettagliati dell'immagine |
| GET | `/api/thumbnail/<id>` | Recupero thumbnail (WebP, cache ETag) |
| GET | `/api/original/<id>` | Recupero immagine originale (supporto Range request) |
| GET | `/api/suggest` | Suggerimenti autocompletamento tag |

### Rating, Tag e Annotazioni

| Metodo | Percorso | Descrizione |
|--------|----------|-------------|
| POST | `/api/ratings/batch-set` | Impostazione batch rating |
| POST | `/api/tags/batch-set` | Modifica batch tag |
| POST | `/api/annotations/batch-set` | Impostazione batch annotazioni |
| GET | `/api/annotations/<id>` | Recupero annotazioni |
| GET | `/api/annotations/search` | Ricerca annotazioni |

### Collezioni

| Metodo | Percorso | Descrizione |
|--------|----------|-------------|
| GET | `/api/collections` | Lista collezioni |
| POST | `/api/collections` | Creazione collezione |
| PUT | `/api/collections/<id>` | Rinomina collezione |
| DELETE | `/api/collections/<id>` | Eliminazione collezione |
| POST | `/api/collections/<id>/batch-add` | Aggiunta batch file |
| POST | `/api/collections/<id>/batch-remove` | Rimozione batch file |

### Scansione

| Metodo | Percorso | Descrizione |
|--------|----------|-------------|
| POST | `/api/scan/start` | Avvio scansione |
| GET | `/api/scan/status` | Recupero avanzamento scansione |
| POST | `/api/scan/cancel` | Cancellazione scansione |
| POST | `/api/scan/resume` | Ripresa scansione interrotta |
| GET | `/api/scan-roots` | Lista radici di scansione |
| POST | `/api/scan-roots` | Aggiunta radice di scansione |

### Analisi AI

| Metodo | Percorso | Descrizione |
|--------|----------|-------------|
| POST | `/api/analysis/analyze/<id>` | Esecuzione analisi AI immagine |
| GET | `/api/analysis/result/<id>` | Recupero risultato analisi |
| POST | `/api/analysis/batch` | Analisi batch |
| POST | `/api/wd-tagger/tag/<id>` | Inferenza WD-Tagger |
| POST | `/api/wd-tagger/batch` | Inferenza batch WD-Tagger |
| POST | `/api/analysis/batch/cancel` | Cancellazione batch analisi AI |
| POST | `/api/wd-tagger/batch/cancel` | Cancellazione batch WD-Tagger |
| POST | `/api/tagger-servers/batch/cancel` | Cancellazione batch cluster tagger |
| POST | `/api/ocr/<id>` | Esecuzione OCR |

### Impostazioni

| Metodo | Percorso | Descrizione |
|--------|----------|-------------|
| GET | `/api/settings/schema` | Recupero schema impostazioni |
| GET | `/api/settings/all` | Recupero tutti i valori impostazioni |
| GET | `/api/settings/<key>` | Recupero valore impostazione |
| PUT | `/api/settings/<key>` | Aggiornamento valore impostazione |

### Gestione Extension

| Metodo | Percorso | Descrizione |
|--------|----------|-------------|
| GET | `/api/extensions` | Lista Extension |
| POST | `/api/extensions/<name>/toggle` | Abilitazione/disabilitazione |
| POST | `/api/extensions/install` | Installazione da repository Git |
| DELETE | `/api/extensions/<name>/uninstall` | Disinstallazione |

### Meccanismi di Sicurezza Agente

| Metodo | Percorso | Descrizione |
|--------|----------|-------------|
| POST | `/api/agent/kill` | Attivazione Kill Switch |
| POST | `/api/agent/resume` | Disattivazione Kill Switch |
| GET | `/api/agent/status` | Stato meccanismi di sicurezza |
| GET | `/api/agent/journal` | Journal operazioni |
| POST | `/api/agent/undo/<journal_id>` | Annullamento operazione |

## Formato Risposte

Tutte le API rispondono in formato JSON unificato.

```json
{
  "ok": true,
  "data": { ... },
  "error": null
}
```

In caso di errore:

```json
{
  "ok": false,
  "data": null,
  "error": "Messaggio di errore"
}
```

## Rate Limiting

Sistema a bucket token con 3 tier.

| Tier | Target | Limite | Burst |
|------|--------|--------|-------|
| READ | Tutte le richieste GET | Illimitato | - |
| WRITE | POST/PUT/DELETE | ~120 req/min | 30 |
| HEAVY | Ricerca simile, analisi AI, scansione | ~20 req/min | 5 |
| DESTRUCTIVE | purge, hard-delete, scrittura config | ~12 req/min | 3 |

In caso di superamento viene restituito HTTP 429. Verificare l'header `Retry-After` per i secondi di attesa prima del retry.

## SSE (Server-Sent Events)

Gli eventi in tempo reale vengono trasmessi via SSE da `/api/events/stream`.
Per i dettagli consultare la sezione "SSE Events".

> **Nota**: Massimo 10 connessioni simultanee per IP. Il limite di dimensione upload è 100 MB.

## Documentazione di Design Interno

Le ragioni dettagliate delle decisioni di design API, ottimizzazioni SQLite, considerazioni sul design DB e altre conoscenze di sviluppo sono consultabili tramite [MD Viewer](/ext/md-viewer/).
