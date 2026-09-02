# Guía avanzada — SSE, operaciones por lotes y seguridad

Funciones avanzadas y patrones de implementación de la UI personalizada.

## Actualizaciones en tiempo real (SSE)

Mediante Server-Sent Events puede recibir en tiempo real el progreso de escaneo, los cambios de favoritos, el progreso del análisis IA, etc.

### Cómo conectar

```javascript
// Usar EventSource directamente (es lo seguro en una UI personalizada)
const sse = new EventSource('/api/events/stream');

// Suscribirse a eventos
sse.addEventListener('scan.progress', (e) => {
  const data = JSON.parse(e.data);
  console.log(`Scan: ${data.scanned}/${data.total}`);
});

sse.addEventListener('scan.complete', (e) => {
  const data = JSON.parse(e.data);
  console.log(`Scan done: ${data.added_count} added`);
  // Recargar la cuadrícula
  reloadResults();
});
```

**Nota**: En la UI de referencia (`ui/default/`), `window.EventSource` está sobrescrito mediante un Proxy, por lo que no se puede usar `new EventSource()`. En las UI personalizadas esta restricción no aplica, así que puede usarse directamente.

### Lista de eventos principales

| Evento | Datos | Uso en la UI |
|---------|--------|------------|
| `scan.progress` | `{ scanned, total, current_file }` | Mostrar barra de progreso |
| `scan.complete` | `{ added_count, updated_count }` | Recargar resultados de búsqueda |
| `favorite.add` | `{ file_id, collection_id }` | Actualizar icono de favorito |
| `favorite.remove` | `{ file_id, collection_id }` | Actualizar icono de favorito |
| `collection.create` | `{ id, name }` | Actualizar lista de colecciones |

Para todos los tipos de evento consulte [events.md](../api/events.md).

### Gestión de la conexión

```javascript
class SSEConnection {
  constructor() {
    this.handlers = new Map();
    this.connect();
  }

  connect() {
    this.sse = new EventSource('/api/events/stream');
    this.sse.onerror = () => {
      this.sse.close();
      // Reconectar (backoff exponencial)
      setTimeout(() => this.connect(), 3000);
    };
    // Reaplicar manejadores registrados
    for (const [type, handler] of this.handlers) {
      this.sse.addEventListener(type, handler);
    }
  }

  on(eventType, callback) {
    const handler = (e) => callback(JSON.parse(e.data));
    this.handlers.set(eventType, handler);
    this.sse.addEventListener(eventType, handler);
  }

  close() {
    this.sse.close();
  }
}

// Ejemplo de uso
const sse = new SSEConnection();
sse.on('scan.progress', (data) => updateProgressBar(data));
sse.on('scan.complete', () => reloadResults());
```

### Conexión sensible a la visibilidad

Suprimir la conexión cuando la pestaña queda oculta para ahorrar recursos:

```javascript
document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    sse.close();
  } else {
    sse.connect();
  }
});
```

## Operaciones por lotes

Patrón de API para ejecutar de forma conjunta operaciones sobre varios archivos.

### Establecer valoraciones en lote

```javascript
async function batchRate(items) {
  // items: [{file_id: 1, rating: 5}, {file_id: 2, rating: 3}]
  // Máximo 500 elementos
  const res = await api('/api/ratings/batch-set', {
    method: 'POST',
    body: JSON.stringify({ items }),
  });
  return res;
}
```

### Operaciones de etiquetas en lote

```javascript
async function batchSetTags(items) {
  // items: [{file_id: 1, add: ["good"], remove: ["bad"]}, ...]
  const res = await api('/api/tags/batch-set', {
    method: 'POST',
    body: JSON.stringify({ items }),
  });
  return res;
}
```

### Operaciones de colección en lote

```javascript
// Añadir a una colección
async function addToCollection(collectionId, fileIds) {
  return api(`/api/collections/${collectionId}/batch-add`, {
    method: 'POST',
    body: JSON.stringify({ file_ids: fileIds }),
  });
}

// Eliminar de una colección
async function removeFromCollection(collectionId, fileIds) {
  return api(`/api/collections/${collectionId}/batch-remove`, {
    method: 'POST',
    body: JSON.stringify({ file_ids: fileIds }),
  });
}
```

### Manejo de éxitos parciales

Las operaciones en lote pueden tener éxito parcial:

```javascript
const result = await batchRate(items);
if (result.failed && result.failed.length > 0) {
  console.warn(`${result.failed.length} items failed:`, result.failed);
  showToast(`${result.succeeded} succeeded, ${result.failed.length} failed`);
}
```

## Manejo de errores

### Códigos de estado HTTP

| Código | Significado | Acción |
|--------|------|------|
| 200 | Éxito | - |
| 304 | Not Modified | Usar la caché (miniaturas) |
| 400 | Solicitud incorrecta | Verificar la entrada |
| 403 | Fallo de autenticación / CSRF inválido | Verificar la cabecera `X-Requested-With` |
| 404 | Recurso no encontrado | Verificar el ID de archivo |
| 429 | Límite de tasa | Esperar los segundos indicados en la cabecera `Retry-After` |
| 500 | Error del servidor | Reintentar o revisar los registros |

### Manejo del límite de tasa

