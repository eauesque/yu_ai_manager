# API di ricerca

API per la ricerca di file, suggerimenti e visualizzazione raggruppata.

## GET /api/search

L'endpoint di ricerca file principale.

### Parametri

| Parametro | Tipo | Predefinito | Descrizione |
|-----------|------|---------|-------------|
| `q` | string | `""` | Query di ricerca (testo nei prompt, nomi tag) |
| `sort` | string | `"date"` | Ordine di ordinamento: `date`, `name`, `size`, `rating`, `random` |
| `order` | string | `"desc"` | `asc` / `desc` |
| `offset` | int | `0` | Posizione di inizio della paginazione |
| `limit` | int | `50` | Numero di risultati (max 200) |
| `cursor` | string | - | Token per la paginazione basata su cursore |
| `meta` | string | `"all"` | Tipo di metadati: `all`, `a1111`, `nai`, `comfy`, `unknown` |
| `tags` | string | - | Filtro tag (separati da virgola) |
| `rating_min` | int | - | Valutazione minima (0-5) |
| `rating_max` | int | - | Valutazione massima (0-5) |
| `path` | string | - | Filtro del prefisso di percorso |
| `ext` | string | - | Filtro estensione (separati da virgola, es. `png,webp`) |
| `has_prompt` | bool | - | Filtra per presenza di prompt |
| `collection_id` | int | - | Ricerca all'interno di una raccolta |
| `favorites_only` | bool | `false` | Solo preferiti |
| `group_by` | string | - | Raggruppamento: `folder`, `conversation` |

### Risposta

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

Risultati di ricerca raggruppati per cartella/ZIP.

### Parametri

Gli stessi parametri di query di `/api/search`, più:

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `group_limit` | int | Numero massimo di elementi mostrati per gruppo |

## GET /api/groups-index

Indice di gruppi di cartelle e contenitori ZIP. Usato per raggruppare i risultati di ricerca.

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `sort` | string | Ordine di ordinamento: `name`, `count`, `date` |
| `order` | string | `asc` / `desc` |
| `offset` | int | Posizione di inizio della paginazione |
| `limit` | int | Numero di risultati |

## GET /api/group-members

Elenco di ID file all'interno di un contenitore specificato.

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `key` | string | Chiave contenitore (percorso cartella o percorso ZIP) |

## GET /api/suggest

Completamento automatico per tag e prompt.

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `q` | string | Testo di input |
| `limit` | int | Numero di suggerimenti (predefinito 10) |

### Risposta

```json
{
  "suggestions": [
    { "value": "1girl", "count": 5432 },
    { "value": "1boy", "count": 1234 }
  ]
}
```

## GET /api/suggest/lora

Suggerimenti dei nomi dei modelli LoRA.

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `q` | string | Testo di input |
| `limit` | int | Numero di suggerimenti |

## GET /api/server-info

Informazioni di base del server.

### Risposta

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
