# YU AI Manager API-Referenz

Diese REST API-Dokumentation behandelt alle Funktionen von YU AI Manager und ist für benutzerdefinierte UIs und Skripte verfügbar.

## Allgemeine Konventionen

### Basis-URL

```
http://<host>:<port>
```

Standard: `http://127.0.0.1:5000`
Testumgebung: `http://127.0.0.1:5100` (mit `config_test.json`)

### Authentifizierung

Es werden vier Authentifizierungsmethoden unterstützt:

| Methode | Anwendungsfall | Header-Beispiel |
|---------|---------|----------------|
| PIN-Authentifizierung | Browser-Sitzungen | Cookie: `session=...` |
| API-Schlüssel | Maschine-zu-Maschine-Kommunikation | `Authorization: Bearer sk_...` |
| Vertrauenswürdiger Proxy | Hinter einem Reverse Proxy | `X-Remote-User: username` |
| LAN-Share-Token | Gastzugriff | URL-Pfad `/s/<token>/...` |

Es ist möglich, die Authentifizierung vollständig zu umgehen, indem Sie mit `config_test.json` starten (keine PIN).

### CSRF-Schutz

Alle `POST` / `PUT` / `DELETE`-Anfragen an `/api/`-Endpunkte erfordern den Header `X-Requested-With`:

```
X-Requested-With: XMLHttpRequest
```

**Ausnahme**: API-Schlüssel-Anfragen mit dem Header `Authorization: Bearer` benötigen CSRF nicht.

### Ratenumgrenzung

| Tier | Bereich | Rate | Burst |
|------|-------|------|-------|
| READ | Alle GET | Unbegrenzt | - |
| WRITE | POST/PUT/DELETE (Standard) | ~120 req/min | 30 |
| HEAVY | Ähnliche Suche, Hash-Berechnung, AI-Analyse, Scan | ~20 req/min | 5 |
| DESTRUCTIVE | Bereinigung, Hartlöschung, Cache-Löschung, Config-Schreiben | ~12 req/min | 3 |

Ein `Retry-After`-Header begleitet 429-Antworten.

### Antwortformat

**Erfolg** (neue APIs):
```json
{
  "ok": true,
  "error": null,
  "data": { ... }
}
```

**Fehler**:
```json
{
  "ok": false,
  "error": "Fehlermeldung",
  "code": "ERROR_CODE",
  "detail": "Zusätzliche Details (optional)"
}
```

Einige ältere APIs geben das Format `{ "success": true, "message": "..." }` zurück.

### Pagination

**Offset-basiert** (Standard):
```
GET /api/search?offset=0&limit=50
```

**Cursor-basiert** (für große Datenmengen):
```
GET /api/search?cursor=<opaque_token>&limit=50
```

Die Antwort enthält ein Feld `next_cursor`.

### Batch-Operationen

Batch-APIs unterstützen bis zu 500 Operationen pro Anfrage. Teilweiser Erfolg ist möglich:

```json
POST /api/ratings/batch-set
{
  "items": [
    { "file_id": 1, "rating": 5 },
    { "file_id": 999, "rating": 3 }
  ]
}
```

## API-Kategorien

