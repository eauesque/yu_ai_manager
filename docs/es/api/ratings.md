# API de Calificaciones

API para gestionar calificaciones de archivo (calificaciones de 1–5 estrellas): establecer, recuperar y ver estadísticas.

## POST /api/ratings/set

Establecer una calificación para un archivo. Especifique `rating=0` para borrar la calificación.

**Limitación de velocidad**: WRITE

### Solicitud

```json
{
  "file_id": 42,
  "rating": 5
}
```

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `file_id` | int | Sí | ID de archivo (entero positivo) |
| `rating` | int | Sí | Valor de calificación (0–5). 0 borra la calificación |

### Respuesta

```json
{
  "file_id": 42,
  "rating": 5
}
```

## POST /api/ratings/batch-set

Establecer calificaciones para múltiples archivos a la vez.

**Limitación de velocidad**: WRITE

### Solicitud

```json
{
  "items": [
    { "file_id": 1, "rating": 5 },
    { "file_id": 2, "rating": 3 }
  ]
}
```

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `items` | array | Sí | Lista de entradas de calificación (máx 500) |
| `items[].file_id` | int | Sí | ID de archivo (entero positivo) |
| `items[].rating` | int | Sí | Valor de calificación (0–5) |

### Respuesta

```json
{
  "total": 2,
  "succeeded": 2,
  "failed": 0,
  "errors": []
}
```

## GET /api/ratings/get

Obtener la calificación para un archivo. Devuelve `rating: 0` si el archivo no está calificado.

### Parámetros

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `file_id` | int | Sí | ID de archivo (parámetro de consulta) |

### Respuesta

```json
{
  "file_id": 42,
  "rating": 5
}
```

> **Nota**: Los archivos sin calificar devuelven `rating: 0`.

## POST /api/ratings/batch

Recuperar calificaciones para múltiples archivos a la vez.

### Solicitud

```json
{
  "file_ids": [1, 2, 3]
}
```

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `file_ids` | array | Sí | Lista de IDs de archivo |

### Respuesta

```json
{
  "ratings": {
    "1": 5,
    "3": 4
  }
}
```

> **Nota**: Solo los archivos calificados aparecen en el mapa. Los archivos sin calificar se omiten de la respuesta.

## GET /api/ratings/stats

Obtener estadísticas de calificación en todos los archivos.

### Parámetros

Ninguno.

### Respuesta

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

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `total_rated` | int | Número total de archivos calificados |
| `distribution` | object | Recuento de archivos por valor de calificación (1–5) |
