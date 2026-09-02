# YU AI Manager Text- und Chatlog-Verwaltungs-Spezifikation

Erstellt: 2026-03-01
Zielversion: TBD (Implementierungs-Timing unter Berücksichtigung)

## Übersicht

Drei Funktionen werden zu YU AI Manager hinzugefügt:

- **MD Viewer** — Lokale Anzeige von Markdown-Dateien
- **Chatlog-Verwaltung** — Importieren, Anzeigen und Durchsuchen von Protokollen von Claude/ChatGPT/Open WebUI
- **Volltext-Suche** — Cross-Content-Suche mit FTS5-Leistung

Die Design-Philosophie ist die gleiche wie bei bestehenden Funktionen: "vollständig lokal, keine Cloud-Abhängigkeit."

---

## 1. MD Viewer

### Zweck

OS-Datei-Viewer bieten schlechtes Markdown-Rendering. Diese Funktion bringt Markdown-Anzeige vollständig innerhalb YU AI Manager, dient als tägliches Referenz-Tool für Entwicklungs-Notizen, Design-Dokumente und TODO-Listen.

### Scan-Ziele

- Erweiterungen: `.md`, `.markdown`
- Bestehende Scan Roots werden wiederverwendet
- Ausgeschlossen: Dateien unter `.git/` und `node_modules/`

### DB-Schema

```sql
CREATE TABLE md_files (
    id          INTEGER PRIMARY KEY,
    path        TEXT NOT NULL UNIQUE,
    mtime       INTEGER NOT NULL,
    size        INTEGER NOT NULL,
    title       TEXT,        -- Extrahiert aus der ersten # Überschrift
    content     TEXT,        -- Roh Markdown-Text
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

### Viewer UI

- In das bestehende Modal oder Seiten-Panel integriert
- Rendering: marked.js (lokal gebündelt, kein CDN)
- Code-Blöcke: Syntax-Hervorhebung (highlight.js)
- Ein Roh-Text-Ansicht-Umschalter wird bereitgestellt

### MCP-Unterstützung

- `search_md_files(query, path_filter)` -> Dateiliste
- `get_md_content(file_id)` -> Roh-Text

---

## 2. Chatlog-Verwaltung

### Zweck

Diese Funktion dient als Such-Engine für Entwicklungs-Geschichte und ermöglicht es, Vergangenheits-Diskussionen mit vagen Schlüsselwörtern zu finden. Beispiele: "Wo war diese Bug-Diskussion?" oder "Was war der Grund für diese Design-Entscheidung?"

### Unterstützte Formate

| Service | Export-Format | Wie zu erhalten |
|---|---|---|
| Claude | conversations.json | Einstellungen -> Daten exportieren |
| ChatGPT | conversations.json | Einstellungen -> Daten exportieren |
| Open WebUI | JSON-Export | Chat-Verlauf -> Exportieren |

### DB-Schema

```sql
-- Pro Konversation
CREATE TABLE chat_conversations (
    id            INTEGER PRIMARY KEY,
    source        TEXT NOT NULL,  -- 'claude' / 'chatgpt' / 'openwebui'
    external_id   TEXT,           -- Konversations-ID aus dem Original-Service
    title         TEXT,
    model         TEXT,           -- Verwendetes Modell-Name
    created_at    INTEGER,
    updated_at    INTEGER,
    message_count INTEGER,
    imported_at   INTEGER NOT NULL
);

-- Pro Nachricht
CREATE TABLE chat_messages (
    id              INTEGER PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES chat_conversations(id),
    role            TEXT NOT NULL,  -- 'user' / 'assistant' / 'system'
    content         TEXT NOT NULL,
    created_at      INTEGER,
    seq             INTEGER         -- Reihenfolge in Konversation
);

