# Drag & Drop Datei-Registrierung

Ziehen Sie Image- oder Videodateien auf die Hauptbibliotheksseite (`/`), um sie in einem konfigurierten **Drop Inbox**-Verzeichnis zu speichern und automatisch in der Bibliothek zu registrieren. Der normale Scan-Pfad (`scan_one`) wird verwendet, sodass Metadaten-Extraktion, Miniaturansicht-Generierung und Tagging alle so ablaufen wie bei einem normalen Scan.

## Verhalten

1. Öffnen Sie die Hauptseite und ziehen Sie Dateien aus dem Datei-Explorer oder einem anderen Browser
2. Eine Überlagerung erscheint auf dem Fenster, die den Zielort (Drop Inbox) anzeigt
3. Beim Ablegen wird jede Datei in die Drop Inbox kopiert und registriert
4. Ein Toast zeigt die Anzahl der Erfolge und Fehler an

## Drop Inbox Auflösung

Die Drop Inbox wird in dieser Priorität aufgelöst:

1. `drop_inbox_dir` aus `config.json` (explizite Einstellung)
2. Falls nicht gesetzt: Das erste aktivierte Scan Root wird wie gehabt verwendet

**Einschränkung**: `drop_inbox_dir` **muss** innerhalb einer der `scan_roots`-Einträge leben. Alle Pfade außerhalb von Scan Roots werden mit HTTP 400 abgelehnt. Dies bewahrt die Invariante, dass Scan Roots die einzige Informationsquelle für Bibliotheksdateien sind.

## Konfigurationsbeispiel

```json
{
  "scan_roots": [
    { "path": "D:/Pictures/AI", "enabled": true, "recursive": true }
  ],
  "drop_inbox_dir": "D:/Pictures/AI/inbox"
}
```

Die `drop_inbox_dir` wird erstellt, falls sie nicht existiert (ihr übergeordnetes Verzeichnis muss weiterhin innerhalb von `scan_roots` sein).

## Behandlung von Namenszusammenstößen

Wenn eine Datei mit demselben Namen bereits in der Inbox existiert, werden automatisch Suffixe `_1`, `_2`, ... hinzugefügt. Vorhandene Dateien werden niemals überschrieben.

## Zulässige Erweiterungen

| Kategorie | Erweiterungen |
|---|---|
| Bilder | `.png` `.jpg` `.jpeg` `.webp` `.gif` `.bmp` `.tiff` `.tif` `.svg` |
| Videos | `.mp4` `.webm` `.mov` `.avi` `.mkv` `.m4v` |

Archive (`.zip` / `.7z` / `.rar`) werden **nicht** über Drag & Drop unterstützt. Legen Sie Archive direkt in ein Scan Root und führen Sie stattdessen einen regulären Scan durch.

## Einschränkungen

- Die Gesamtanfrage-Größe ist auf `MAX_CONTENT_LENGTH` begrenzt (Standard **100 MB**)
- Dateinamen mit Pfad-Traversal (`..`) werden abgelehnt
- Ein ganzes Verzeichnis zu ziehen wird derzeit nicht unterstützt (nur einzelne Dateien)

## HTTP-API

### `POST /api/dnd-upload`

Akzeptiert Multipart-Datei-Uploads, speichert sie in der Drop Inbox und registriert sie in der Bibliothek.

Antwort:

```json
{
  "ok": true,
  "total": 3,
  "success": 2,
  "results": [
    { "ok": true, "status": "added", "file_id": 12345, "path": "...", "filename": "a.png" },
    { "ok": true, "status": "skipped", "path": "...", "filename": "b.png" },
    { "ok": false, "code": "unsupported_type", "error": "...", "filename": "c.xyz" }
  ]
}
```

### `GET /api/dnd-inbox`

Gibt die derzeit aufgelöste Drop Inbox zurück, die die UI-Überlagerung anzeigt.

```json
{ "ok": true, "inbox": "D:/Pictures/AI/inbox", "explicit": true }
```

### `POST /api/files/register-path`

Registriert eine bereits auf der Festplatte vorhandene Datei per Pfad (kein Upload). Der Pfad muss innerhalb von `scan_roots` liegen. Wird vom `register_file` MCP-Tool verwendet.

```json
{ "path": "D:/Pictures/AI/inbox/a.png" }
```

## MCP-Tools

| Tool | Beschreibung |
|---|---|
| `register_file(path)` | Datei an absolutem Pfad in der Bibliothek registrieren |
| `drop_inbox_info()` | Derzeit aufgelöstes Drop Inbox-Verzeichnis zurückgeben |
