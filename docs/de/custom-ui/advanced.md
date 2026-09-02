# Erweiterte Anleitung — SSE, Batch-Operationen, Sicherheit

Erweiterte Funktionen und Implementierungsmuster für benutzerdefinierte UIs.

## Echtzeit-Updates (SSE)

Mit Server-Sent Events können Scan-Fortschritte, Favoriten-Änderungen, KI-Analyse-Fortschritte und mehr in Echtzeit empfangen werden.

### Verbindungsaufbau

EventSource kann in benutzerdefinierten UIs direkt verwendet werden (anders als in der Referenz-UI).

**Hinweis**: In der Referenz-UI (`ui/default/`) wird `window.EventSource` durch einen Proxy überschrieben. In benutzerdefinierten UIs gilt diese Einschränkung nicht.

### Wichtige Ereignisliste

| Ereignis | Daten | Verwendung in der UI |
|---------|--------|------------|
| `scan.progress` | `{ scanned, total, current_file }` | Fortschrittsbalken anzeigen |
| `scan.complete` | `{ added_count, updated_count }` | Suchergebnisse neu laden |
| `favorite.add` | `{ file_id, collection_id }` | Favoriten-Symbol aktualisieren |
| `favorite.remove` | `{ file_id, collection_id }` | Favoriten-Symbol aktualisieren |
| `collection.create` | `{ id, name }` | Sammlungsliste aktualisieren |

Alle Ereignistypen finden Sie unter [events.md](../api/events.md).

### Visibility-aware-Verbindung

Verbindung unterdrücken, wenn der Tab ausgeblendet ist, um Ressourcen zu sparen. Auf das `visibilitychange`-Event horchen und die SSE-Verbindung bei `document.hidden === true` trennen und bei Wiederherstellung neu aufbauen.

## Batch-Operationen

API-Muster für die gleichzeitige Ausführung von Operationen an mehreren Dateien.

### Massenbewertung

Endpunkt: `POST /api/ratings/batch-set`  
Body: `{ items: [{file_id, rating}, ...] }` (max. 500 Einträge)

### Massen-Tag-Operationen

Endpunkt: `POST /api/tags/batch-set`  
Body: `{ items: [{file_id, add: [...], remove: [...]}, ...] }`

### Massen-Sammlungsoperationen

- Hinzufügen: `POST /api/collections/<id>/batch-add` mit `{ file_ids: [...] }`
- Entfernen: `POST /api/collections/<id>/batch-remove` mit `{ file_ids: [...] }`

### Behandlung von Teilerfolgen

Batch-Operationen können teilweise erfolgreich sein. Die Antwort enthält `succeeded` und `failed`-Felder.

## Fehlerbehandlung

### HTTP-Statuscodes

| Code | Bedeutung | Maßnahme |
|--------|------|------|
| 200 | Erfolg | - |
| 304 | Not Modified | Cache verwenden (Thumbnails) |
| 400 | Ungültige Anfrage | Eingabe prüfen |
| 403 | Authentifizierungsfehler / CSRF-Fehler | `X-Requested-With`-Header prüfen |
| 404 | Ressource nicht gefunden | Datei-ID prüfen |
| 429 | Ratenbegrenzung | Sekunden aus `Retry-After`-Header warten |
| 500 | Server-Fehler | Wiederholen oder Logs prüfen |

### Antwortformatbestimmung

Es gibt zwei Antwortformate:
- Neues Format: `{ ok, error, data }`
- Altes Format: `{ success, message }`
- Direktes Datenformat (z.B. `results`)

## Sicherheit

### CSRF-Schutz

Alle Schreiboperationen (POST / PUT / DELETE) erfordern den Header `X-Requested-With: XMLHttpRequest`.

**Ausnahme**: API-Key-Anfragen mit `Authorization: Bearer sk_...`-Header benötigen keinen CSRF-Header.

### XSS-Prävention

Benutzereingaben und Dateinamen müssen vor dem Einfügen in das DOM bereinigt werden. Verwenden Sie `textContent` statt direkter HTML-Einbettung für nicht vertrauenswürdige Inhalte. Bei Bedarf DOM-API-Methoden (`createElement`, `appendChild`) nutzen.

### Umgang mit API-Schlüsseln

Schlüssel nicht clientseitig einbetten. Browser-basierte UIs verwenden normalerweise PIN/Session-Authentifizierung mit CSRF-Header-Schutz.

## Implementierung der Suchfunktion

### Grundlegende Suche

Endpunkt: `GET /api/search`  
Parameter: `q`, `limit`, `sort`, `cursor`, `rating_min`, `collection_id`, `favorites_only`

### Autovervollständigung

Endpunkt: `GET /api/suggest?q=<query>&limit=10`  
Rückgabe: `{ suggestions: [{value, count}, ...] }`

Debouncing empfohlen (z.B. 200ms), um unnötige Anfragen zu vermeiden.

### Sortieroptionen

Verfügbare Werte: `date`, `name`, `size`, `rating`, `random`

## Sammlungsverwaltung

- Liste: `GET /api/collections`
- Erstellen: `POST /api/collections` mit `{ name }`
- In Sammlung suchen: Suchparameter `collection_id` verwenden

## Prompt-Konvertierung

Endpunkt: `POST /api/convert`  
Body: `{ prompt, direction }` (direction: `"a1111_to_nai"` oder `"nai_to_a1111"`)

## Deployment

### Verteilung benutzerdefinierter UIs

1. **Git-Repository**: Auf GitHub o.ä. pushen → Über die Settings-UI installieren
2. **ZIP-Archiv**: Dateien zippen und Download-URL teilen
3. **Manuelle Platzierung**: Direkt in das Verzeichnis `ui/<name>/` kopieren

### Installation per API

```bash
curl -X POST http://localhost:5000/api/ui/install \
  -H "X-Requested-With: XMLHttpRequest" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://github.com/user/my-custom-ui.git"}'
```

### Anforderungen an manifest.json

```json
{
  "name": "my-custom-ui",
  "version": "1.0.0",
  "description": "A beautiful custom UI for YU AI Manager",
  "author": "Your Name",
  "api_version": "1"
}
```

- `name` und `version` sind Pflichtfelder
- `name` wird auch zum Verzeichnisnamen des Installationsorts
- `"default"` ist ein reservierter Name und darf nicht verwendet werden
