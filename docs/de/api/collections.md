# Sammlungen API

APIs zum Verwalten von Sammlungen (Favoritengruppen).

## GET /api/collections

Alle Sammlungen auflisten. Sortiert nach `sort_order` ASC, dann `id` ASC.

### Parameter

Keine

### Antwort

```json
{
  "collections": [
    {
      "id": 1,
      "name": "Favoriten",
      "sort_order": 0,
      "created_at": 1709500000,
      "count": 42,
      "is_smart": false,
      "query_json": null
    }
  ]
}
```

## POST /api/collections

Eine neue Sammlung erstellen.

### Ratenumgrenzung

WRITE

### Anfrage

```json
{
  "name": "Meine Sammlung",
  "query_json": null
}
```

| Parameter | Typ | Erforderlich | Beschreibung |
|-----------|------|----------|-------------|
| `name` | string | Ja | Sammlungsname |
| `query_json` | object/null | Nein | Abfrage für intelligente Sammlungen. Weglassen für normale Sammlungen |

### Antwort (201)

```json
{
  "id": 2,
  "name": "Meine Sammlung",
  "is_smart": false
}
```

## PUT /api/collections/<id>

Eine Sammlung umbenennen.

### Ratenumgrenzung

WRITE

### Parameter

| Parameter | Typ | Beschreibung |
|-----------|------|-------------|
| `id` | int | Sammlungs-ID (Pfad-Parameter) |

### Anfrage

```json
{
  "name": "Umbenannte Sammlung"
}
```

### Antwort

```json
{
  "id": 2,
  "name": "Umbenannte Sammlung"
}
```

## DELETE /api/collections/<id>

Eine Sammlung löschen. Alle Favoriteneinträge in der Sammlung werden ebenfalls gelöscht.

Die Standardsammlung (`id=1`) kann nicht gelöscht werden.

### Ratenumgrenzung

WRITE

### Parameter

| Parameter | Typ | Beschreibung |
|-----------|------|-------------|
| `id` | int | Sammlungs-ID (Pfad-Parameter) |

### Antwort

```json
{
  "deleted": 2
}
```

## POST /api/collections/reorder

Ändern Sie die Anzeigereihenfolge von Sammlungen.

### Ratenumgrenzung

WRITE

### Anfrage

```json
{
  "ids": [3, 1, 2]
}
```

| Parameter | Typ | Beschreibung |
|-----------|------|-------------|
| `ids` | int[] | Array von Sammlungs-IDs. Die angegebene Reihenfolge wird zur neuen Sortierreihenfolge |

### Antwort

```json
{
  "ok": true
}
```

## POST /api/collections/<id>/batch-add

Dateien in Bulk zu einer Sammlung hinzufügen. Idempotent: Einträge, die bereits vorhanden sind, werden übersprungen und als erfolgreich gezählt.

### Ratenumgrenzung

WRITE

### Parameter

| Parameter | Typ | Beschreibung |
|-----------|------|-------------|
| `id` | int | Sammlungs-ID (Pfad-Parameter) |

### Anfrage

```json
{
  "file_ids": [1, 2, 3]
}
```

| Parameter | Typ | Limit | Beschreibung |
|-----------|------|-------|-------------|
| `file_ids` | int[] | Max 500 | Array von Datei-IDs zum Hinzufügen |

### Antwort

```json
{
  "total": 3,
  "succeeded": 3,
  "failed": 0,
  "errors": []
}
```

## POST /api/collections/<id>/batch-remove

Dateien in Bulk aus einer Sammlung entfernen.

### Ratenumgrenzung

WRITE

### Parameter

| Parameter | Typ | Beschreibung |
|-----------|------|-------------|
| `id` | int | Sammlungs-ID (Pfad-Parameter) |

### Anfrage

```json
{
  "file_ids": [1, 2]
}
```

| Parameter | Typ | Limit | Beschreibung |
|-----------|------|-------|-------------|
| `file_ids` | int[] | Max 500 | Array von Datei-IDs zum Entfernen |

### Antwort

```json
{
  "total": 2,
  "succeeded": 2,
  "failed": 0,
  "errors": []
}
```

## GET /api/collections/<id>/export/csv

Dateien in einer Sammlung als CSV exportieren.

### Parameter

| Parameter | Typ | Beschreibung |
|-----------|------|-------------|
| `id` | int | Sammlungs-ID (Pfad-Parameter) |

### Antwort

- Content-Type: `text/csv; charset=utf-8`
- CSV-Spalten: `id`, `filename`, `folder`, `path`, `meta_source`, `mtime`, `positive`, `negative`
- Gibt 404 zurück, wenn Sammlung nicht gefunden
