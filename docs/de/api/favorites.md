# Favoriten API

API zum Hinzufügen, Entfernen, Überprüfen und Auflisten von Favoriten.

## POST /api/favorites/toggle

Wechsel Sie den Favoritenstatus einer Datei. Fügt die Datei hinzu, falls nicht bereits favorisiert; entfernt sie, falls bereits vorhanden.

- **Ratenumgrenzung**: WRITE

### Anfragekörper

| Parameter | Typ | Erforderlich | Beschreibung |
|-----------|------|----------|-------------|
| `file_id` | int | Ja | Zieldatei-ID (positive ganze Zahl) |
| `collection_id` | int | Nein | Sammlungs-ID (Standard: 1) |

```json
{
  "file_id": 42,
  "collection_id": 1
}
```

### Antwort

```json
{
  "file_id": 42,
  "collection_id": 1,
  "favorited": true
}
```

| Feld | Typ | Beschreibung |
|-------|------|-------------|
| `file_id` | int | Zieldatei-ID |
| `collection_id` | int | Sammlungs-ID |
| `favorited` | bool | Status nach Umschaltung. `true` = hinzugefügt, `false` = entfernt |

## GET /api/favorites/check

Gibt zurück, welche der angegebenen Datei-IDs favorisiert sind.

### Parameter

| Parameter | Typ | Erforderlich | Beschreibung |
|-----------|------|----------|-------------|
| `ids` | string | Ja | Kommagetrennte Datei-IDs (z.B. `1,2,3`) |
| `collection_id` | int | Nein | Nach einer bestimmten Sammlung filtern |

### Antwort

```json
{
  "favorites": [1, 3]
}
```

| Feld | Typ | Beschreibung |
|-------|------|-------------|
| `favorites` | int[] | Array von Datei-IDs, die favorisiert sind |

## GET /api/favorites/check_collections

Gibt die Sammlungs-IDs zurück, die die angegebene Datei enthalten.

### Parameter

| Parameter | Typ | Erforderlich | Beschreibung |
|-----------|------|----------|-------------|
| `file_id` | int | Ja | Zieldatei-ID |

### Antwort

```json
{
  "collections": [1, 3]
}
```

| Feld | Typ | Beschreibung |
|-------|------|-------------|
| `collections` | int[] | Array von Sammlungs-IDs, die diese Datei enthalten |

## GET /api/favorites/list

Ruft eine Liste mit favorisierten Datei-IDs ab. Ergebnisse werden nach Hinzufügungsdatum in absteigender Reihenfolge sortiert. Logisch gelöschte Dateien werden ausgeschlossen.

### Parameter

| Parameter | Typ | Erforderlich | Beschreibung |
|-----------|------|----------|-------------|
| `collection_id` | int | Nein | Nach einer bestimmten Sammlung filtern |

### Antwort

```json
{
  "ids": [42, 55, 67]
}
```

| Feld | Typ | Beschreibung |
|-------|------|-------------|
| `ids` | int[] | Array von favorisierten Datei-IDs (geordnet nach `added_at` DESC) |
