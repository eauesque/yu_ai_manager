# Quellcode-Browsing API

Eine schreibgeschützte API zum Durchsuchen von Projekt-Quellcode.
Sie ist so gestaltet, dass MCP-Tools und externe AI-Agenten die Codebasis sicher anzeigen und durchsuchen können.

## Sicherheitsmodell

Drei Ebenen der Verteidigung gewährleisten Sicherheit:

### 1. Pfad-Normalisierung (Traversal-Prävention)

- Alle Pfade werden mit `os.path.realpath()` normalisiert und gegen das Projekt-Root über Präfix-Abgleich überprüft.
- Traversal-Angriffe wie `../../etc/passwd` oder `../../../Windows/System32` werden blockiert.
- Null-Byte-Injection (`\x00`) wird ebenfalls erkannt und abgelehnt.

### 2. Dateiextensions-Whitelist

Zulässige Dateiextensions zum Lesen:

| Kategorie | Erweiterungen |
|----------|-----------|
| Python | `.py` |
| TypeScript / JavaScript | `.ts`, `.js`, `.mjs`, `.tsx`, `.jsx` |
| Web | `.html`, `.css`, `.scss` |
| Konfiguration | `.json`, `.yaml`, `.yml`, `.toml`, `.cfg`, `.ini` |
| Dokumentation | `.md`, `.txt`, `.rst` |
| Scripts | `.sh`, `.bat`, `.cmd`, `.ps1` |
| Sonstiges | `.sql`, `.gitignore`, `.gitattributes`, `.editorconfig` |

Die folgenden Dateien ohne Extension sind speziell zulässig: `Dockerfile`, `Makefile`, `Procfile`, `VERSION`, `LICENSE`, `CHANGELOG`, `TODO`

### 3. Sensible Datei-Blocklist

Dateien, die den folgenden Mustern entsprechen, werden abgelehnt:

| Muster | Grund |
|---------|--------|
| `config.json`, `config_*.json` | Authentifizierungsdaten wie PIN und API-Schlüssel |
| `*.env`, `.env.*` | Umgebungsvariablen (Geheimnisse) |
| `secret.salt`, `*.key`, `*.pem`, `*.cert` | Verschlüsselungs-Schlüssel und Zertifikate |
| `credentials*`, `*token*`, `*secret*` | Authentifizierungsdaten |
| `*.db`, `*.sqlite*` | Datenbankdateien |
| `pnpm-lock.yaml`, `package-lock.json`, usw. | Lock-Dateien (große) |
| Bild-, Video-, Font- und Modelldateien | Binärdateien |

### Blockierte Verzeichnisse

`.git`, `__pycache__`, `node_modules`, `venv`, `dist`, `data`, `backups`, `screenshots`, `reports`, `src-tauri`

### Lesebeschränkungen

| Element | Limit |
|------|-------|
| Dateigröße | 1 MB |
| Linien pro Read | 2.000 |
| Baum-Traversal-Tiefe | 6 |
| Such-Ergebnisse | 50 |

---

## Endpunkte

### GET /api/source/tree

Ein Verzeichnisbaum abrufen.

#### Parameter

| Parameter | Typ | Standard | Beschreibung |
|-----------|------|---------|-------------|
| `path` | string | `""` (Root) | Relativer Pfad |
| `depth` | int | `3` | Traversal-Tiefe (1-6) |

#### Antwort

```json
{
  "ok": true,
  "root": ".",
  "depth": 3,
  "entries": [
    {
      "name": "core",
      "type": "dir",
      "path": "core",
      "children": [
        {
          "name": "source_core",
          "type": "dir",
          "path": "core/source_core",
          "children": [
            {
              "name": "source_browser.py",
              "type": "file",
              "path": "core/source_core/source_browser.py",
              "size": 8234
            }
          ]
        }
      ]
    },
    {
      "name": "web_ui.py",
      "type": "file",
      "path": "web_ui.py",
      "size": 3456
    }
  ]
}
```

