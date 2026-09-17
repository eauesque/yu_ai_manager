# Such API

APIs für Dateisuche, Vorschläge und gruppierte Anzeige.

## GET /api/search

Der Hauptdatei-Such-Endpunkt.

### Parameter

| Parameter | Typ | Standard | Beschreibung |
|-----------|------|---------|-------------|
| `q` | string | `""` | Suchanfrage (Text in Prompts, Tag-Namen) |
| `sort` | string | `"date"` | Sortierreihenfolge: `date`, `name`, `size`, `rating`, `random` |
| `order` | string | `"desc"` | `asc` / `desc` |
| `offset` | int | `0` | Pagination-Startposition |
| `limit` | int | `50` | Anzahl der Ergebnisse (max 200) |
| `cursor` | string | - | Token für cursor-basierte Pagination |
| `meta` | string | `"all"` | Metadatentyp: `all`, `a1111`, `nai`, `comfy`, `unknown` |
| `tags` | string | - | Tag-Filter (kommagetrennt) |
| `rating_min` | int | - | Minimale Bewertung (0-5) |
| `rating_max` | int | - | Maximale Bewertung (0-5) |
| `path` | string | - | Pfad-Präfix-Filter |
| `ext` | string | - | Erweiterungs-Filter (kommagetrennt, z.B. `png,webp`) |
| `has_prompt` | bool | - | Nach Prompt-Präsenz filtern |
| `collection_id` | int | - | Innerhalb einer Sammlung suchen |
| `favorites_only` | bool | `false` | Nur Favoriten |
| `group_by` | string | - | Gruppierung: `folder`, `conversation` |

### Antwort

```json
{
  "results": [
    {
      "id": 42,
      "path": "/images/output/00042.png",
      "filename": "00042.png",
      "size": 1234567,
      "mtime": 1709500000,
      "width": 1024,
      "height": 1536,
      "meta_type": "a1111_png",
      "model_name": "animagine-xl-3.1",
      "positive": "1girl, landscape, sunset",
      "negative": "low quality",
      "rating": 4,
      "is_favorite": true,
      "tags": ["landscape", "sunset"]
    }
  ],
  "total": 1500,
  "offset": 0,
  "limit": 50,
  "next_cursor": "eyJtdGltZSI6MTcwOTUwMDAwMCwiaWQiOjQyfQ=="
}
```

## GET /api/search-grouped

Suchergebnisse gruppiert nach Ordner/ZIP.

### Parameter

Die gleichen Abfrageparameter wie `/api/search`, plus:

| Parameter | Typ | Beschreibung |
|-----------|------|-------------|
| `group_limit` | int | Maximale Anzahl der Elemente pro Gruppe |

## GET /api/groups-index

Index der Ordner- und ZIP-Container-Gruppen. Wird für Gruppierung von Suchergebnissen verwendet.

### Parameter

| Parameter | Typ | Beschreibung |
|-----------|------|-------------|
| `sort` | string | Sortierreihenfolge: `name`, `count`, `date` |
| `order` | string | `asc` / `desc` |
| `offset` | int | Pagination-Startposition |
| `limit` | int | Anzahl der Ergebnisse |

## GET /api/group-members

Liste der Datei-IDs innerhalb eines angegebenen Containers.

### Parameter

| Parameter | Typ | Beschreibung |
|-----------|------|-------------|
| `key` | string | Container-Schlüssel (Ordnerpfad oder ZIP-Pfad) |

## GET /api/suggest

Automatische Vervollständigung für Tags und Prompts.

### Parameter

| Parameter | Typ | Beschreibung |
|-----------|------|-------------|
| `q` | string | Eingabetext |
| `limit` | int | Anzahl der Vorschläge (Standard 10) |

### Antwort

```json
{
  "suggestions": [
    { "value": "1girl", "count": 5432 },
    { "value": "1boy", "count": 1234 }
  ]
}
```

## GET /api/suggest/lora

LoRA-Modellname-Vorschläge.

### Parameter

| Parameter | Typ | Beschreibung |
|-----------|------|-------------|
| `q` | string | Eingabetext |
| `limit` | int | Anzahl der Vorschläge |

## GET /api/server-info

Grundlegende Server-Informationen.

### Antwort

```json
{
  "version": "4.12.1",
  "db_path": "/path/to/tags.db",
  "file_count": 150000,
  "tag_count": 8500,
  "auth_required": false,
  "lan_ip": "192.168.1.100",
  "active_ui": "default"
}
```
