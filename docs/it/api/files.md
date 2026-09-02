# API File

API per il recupero dei dettagli del file, delle miniature e dei media originali.

## GET /api/file/<id>

Recupera i metadati dettagliati per un file.

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `id` | int | ID file (parametro di percorso) |

### Risposta

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

Immagine in miniatura (WebP). Supporta la memorizzazione nella cache ETag.

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `id` | int | ID file |
| `size` | int | Dimensione miniatura (predefinito 300) |

### Risposta

- Content-Type: `image/webp`
- Supporto ETag / If-None-Match (304 Not Modified)
- Cache: 24 ore

## GET /api/original/<id>

Trasmetti il file originale. Supporta anche i file dentro gli archivi ZIP.

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `id` | int | ID file |

### Risposta

- Content-Type: Tipo MIME del file
- Content-Disposition: `inline`
- Supporto Rich Request (per la ricerca video)

## POST /api/convert

Conversione del formato del prompt (A1111 <-> NAI).

### Richiesta

```json
{
  "prompt": "1girl, (masterpiece:1.2)",
  "direction": "a1111_to_nai"
}
```

### Risposta

```json
{
  "converted": "1girl, {{masterpiece}}",
  "direction": "a1111_to_nai"
}
```

## GET /api/container-thumb-ids

Elenco di ID miniature per un contenitore (cartella/ZIP), escludendo le voci già memorizzate nella cache.

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `keys` | string | Chiavi contenitore (separate da virgola) |
