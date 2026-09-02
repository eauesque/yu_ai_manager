# Specifica di Gestione Testo e Chatlog di YU AI Manager

Creato: 2026-03-01
Versione target: TBD (il timing di implementazione è in considerazione)

## Panoramica

Tre funzionalità vengono aggiunte a YU AI Manager:

- **MD Viewer** — Visualizzazione locale di file Markdown
- **Gestione Chatlog** — Importa, visualizza e ricerca log da Claude/ChatGPT/Open WebUI
- **Ricerca Full-Text** — Ricerca tra i contenuti alimentata da FTS5

La filosofia di design è la stessa delle funzionalità esistenti: "completamente locale, senza dipendenza dal cloud."

---

## 1. MD Viewer

### Scopo

I visualizzatori di file SO forniscono un rendering Markdown scarso. Questa funzionalità porta il rendering Markdown interamente all'interno di YU AI Manager, servendo come strumento di riferimento quotidiano per note di sviluppo, documenti di design e liste TODO.

### Target Scansione

- Estensioni: `.md`, `.markdown`
- I scan root esistenti vengono riutilizzati
- Escluso: file sotto `.git/` e `node_modules/`

### Schema DB

```sql
CREATE TABLE md_files (
    id          INTEGER PRIMARY KEY,
    path        TEXT NOT NULL UNIQUE,
    mtime       INTEGER NOT NULL,
    size        INTEGER NOT NULL,
    title       TEXT,        -- Estratto dall'intestazione # iniziale
    content     TEXT,        -- Testo Markdown grezzo
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    indexed_at  INTEGER
);

CREATE VIRTUAL TABLE md_files_fts USING fts5(
    title,
    content,
    content='md_files',
    content_rowid='id'
);
```

### UI Viewer

- Integrato nel modale esistente o nel pannello laterale
- Rendering: marked.js (raggruppato localmente, no CDN)
- Blocchi di codice: evidenziazione della sintassi (highlight.js)
- È fornito un pulsante di commutazione della vista testo grezzo

### Supporto MCP

- `search_md_files(query, path_filter)` -> lista file
- `get_md_content(file_id)` -> testo grezzo

---

## 2. Gestione Chatlog

### Scopo

Questa funzionalità serve come motore di ricerca per la cronologia dello sviluppo, rendendo possibile trovare discussioni passate utilizzando parole chiave vaghe. Esempi: "Dov'era quella discussione sui bug?" o "Qual era il motivo di quella decisione di design?"

### Formati Supportati

| Servizio | Formato Export | Come Ottenere |
|---|---|---|
| Claude | conversations.json | Impostazioni -> Esporta Dati |
| ChatGPT | conversations.json | Impostazioni -> Esporta Dati |
| Open WebUI | Esportazione JSON | Cronologia Chat -> Esporta |

### Schema DB

```sql
-- Per conversazione
CREATE TABLE chat_conversations (
    id            INTEGER PRIMARY KEY,
    source        TEXT NOT NULL,  -- 'claude' / 'chatgpt' / 'openwebui'
    external_id   TEXT,           -- ID Conversazione dal servizio originale
    title         TEXT,
    model         TEXT,           -- Nome modello utilizzato
    created_at    INTEGER,
    updated_at    INTEGER,
    message_count INTEGER,
    imported_at   INTEGER NOT NULL
);

-- Per messaggio
CREATE TABLE chat_messages (
    id              INTEGER PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES chat_conversations(id),
    role            TEXT NOT NULL,  -- 'user' / 'assistant' / 'system'
    content         TEXT NOT NULL,
    created_at      INTEGER,
    seq             INTEGER         -- Ordine all'interno della conversazione
);

-- Ricerca full-text FTS5
CREATE VIRTUAL TABLE chat_messages_fts USING fts5(
    content,
    content='chat_messages',
    content_rowid='id',
    tokenize='unicode61'
);
```

### Importatore

Il JSON di ogni servizio viene convertito in un formato intermedio comune e inserito nel DB.

**Struttura JSON Claude (campi chiave):**

```json
{
  "uuid": "...",
  "name": "Titolo conversazione",
  "created_at": "2026-01-01T00:00:00Z",
  "chat_messages": [
    {"role": "human", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}
```

**Struttura JSON ChatGPT (campi chiave):**

```json
{
  "id": "...",
  "title": "Titolo conversazione",
  "create_time": 1234567890,
  "mapping": {
    "node_id": {
      "message": {
        "author": {"role": "user"},
        "content": {"parts": ["..."]}
      }
    }
  }
}
```

**Struttura JSON Open WebUI:**

- Segue il formato API compatibile con OpenAI
- Array messaggi con ruolo/contenuto

### UI Importatore

- Una sezione di importazione viene aggiunta alla pagina impostazioni
- I file JSON possono essere trascinati via trascinamento o selezionati con un selezionatore file
- Le conversazioni precedentemente importate vengono deduplicate per `external_id` (idempotente)
- Un riepilogo dell'importazione (conteggio aggiunto e conteggio saltato) viene visualizzato

### UI Viewer

- Pagina elenco conversazioni (titolo, data, modello, origine)
- Pagina dettagli conversazione (visualizzazione basata su turni con colorazione basata su ruolo)
- Filtri per nome modello, origine e intervallo di date
- Le immagini allegate archiviano solo i riferimenti di percorso (nessuna copia di file)

### Supporto MCP

- `search_chat_logs(query, source, model, date_from, date_to)` -> lista conversazioni
- `get_conversation(conversation_id)` -> lista messaggi
- `import_chat_log(source, json_path)` -> esegui importazione

---

## 3. Ricerca Full-Text

### Target

- File MD (`md_files_fts`)
- Log chat (`chat_messages_fts`)
- Libreria prompt esistente (`prompt_library_fts`, già implementato)

### UI Ricerca

- Estendi la barra di ricerca esistente o fornisci una pagina di ricerca testo dedicata
- Commuta i target di ricerca (MD / chatlog / libreria prompt)
- Risultati classificati per punteggio BM25
- Visualizzazione frammento di hit (~50 caratteri di contesto circostante)

### API Ricerca

```
GET /api/text-search?q=keyword&target=md,chat,prompt&limit=20
```

Risposta:

```json
{
  "results": [
    {
      "type": "chat",
      "conversation_id": 123,
      "title": "Titolo conversazione",
      "snippet": "...testo attorno all'hit...",
      "score": 0.95,
      "date": "2026-01-01"
    }
  ]
}
```

---

## Priorità Implementazione

1. MD Viewer (costo implementazione basso, valore immediato alto)
2. Importatore Chatlog (supporto Claude/ChatGPT prima)
3. Viewer Chatlog
4. Supporto Open WebUI
5. UI ricerca contenuti cross

---

## Estensioni Future

- Importazione periodica automatica di chatlog (posiziona i file di esportazione in una cartella osservata per l'ingestione automatica)
- Collegamento dei prompt di generazione immagini alle discussioni del chatlog che le hanno prodotte
- Riassunto e tagging automatico del chatlog tramite Ollama

---

## Note

- I pattern FTS5 possono essere riutilizzati dall'implementazione `prompt_library_fts` esistente
- marked.js viene raggruppato localmente piuttosto che caricato da un CDN (seguendo la filosofia locale-only di design)
- Le immagini allegate nei chatlog (immagini generate DALL-E, ecc.) non vengono salvate localmente perché i loro URL scadono