```javascript
async function apiWithRetry(path, options = {}, maxRetries = 3) {
  for (let i = 0; i < maxRetries; i++) {
    const res = await fetch(path, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
        ...options.headers,
      },
    });

    if (res.status === 429) {
      const retryAfter = parseInt(res.headers.get('Retry-After') || '5', 10);
      console.warn(`Rate limited, retry after ${retryAfter}s`);
      await new Promise(r => setTimeout(r, retryAfter * 1000));
      continue;
    }

    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: res.statusText }));
      throw new Error(err.error || `HTTP ${res.status}`);
    }

    return res.json();
  }
  throw new Error('Max retries exceeded');
}
```

### Detección del formato de respuesta

Existen dos formatos de respuesta, el nuevo y el antiguo:

```javascript
function parseApiResponse(json) {
  // Formato nuevo: { ok, error, data }
  if ('ok' in json) {
    if (!json.ok) throw new Error(json.error || 'Unknown error');
    return json.data ?? json;
  }
  // Formato antiguo: { success, message }
  if ('success' in json) {
    if (!json.success) throw new Error(json.message || 'Unknown error');
    return json;
  }
  // Datos directos (por ejemplo, results)
  return json;
}
```

## Seguridad

### Protección CSRF

Todas las operaciones de escritura (POST / PUT / DELETE) requieren la cabecera `X-Requested-With`:

```javascript
// Buen ejemplo: incluye la cabecera
fetch('/api/ratings/set', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-Requested-With': 'XMLHttpRequest',
  },
  body: JSON.stringify({ file_id: 42, rating: 5 }),
});
```

**Excepción**: Las solicitudes con cabecera `Authorization: Bearer sk_...` (API Key) no necesitan la cabecera CSRF.

### Prevención de XSS

Al insertar en el DOM entradas del usuario o nombres de archivo, es necesario sanearlos:

```javascript
function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// Mal ejemplo: se inserta el nombre de archivo tal cual
card.innerHTML = `<p>${file.filename}</p>`;  // riesgo de XSS

// Buen ejemplo: escape
card.innerHTML = `<p>${escapeHtml(file.filename)}</p>`;

// Mejor aún: usar la API del DOM
const p = document.createElement('p');
p.textContent = file.filename;  // escape automático
card.appendChild(p);
```

### Manejo de claves API

Al utilizar una API Key desde la UI personalizada, no incruste la clave en el lado del cliente.
Una UI basada en navegador normalmente usa autenticación por PIN / sesión y se protege con la cabecera CSRF.

## Implementación de la búsqueda

### Búsqueda básica

```javascript
async function search(query, options = {}) {
  const params = new URLSearchParams({
    q: query,
    limit: String(options.limit || 50),
    sort: options.sort || 'date',
  });

  if (options.cursor) params.set('cursor', options.cursor);
  if (options.minRating) params.set('rating_min', String(options.minRating));
  if (options.collection) params.set('collection_id', String(options.collection));
  if (options.favOnly) params.set('favorites_only', 'true');

  const res = await fetch(`/api/search?${params}`);
  return res.json();
}
```

### Autocompletado

```javascript
let debounceTimer;

function onSearchInput(e) {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(async () => {
    const q = e.target.value;
    if (q.length < 2) return;

    const res = await fetch(`/api/suggest?q=${encodeURIComponent(q)}&limit=10`);
    const { suggestions } = await res.json();
    showSuggestions(suggestions);  // [{value: "1girl", count: 5432}, ...]
  }, 200);
}
```

### Cambio de orden

```javascript
const SORT_OPTIONS = [
  { value: 'date', label: 'Date (New)' },
  { value: 'name', label: 'Name' },
  { value: 'size', label: 'Size' },
  { value: 'rating', label: 'Rating' },
  { value: 'random', label: 'Random' },
];
```

## Gestión de colecciones

```javascript
// Obtener la lista de colecciones
async function getCollections() {
  const res = await fetch('/api/collections');
  return res.json();
}

// Crear una colección
async function createCollection(name) {
  return api('/api/collections', {
    method: 'POST',
    body: JSON.stringify({ name }),
  });
}

// Buscar dentro de una colección
async function searchInCollection(collectionId, query = '') {
  return search(query, { collection: collectionId });
}
```

## Conversión de prompts

Conversión del formato de prompt entre A1111 y NAI:

```javascript
async function convertPrompt(prompt, direction) {
  // direction: "a1111_to_nai" or "nai_to_a1111"
  const res = await api('/api/convert', {
    method: 'POST',
    body: JSON.stringify({ prompt, direction }),
  });
  return res.converted;
}
```

## Despliegue

### Distribución de una UI personalizada

Para distribuir su UI personalizada a otros usuarios:

1. **Repositorio Git**: push a GitHub, etc. → instalar desde la UI de Settings
2. **Archivo ZIP**: comprimir los archivos en ZIP y compartir la URL de descarga
3. **Colocación manual**: copiar directamente al directorio `ui/<name>/`

### Instalación

Desde la pestaña "UI" de la página Settings, o mediante la API:

```bash
# Instalar con curl
curl -X POST http://localhost:5000/api/ui/install \
  -H "X-Requested-With: XMLHttpRequest" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://github.com/user/my-custom-ui.git"}'
```

### Requisitos de manifest.json

El `manifest.json` de la UI que se distribuye debe incluir:

```json
{
  "name": "my-custom-ui",
  "version": "1.0.0",
  "description": "A beautiful custom UI for YU AI Manager",
  "author": "Your Name",
  "api_version": "1"
}
```

- `name` y `version` son obligatorios
- `name` también será el nombre del directorio de instalación
- `"default"` es un nombre reservado y no puede usarse