- Verzeichnisse erscheinen zuerst, gefolgt von Dateien (sortiert nach Namen).
- `size` ist in Bytes (nur Dateien).
- `children` wird weggelassen, sobald die Traversal die angegebene `depth` erreicht.

---

### GET /api/source/read

Dateiinhalte mit Zeilennummern lesen.

#### Parameter

| Parameter | Typ | Standard | Beschreibung |
|-----------|------|---------|-------------|
| `path` | string | — (erforderlich) | Relativer Dateipfad |
| `offset` | int | `0` | Startzeilennummer (0-basiert) |
| `limit` | int | `2000` | Maximale Anzahl von Linien |

#### Antwort

```json
{
  "ok": true,
  "path": "core/source_core/source_browser.py",
  "total_lines": 250,
  "offset": 0,
  "limit": 2000,
  "content": "    1\t\"\"\"Source code browser...\n    2\t\n    3\timport os\n..."
}
```

- `content` verwendet das Format `{line_number}\t{line_content}`.
- Verwenden Sie `offset` + `limit`, um große Dateien zu paginieren.

#### Fehler-Beispiele

```json
{
  "ok": false,
  "error": "Diese Datei ist nicht zum Lesen berechtigt"
}
```

```json
{
  "ok": false,
  "error": "Zugriff außerhalb des Projekt-Roots ist untersagt"
}
```

---

### GET /api/source/search

Innerhalb von Quellcode nach Text suchen.

#### Parameter

| Parameter | Typ | Standard | Beschreibung |
|-----------|------|---------|-------------|
| `q` | string | — (erforderlich) | Suchtext (Mindestens 2 Zeichen) |
| `glob` | string | `""` (alle Dateien) | Dateinamen-Filter (z.B. `*.py`) |
| `limit` | int | `30` | Maximale Anzahl von Ergebnissen (1-50) |

#### Antwort

```json
{
  "ok": true,
  "query": "def source_tree",
  "glob": "*.py",
  "total": 2,
  "results": [
    {
      "file": "core/source_core/source_browser.py",
      "line": 120,
      "text": "def source_tree("
    },
    {
      "file": "routes/source_api.py",
      "line": 15,
      "text": "    result = source_tree(rel_path, depth_int)"
    }
  ]
}
```

- Die Suche ist Groß-/Kleinschreibung-unabhängig.
- `text` wird auf maximal 200 Zeichen gekürzt.

---

## MCP-Tools

| Tool | Beschreibung | Wichtige Parameter |
|------|-------------|----------------|
| `source_tree` | Verzeichnisbaum anzeigen | `path`: str = '', `depth`: int = 3 |
| `source_read` | Dateiinhalte lesen | `path`: str (erforderlich), `offset`: int = 0, `limit`: int = 2000 |
| `source_search` | Quellcode nach Text durchsuchen | `query`: str (erforderlich), `glob`: str = '', `limit`: int = 30 |

### Verwendungsbeispiele mit MCP

```
# Projektstruktur anzeigen
source_tree(path="", depth=2)

# Eine bestimmte Datei lesen
source_read(path="core/source_core/source_browser.py")

# Innerhalb der Codebasis suchen
source_search(query="def register_blueprints", glob="*.py")
```

### Umfang & Ratenumgrenzung

- **Scope Fence**: Verfügbar im `read_only`-Bereich (in allen Presets zulässig)
- **Budget Tracker**: `read`-Kategorie (keine Ratenumgrenzung)
- **HITL Gate**: Level 0 (keine Genehmigung erforderlich)

---

## Implementierungs-Dateien

| Datei | Rolle |
|------|------|
| `core/source_core/source_browser.py` | Sicherheitsschicht + Geschäftslogik |
| `routes/source_api.py` | Flask API Endpunkte (Blueprint) |
| `mcp_server/source_tools.py` | MCP-Tool-Registrierung |
