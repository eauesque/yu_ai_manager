# MCP-Integrationsleitfaden — Betrieb von YU AI Manager von einem LLM aus

YU AI Manager hat einen integrierten **MCP (Model Context Protocol)**-Server, mit dem LLM-Anwendungen die Bildbibliothek mit natürlicher Sprache betreiben können.

Es gibt keine integrierte Chat-UI in dieser Anwendung. Um mit natürlicher Sprache interagieren zu können, verbinden Sie sich von Ihrem bevorzugten MCP-kompatiblen Client aus.

---

## Was ist MCP?

MCP (Model Context Protocol) ist ein Standard-Protokoll, das LLM-Anwendungen den Zugriff auf externe Tools und Datenquellen ermöglicht. YU AI Manager fungiert als MCP-Server, und LLM-Clients (wie Claude Desktop) verbinden sich damit, wodurch Anweisungen in natürlicher Sprache in API-Operationen übersetzt werden.

```
┌─────────────────┐      MCP (stdio)       ┌─────────────────────┐
│  LLM Client     │ <--------------------> │  YU AI Manager      │
│  (Claude Desktop │                        │  MCP Server         │
│   / Open WebUI   │                        │  (python -m         │
│   / Cline etc.)  │                        │   mcp_server)       │
└─────────────────┘                        └────────┬────────────┘
                                                     │ HTTP API
                                                     v
                                           ┌─────────────────────┐
                                           │  YU AI Manager      │
                                           │  Web Server          │
                                           │  (localhost:5000)    │
                                           └─────────────────────┘
```

## Unterstützte MCP-Clients

Die folgenden sind repräsentativ MCP-kompatible Clients. Die Konfigurationsschritte sind für alle ähnlich.

| Client | Anbieter | Features |
|---|---|---|
| **Claude Desktop** | Anthropic | Direkter Claude-Zugriff. Native MCP-Unterstützung |
| **Claude Code** | Anthropic | Terminal-basierter Client für Entwickler |
| **Cline** | VS Code Extension | Editor-Integration. Multi-LLM-Unterstützung |
| **Open WebUI** | Open Source | Selbstgehostet. Kann mit lokalen LLMs wie Ollama kombiniert werden |

Hinweis: Die Anzahl der MCP-kompatiblen Clients wächst schnell. Jeder Client, der stdio-Transport unterstützt, sollte sich verbinden können.

## Einrichtung

### 1. Starten Sie YU AI Manager

Der MCP-Server funktioniert über die Web-Server-API, daher muss YU AI Manager zuerst laufen.

```bash
python web_ui.py --db ./tags.db --port 5000
```

### 2. Ausstellen Sie einen API-Schlüssel (empfohlen)

Die Ausstellung eines API-Schlüssels ermöglicht dem MCP-Server, die PIN-Authentifizierung bei LAN-Freigabe oder PIN-Authentifizierung zu umgehen.

API-Schlüssel können unter Einstellungen -> API-Schlüssel ausgestellt werden.

Ein API-Schlüssel ist nicht erforderlich, wenn ohne PIN ausgeführt wird (`config_test.json`).

### 3. Fügen Sie Verbindungseinstellungen zu Ihrem MCP-Client hinzu

#### Claude Desktop

Bearbeiten Sie `claude_desktop_config.json`:

**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "yu-ai-manager": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "C:/path/to/yu_ai_manager",
      "env": {
        "YU_BASE_URL": "http://127.0.0.1:5000",
        "YU_API_KEY": "sk_your_api_key_here"
      }
    }
  }
}
```

#### Claude Code

Fügen Sie Einstellungen zu `.mcp.json` im Projektstamm hinzu, oder verwenden Sie den Befehl `claude mcp add`:

```json
{
  "mcpServers": {
    "yu-ai-manager": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "/path/to/yu_ai_manager",
      "env": {
        "YU_BASE_URL": "http://127.0.0.1:5000",
        "YU_API_KEY": "sk_your_api_key_here"
      }
    }
  }
}
```

#### Cline (VS Code)

Geben Sie die gleiche Information durch Clines MCP-Einstellungen ein.

#### Umgebungsvariablen

| Variable | Erforderlich | Standard | Beschreibung |
|---|---|---|---|
| `YU_BASE_URL` | - | `http://localhost:5000` | Web-Server-URL |
| `YU_API_KEY` | - | Keine | API-Schlüssel (erforderlich in PIN-Umgebungen) |
| `YU_DEBUG_MODE` | - | `0` | Auf `1` setzen, um Debug-Tools hinzuzufügen |

## Verwendungsbeispiele

