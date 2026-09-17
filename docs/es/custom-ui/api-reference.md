# Referencia de API — Colección de enlaces de documentación para desarrolladores de interfaz personalizada

Colección de enlaces a documentación de API y tabla de referencia rápida para API de uso común.

## Lista de documentación

### Convenciones comunes

- [Convenciones comunes de API](../api/README.md) — URL base, autenticación (4 métodos), protección CSRF, límite de velocidad, formato de respuesta, paginación

### Por endpoint

- [API de búsqueda](../api/search.md) — GET /api/search, sugerencias, agrupamiento, server-info
- [API de archivos](../api/files.md) — Detalles de archivo, miniatura, original, conversión de indicación
- [API de escaneo](../api/scan.md) — Control de escaneo, gestión de raíz de escaneo, relleno de hash
- [API de eventos](../api/events.md) — Eventos en tiempo real SSE, transmisión de registros

### Tema

- [Lista de variables CSS](../api/theming.md) — Propiedades personalizadas de tema (Claro/Oscuro)

## Tabla de referencia rápida de API comúnmente utilizada

### Lectura (GET, sin autenticación requerida*)

| Endpoint | Uso | Parámetros principales |
|----------|-----|------|
| `/api/search` | Búsqueda de archivo | `q`, `sort`, `limit`, `cursor`, `rating_min`, `collection_id` |
| `/api/thumbnail/<id>` | Imagen de miniatura (WebP) | `size` (predeterminado 300) |
| `/api/original/<id>` | Archivo original | Compatible con Range |
| `/api/file/<id>` | Detalles de archivo | — |
| `/api/suggest` | Sugerencia de etiqueta | `q`, `limit` |
| `/api/stats/all` | Información de estadísticas | — |
| `/api/collections` | Lista de colecciones | — |
| `/api/server-info` | Información del servidor | — |
| `/api/events/stream` | Transmisión SSE | `types` |

*En entornos sin PIN o con autenticación de sesión iniciada

### Escritura (POST, requiere encabezado `X-Requested-With`)

| Endpoint | Uso | Ejemplo de cuerpo |
|----------|-----|---------|
| `/api/ratings/set` | Configurar calificación | `{file_id: 42, rating: 5}` |
| `/api/ratings/batch-set` | Calificación por lotes | `{items: [{file_id, rating}, ...]}` |
| `/api/favorites/add` | Agregar favorito | `{file_id: 42}` |
| `/api/favorites/remove` | Eliminar favorito | `{file_id: 42}` |
| `/api/tags/batch-set` | Operación por lotes de etiqueta | `{items: [{file_id, add: [], remove: []}]}` |
| `/api/collections` | Crear colección | `{name: "My Collection"}` |
| `/api/collections/<id>/batch-add` | Agregar a colección | `{file_ids: [1, 2, 3]}` |
| `/api/scan-all` | Iniciar escaneo | `{}` |
| `/api/convert` | Conversión de indicación | `{prompt, direction}` |

### Gestión de interfaz

| Endpoint | Método | Uso |
|----------|--------|-----|
| `/api/ui/list` | GET | Lista de interfaz |
| `/api/ui/switch` | POST | Cambiar interfaz |
| `/api/ui/install` | POST | Instalar interfaz (solo localhost) |
| `/api/ui/<nombre>/uninstall` | DELETE | Desinstalar interfaz (solo localhost) |

## Formato de respuesta

### Resultado de búsqueda

```javascript
{
  results: [
    {
      id: 42,
      path: "/images/00042.png",
      filename: "00042.png",
      width: 1024,
      height: 1536,
      meta_type: "a1111_png",   // a1111_png, novelai_v4_png, comfy_png, unknown
      model_name: "animagine-xl-3.1",
      positive: "1girl, landscape",
      rating: 4,                 // 0-5 (0 = sin calificar)
      is_favorite: true,
      tags: ["landscape", "sunset"]
    }
  ],
  total: 1500,
  next_cursor: "base64token..."  // null = última página
}
```

### Miniatura

```
GET /api/thumbnail/42
→ Content-Type: image/webp
→ ETag: "abc123"
→ Cache-Control: max-age=86400
```

Puede ser referenciada directamente en etiqueta `<img>` (caché automático del navegador):

```html
<img src="/api/thumbnail/42" loading="lazy" alt="thumbnail">
```

### Respuesta de error

```javascript
{
  ok: false,
  error: "Rate limit exceeded",
  code: "RATE_LIMIT",      // opcional
  detail: "Retry after 5s"  // opcional
}
```

## Nota sobre encabezado CSRF

```javascript
// Asistente de encabezado común
const API_HEADERS = {
  'Content-Type': 'application/json',
  'X-Requested-With': 'XMLHttpRequest',
};

// GET: encabezado no requerido
fetch('/api/search?q=test');

// POST: X-Requested-With obligatorio
fetch('/api/ratings/set', {
  method: 'POST',
  headers: API_HEADERS,
  body: JSON.stringify({ file_id: 42, rating: 5 }),
});
```