| Dokument | Inhalt |
|----------|---------|
| [search.md](search.md) | Suche, Vorschläge, Gruppen |
| [files.md](files.md) | Dateidetails, Miniaturen, Medienabruf |
| [scan.md](scan.md) | Scan-Steuerung, Scan-Root-Verwaltung |
| [events.md](events.md) | SSE-Ereignisstrom |
| [theming.md](theming.md) | CSS-Variablen, Theme-Anpassung |
| [source.md](source.md) | Quellcode-Browsing (schreibgeschützt für MCP) |
| [github.md](github.md) | GitHub-Integration (Konten, Issues, PRs, Benachrichtigungen, Diskussionen, Releases) |
| [scheduler.md](scheduler.md) | Task Scheduler (Job-Verwaltung, Ausführungsverlauf) |
| [ratings.md](ratings.md) | Bewertungen (setzen, Batch-setzen, abrufen, Statistiken) |
| [favorites.md](favorites.md) | Favoriten (umschalten, prüfen, auflisten) |
| [collections.md](collections.md) | Sammlungen (CRUD, Neuanordnung, Batch-Add/Remove, CSV-Export) |
| [tags.md](tags.md) | Tags (Batch-setzen, Vorschlag) |
| [sns.md](sns.md) | SNS-Freigabe & Bluesky-Monitor (Posten, Benachrichtigungen, Triage, automatische Antwort) |
| [hailo-remote-tagger.md](hailo-remote-tagger.md) | Hailo Remote Tagger (Konfiguration, Einzel-/Batch-Tagging, Tag-CRUD) |
| [tagger-servers.md](tagger-servers.md) | Tagger-Server-Registry (verteilter Tag-Inferenz-Cluster, Server-Verwaltung, Batch-Ausführung) |
| [svg.md](svg.md) | SVG-Rasterisierung (SVG zu PNG/WebP-Konvertierung, img2img-Pipeline-Unterstützung) |
| [settings.md](settings.md) | Einstellungsverwaltung (Schema, Abrufen/Aktualisieren von Werten, Geheime Verschlüsselung, 1Password/Bitwarden-Integration) |
| [extensions.md](extensions.md) | Erweiterungen (auflisten, umschalten, konfigurieren, installieren, Sicherheit, Marketplace, Authoring) |
| [analysis.md](analysis.md) | AI-Analyse (Konfiguration, Einzel-/Batch-Analyse, Trend-Analyse, Statistiken, Server-Registry) |
| [system-update.md](system-update.md) | Systemupdate (Versionsprüfung, Update anwenden, einheitlicher Update-Manager) |
| [tools.md](tools.md) | Tools (Duplikat-Erkennung, Hash-Berechnung, ähnliche Suche, Cache-Verwaltung, Sicherung, Archiv-Cleanup, Debug-Log) |
| [agent.md](agent.md) | Agent Safety Gateway (Kill Switch, Circuit Breaker, Budget, Approval, Scope Fence, Undo, Anomaly Detection) |
| [profiles.md](profiles.md) | Profilmanagement (CRUD, Duplikat, QR-Export/Import) |
| [wd-tagger.md](wd-tagger.md) | WD-Tagger (Danbooru Auto-Tagging, Model-Verwaltung, VLM, XMP) |
| [ocr.md](ocr.md) | OCR (Texterkennung, Übersetzung, Video-/PDF-Unterstützung, Benchmarks, Profile) |
| [apikeys.md](apikeys.md) | API-Schlüsselverwaltung (erstellen, auflisten, Bereiche, widerrufen) |
| [debug.md](debug.md) | Debug (Metadaten-Inspektion, SQL-Abfrage, Model-Überprüfung) |
| [ui.md](ui.md) | UI-Verwaltung (auflisten, wechseln, installieren, deinstallieren) |
| [video-analysis.md](video-analysis.md) | Videoanalyse (Konfiguration, Status, Keyframe-Extraktion) |

## Schnellstart (curl)

```bash
# Suche (Umgebung ohne PIN)
curl "http://localhost:5100/api/search?q=landscape&limit=10"

# Eine Miniatur abrufen
curl "http://localhost:5100/api/thumbnail/42" -o thumb.webp

# Suche mit API-Schlüssel
curl -H "Authorization: Bearer sk_your_key_here" \
     "http://localhost:5100/api/search?q=portrait"

# Eine Bewertung setzen
curl -X POST "http://localhost:5100/api/ratings/set" \
     -H "X-Requested-With: XMLHttpRequest" \
     -H "Content-Type: application/json" \
     -d '{"file_id": 42, "rating": 5}'
```
