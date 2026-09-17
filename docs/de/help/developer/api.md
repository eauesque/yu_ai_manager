# API-Übersicht

YU AI Manager bietet eine REST-API, mit der alle WebUI-Operationen programmatisch ausgeführt werden können.
Es gibt mehr als 320 Endpunkte, die von der Bildverwaltung bis zur KI-Analyse abdecken.

> **Tipp**: Für detaillierte allgemeine Konventionen (Authentifizierung, CSRF, Ratenbegrenzung, Antwortformat) siehe den Abschnitt "API-Referenz".

## Authentifizierung

4 Authentifizierungstypen werden unterstützt.

| Methode | Verwendung | Header/Parameter |
|------|------|-------------------|
| PIN-Authentifizierung | Browser-Session | Anmeldung über `/_pin` → Session-Cookie |
| API-Schlüssel | Maschine-zu-Maschine / MCP | `Authorization: Bearer sk_xxxx` |
| Trusted Proxy | Reverse Proxy | `X-Remote-User`-Header |
| LAN Share-Token | Gastzugriff | `/s/<token>`-Pfad |

### curl-Testbeispiele

```bash
# API-Schlüssel-Authentifizierung (kein CSRF-Header erforderlich)
curl -H "Authorization: Bearer sk_your_key" \
     http://localhost:5000/api/search?tags=1girl

# PIN-Authentifizierungsumgebung erfordert 2 Schritte
# 1. CSRF-Token abrufen
curl -c cookies.txt http://localhost:5000/_pin
# 2. PIN senden
curl -b cookies.txt -X POST \
     -H "X-Requested-With: XMLHttpRequest" \
     -d "pin=1234" http://localhost:5000/_pin_check
```

### CSRF-Schutz

Alle POST/PUT/DELETE-`/api/`-Endpunkte erfordern den `X-Requested-With`-Header.
Bei Bearer-API-Schlüssel-Anfragen nicht erforderlich.

## Hauptendpunkte

### Bildsuche und Durchsuchen

| Methode | Pfad | Beschreibung |
|---------|------|------|
| GET | `/api/search` | Filtersuche nach Tags, Datum, Bewertung usw. |
| GET | `/api/search-grouped` | Gruppensuche nach Ordner/ZIP |
| GET | `/api/file/<id>` | Bild-Detailmetadaten abrufen |
| GET | `/api/thumbnail/<id>` | Thumbnail abrufen (WebP, ETag-Cache) |
| GET | `/api/original/<id>` | Originalbild abrufen (Range-Anfragen unterstützt) |
| GET | `/api/suggest` | Tag-Vervollständigungsvorschläge |

### Bewertungen, Tags und Annotationen

| Methode | Pfad | Beschreibung |
|---------|------|------|
| POST | `/api/ratings/batch-set` | Massenbewertung setzen |
| POST | `/api/tags/batch-set` | Tags massenweise bearbeiten |
| POST | `/api/annotations/batch-set` | Annotationen massenweise setzen |
| GET | `/api/annotations/<id>` | Annotationen abrufen |
| GET | `/api/annotations/search` | Annotationen suchen |

### Sammlungen

| Methode | Pfad | Beschreibung |
|---------|------|------|
| GET | `/api/collections` | Sammlungsliste |
| POST | `/api/collections` | Sammlung erstellen |
| PUT | `/api/collections/<id>` | Sammlung umbenennen |
| DELETE | `/api/collections/<id>` | Sammlung löschen |
| POST | `/api/collections/<id>/batch-add` | Dateien massenweise hinzufügen |
| POST | `/api/collections/<id>/batch-remove` | Dateien massenweise löschen |

### Scannen

| Methode | Pfad | Beschreibung |
|---------|------|------|
| POST | `/api/scan/start` | Scan starten |
| GET | `/api/scan/status` | Scan-Fortschritt abrufen |
| POST | `/api/scan/cancel` | Scan abbrechen |
| POST | `/api/scan/resume` | Unterbrochenen Scan fortsetzen |
| GET | `/api/scan-roots` | Scan-Root-Liste |
| POST | `/api/scan-roots` | Scan-Root hinzufügen |

