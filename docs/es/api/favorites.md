# API de Favoritos

API para agregar, eliminar, verificar y listar favoritos.

## POST /api/favorites/toggle

Alternar el estado de favorito de un archivo. Agrega el archivo si no ya está marcado como favorito; lo elimina si ya está presente.

- **Limitación de velocidad**: WRITE

### Cuerpo de Solicitud

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `file_id` | int | Sí | ID de archivo objetivo (entero positivo) |
| `collection_id` | int | No | ID de colección (predeterminado: 1) |

```json
{
  "file_id": 42,
  "collection_id": 1
}
```

### Respuesta

```json
{
  "file_id": 42,
  "collection_id": 1,
  "favorited": true
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `file_id` | int | ID de archivo objetivo |
| `collection_id` | int | ID de colección |
| `favorited` | bool | Estado después de alternar. `true` = agregado, `false` = eliminado |

## GET /api/favorites/check

Devuelve cuáles de los IDs de archivo especificados están marcados como favoritos.

### Parámetros

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `ids` | string | Sí | IDs de archivo separados por comas (p. ej. `1,2,3`) |
| `collection_id` | int | No | Filtrar a una colección específica |

### Respuesta

```json
{
  "favorites": [1, 3]
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `favorites` | int[] | Array de IDs de archivo que están marcados como favoritos |

## GET /api/favorites/check_collections

Devuelve los IDs de colección que contienen el archivo especificado.

### Parámetros

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `file_id` | int | Sí | ID de archivo objetivo |

### Respuesta

```json
{
  "collections": [1, 3]
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `collections` | int[] | Array de IDs de colección que contienen este archivo |

## GET /api/favorites/list

Recupera una lista de IDs de archivo favoritos. Los resultados se ordenan por fecha agregada en orden descendente. Los archivos eliminados lógicamente se excluyen.

### Parámetros

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `collection_id` | int | No | Filtrar a una colección específica |

### Respuesta

```json
{
  "ids": [42, 55, 67]
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `ids` | int[] | Array de IDs de archivo favoritos (ordenado por `added_at` DESC) |
