# YU AI Manager Text and Chatlog Management Specification

Created: 2026-03-01
Target version: TBD (implementation timing under consideration)

## Overview

Three features are added to YU AI Manager:

- **MD Viewer** — Local viewing of Markdown files
- **Chatlog Management** — Import, view, and search logs from Claude/ChatGPT/Open WebUI
- **Full-Text Search** — Cross-content search powered by FTS5

The design philosophy is the same as existing features: "fully local, no cloud dependency."

---

## 1. MD Viewer

### Purpose

OS file viewers provide poor Markdown rendering. This feature brings Markdown viewing entirely within YU AI Manager, serving as a daily reference tool for development notes, design documents, and TODO lists.

### Scan Targets

- Extensions: `.md`, `.markdown`
- Existing scan roots are reused
- Excluded: files under `.git/` and `node_modules/`

### DB Schema

```sql
CREATE TABLE md_files (
    id          INTEGER PRIMARY KEY,
    path        TEXT NOT NULL UNIQUE,
    mtime       INTEGER NOT NULL,
    size        INTEGER NOT NULL,
    title       TEXT,        -- Extracted from the first # heading
    content     TEXT,        -- Raw Markdown text
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

- Integrated into the existing modal or side panel
- Rendering: marked.js (bundled locally, no CDN)
- Code blocks: syntax highlighting (highlight.js)
- A raw text view toggle button is provided

### MCP Support

- `search_md_files(query, path_filter)` -> file list
- `get_md_content(file_id)` -> raw text

---

## 2. Chatlog Management

### Purpose

This feature serves as a search engine for development history, making it possible to find past discussions using vague keywords. Examples: "Where was that bug discussion?" or "What was the reason for that design decision?"

### Supported Formats

| Service | Export Format | How to Obtain |
|---|---|---|
| Claude | conversations.json | Settings -> Export Data |
| ChatGPT | conversations.json | Settings -> Export Data |
| Open WebUI | JSON export | Chat History -> Export |

### DB Schema

```sql
-- Per conversation
CREATE TABLE chat_conversations (
    id            INTEGER PRIMARY KEY,
    source        TEXT NOT NULL,  -- 'claude' / 'chatgpt' / 'openwebui'
    external_id   TEXT,           -- Conversation ID from the original service
    title         TEXT,
    model         TEXT,           -- Model name used
    created_at    INTEGER,
    updated_at    INTEGER,
    message_count INTEGER,
    imported_at   INTEGER NOT NULL
);

-- Per message
CREATE TABLE chat_messages (
    id              INTEGER PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES chat_conversations(id),
    role            TEXT NOT NULL,  -- 'user' / 'assistant' / 'system'
    content         TEXT NOT NULL,
    created_at      INTEGER,
    seq             INTEGER         -- Order within conversation
);

-- FTS5 full-text search
CREATE VIRTUAL TABLE chat_messages_fts USING fts5(
    content,
    content='chat_messages',
    content_rowid='id',
    tokenize='unicode61'
);
```

### Importer

Each service's JSON is converted to a common intermediate format and inserted into the DB.

**Claude JSON structure (key fields):**

```json
{
  "uuid": "...",
  "name": "Conversation title",
  "created_at": "2026-01-01T00:00:00Z",
  "chat_messages": [
    {"role": "human", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}
```

**ChatGPT JSON structure (key fields):**

```json
{
  "id": "...",
  "title": "Conversation title",
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

**Open WebUI JSON structure:**

- Follows the OpenAI-compatible API format
- messages array with role/content

### Import UI

- An import section is added to the settings page
- JSON files can be dropped via drag-and-drop or selected with a file picker
- Previously imported conversations are deduplicated by `external_id` (idempotent)
- An import summary (added count and skipped count) is displayed

### Viewer UI

- Conversation list page (title, date, model, source)
- Conversation detail page (turn-based display with role-based color coding)
- Filters by model name, source, and date range
- Attached images store path references only (no file copies)

### MCP Support

- `search_chat_logs(query, source, model, date_from, date_to)` -> conversation list
- `get_conversation(conversation_id)` -> message list
- `import_chat_log(source, json_path)` -> execute import

---

## 3. Full-Text Search

### Targets

- MD files (`md_files_fts`)
- Chat logs (`chat_messages_fts`)
- Existing prompt library (`prompt_library_fts`, already implemented)

### Search UI

- Either extend the existing search bar or provide a dedicated text search page
- Toggle search targets (MD / chatlog / prompt library)
- Results ranked by BM25 score
- Hit snippet display (~50 characters of surrounding context)

### Search API

```
GET /api/text-search?q=keyword&target=md,chat,prompt&limit=20
```

Response:

```json
{
  "results": [
    {
      "type": "chat",
      "conversation_id": 123,
      "title": "Conversation title",
      "snippet": "...text around the hit...",
      "score": 0.95,
      "date": "2026-01-01"
    }
  ]
}
```

---

## Implementation Priority

1. MD Viewer (low implementation cost, high immediate value)
2. Chatlog importer (Claude/ChatGPT support first)
3. Chatlog viewer
4. Open WebUI support
5. Cross-content text search UI

---

## Future Extensions

- Automatic periodic chatlog import (place export files in a watched folder for automatic ingestion)
- Link image generation prompts to the chatlog discussions that produced them
- Automatic chatlog summarization and tagging via Ollama

---

## Notes

- FTS5 patterns can be reused from the existing `prompt_library_fts` implementation
- marked.js is bundled locally rather than loaded from a CDN (following the local-only design philosophy)
- Attached images in chatlogs (DALL-E generated images, etc.) are not saved locally because their URLs expire
