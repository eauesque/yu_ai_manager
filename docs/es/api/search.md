# API de Búsqueda

APIs para búsqueda de archivo, sugerencias y visualización agrupada.

## GET /api/search

El endpoint principal de búsqueda de archivo.

### Parámetros

| Parámetro | Tipo | Predeterminado | Descripción |
|-----------|------|---------|-------------|
| `q` | string | `""` | Consulta de búsqueda (texto en prompts, nombres de etiqueta) |
| `sort` | string | `"date"` | Orden de clasificación: `date`, `name`, `size`, `rating`, `random` |
| `order` | string | `"desc"` | `asc` / `desc` |
| `offset` | int | `0` | Posición de inicio de paginación |
| `limit` | int | `50` | Número de resultados (máx 200) |
| `cursor` | string | - | Token para paginación basada en cursor |
| `meta` | string | `"all"` | Tipo de metadatos: `all`, `a1111`, `nai`, `comfy`, `unknown` |
| `tags` | string | - | Filtro de etiqueta (separado por comas) |
| `rating_min` | int | - | Calificación mínima (0-5) |
| `rating_max` | int | - | Calificación máxima (0-5) |
| `path` | string | - | Filtro de prefijo de ruta |
| `ext` | string | - | Filtro de extensión (separado por comas, p. ej., `png,webp`) |
| `has_prompt` | bool | - | Filtrar por presencia de prompt |
| `collection_id` | int | - | Buscar dentro de una colección |
| `favorites_only` | bool | `false` | Solo favoritos |
| `group_by` | string | - | Agrupación: `folder`, `conversation` |

### Respuesta

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

Resultados de búsqueda agrupados por carpeta/ZIP.

### Parámetros

Los mismos parámetros de consulta que `/api/search`, más:

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `group_limit` | int | Número máximo de elementos mostrados por grupo |

## GET /api/groups-index

Índice de grupos de carpeta y contenedor ZIP. Se utiliza para agrupar resultados de búsqueda.

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `sort` | string | Orden de clasificación: `name`, `count`, `date` |
| `order` | string | `asc` / `desc` |
| `offset` | int | Posición de inicio de paginación |
| `limit` | int | Número de resultados |

## GET /api/group-members

Lista de IDs de archivo dentro de un contenedor especificado.

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `key` | string | Clave de contenedor (ruta de carpeta o ruta ZIP) |

## GET /api/suggest

Autocompletado para etiquetas y prompts.

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `q` | string | Texto de entrada |
| `limit` | int | Número de sugerencias (predeterminado 10) |

### Respuesta

```json
{
  "suggestions": [
    { "value": "1girl", "count": 5432 },
    { "value": "1boy", "count": 1234 }
  ]
}
```

## GET /api/suggest/lora

Sugerencias de nombre de modelo LoRA.

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `q` | string | Texto de entrada |
| `limit` | int | Número de sugerencias |

## GET /api/server-info

Información básica del servidor.

### Respuesta

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
