# MCP Integration

YU AI Manager hat einen integrierten MCP (Model Context Protocol) Server,
der direkt von AI-Clients wie Claude Desktop, Claude Code, Cline usw. bedient werden kann.
Es bietet 137+ Tools für alle Funktionen von Bildverwaltung bis AI-Analyse.

## Unterstützte MCP-Clients

| Client | Verbindungstyp | Bemerkung |
|--------|---|---|
| Claude Desktop | stdio / HTTP | Empfohlener Client |
| Claude Code | stdio | CLI-Umgebung |
| Cline (VS Code) | stdio | VS Code Extension |
| Open WebUI | HTTP/SSE | Web-basiert |

## Lokale Verbindung (stdio)

Für Verbindung von Claude Desktop / Claude Code auf der gleichen Maschine:

1. Settings > API Keys Tab um API-Schlüssel zu erstellen
2. Folgendes zu Client-Konfigurationsdatei hinzufügen

### Claude Desktop

`claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "yu-ai-manager": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "/path/to/yu_ai_manager",
      "env": {
        "YU_BASE_URL": "http://localhost:5000",
        "YU_API_KEY": "sk_your_api_key_here"
      }
    }
  }
}
```

### Claude Code

`.mcp.json`:

```json
{
  "mcpServers": {
    "yu-ai-manager": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "/path/to/yu_ai_manager",
      "env": {
        "YU_BASE_URL": "http://localhost:5000",
        "YU_API_KEY": "sk_your_api_key_here"
      }
    }
  }
}
```

## LAN-Verbindung (HTTP/SSE)

Für Verbindung von anderer Maschine im LAN:

1. YU AI Manager LAN Access ON stellen
2. API-Schlüssel erstellen
3. Settings > API Keys Tab "MCP Connection Snippet" kopieren

```json
{
  "mcpServers": {
    "yu-ai-manager": {
      "type": "http",
      "url": "http://192.168.x.x:5000/mcp",
      "headers": {
        "Authorization": "Bearer sk_your_api_key_here"
      }
    }
  }
}
```

## Verfügbare Tools (nach Kategorie)

### Bildsuche & Verwaltung

| Tool | Beschreibung |
|------|----------|
| `search_images` | Filter-Suche nach Tags, Datum, Bewertung |
| `get_image_detail` | Vollständige Bild-Metadaten abrufen |
| `get_library_stats` | Bibliotheks-Statistiken (Dateien, Tag-Verteilung usw.) |
| `find_similar` | Ähnliche Bilder mit Perzeptual-Hash erkennen |
| `rate_images` | Stern-Bewertung Batch-Set |
| `set_tags` | Tags hinzufügen/entfernen |
| `set_annotations` | Anmerkungen setzen |
| `get_annotations` | Anmerkungen abrufen |

### Kollektionen

| Tool | Beschreibung |
|------|----------|
| `list_collections` | Kollektions-Liste |
| `create_collection` | Kollektion erstellen |
| `add_to_collection` | Bilder zu Kollektion hinzufügen |
| `remove_from_collection` | Bilder aus Kollektion entfernen |
| `delete_collection` | Kollektion löschen |

### Scan

| Tool | Beschreibung |
|------|----------|
| `trigger_scan` | Scan ausführen |
| `get_scan_status` | Scan-Fortschritt überprüfen |
| `list_scan_roots` | Scan-Verzeichnis-Liste |
| `add_scan_root` | Scan-Verzeichnis hinzufügen |
| `scan_directory` | Spezifisches Verzeichnis scannen |

### AI Analyse

| Tool | Beschreibung |
|------|----------|
| `analyze_image` | AI-Bildanalyse (einzeln) |
| `analyze_batch` | AI-Bildanalyse (Batch) |
| `wd_tagger_tag_file` | WD-Tagger Inferenz (einzeln) |
| `wd_tagger_batch` | WD-Tagger Inferenz (Batch) |
| `semantic_search` | CLIP Semantische Suche |
| `s2t_transcribe_video` | Sprache in Text umwandeln |

### Bridge Integration

| Tool | Beschreibung |
|------|----------|
| `sd_generate` | Bild mit SD WebUI generieren |
| `sd_list_models` | SD WebUI Modelle auflisten |
| `comfyui_generate` | Bild mit ComfyUI generieren |
| `comfyui_generate_json` | ComfyUI Workflow JSON ausführen |

### Prompt-Bibliothek

| Tool | Beschreibung |
|------|----------|
| `create_prompt` | Prompt erstellen |
| `search_prompts` | Prompts suchen |
| `get_prompt` | Prompt abrufen |
| `update_prompt` | Prompt aktualisieren |

### Einstellungen

