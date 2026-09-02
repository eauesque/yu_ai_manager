# API de Colecciones

APIs para gestionar colecciones (grupos de favoritos).

## GET /api/collections

Listar todas las colecciones. Ordenadas por `sort_order` ASC, luego `id` ASC.

### Parámetros

Ninguno

### Respuesta

```json
{
  "collections": [
    {
      "id": 1,
      "name": "Favorites",
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

Crear una nueva colección.

### Limitación de Velocidad

WRITE

### Solicitud

```json
{
  "name": "My Collection",
  "query_json": null
}
```

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `name` | string | Sí | Nombre de la colección |
| `query_json` | object/null | No | Consulta para colecciones inteligentes. Omitir para colecciones normales |

### Respuesta (201)

```json
{
  "id": 2,
  "name": "My Collection",
  "is_smart": false
}
```

## PUT /api/collections/<id>

Renombrar una colección.

### Limitación de Velocidad

WRITE

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `id` | int | ID de la colección (parámetro de ruta) |

### Solicitud

```json
{
  "name": "Renamed Collection"
}
```

### Respuesta

```json
{
  "id": 2,
  "name": "Renamed Collection"
}
```

## DELETE /api/collections/<id>

Eliminar una colección. Todas las entradas de favoritos en la colección también se eliminan.

La colección predeterminada (`id=1`) no puede ser eliminada.

### Limitación de Velocidad

WRITE

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `id` | int | ID de la colección (parámetro de ruta) |

### Respuesta

```json
{
  "deleted": 2
}
```

## POST /api/collections/reorder

Cambiar el orden de visualización de las colecciones.

### Limitación de Velocidad

WRITE

### Solicitud

```json
{
  "ids": [3, 1, 2]
}
```

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `ids` | int[] | Array de IDs de colección. El orden especificado se convierte en el nuevo orden de clasificación |

### Respuesta

```json
{
  "ok": true
}
```

## POST /api/collections/<id>/batch-add

Agregar archivos a una colección en lotes. Idempotente: las entradas que ya existen se omiten y se cuentan como éxitos.

### Limitación de Velocidad

WRITE

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `id` | int | ID de la colección (parámetro de ruta) |

### Solicitud

```json
{
  "file_ids": [1, 2, 3]
}
```

| Parámetro | Tipo | Límite | Descripción |
|-----------|------|-------|-------------|
| `file_ids` | int[] | Max 500 | Array de IDs de archivo a agregar |

### Respuesta

```json
{
  "total": 3,
  "succeeded": 3,
  "failed": 0,
  "errors": []
}
```

## POST /api/collections/<id>/batch-remove

Eliminar archivos de una colección en lotes.

### Limitación de Velocidad

WRITE

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `id` | int | ID de la colección (parámetro de ruta) |

### Solicitud

```json
{
  "file_ids": [1, 2]
}
```

| Parámetro | Tipo | Límite | Descripción |
|-----------|------|-------|-------------|
| `file_ids` | int[] | Max 500 | Array de IDs de archivo a eliminar |

### Respuesta

```json
{
  "total": 2,
  "succeeded": 2,
  "failed": 0,
  "errors": []
}
```

## GET /api/collections/<id>/export/csv

Exportar archivos en una colección como CSV.

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `id` | int | ID de la colección (parámetro de ruta) |

### Respuesta

- Content-Type: `text/csv; charset=utf-8`
- Columnas CSV: `id`, `filename`, `folder`, `path`, `meta_source`, `mtime`, `positive`, `negative`
- Devuelve 404 si la colección no se encuentra
