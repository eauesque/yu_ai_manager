# Bewertungen API

API zum Verwalten von Dateibewertungen (1-5-Stern-Bewertungen): Setzen, Abrufen und Anzeigen von Statistiken.

## POST /api/ratings/set

Legen Sie eine Bewertung für eine Datei fest. Geben Sie `rating=0` an, um die Bewertung zu löschen.

**Ratenumgrenzung**: WRITE

### Anfrage

```json
{
  "file_id": 42,
  "rating": 5
}
```

| Parameter | Typ | Erforderlich | Beschreibung |
|-----------|------|----------|-------------|
| `file_id` | int | Ja | Datei-ID (positive ganze Zahl) |
| `rating` | int | Ja | Bewertungswert (0–5). 0 löscht die Bewertung |

### Antwort

```json
{
  "file_id": 42,
  "rating": 5
}
```

## POST /api/ratings/batch-set

Legen Sie Bewertungen für mehrere Dateien auf einmal fest.

**Ratenumgrenzung**: WRITE

### Anfrage

```json
{
  "items": [
    { "file_id": 1, "rating": 5 },
    { "file_id": 2, "rating": 3 }
  ]
}
```

| Parameter | Typ | Erforderlich | Beschreibung |
|-----------|------|----------|-------------|
| `items` | array | Ja | Liste der Bewertungseinträge (max 500) |
| `items[].file_id` | int | Ja | Datei-ID (positive ganze Zahl) |
| `items[].rating` | int | Ja | Bewertungswert (0–5) |

### Antwort

```json
{
  "total": 2,
  "succeeded": 2,
  "failed": 0,
  "errors": []
}
```

## GET /api/ratings/get

Rufen Sie die Bewertung für eine Datei ab. Gibt `rating: 0` zurück, wenn die Datei nicht bewertet ist.

### Parameter

| Parameter | Typ | Erforderlich | Beschreibung |
|-----------|------|----------|-------------|
| `file_id` | int | Ja | Datei-ID (Abfrageparameter) |

### Antwort

```json
{
  "file_id": 42,
  "rating": 5
}
```

> **Hinweis**: Nicht bewertete Dateien geben `rating: 0` zurück.

## POST /api/ratings/batch

Rufen Sie Bewertungen für mehrere Dateien auf einmal ab.

### Anfrage

```json
{
  "file_ids": [1, 2, 3]
}
```

| Parameter | Typ | Erforderlich | Beschreibung |
|-----------|------|----------|-------------|
| `file_ids` | array | Ja | Liste von Datei-IDs |

### Antwort

```json
{
  "ratings": {
    "1": 5,
    "3": 4
  }
}
```

> **Hinweis**: Nur bewertete Dateien erscheinen in der Zuordnung. Nicht bewertete Dateien werden aus der Antwort weggelassen.

## GET /api/ratings/stats

Rufen Sie Bewertungsstatistiken für alle Dateien ab.

### Parameter

Keine.

### Antwort

```json
{
  "total_rated": 1234,
  "distribution": {
    "1": 50,
    "2": 100,
    "3": 300,
    "4": 500,
    "5": 284
  }
}
```

| Feld | Typ | Beschreibung |
|-------|------|-------------|
| `total_rated` | int | Gesamtanzahl der bewerteten Dateien |
| `distribution` | object | Dateianzahl pro Bewertungswert (1–5) |
