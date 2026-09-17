# Specifica di Accesso LAN MCP ed Endpoint Guida

**Versione implementazione**: 3.1.0
**Documentazione correlata**: `docs/en/features/mcp-integration-guide.md`
**File correlati**: `routes/mcp_endpoint.py`, `routes/help.py`, `mcp_server/help_tools.py`

---

## Panoramica

1. **Accesso LAN MCP** — Consenti ai client MCP sulla LAN di connettersi all'endpoint MCP tramite indirizzo IP quando la modalità condivisione LAN è abilitata
2. **Endpoint `/help`** — Fornisci un manuale web incorporato per l'applicazione (anche pubblicato come risorsa MCP)

---

## 1. Accesso LAN MCP

### 1-1. Architettura

Sulla LAN, i client MCP si connettono direttamente all'endpoint `/mcp` di YU AI Manager utilizzando il trasporto HTTP/SSE.

### 1-2. Endpoint SSE MCP

| Elemento | Dettagli |
|------|------|
| Endpoint | `/mcp` (SSE + postaggio messaggi) |
| Trasporto | HTTP + Server-Sent Events (SSE) |
| Autenticazione | Non richiesta da localhost. Chiave API richiesta da IP LAN |

### 1-3. Autenticazione Chiave API

Il meccanismo di gestione della chiave API esistente (`/api/keys`) viene riutilizzato.

### 1-4. UI Impostazioni

Uno snippet di configurazione della connessione LAN MCP (versione HTTP) viene aggiunto alla scheda Impostazioni > Chiavi API.

---

## 2. Endpoint `/help`

### 2-1. Principi di Design

- Completamente offline
- Scopo duale come risorsa MCP
- Nessuna autenticazione richiesta

### 2-2. Endpoint

| Endpoint | Contenuto |
|----------------|------|
| `GET /help` | Pagina principale manuale |
| `GET /help/<section>` | Pagina specifica sezione |
| `GET /api/help/toc` | JSON tabella dei contenuti |
| `GET /api/help/content/<section>` | JSON corpo sezione |

### 2-3. Strumenti MCP

- `help_search`: Ricerca parola chiave
- `help_get_section`: Recupero sezione
