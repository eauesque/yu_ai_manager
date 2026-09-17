# API de Etiquetas

APIs para operaciones de etiqueta en lotes y sugerencia/autocompletado de etiqueta.

## POST /api/tags/batch-set

Agregar o eliminar etiquetas de múltiples archivos en una única solicitud.

### Limitación de Velocidad

WRITE (~120 req/min, burst 30)

### Cuerpo de Solicitud

| Campo | Tipo | Requerido | Descripción |
|-------|------|----------|-------------|
| `items` | array | Sí | Lista de operaciones (máx 500 elementos) |
| `items[].file_id` | int | Sí | ID de archivo (entero positivo) |
| `items[].add` | string[] | No | Nombres de etiqueta a agregar |
| `items[].remove` | string[] | No | Nombres de etiqueta a eliminar |

- Cada elemento requiere al menos uno de `add` o `remove`
- Las etiquetas que no existen se crean automáticamente (namespace=null)
- Las etiquetas agregadas a través de API tienen su origen establecido en `"user"`
- Las etiquetas huérfanas (sin asociaciones de archivo restantes) se eliminan automáticamente

### Ejemplo de Solicitud

```json
{
  "items": [
    {
      "file_id": 42,
      "add": ["landscape", "sunset"],
      "remove": ["lowres"]
    }
  ]
}
```

### Respuesta

```json
{
  "total": 1,
  "succeeded": 1,
  "failed": 0,
  "errors": []
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `total` | int | Número total de elementos procesados |
| `succeeded` | int | Número de operaciones exitosas |
| `failed` | int | Número de operaciones fallidas |
| `errors` | array | Lista de detalles de error |

### Errores

| Estado | Descripción |
|--------|-------------|
| 400 | Cuerpo de solicitud inválido (elementos vacíos, file_id inválido, falta tanto add/remove, etc.) |
| 429 | Límite de velocidad excedido |

---

## GET /api/tags/suggest

Devolver candidatos de etiqueta que coincidan con una cadena de búsqueda parcial. Destinado a autocompletado.

### Parámetros

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `q` | string | Sí | Cadena de búsqueda |
| `limit` | int | No | Número máximo de resultados (predeterminado: 20, máx: 100) |

- La búsqueda no distingue entre mayúsculas y minúsculas (LIKE %q%)
- Los resultados se ordenan por `file_count` en orden descendente
- Un `q` vacío devuelve un array vacío

### Respuesta

```json
{
  "data": [
    { "id": 1, "tag": "landscape", "namespace": null, "file_count": 150 },
    { "id": 2, "tag": "1girl", "namespace": null, "file_count": 3420 }
  ]
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `data[].id` | int | ID de etiqueta |
| `data[].tag` | string | Nombre de etiqueta |
| `data[].namespace` | string\|null | Namespace (usualmente null) |
| `data[].file_count` | int | Número de archivos asociados con esta etiqueta |
