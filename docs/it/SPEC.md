# Yu AI Manager — Specifica globale

> **Pubblico di riferimento**: Agenti AI come Claude Desktop  
> **Versione**: v4.91.15  
> **Aggiornamento**: 2026-04-19

---

## Indice

1. [Panoramica del progetto](#1-panoramica-del-progetto)
2. [Stack tecnologico](#2-stack-tecnologico)
3. [Panoramica dell'architettura](#3-panoramica-dellarchitettura)
4. [Autenticazione e sicurezza](#4-autenticazione-e-sicurezza)
5. [Endpoint REST API](#5-endpoint-rest-api)
6. [Server MCP](#6-server-mcp)
7. [Eventi SSE](#7-eventi-sse)
8. [Schema del database](#8-schema-del-database)
9. [Estensioni](#9-estensioni)
10. [Configurazione (config.json)](#10-configurazione-configjson)
11. [Struttura dei file](#11-struttura-dei-file)
12. [Convenzioni di sviluppo](#12-convenzioni-di-sviluppo)

---

## 1. Panoramica del progetto

**yu_ai_manager** è un sistema di gestione di librerie locali per immagini, video, audio e testo generati da IA.  
Con una filosofia di design edge-first e cloud-independent, prioritizza il completamento locale/LAN.

### Funzionalità principali

| Funzionalità | Descrizione |
|------|------|
| Gestione libreria | Scansione, tagging e ricerca di immagini/video/audio/testo |
| Estrazione metadati | Estrazione automatica di parametri generativi da A1111 / ComfyUI / NovelAI |
| Analisi IA | Analisi di immagini tramite Claude / OpenAI / Ollama / Hailo VLM |
| Ricerca semantica | Ricerca semantica tramite CLIP (ONNX/CoreML) + Hailo |
| Integrazione Bridge | Richieste di generazione a Stable Diffusion / ComfyUI / NovelAI |
| LLM Router | Routing integrato verso backend compatibili Ollama / OpenAI |
| Sicurezza degli agenti | Meccanismi di sicurezza come Kill Switch / Circuit Breaker / Approval Gate |
| Collaborazione LAN | Scoperta automatica tramite mDNS + condivisione tra peer |
| Server MCP | 180+ strumenti operabili direttamente da Claude Desktop |

---

## 2. Stack tecnologico

| Layer | Tecnologia |
|---------|------|
| Backend | Python 3.11+ / Quart (async) / Hypercorn |
| Database | SQLite3 (ricerca full-text FTS5 + BLOB compresso zstd) |
| Frontend | TypeScript + build Vite |
| Desktop | Tauri (Rust) |
| MCP | FastMCP (Anthropic MCP Server) |
| LLM | Claude API / OpenAI API / Ollama / Hailo VLM |
| Inference | ONNX Runtime / CoreML / Hailo Runtime |
| Gestione pacchetti | Python: `uv pip` / Node.js: `pnpm` |

### Convenzione di porta

- `5000–5099`: Banda riservata app in produzione (non modificare)
- `5100+`: Uso per test e debug (`scripts/find_port.py` per ottenere porta libera automaticamente)

---

## 3. Panoramica dell'architettura

```
┌──────────────────────────────────────────────────┐
│  Livello client                                   │
│  ├─ Web UI (TypeScript / Tauri)                  │
│  ├─ Claude Desktop (MCP)                         │
│  └─ Strumenti esterni (API Key / LAN Peer)       │
├──────────────────────────────────────────────────┤
│  Livello autenticazione (auth_chain.py)          │
│  ├─ PIN / QuickLock (boss lock)                  │
│  ├─ API Key (Bearer / scopes)                    │
│  └─ Fiducia peer LAN (validazione mDNS)          │
├──────────────────────────────────────────────────┤
│  Livello API                                     │
│  ├─ REST API (235+ endpoint / Quart Blueprint)   │
│  ├─ Flusso SSE (/api/events/stream)              │
│  └─ Server MCP (180+ strumenti)                  │
├──────────────────────────────────────────────────┤
│  Livello servizi                                 │
│  ├─ TagDB (SQLite / schema v53)                  │
│  ├─ Event Bus (broadcaster SSE)                  │
│  ├─ LLM Router (integrazione multi-backend)      │
│  ├─ Analysis Engine (Claude/OpenAI/Ollama/Hailo) │
│  ├─ Extensions (47 builtin)                      │
│  └─ File Services (scansione/servizio/miniature) │
├──────────────────────────────────────────────────┤
│  Livello Agent Safety                            │
│  ├─ Kill Switch          ├─ Budget Tracker       │
│  ├─ Circuit Breaker      ├─ Approval Gate        │
│  ├─ Scope Fence          ├─ Undo Engine          │
│  ├─ Anomaly Detector     └─ Audit Bureau         │
└──────────────────────────────────────────────────┘
```

### Direzione delle dipendenze dei moduli

```
routes/ → core/services_core/ → core/tagdb_core/ → SQLite
routes/ → core/web/ (autenticazione)
mcp_server/ → routes/ oppure chamata diretta al core
extensions/ → core/extensions_core/ (gestione ciclo di vita)
```

---

## 4. Autenticazione e sicurezza

### Catena di autenticazione (core/web/auth_chain.py)

Valutato in questo ordine per ogni richiesta:

1. **Bypass file statici** — `/static/`, `/favicon.ico`, `/help/*`
2. **Bypass MCP** — `/mcp` (autenticazione MCP stessa)
3. **Bypass LLM Router** — `/v1/` (solo loopback)
4. **Bypass LAN Share** — `/s/<token>` (token condiviso)
5. **Fiducia peer LAN** — I peer verificati tramite mDNS non richiedono PIN
6. **Autenticazione API Key** — `Authorization: Bearer <key>` (validazione scopes)
7. **Controllo QuickLock** — Quando bloccato, solo `/api/lock/unlock` è consentito
8. **Controllo PIN** — Autenticazione sessione browser

### Scopes API Key

| Scope | Permesso |
|---------|------|
| `read` | Lettura generale |
| `write` | Scrittura file e configurazione |
| `tag.write` | Aggiunta e rimozione tag |
| `collection.write` | Gestione collezioni |
| `annotate` | Annotazione |
| `scan` | Operazioni di scansione |
| `admin` | Amministratore (tutte le operazioni) |

### QuickLock / Boss Mode

- PIN hash tramite PBKDF2-SHA256 (600k iterazioni)
- Limite di frequenza: 5 fallimenti massimi, blocco di 60 secondi
- `/api/lock/status` per verificare stato blocco (nessuna autenticazione richiesta)
- `/api/lock/unlock` per sbloccare (PIN richiesto)

### Gestione segreti

- Integrazione 1Password (`op://vault/item/field` formato riferimento)
- Integrazione Bitwarden
- Valori configurazione criptati con Fernet simmetrica (`enc:...` prefisso)

---

*Questo documento è archiviato in `docs/ja/SPEC.md`. Se il contenuto è obsoleto, fare riferimento al codice e git log.*
