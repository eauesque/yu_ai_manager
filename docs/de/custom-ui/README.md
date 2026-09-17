# Custom UI-Entwicklungsanleitung

YU AI Manager's Frontend kann vollständig ersetzt werden. Diese Anleitung zeigt das Custom UI-System.

## Inhaltsverzeichnis

- [Übersicht](#übersicht)
- [Architektur](#architektur)
- [Erste Schritte](quickstart.md) — Minimale UI-Erstellung
- [Design-Anleitung](design-guide.md) — CSS-Design, Themes, Responsive, Komponenten
- [Template-Anleitung](templates.md) — Jinja2-Muster, i18n, Seitenstruktur
- [Erweiterte Funktionen](advanced.md) — SSE-Echtzeit, Batch-Operationen, Sicherheit
- [API-Referenz](api-reference.md) — Links zur vollständigen API-Dokumentation

## Übersicht

YU AI Manager trennt Backend-API vollständig vom Frontend. Die Custom UI kann frei ersetzt werden.
Eine Custom UI wird einfach im `ui/<name>/`-Verzeichnis platziert.

### Was ist mit diesem System möglich

- **Vollständiger UI-Austausch**: Alle Seiten (Suche, Statistiken, Einstellungen) mit eigenem Design
- **Theme-Anpassung**: CSS-Variablen-Überschreibungen für Farbschema
- **Teilweiser Austausch**: Nur bestimmte Seiten anpassen, Rest mit Standard UI
- **AI-generierte UI**: Claude oder ChatGPT API-Dokumentation geben, UI automatisch generieren lassen

### Architektur

```
yu_ai_manager/
├── ui/
│   ├── default/              # Referenz UI (built-in)
│   │   ├── manifest.json     # UI-Metadaten (erforderlich)
│   │   ├── templates/        # Jinja2 HTML-Templates
│   │   │   ├── index.html    # Hauptsuchseite
│   │   │   ├── stats.html    # Statistik-Dashboard
│   │   │   ├── tools.html    # Werkzeugseite
│   │   │   ├── settings.html # Einstellungsseite
│   │   │   ├── story.html    # Your Story Seite
│   │   │   ├── inspect.html  # Metadaten-Inspektor
│   │   │   └── _nav.html     # Gemeinsame Navigationsleiste
│   │   └── static/           # CSS, JS, Images
│   │       ├── css/          # Stylesheets
│   │       ├── dist/         # TypeScript Build-Output
│   │       └── favicon.svg   # Favicon
│   ├── custom/               # Custom UI (gitignored, auto-detect)
│   │   ├── manifest.json
│   │   ├── templates/
│   │   └── static/
│   └── my-theme/             # Zusätzliche UI (Name frei)
│       ├── manifest.json
│       └── ...
├── routes/                   # Server-seitige API-Routes
│   ├── pages.py              # Seiten-Routing-Definition
│   └── ...                   # Verschiedene API-Endpunkte
└── docs/api/                 # API-Dokumentation
```

### UI-Auflösungsreihenfolge

Bei Server-Start wird die zu verwendende UI in dieser Priorität bestimmt:

| Priorität | Bedingung | Verhalten |
|-----------|-----------|-----------|
| 1 | `"ui": "my-theme"` in `config.json` | Verwende `ui/my-theme/` |
| 2 | `ui/custom/` mit gültigem `manifest.json` | Auto-Detect und verwende |
| 3 | Keine der oben | `ui/default/` als Fallback |

### manifest.json

Alle Custom UIs müssen `manifest.json` haben:

```json
{
  "name": "my-custom-ui",
  "version": "1.0.0",
  "description": "My custom UI for YU AI Manager",
  "author": "Your Name",
  "api_version": "1"
}
```

| Feld | Erforderlich | Beschreibung |
|------|------|----------|
| `name` | Ja | UI-Identifikationsname (sollte mit Verzeichnisname übereinstimmen) |
| `version` | Ja | Semantische Versionierung |
| `description` | Nein | UI-Beschreibung |
| `author` | Nein | Autorname |
| `api_version` | Nein | Unterstützte API-Version (`"1"`) |
| `type` | Nein | `"full"` (Standard) oder `"theme"` |

### Statische Datei-Zustellung

Das `static/`-Verzeichnis der Custom UI wird auf Flask's `/static/` URL gemappt:

```
ui/custom/static/style.css  →  /static/style.css
ui/custom/static/js/app.js  →  /static/js/app.js
ui/custom/static/img/logo.png  →  /static/img/logo.png
```

HTML-Referenz:
```html
<link rel="stylesheet" href="/static/style.css">
<script src="/static/js/app.js"></script>
<img src="/static/img/logo.png">
```

### UI-Verwaltungs-API

UI-Verwaltung über Settings-Seite oder API:

| Methode | Pfad | Beschreibung |
|---------|------|----------|
| GET | `/api/ui/list` | Installierte UI-Liste |
| POST | `/api/ui/switch` | Aktive UI wechseln (Neustart erforderlich) |
| POST | `/api/ui/install` | UI von URL installieren (nur localhost) |
| DELETE | `/api/ui/<name>/uninstall` | UI deinstallieren (nur localhost) |

### MCP-Tools

UI-Verwaltung auch über MCP (Model Context Protocol):

- `list_uis()` — Installierte UIs auflisten
- `switch_ui(name)` — Aktive UI wechseln
- `install_ui(url)` — UI von URL installieren
- `uninstall_ui(name)` — UI deinstallieren

