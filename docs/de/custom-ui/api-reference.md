# API-Referenz — Links für Custom-UI-Entwickler

Linksammlung zur API-Dokumentation für die Custom-UI-Entwicklung sowie eine Kurzübersicht der häufig verwendeten APIs.

## Dokumentationsübersicht

### Allgemeine Konventionen

- [API-Allgemeine-Konventionen](../api/README.md) — Basis-URL, Authentifizierung (4 Methoden), CSRF-Schutz, Ratenbegrenzung, Antwortformat, Paginierung

### Nach Endpunkt

- [Such-API](../api/search.md) — GET /api/search, Vorschläge, Gruppen, server-info
- [Datei-API](../api/files.md) — Dateidetails, Thumbnail, Original, Prompt-Konvertierung
- [Scan-API](../api/scan.md) — Scan-Steuerung, Scan-Root-Verwaltung, Hash-Backfill
- [Ereignis-API](../api/events.md) — SSE-Echtzeitereignisse, Log-Stream

### Themes

- [CSS-Variablen](../api/theming.md) — Theme-benutzerdefinierte Eigenschaften (Hell/Dunkel)

## Häufig verwendete API-Kurzübersicht

### Lesen (GET, keine Authentifizierung erforderlich*)

| Endpunkt | Zweck | Wichtige Parameter |
|--------------|------|---------------|
| `/api/search` | Dateisuche | `q`, `sort`, `limit`, `cursor`, `rating_min`, `collection_id` |
| `/api/thumbnail/<id>` | Thumbnail-Bild (WebP) | `size` (Standard 300) |
| `/api/original/<id>` | Originaldatei | Range-Anfragen unterstützt |
| `/api/file/<id>` | Dateidetails | — |
| `/api/suggest` | Tag-Vorschläge | `q`, `limit` |
| `/api/stats/all` | Statistikinformationen | — |
| `/api/collections` | Sammlungsliste | — |
| `/api/server-info` | Server-Informationen | — |
| `/api/events/stream` | SSE-Stream | `types` |

*Keine PIN-Umgebung oder bei bestehender Session-Authentifizierung

### Schreiben (POST, `X-Requested-With`-Header erforderlich)

| Endpunkt | Zweck | Beispiel-Body |
|--------------|------|---------|
| `/api/ratings/set` | Bewertung setzen | `{file_id: 42, rating: 5}` |
| `/api/ratings/batch-set` | Massenbewertung | `{items: [{file_id, rating}, ...]}` |
| `/api/favorites/add` | Zu Favoriten hinzufügen | `{file_id: 42}` |
| `/api/favorites/remove` | Aus Favoriten entfernen | `{file_id: 42}` |
| `/api/tags/batch-set` | Massen-Tag-Operationen | `{items: [{file_id, add: [], remove: []}]}` |
| `/api/collections` | Sammlung erstellen | `{name: "My Collection"}` |
| `/api/collections/<id>/batch-add` | Zur Sammlung hinzufügen | `{file_ids: [1, 2, 3]}` |
| `/api/scan-all` | Scan starten | `{}` |
| `/api/convert` | Prompt konvertieren | `{prompt, direction}` |

### UI-Verwaltung

| Endpunkt | Methode | Zweck |
|--------------|---------|------|
| `/api/ui/list` | GET | UI-Liste |
| `/api/ui/switch` | POST | UI wechseln |
| `/api/ui/install` | POST | UI installieren (nur localhost) |
| `/api/ui/<name>/uninstall` | DELETE | UI deinstallieren (nur localhost) |

## Antwortformate

### Suchergebnisse

```json
{
  "results": [
    {
      "id": 42,
      "path": "/images/00042.png",
      "filename": "00042.png",
      "width": 1024,
      "height": 1536,
      "meta_type": "a1111_png",
      "model_name": "animagine-xl-3.1",
      "positive": "1girl, landscape",
      "rating": 4,
      "is_favorite": true,
      "tags": ["landscape", "sunset"]
    }
  ],
  "total": 1500,
  "next_cursor": "base64token..."
}
```

`next_cursor: null` bedeutet letzte Seite.

### Thumbnails

```
GET /api/thumbnail/42
→ Content-Type: image/webp
→ ETag: "abc123"
→ Cache-Control: max-age=86400
```

Der Browser cached automatisch. Kann direkt mit dem `<img>`-Tag referenziert werden:

```html
<img src="/api/thumbnail/42" loading="lazy" alt="thumbnail">
```

### Fehlerantworten

```json
{
  "ok": false,
  "error": "Rate limit exceeded",
  "code": "RATE_LIMIT",
  "detail": "Retry after 5s"
}
```

## Hinweis zum CSRF-Header

```javascript
// Gemeinsame Header-Konstante
const API_HEADERS = {
  'Content-Type': 'application/json',
  'X-Requested-With': 'XMLHttpRequest',
};

// GET: kein Header erforderlich
fetch('/api/search?q=test');

// POST: X-Requested-With erforderlich
fetch('/api/ratings/set', {
  method: 'POST',
  headers: API_HEADERS,
  body: JSON.stringify({ file_id: 42, rating: 5 }),
});
```