Sobald verbunden, können Sie die Bildbibliothek durch natürlichsprachliche Anweisungen an das LLM betreiben.

### Suchen und Durchsuchen

```
"Zeigen Sie mir die 20 neuesten Bilder von Mädchen mit blauen Augen"
"Filtern Sie nur Bilder, die mit NovelAI generiert wurden"
"Zeigen Sie mir Statistiken für Bilder, die letzte Woche gescannt wurden"
```

### Organisieren und Klassifizieren

```
"Geben Sie diesen 10 Bildern eine 5-Sterne-Bewertung"
"Fügen Sie Bilder mit Tag 'landscape' zur 'Scenery Collection' hinzu"
"Listen Sie alle Bilder mit einer Bewertung von 3 oder darunter auf"
```

### Analyse und Anmerkung

```
"Bewerten Sie die Qualität der neu hinzugefügten Bilder und speichern Sie sie als Anmerkungen"
"Zeigen Sie mir alle Anmerkungen für Bild-ID 12345"
"Suchen Sie nach Anmerkungen mit Quellageent:claude"
```

### Scan-Operationen

```
"Nach neuen Bildern scannen"
"Überprüfen Sie den Scan-Fortschritt"
"Zeigen Sie mir alle Scan-Fehler"
```

## Verfügbare Tools

Der MCP-Server legt die folgenden Tools dem LLM aus:

### Suchen und Durchsuchen (4 Tools)

| Tool-Name | Beschreibung |
|---|---|
| `search_images` | Bilder nach Tags, Datum, Format, Bewertung usw. suchen |
| `get_image_detail` | Alle Metadaten für ein Bild abrufen |
| `get_library_stats` | Bibliotheks-Statistiken (Dateianzahl, Tag-Anzahl, Quellverteilung usw.) |
| `find_similar` | Suche ähnliche Bilder mit Perceptual Hash |

### Sammlungen (4 Tools)

| Tool-Name | Beschreibung |
|---|---|
| `list_collections` | Sammlungen auflisten |
| `create_collection` | Sammlung erstellen |
| `delete_collection` | Sammlung löschen |
| `add_to_collection` / `remove_from_collection` | Bilder hinzufügen/entfernen |

### Tags und Bewertungen (2 Tools)

| Tool-Name | Beschreibung |
|---|---|
| `rate_images` | Sterne-Bewertungen für mehrere Bilder auf einmal setzen |
| `set_tags` | Tags für mehrere Bilder auf einmal hinzufügen/entfernen |

### Anmerkungen (4 Tools)

| Tool-Name | Beschreibung |
|---|---|
| `set_annotations` | AI-Analyseergebnisse als Anmerkungen speichern |
| `get_annotations` | Anmerkungen für ein Bild abrufen |
| `search_annotations` | Anmerkungen über Quelle, Schlüssel und Konfidenz suchen |
| `delete_annotations` | Anmerkungen löschen |

### Scan (3 Tools)

| Tool-Name | Beschreibung |
|---|---|
| `trigger_scan` | Einen Scan starten |
| `get_scan_status` | Scan-Fortschritt überprüfen |
| `get_scan_errors` | Scan-Fehler auflisten |

### Weitere

Tools für Eingabeaufforderungs-Bibliothek, Sicherung und MCP-Client-Verwaltung sind ebenfalls enthalten.

## FAQ

### F: Gibt es keine Chat-Funktion in der App?

A: Es gibt keine. YU AI Manager spezialisiert sich auf Bilder-Metadaten-Verwaltung, und die Schnittstelle für konversationelle KI wird an MCP-kompatible Clients delegiert. Sie können alle Operationen per natürlicher Sprache durchführen, indem Sie Claude Desktop oder einen ähnlichen Client daneben ausführen.

### F: Welches LLM sollte ich verwenden?

A: Jedes LLM funktioniert, solange der MCP-Client es unterstützt. Für zuverlässige Tool-Argument-Verarbeitung funktionieren große Modelle wie Claude oder GPT-4-Klasse am konsistentesten.

### F: Kann ich ein lokales LLM verwenden?

A: Ja, lokale LLMs funktionieren mit Kombinationen wie Open WebUI + Ollama, unter der Voraussetzung, dass sie MCP unterstützen. Die Genauigkeit der Tool-Aufrufe hängt von den Fähigkeiten des Modells ab.

### F: Hat YU AI Manager auch eine MCP-Client-Funktion?

A: Die `MCP Client`-Erweiterung (auf der Tools-Seite) verbindet YU AI Manager mit **anderen MCP-Servern**. Dieser Leitfaden beschreibt die entgegengesetzte Richtung: externes LLM -> YU AI Manager.