### KI-Analyse

| Methode | Pfad | Beschreibung |
|---------|------|------|
| POST | `/api/analysis/analyze/<id>` | KI-Bildanalyse ausführen |
| GET | `/api/analysis/result/<id>` | Analyseergebnis abrufen |
| POST | `/api/analysis/batch` | Batch-Analyse |
| POST | `/api/wd-tagger/tag/<id>` | WD-Tagger-Inferenz |
| POST | `/api/wd-tagger/batch` | WD-Tagger-Batch-Inferenz |
| POST | `/api/analysis/batch/cancel` | KI-Analyse-Batch abbrechen |
| POST | `/api/wd-tagger/batch/cancel` | WD-Tagger-Batch abbrechen |
| POST | `/api/tagger-servers/batch/cancel` | Tagger-Cluster-Batch abbrechen |
| POST | `/api/ocr/<id>` | OCR ausführen |

### Einstellungen

| Methode | Pfad | Beschreibung |
|---------|------|------|
| GET | `/api/settings/schema` | Einstellungsschema abrufen |
| GET | `/api/settings/all` | Alle Einstellungswerte abrufen |
| GET | `/api/settings/<key>` | Einstellungswert abrufen |
| PUT | `/api/settings/<key>` | Einstellungswert aktualisieren |

### Extension-Verwaltung

| Methode | Pfad | Beschreibung |
|---------|------|------|
| GET | `/api/extensions` | Extension-Liste |
| POST | `/api/extensions/<name>/toggle` | Aktivieren/Deaktivieren umschalten |
| POST | `/api/extensions/install` | Aus Git-Repository installieren |
| DELETE | `/api/extensions/<name>/uninstall` | Deinstallieren |

### Agent-Sicherheitsmechanismus

| Methode | Pfad | Beschreibung |
|---------|------|------|
| POST | `/api/agent/kill` | Kill Switch aktivieren |
| POST | `/api/agent/resume` | Kill Switch deaktivieren |
| GET | `/api/agent/status` | Sicherheitsmechanismus-Status |
| GET | `/api/agent/journal` | Operationsjournal |
| POST | `/api/agent/undo/<journal_id>` | Operation rückgängig machen |

## Antwortformat

Alle APIs antworten in einem einheitlichen JSON-Format.

```json
{
  "ok": true,
  "data": { ... },
  "error": null
}
```

Bei Fehler:

```json
{
  "ok": false,
  "data": null,
  "error": "Fehlermeldung"
}
```

## Ratenbegrenzung

3-Tier-Token-Bucket-System.

| Tier | Ziel | Limit | Burst |
|--------|------|------|---------|
| READ | Alle GET-Anfragen | Unbegrenzt | - |
| WRITE | POST/PUT/DELETE | ~120 req/min | 30 |
| HEAVY | Ähnlichkeitssuche, KI-Analyse, Scan | ~20 req/min | 5 |
| DESTRUCTIVE | purge, hard-delete, Konfigurationsschreiben | ~12 req/min | 3 |

Bei Überschreitung wird HTTP 429 zurückgegeben. `Retry-After`-Header gibt Wartezeit in Sekunden an.

## SSE (Server-Sent Events)

Echtzeitereignisse werden per SSE von `/api/events/stream` geliefert.
Details im Abschnitt "SSE-Ereignisse".

> **Hinweis**: Maximal 10 simultane Verbindungen pro IP. Upload-Größenlimit 100 MB.

## Interne Designdokumente

Detaillierte Designentscheidungen zur API, SQLite-Leistungsoptimierung, DB-Schema-Design und andere Entwicklungserkenntnisse sind über den [MD Viewer](/ext/md-viewer/) zugänglich.
