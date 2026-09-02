# YU AI Manager Debug-Anleitung

## Schnellstart

```bash
# Alle Diagnosen ausführen
python debug_check.py

# DB angeben
python debug_check.py --db /path/to/tags.db

# Schnell-Check (ohne Syntax-/Extension-Check)
python debug_check.py --quick
```

---

## Häufige Probleme und Maßnahmen

### 1. config.json ist beschädigt (Backslash-Problem)

**Symptom:** JSONDecodeError beim Serverstart
**Ursache:** Bei manueller Eingabe von Windows-Pfaden werden `\U`, `\w` etc. zu ungültigen Escapes
**Maßnahme:** Wird beim Serverstart automatisch repariert. Für manuelle Reparatur:
```bash
python -c "
from core.config import safe_load_json
data = safe_load_json('config.json')
print('OK' if data else 'FAILED')
"
```

### 2. Bei scan-all werden bestimmte Ordner übersprungen

**Symptom:** Einige Ordner werden beim "Alle-Ordner-Scan" nicht verarbeitet
**Prüfschritte:**
```bash
# Inhalt von scan_roots prüfen
python -c "
import json
c = json.load(open('config.json'))
for i, r in enumerate(c.get('scan_roots', [])):
    print(f'  [{i}] repr={repr(r)} len={len(r)}')
"
```
**Prüfpunkte:**
- Ist der Pfad zu kurz (nur `\\wsl.localhost\`)?
- Ist am Ende ein `\` übrig?
- Gibt `os.path.exists(path)` True zurück?

### 3. QR-Teilen zeigt "Kein Inhalt"

**Symptom:** QR-Teilen-Button → Positive/Negative ist leer
**Mögliche Ursachen:**
1. Keine Einträge in der `templates`-Tabelle (meta_source=unknown)
2. Key-Mismatch in API-Response (in v2.7.0 behoben)

**Prüfung:**
```bash
# Template-Vorhandensein für Datei-ID prüfen
python -c "
import sqlite3
con = sqlite3.connect('tags.db')
file_id = 276323  # problematische ID
row = con.execute('SELECT * FROM templates WHERE file_id=?', (file_id,)).fetchone()
print('templates:', 'EXISTS' if row else 'MISSING')
meta = con.execute('SELECT meta_source FROM files WHERE id=?', (file_id,)).fetchone()
print('meta_source:', meta[0] if meta else 'NOT FOUND')
"
```

### 4. Scan-Fehler bei WSL/UNC-Pfaden

**Symptom:** Probe-Fehlschlag bei `\\wsl.localhost\...`-Pfaden
**Prüfung:**
```bash
python -c "
import os
path = r'\\\\wsl.localhost\\Ubuntu\\home\\user\\...'
print(f'exists: {os.path.exists(path)}')
print(f'isdir: {os.path.isdir(path)}')
print(f'repr: {repr(path)}')
print(f'len: {len(path)}')
"
```
**Hinweis:** `pathlib.Path.exists()` hat einen Bug mit WSL-UNC-Pfaden. `os.path.exists()` verwenden.

### 5. Extension wird nicht geladen

**Symptom:** Extension erscheint nicht in der Liste
**Prüfung:**
```bash
python debug_check.py  # Abschnitt Extension-Check ansehen
```
**Prüfpunkte:**
- Existiert `extension.json` oder `extension.yml`?
- Ist JSON/YAML gültig? (mit `safe_load_config` prüfen)
- Existiert das Feld `name`?

### 6. Durch PIN-Authentifizierung ausgesperrt

**Symptom:** 5 Fehlschläge → 60 Sek. Lockout
**Maßnahme:** 60 Sekunden warten. Oder Server neu starten zum Zurücksetzen.
**Prüfung:** Browser-DevTools → Network → Fehlermeldung in Response von `/_pin_check` prüfen

### 7. QR- / Bundle-Bugreport der 500er-Fehlerseite prüfen

**Symptom:** Gesamte Seite ergibt 500 und zeigt die spezielle Fehlerseite
**Zielgruppe:** Unbehandelte serverseitige Exceptions, vollständiger HTML-Seitenausfall

**Minimum-Prüfpunkte:**
- QR-Code wird auf dem Bildschirm angezeigt
- Button `Bundle JSON kopieren` wird angezeigt
- Button `Bundle herunterladen (.json.gz)` wird angezeigt
- Im per QR geöffneten `docs/bugreport.html` ist `AI Error Bundle` sichtbar

**Prüfschritte:**
```bash
# Zuerst Server normal starten
venv\Scripts\python.exe web_ui.py
```

1. Im Browser eine Aktion auslösen, die absichtlich 500 erzeugt
2. Prüfen, ob auf der 500-Seite QR und Bundle-Buttons erscheinen
3. `Bundle JSON kopieren` drücken und prüfen, ob im JSON `schema`, `error_id`, `request`, `error`, `state` enthalten sind
4. `Bundle herunterladen (.json.gz)` drücken und prüfen, ob `err_*.json.gz` gespeichert werden kann
5. QR mit Smartphone lesen oder die QR-URL im Browser öffnen, um zu `bugreport.html` zu navigieren
6. Auf der Relay-Page prüfen, ob der gesamte `AI Error Bundle`-Text sichtbar ist und beim Erstellen eines GitHub-Issues als Body eingefügt wird

**Worauf zu achten ist:**
- `bundle.error.class` und `bundle.error.message` nicht leer
- `bundle.request.path` stimmt mit der tatsächlichen Fehler-URL überein
- `bundle.error.frames` enthält file/line/function der Fehlerstelle
- `bundle.state.server_info` und `bundle.state.extensions` sind nicht leer
- Auch lange QR-Codes werden auf der Relay-Page dekodiert

**Eingrenzung:**
- QR wird angezeigt, aber die Relay-Page dekodiert nicht
  `core/web/error_bundle.py` pack/shrink und gzip-Decode in `docs/bugreport.html` prüfen
- Copy/Download-Button fehlt
  In `core/web/error_handlers.py` prüfen, ob `bundle_json` / `bundle_download_b64` ans Template übergeben wird
- Nur Download ist defekt
  In `ui/default/templates/error.html` base64-Decode und Erzeugung des `application/gzip`-Blobs prüfen

**Verwandte Dateien:**
- `core/web/error_bundle.py`
- `core/web/error_handlers.py`
- `ui/default/templates/error.html`
- `docs/bugreport.html`
- `docs/ja/features/qr-protocol-v1.md`

### 8. Client-Error-Reporter bei Teilfehlern auf der Seite prüfen

**Symptom:** Die Seite als Ganzes öffnet sich, aber Karten, Abschnitte oder API-Ladevorgänge schlagen fehl
**Zielgruppe:** `fetch` 4xx/5xx, Network-Errors, `window.error`, `unhandledrejection`, Tools-Page-Loader-Fehler

**Minimum-Prüfpunkte:**
- Unten rechts erscheint der Error-Reporter-Launcher
- Aus dem Launcher lässt sich das Modal öffnen
- Im Modal sind `Copy JSON` / `Download .json.gz` / `GitHub Issue` verwendbar
- Bundle enthält `X-Request-Id` und `ui_events`

**Prüfschritte:**
1. Eine Seite öffnen, die `apiFetch` verwendet
2. Absichtlich eine API, die 500 liefert, oder eine nicht existierende API ansprechen
3. Prüfen, ob der Launcher unten rechts erscheint
4. Modal öffnen und Bundle-JSON prüfen
5. Prüfen, ob `request.status`, `request.url`, `request.request_id`, `repro.ui_events` enthalten sind
6. `Download .json.gz` drücken und prüfen, ob das komprimierte Bundle gespeichert werden kann

**Prüfung in den Entwicklertools:**
- Im Network-Tab prüfen, ob die Response der fehlgeschlagenen API `X-Request-Id` im Header hat
- Wenn unhandled Exception in der Console: Gleicher Inhalt muss im Launcher-Bundle stehen
- Prüfen, ob `/api/error-report/enrich` 200 liefert und das angereicherte Bundle `state.server_info` und `artifacts.recent_logs` enthält

**Einfache Reproduktion:**
- Im Loader der Tools-Page absichtlich eine Exception werfen
- Zeitweise `apiFetch('/api/not-found-for-debug')` auf einen nicht existierenden Endpoint
- Auf Serverseite die Zielroute temporär durch `api_error(...)` oder Exception ersetzen

**Eingrenzung:**
- Trotz Fehler kein Launcher
  `src/ts/main/api-utils.ts` oder `src/ts/shared/error-reporter.ts` prüfen. Vermutlich läuft es nicht durch den gemeinsamen `apiFetch`
- Bundle enthält keine `request_id`
  In `core/web/request_hooks.py` prüfen, ob `X-Request-Id` an allen Responses gesetzt ist
- Auch nach Enrich fehlen Server-Informationen
  `routes/server_info.py` `/api/error-report/enrich` und `core/web/error_bundle.py` `enrich_error_bundle()` prüfen
- Nur Teilfehler der Tools-Page werden nicht erfasst
  `src/ts/tools-page/index.ts` `captureThrownError(...)`-Aufrufe prüfen

**Verwandte Dateien:**
- `src/ts/shared/error-reporter.ts`
- `src/ts/main/api-utils.ts`
- `src/ts/tools-page/index.ts`
- `src/ts/nav/index.ts`
- `core/web/request_hooks.py`
- `routes/server_info.py`
- `core/web/error_bundle.py`

---

## Debug-Logs lesen

### Server-Konsolenausgabe

```
[WARN] config.json had invalid escapes -- auto-repaired and saved
  → Automatische Backslash-Reparatur der config.json durchgeführt

[DEBUG] scan/start: raw=..., sanitized=...
  → Pfad zum Scan-Start (roh → sanitized)

[DEBUG] scan-all root 0: repr=..., len=...
  → Details zu jedem Root beim Alle-Ordner-Scan

[Scan] Auto-registered scan root: /path/to/dir
  → Auto-Registrierung bei erfolgreichem Scan

[DEBUG share] file_id=123, file_row=yes, tmpl=no
  → QR-Share-API: Datei existiert, aber kein Template

[ERROR] file.json: JSON parse failed: ...
  → Parse-Fehler in safe_load_json (App stürzt nicht ab)
```

---

## Dateistruktur und Debug-Ziele

```
web_ui.py          ← Entry Point (Serverstart)
core/
  config.py        ← Konfigurations-Management, safe_load_*
  server.py        ← PIN-Auth, QuickLock
  scanner.py       ← Scan-Engine
  extensions.py    ← Extension-Laden
  db.py            ← DB-Verbindungsverwaltung
  schema.py        ← Tabellendefinitionen
routes/
  scan.py          ← Scan-API
  search.py        ← Such-API
  share.py         ← QR-Share-API
  tools.py         ← Tools-API + Inspect-API
  debug.py         ← Debug-API
  pages.py         ← Seiten-Routing
  server_info.py   ← server-info / error-report enrich API
core/web/
  error_handlers.py ← 500-Fehlerseite + QR-Bugreport-Erzeugung
  error_bundle.py   ← Error-Bundle erzeugen / verkleinern / anreichern
  request_hooks.py  ← X-Request-Id-Injektion
ui/default/templates/
  error.html       ← Copy-/Download-UI der 500-Seite
static/js/
  main.js          ← Haupt-UI (Suche, Modal, QR, Tastatur)
  scan-banner.js   ← Scan-Fortschritt + Scroll-Top (alle Seiten)
src/ts/shared/
  error-reporter.ts ← Client-seitiger Error-Reporter für Teilfehler
```