-- FTS5 Volltext-Suche
CREATE VIRTUAL TABLE chat_messages_fts USING fts5(
    content,
    content='chat_messages',
    content_rowid='id',
    tokenize='unicode61'
);
```

### Importer

Jeder Service JSON wird in ein gemeinsames Zwischen-Format konvertiert und in die DB eingefügt.

**Claude JSON-Struktur (Schlüssel-Felder):**

```json
{
  "uuid": "...",
  "name": "Konversations-Titel",
  "created_at": "2026-01-01T00:00:00Z",
  "chat_messages": [
    {"role": "human", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}
```

**ChatGPT JSON-Struktur (Schlüssel-Felder):**

```json
{
  "id": "...",
  "title": "Konversations-Titel",
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

**Open WebUI JSON-Struktur:**

- Folgt das OpenAI-kompatible API-Format
- messages Array mit role/content

### Import UI

- Ein Import-Bereich wird zur Einstellungs-Seite hinzugefügt
- JSON-Dateien können per Drag-and-Drop oder mit Datei-Picker ausgewählt werden
- Zuvor importierte Konversationen werden durch `external_id` dedupliziert (idempotent)
- Eine Import-Zusammenfassung (hinzugefügte und übersprungene Anzahl) wird angezeigt

### Viewer UI

- Konversations-Listen-Seite (Titel, Datum, Modell, Quelle)
- Konversations-Detail-Seite (Turn-basierte Anzeige mit Rollen-basierter Farbcodierung)
- Filter nach Modell-Name, Quelle und Datums-Bereich
- Angehängte Bilder speichern nur Pfad-Referenzen (keine Datei-Kopien)

### MCP-Unterstützung

- `search_chat_logs(query, source, model, date_from, date_to)` -> Konversations-Liste
- `get_conversation(conversation_id)` -> Nachrichtenliste
- `import_chat_log(source, json_path)` -> Import ausführen

---

## 3. Volltext-Suche

### Ziele

- MD-Dateien (`md_files_fts`)
- Chat-Protokolle (`chat_messages_fts`)
- Bestehende Eingabeaufforderungs-Bibliothek (`prompt_library_fts`, bereits implementiert)

### Such-UI

- Entweder die bestehende Such-Leiste erweitern oder eine dedizierte Text-Such-Seite bereitstellen
- Umschalter für Such-Ziele (MD / Chatlog / Eingabeaufforderungs-Bibliothek)
- Ergebnisse nach BM25-Score gereiht
- Hit-Snippet-Anzeige (~50 Zeichen umgebendes Kontext)

### Such-API

```
GET /api/text-search?q=keyword&target=md,chat,prompt&limit=20
```

Antwort:

```json
{
  "results": [
    {
      "type": "chat",
      "conversation_id": 123,
      "title": "Konversations-Titel",
      "snippet": "...Text um den Hit...",
      "score": 0.95,
      "date": "2026-01-01"
    }
  ]
}
```

---

## Implementierungs-Priorität

1. MD Viewer (niedrige Implementierungs-Kosten, hoher sofortiger Wert)
2. Chatlog-Importer (zuerst Claude/ChatGPT-Unterstützung)
3. Chatlog-Viewer
4. Open WebUI-Unterstützung
5. Cross-Content-Text-Such-UI

---

## Zukünftige Erweiterungen

- Automatischer periodischer Chatlog-Import (platzieren Sie Export-Dateien in einem überwachten Ordner für automatischen Einzug)
- Verbinden Sie Bild-Generierungs-Eingabeaufforderungen mit den Chatlog-Diskussionen, die sie erzeugt haben
- Automatische Chatlog-Zusammenfassung und Tagging via Ollama

---

## Notizen

- FTS5-Muster können aus der bestehenden `prompt_library_fts`-Implementierung wiederverwendet werden
- marked.js wird lokal gebündelt, anstatt von einem CDN geladen (nach der Local-Only-Design-Philosophie)
- Angehängte Bilder in Chatlogs (DALL-E generierte Bilder usw.) werden nicht lokal gespeichert, da ihre URLs ablaufen
