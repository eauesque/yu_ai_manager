# Debugging-Handbuch

Ein umfassendes Handbuch zum Debuggen von YU AI Manager.
Leitfaden für Entwickler und KI-Agenten zur effizienten Fehlersuche und -behebung.

---

## Inhaltsverzeichnis

1. [Server starten](#server-starten)
2. [Debug-Logs](#debug-logs)
3. [Tests ausführen](#tests-ausführen)
4. [DB-Debugging](#db-debugging)
5. [Authentifizierung testen](#authentifizierung-testen)
6. [MCP-Debugging](#mcp-debugging)
7. [Frontend-Debugging](#frontend-debugging)
8. [Umgebungsvariablen](#umgebungsvariablen)
9. [Häufige Fehler und Lösungen](#häufige-fehler-und-lösungen)
10. [Performance-Debugging](#performance-debugging)

---

## Server starten

### Zur Verifizierung (empfohlen)

Ohne PIN, lokales Binding — Grundform für Tests und Debugging.

```bash
source venv/Scripts/activate  # Windows Git Bash
python web_ui.py --db ./tags.db --config config_test.json --port 5100
```

`config_test.json` erstellen (falls nicht vorhanden):

```json
{
  "scan_roots": [],
  "server": {
    "host": "127.0.0.1",
    "port": 5100,
    "lan": false
  },
  "extract_a1111": true,
  "extract_comfyui": true,
  "lowercase_tags": true,
  "compute_hash": false,
  "enable_fts": true,
  "extensions": {}
}
```

### Produktionsäquivalent (LAN-öffentlich)

```bash
python web_ui.py --db ./tags.db --host 0.0.0.0 --port 5000 --pin 1234
```

> **Hinweis**: Bei `0.0.0.0`-Binding ist PIN Pflicht.

### CLI-Optionen

| Option | Typ | Standard | Beschreibung |
|-----------|-----|----------|------|
| `--db` | Pfad | `data/tags.db` | SQLite-DB-Dateipfad |
| `--config` | Pfad | `config.json` | Konfigurationsdateipfad |
| `--host` | str | `127.0.0.1` | Bind-Adresse |
| `--port` | int | 5000 | Bind-Port |
| `--lan` | Flag | - | Bind an `0.0.0.0` |
| `--pin` | str | - | PIN-Authentifizierung aktivieren |
| `--debug` | Flag | - | Quart-Debug-Modus |
| `--debug-log` | `on`/`off` | - | Debug-Log aktivieren |
| `--allow-restart` | Flag | - | `/api/server/restart` aktivieren |

---

## Debug-Logs

### Aktivierung

```bash
# CLI
python web_ui.py --db ./tags.db --debug-log on

# Umgebungsvariable
export TAGDB_DEBUG=1
python web_ui.py --db ./tags.db
```

### Log-Format

```
[DEBUG] 2026-03-15 12:34:56 | scan:prepare | counting_start | root=/path/to/dir, recursive=True
```

Format: `[DEBUG] Zeitstempel | Quelle | Ereignisname | key=value, ...`

### Echtzeit-Überwachung

```bash
# Datei tailing
tail -f logs/debug.log

# Per API abrufen
curl http://127.0.0.1:5100/api/debug/logs
```

---

## Tests ausführen

### Unit-Tests

```bash
source venv/Scripts/activate
python -m pytest tests/test_basic.py -v
python -m pytest tests/test_basic.py::TestImports -v
python -m pytest tests/test_basic.py -x  # Bei Fehler stoppen
```

### API-Integrationstests

```bash
python -m pytest tests/api/ -v
```

### Playwright-Browser-Tests

```bash
# 1. Server starten
python web_ui.py --db ./tags.db --config config_test.json --port 5100 &

# 2. Tests ausführen
TARGET_URL=http://localhost:5100 python -m pytest tests/test_webui_browser.py -v
```

### Test-Strategie

1. Tests zuerst ausführen, um aktuellen Fehlerzustand zu verstehen
2. Screenshots fehlgeschlagener Tests überprüfen
3. Korrekturen minimal halten
4. Nach Korrektur erneut testen

---

## DB-Debugging

### Schema-Version prüfen

```bash
python -c "
import sqlite3
con = sqlite3.connect('data/tags.db')
v = con.execute('SELECT MAX(version) FROM schema_version').fetchone()[0]
print(f'Schema version: {v}')
"
```

### DB-Integritätsprüfung

```bash
python db_health.py --db ./tags.db
```

### Häufig verwendete Debugging-Abfragen

```sql
-- Dateianzahl nach Quelle
SELECT meta_source, COUNT(*) as cnt FROM files WHERE is_deleted=0 GROUP BY meta_source;

-- Modellnutzungs-Ranking
SELECT model_name, COUNT(*) as cnt FROM templates GROUP BY model_name ORDER BY cnt DESC LIMIT 20;

-- Verwaiste Tags
SELECT t.id, t.name FROM tags t LEFT JOIN file_tags ft ON t.id=ft.tag_id WHERE ft.tag_id IS NULL;

-- Doppelte Pfade
SELECT path, COUNT(*) as cnt FROM files GROUP BY path HAVING cnt > 1;
```

### DB-Verbindungstypen

| Funktion | Zweck | Verwendungsfall |
|------|------|---------|
| `get_readonly_db()` | Nur-Lese | GET-APIs, Suche, Statistiken |
| `get_db()` | Schreibbar (Row-Factory) | POST/PUT/DELETE-APIs |
| `get_raw_db()` | Schreibbar (kein Row-Factory) | Batch, Scan, Migration |

> **Wichtig**: Lese-APIs müssen `get_readonly_db()` verwenden, um Write-Lock-Konflikte zu vermeiden.

---

## Authentifizierung testen

### PIN überspringen

`config_test.json` ohne PIN starten überspringt alle Authentifizierung.

### API-Schlüssel testen

```bash
curl -H "Authorization: Bearer sk_xxxxxxxxxxxxxx" \
  http://127.0.0.1:5000/api/stats/all
```

### API-Schlüssel-Bereiche

Ab v4.8.1 dürfen Schlüssel ohne Bereich nur lesen.

| Bereich | Erlaubte Operationen |
|---------|--------------|
| `read` | Suche, Dateidetails, Thumbnails, Statistiken |
| `rate` | Bewertungen setzen/abrufen/Batch |
| `tag.write` | Tags hinzufügen/löschen |
| `collection.write` | Sammlungs-CRUD, Favoriten |
| `annotate` | Annotationen lesen/schreiben |
| `scan` | Scan starten/stoppen |
| `admin` | Schlüssel-Verwaltung, Einstellungen, Backup |

---

## MCP-Debugging

### MCP-Server starten

```bash
source venv/Scripts/activate
python -m mcp_server
```

### Debug-Tools aktivieren

```bash
export YU_DEBUG_MODE=1
export YU_BASE_URL=http://127.0.0.1:5100
export YU_API_KEY=sk_...
python -m mcp_server
```

### MCP-Debug-Tool-Liste

Mit `YU_DEBUG_MODE=1` werden 9 Debug-Tools registriert:

| Tool | Zweck |
|--------|------|
| `debug_health_check` | Server/DB/Tabellen-Lebendprüfung |
| `debug_validate_counts` | API-Statistiken und DB-Zähler abgleichen |
| `debug_validate_search` | Such-API-Regressionsverifizierung |
| `debug_validate_collection` | Sammlungs-Zähler-Konsistenz |
| `debug_validate_annotations` | Annotationstabellen-Konsistenz |
| `debug_sample_files` | Zufällige Stichprobe für Feldanalyse |
| `debug_roundtrip_test` | annotation/rating/tag-Roundtrip-Test |
| `debug_readonly_query` | Beliebige SELECT-Abfrage |
| `debug_full_report` | Alle Beobachtungs-Tools als Gesamtbericht |

---

## Extension-Sicherheitsscan

Extensions werden beim Laden automatisch gescannt.

### Scan-Ablauf

```
1. ManifestAuthority.review()   — Manifest-Prüfung
2. CodeVerifier.verify()        — AST-Statische Analyse
3. Benutzergenehmigungsprüfung — Berechtigungen genehmigen/ablehnen
4. Capability-Token ausstellen
```

### Was CodeVerifier erkennt

| Kategorie | Erkennungsziel | Schweregrad |
|---------|---------|----------|
| Gefährliche Module | `subprocess`, `ctypes`, `importlib` | block |
| Direkter DB-Zugriff | `import sqlite3` | block |
| Netzwerk | `requests`, `urllib`, `httpx`, `aiohttp`, `socket` | warn |
| Dynamische Code-Ausführung | `eval()`, `exec()`, `__import__()`, `compile()` | block |

### Vertrauensstufen

| Stufe | Bedingung | Einschränkungen |
|--------|------|------|
| L0 Trusted | `builtin-`-Präfix | Keine |
| L1 Verified | Signaturverifiziert | Nur deklarierte Berechtigungen |
| L2 Untrusted | Manuell installiert | Berechtigungen + Benutzergenehmigung |

---

## Frontend-Debugging

### TypeScript-Build

```bash
pnpm run build        # Bundle mit esbuild
pnpm run typecheck    # Nur Typprüfung
```

### SSE-Shared-Engine

`window.EventSource` ist durch Proxy überschrieben. Für Ereignisse `window.sseSubscribe()` verwenden.

### i18n-Debugging

```javascript
window.setLang('de');  // Sprachwechsel
console.log(window.tr('search.count.normal', { count: 5 }));
```

---

## Umgebungsvariablen

### Debugging / Logging

| Variable | Standard | Beschreibung |
|------|----------|------|
| `TAGDB_DEBUG` | `0` | Strukturiertes Debug-Log (`1` = aktiviert) |
| `TAGDB_DEBUG_LOG` | `logs/debug.log` | Log-Dateipfad |
| `TAGDB_DEBUG_LOG_MAX_MB` | `10` | Log-Rotationsgröße (MB) |
| `TAGDB_DEBUG_STDOUT` | `1` | Logs an stderr ausgeben |

### MCP

| Variable | Beschreibung |
|------|------|
| `YU_DEBUG_MODE` | `1` = 9 Debug-Tools registrieren |
| `YU_BASE_URL` | Basis-URL für MCP-Clients |
| `YU_API_KEY` | API-Schlüssel für MCP-Clients |

---

## Häufige Fehler und Lösungen

### Server-Start

| Fehler | Ursache | Lösung |
|--------|------|------|
| `Address already in use` | Port belegt | `--port 5200` |
| `database is locked` | DB-Lock-Konflikt | DB-Netzwerkpfad prüfen |
| `--pin is required` | LAN ohne PIN | `--pin <Zahl>` setzen |
| `ModuleNotFoundError` | venv nicht aktiviert | `source venv/Scripts/activate && uv pip install -r requirements.txt` |

### Authentifizierung

| Fehler | Ursache | Lösung |
|--------|------|------|
| PIN-Seite wiederholt | Cookie-Fehler | Browser-Cookies prüfen |
| `CSRF header missing` (403) | `X-Requested-With` fehlt | Header hinzufügen |
| API-Schlüssel abgelehnt | Bereich fehlt | Erforderlichen Bereich zuweisen |

### DB

| Fehler | Ursache | Lösung |
|--------|------|------|
| `no such table: schema_version` | Erster Start | Automatisch erstellt, ignorieren |
| `SQLITE_BUSY` (Timeout) | Langer Transaktionsblock | Lese-API auf `get_readonly_db()` prüfen |

---

## Performance-Debugging

### Viewer-Blockierung während des Scans

**Symptom**: Bildanzeige stoppt für 5-10 Sekunden

**Ursache**: Lese-API verwendete `get_db()` statt `get_readonly_db()`

### Debug-Log-Analyse

```bash
# Einträge > 120 Sekunden
grep "per-entry.*120" logs/debug.log

# Lock-Konflikte
grep "SQLITE_BUSY" logs/debug.log
```

---

## Verwandte Dokumente

| Dokument | Speicherort |
|-------------|------|
| DB-Lese-/Schreib-Trennung | `docs/development/development_docs/SQLITE_READONLY_SEPARATION.md` |
| Fehlerformat | `docs/development/development_docs/ERROR_HANDLING.md` |
| Cross-Platform | `docs/development/development_docs/CROSS_PLATFORM_ISSUES.md` |
| MCP-Debug-Tools | `docs/development/development_docs/MCP_DEBUG_TOOLS.md` |
| QA-Übergabe | `docs/development/development_docs/QA_HANDOFF.md` |
