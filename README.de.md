# YU AI Manager

Eine WebUI zur Verwaltung von KI-generierten Bild-Metadaten.

## Übersicht

Ein WebUI-Tool zum Extrahieren, Suchen und Verwalten von Metadaten (Prompts, Modelle, Seeds usw.), die in KI-generierten Bildern eingebettet sind.

**Was du tun kannst:**

- Ordner oder ZIP-Archive in großen Mengen scannen, um Bilder automatisch zu registrieren
- Nach Prompt, Tag, Modellname, Seed-Wert und mehr suchen und filtern
- Bilder sofort zur Neugenerierung an SD / ComfyUI / NovelAI senden
- Automatisch taggen mit WD-Tagger, analysieren mit Ollama/OpenAI
- Über QR-Code vom Smartphone oder einem anderen Gerät im LAN zugreifen

**Unterstützte Quellen**: Stable Diffusion (A1111/Forge), NovelAI V3/V4, ComfyUI

## Voraussetzungen

- Windows / Linux / macOS

> **Keine manuelle Installation erforderlich.** `start.sh` / `start.bat` bootstrappt alle benötigten Werkzeuge in den Projektbaum (keine systemweiten Änderungen, keine Admin-Rechte).

## Installation & Start

```bash
git clone https://github.com/eauesque/yu_ai_manager.git
cd yu_ai_manager

# Windows
start.bat

# macOS / Linux
./start.sh
```

Was der Launcher beim ersten Start einrichtet:

| Werkzeug | Installationsweg |
| --- | --- |
| `uv` | Wird automatisch nach `./bin/uv` heruntergeladen |
| Python 3.11+ | Wird von `uv` automatisch installiert |
| Node.js 22 LTS | Optional — fragt nach Download nach `./bin/node/` (~30 MB) |
| pnpm | Wird via `corepack` aktiviert, sobald Node verfügbar ist |
| ffmpeg | Optional — fragt unter Windows/macOS nach Download nach `./bin/ffmpeg/` (~80 MB), gibt unter Linux einen distributionsspezifischen `apt`/`dnf`/`pacman`-Hinweis aus |

Setze `YU_AUTO_INSTALL=1`, um die Abfragen in nicht-interaktiven Umgebungen (CI usw.) zu überspringen. ffmpeg wird nur von Video- / Sprache-zu-Text- / OCR-Erweiterungen benötigt — die App selbst startet auch ohne.

Bei nachfolgenden Starts werden venv wiederverwendet und nur bei Änderungen der Abhängigkeitsmanifeste oder TypeScript-Quellen neu installiert bzw. gebaut.

Füge `--db`, `--port`, `--lan`, `--pin` usw. in `launch-args.txt` für dauerhafte Konfiguration ein.

## Hauptfunktionen

### Scan & Registrierung
- Automatisches Extrahieren von Metadaten aus PNG / WebP / JPEG
- Transparentes Scannen von ZIP- / 7z-Archiven (kein Entpacken erforderlich)
- Dateien per Drag & Drop hinzufügen

### Suche & Durchsuchen
- Volltextsuche nach Prompt, Tag, Modellname, Seed-Wert
- Regex-Suche, Mehrfachbedingungsfilter
- pHash-Ähnlichkeitssuche, CLIP semantische Suche

### Organisation
- Favoriten, Sternebewertungen (1–5), Notizen (Anmerkungen)
- Sammlungen (Gruppierung)
- Statistiken-Dashboard, Monatsberichte, Trophy-System

### Generierungswerkzeug-Bridge
- Sofortiger Prompt-Transfer zu SD WebUI / Forge / ComfyUI / NovelAI
- Zwischenablage-basierter Transfer ebenfalls unterstützt

### KI-Unterstützung
- WD-Tagger Auto-Tagging
- Bildinhaltanalyse via Ollama / OpenAI
- Sprache-zu-Text (S2T)

### Netzwerk & Freigabe
- LAN-Freigabemodus (QR-Code-Zugang vom Smartphone)
- MCP-Server (KI-Agenten-Integration)
- Flottenmanagement (zentrale Steuerung mehrerer Instanzen)

### Anpassung
- Benutzerdefiniertes UI- und Erweiterungssystem
- Theme-Unterstützung (Hell / Dunkel)
- Tauri Desktop-App (kein Browser erforderlich)

## Sprachen

English / 日本語 / 繁體中文 / 简体中文 / 한국어

## Dokumentation

- [Schnellstart](docs/en/help/user/quickstart.md)
- [Anwendungsfälle](docs/en/help/user/use-cases.md)
- [API-Referenz](docs/en/api/README.md)
- [Performance-Optimierung](docs/en/help/user/performance-tuning.md)
- [Deployment](docs/en/help/user/deployment.md)
- [Erweiterungsentwicklung](docs/en/plugin-development/getting-started.md)
- [Benutzerdefiniertes UI](docs/en/custom-ui/README.md)
- [MCP-Tools](docs/en/api/MCP_TOOLS_REFERENCE.md)
- [Alle Dokumente](docs/en/README.md)

## Entwicklung

Siehe [DEVELOPMENT.md](DEVELOPMENT.de.md)

## FAQ

[docs/en/FAQ.md](docs/en/FAQ.md)

## Fehlerberichte

[GitHub Issues](https://github.com/eauesque/yu_ai_manager/issues)

## Lizenz

MIT License — [LICENSE](LICENSE) / [Einfache Sprache](docs/en/LICENSE.md)
