# Dateien API

APIs zum Abrufen von Dateidetails, Miniaturen und ursprünglichen Medien.

## GET /api/file/<id>

Detaillierte Metadaten für eine Datei abrufen.

### Parameter

| Parameter | Typ | Beschreibung |
|-----------|------|-------------|
| `id` | int | Datei-ID (Pfad-Parameter) |

### Antwort

```json
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
  "positive": "1girl, landscape",
  "negative": "low quality",
  "steps": 28,
  "sampler": "Euler a",
  "cfg_scale": 7.0,
  "seed": 1234567890,
  "rating": 4,
  "is_favorite": true,
  "tags": ["landscape"],
  "collections": [1, 3],
  "hash_md5": "abc123...",
  "hash_phash": "def456...",
  "analysis": { "description": "A scenic landscape..." }
}
```

## GET /api/thumbnail/<id>

Miniaturbild (WebP). Unterstützt ETag-Caching.

### Parameter

| Parameter | Typ | Beschreibung |
|-----------|------|-------------|
| `id` | int | Datei-ID |
| `size` | int | Miniaturgröße (Standard 300) |

### Antwort

- Content-Type: `image/webp`
- ETag / If-None-Match-Unterstützung (304 Nicht geändert)
- Cache: 24 Stunden

## GET /api/original/<id>

Streamen Sie die ursprüngliche Datei. Unterstützt auch Dateien in ZIP-Archiven.

### Parameter

| Parameter | Typ | Beschreibung |
|-----------|------|-------------|
| `id` | int | Datei-ID |

### Antwort

- Content-Type: MIME-Typ der Datei
- Content-Disposition: `inline`
- Range-Request-Unterstützung (für Video-Suche)

## POST /api/convert

Prompt-Format-Konvertierung (A1111 <-> NAI).

### Anfrage

```json
{
  "prompt": "1girl, (masterpiece:1.2)",
  "direction": "a1111_to_nai"
}
```

### Antwort

```json
{
  "converted": "1girl, {{masterpiece}}",
  "direction": "a1111_to_nai"
}
```

## GET /api/container-thumb-ids

Liste der Miniaturen-IDs für einen Container (Ordner/ZIP), ohne bereits zwischengespeicherte Einträge.

### Parameter

| Parameter | Typ | Beschreibung |
|-----------|------|-------------|
| `keys` | string | Container-Schlüssel (kommagetrennt) |
