# Custom UI Quickstart

Pasos para crear una UI personalizada con configuración mínima y verificar su funcionamiento.

## 1. Crear directorios

```bash
mkdir -p ui/custom/templates ui/custom/static
```

## 2. Crear manifest.json

`ui/custom/manifest.json`:

```json
{
  "name": "my-custom-ui",
  "version": "1.0.0",
  "description": "My custom UI for YU AI Manager",
  "author": "Your Name",
  "api_version": "1"
}
```

## 3. Crear plantillas mínimas

### Página principal (`index.html`)

`ui/custom/templates/index.html`:

```html
<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>My Custom UI</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
  <header class="header">
    <h1>My Custom UI</h1>
    <nav>
      <a href="/" class="active">Search</a>
      <a href="/stats">Stats</a>
    </nav>
  </header>

  <main>
    <div class="search-bar">
      <input type="text" id="query" placeholder="Search tags...">
      <button onclick="doSearch()">Search</button>
    </div>
    <div id="results" class="grid"></div>
  </main>

  <script>
    async function doSearch() {
      const q = document.getElementById('query').value;
      const res = await fetch(`/api/search?q=${encodeURIComponent(q)}&limit=50`);
      const json = await res.json();
      const items = json.results || json.data?.results || [];
      document.getElementById('results').innerHTML = items.map(f => `
        <div class="card" onclick="showDetail(${f.id})">
          <img src="/api/thumbnail/${f.id}" loading="lazy" alt="${f.filename}">
          <span class="filename">${f.filename}</span>
          ${f.rating ? '<span class="rating">' + '★'.repeat(f.rating) + '</span>' : ''}
        </div>
      `).join('');
    }

    function showDetail(id) {
      const api = window.detailModalApi || window;
      if (typeof api.showDetail === 'function') {
        api.showDetail(id);
        return;
      }
      fetch(`/api/file/${id}`)
        .then(r => r.json())
        .then(file => alert(JSON.stringify(file, null, 2)));
    }

    // Visualización inicial
    doSearch();
  </script>
</body>
</html>
```

Use `window.detailModalApi.showDetail(id)` como API pública principal. Es más seguro escribir asumiendo que no dependerá de los antiguos nombres globales como `window.showDetail(id)`.

Notas adicionales:

- Prefiera las APIs por funcionalidad `window.<feature>Api.*`
- `window.tr`, `window.apiFetch`, `window.apiUrl`, `window.escapeHtml` siguen disponibles como globales base

### Hoja de estilos

`ui/custom/static/style.css`:

```css
* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  font-family: system-ui, -apple-system, sans-serif;
  background: #0f1115;
  color: #e7eaf0;
}

.header {
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 16px 24px;
  background: #1b1f2a;
  border-bottom: 1px solid #2b3240;
}
.header h1 { font-size: 1.2rem; }
.header nav { display: flex; gap: 12px; }
.header a {
  color: #aab2c0;
  text-decoration: none;
  padding: 4px 8px;
  border-radius: 4px;
}
.header a.active, .header a:hover {
  color: #60a5fa;
  background: rgba(96, 165, 250, 0.1);
}

main { padding: 24px; max-width: 1400px; margin: 0 auto; }

.search-bar {
  display: flex;
  gap: 8px;
  margin-bottom: 24px;
}
.search-bar input {
  flex: 1;
  padding: 10px 16px;
  background: #1b1f2a;
  color: #e7eaf0;
  border: 1px solid #2b3240;
  border-radius: 8px;
  font-size: 1rem;
}
.search-bar input:focus {
  outline: none;
  border-color: #60a5fa;
}
.search-bar button {
  padding: 10px 20px;
  background: #60a5fa;
  color: #0f1115;
  border: none;
  border-radius: 8px;
  font-weight: 600;
  cursor: pointer;
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
}

.card {
  background: #1b1f2a;
  border-radius: 8px;
  overflow: hidden;
  cursor: pointer;
  transition: transform 0.15s, box-shadow 0.15s;
}
.card:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(0,0,0,0.4);
}
.card img {
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
  display: block;
}
.card .filename {
  display: block;
  padding: 8px 10px;
  font-size: 0.8rem;
  color: #aab2c0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.card .rating {
  display: block;
  padding: 0 10px 8px;
  font-size: 0.75rem;
  color: #fbbf24;
}
```

## 4. Activación

Al reiniciar el servidor, `ui/custom/` se detecta automáticamente.

```bash
python web_ui.py --db ./tags.db --port 5000
```

Para especificarlo explícitamente, añada a `config.json`:

```json
{
  "ui": "custom"
}
```

## 5. Rutas de página soportadas

El enrutamiento de Flask está asociado a los siguientes nombres de plantilla:

| Ruta | Plantilla | Descripción |
|--------|------------|------|
| `/` | `index.html` | Página principal de búsqueda |
| `/stats` | `stats.html` | Panel de estadísticas |
| `/tools` | `tools.html` | Página de herramientas |
| `/settings` | `settings.html` | Página de configuración |
| `/extensions` | `extensions.html` | Gestión de extensiones |
| `/story` | `story.html` | Página Your Story |
| `/inspect` | `inspect.html` | Página de inspección de metadatos |

Si se colocan plantillas con estos nombres en una UI personalizada, se mostrarán en la misma URL.
Acceder a una ruta cuya plantilla no existe produce un error.

## 6. Ejemplo de página de estadísticas

`ui/custom/templates/stats.html`:

```html
<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Stats - My Custom UI</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
  <header class="header">
    <h1>My Custom UI</h1>
    <nav>
      <a href="/">Search</a>
      <a href="/stats" class="active">Stats</a>
    </nav>
  </header>

  <main>
    <h2>Library Statistics</h2>
    <div id="stats" class="stats-grid"></div>
  </main>

  <script>
    fetch('/api/stats/all')
      .then(r => r.json())
      .then(data => {
        const stats = data.data || data;
        document.getElementById('stats').innerHTML = `
          <div class="stat-card">
            <div class="stat-value">${(stats.total_files ?? 0).toLocaleString()}</div>
            <div class="stat-label">Total Files</div>
          </div>
          <div class="stat-card">
            <div class="stat-value">${(stats.total_tags ?? 0).toLocaleString()}</div>
            <div class="stat-label">Total Tags</div>
          </div>
          <div class="stat-card">
            <div class="stat-value">${(stats.rated_count ?? 0).toLocaleString()}</div>
            <div class="stat-label">Rated</div>
          </div>
        `;
      });
  </script>

  <style>
    .stats-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
      gap: 16px;
      margin-top: 20px;
    }
    .stat-card {
      background: #1b1f2a;
      border-radius: 12px;
      padding: 24px;
      text-align: center;
    }
    .stat-value {
      font-size: 2rem;
      font-weight: 700;
      color: #60a5fa;
    }
    .stat-label {
      font-size: 0.9rem;
      color: #aab2c0;
      margin-top: 4px;
    }
  </style>
</body>
</html>
```

## 7. Soportar la protección CSRF

Las llamadas a la API que usan POST / PUT / DELETE requieren la cabecera `X-Requested-With`:

```javascript
// Ejemplo de establecer valoración
async function setRating(fileId, rating) {
  const res = await fetch('/api/ratings/set', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Requested-With': 'XMLHttpRequest'  // Protección CSRF
    },
    body: JSON.stringify({ file_id: fileId, rating: rating })
  });
  return res.json();
}

// Añadir a favoritos
async function addFavorite(fileId) {
  return fetch('/api/favorites/add', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Requested-With': 'XMLHttpRequest'
    },
    body: JSON.stringify({ file_id: fileId })
  }).then(r => r.json());
}
```

**Consejo**: Resulta útil preparar una función auxiliar que envuelva todas las llamadas a la API:

```javascript
async function api(path, options = {}) {
  const res = await fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'X-Requested-With': 'XMLHttpRequest',
      ...options.headers,
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(err.error || `HTTP ${res.status}`);
  }
  return res.json();
}

// Ejemplos de uso
const results = await api('/api/search?q=landscape&limit=20');
await api('/api/ratings/set', {
  method: 'POST',
  body: JSON.stringify({ file_id: 42, rating: 5 }),
});
```

## Crear la UI con IA

Ejemplo de instrucción al pedir a Claude o ChatGPT que genere una UI personalizada:

```
Crea una UI personalizada para YU AI Manager.

## Estructura de archivos
- ui/custom/manifest.json — Metadatos de la UI
- ui/custom/templates/index.html — Página principal de búsqueda
- ui/custom/templates/stats.html — Página de estadísticas
- ui/custom/static/style.css — Hoja de estilos

## APIs principales (todos los GET no requieren autenticación)
- GET /api/search?q=...&limit=50&sort=date — Búsqueda de imágenes (resultado: {results: [{id, filename, rating, ...}]})
- GET /api/thumbnail/<id> — Imagen miniatura (WebP)
- GET /api/original/<id> — Imagen original
- GET /api/file/<id> — Metadatos detallados del archivo
- GET /api/stats/all — Estadísticas
- GET /api/suggest?q=... — Sugerencia de etiquetas
- GET /api/collections — Lista de colecciones

## APIs de escritura (POST requiere la cabecera X-Requested-With: XMLHttpRequest)
- POST /api/ratings/set {file_id, rating} — Establecer valoración
- POST /api/favorites/add {file_id} — Añadir a favoritos
- POST /api/tags/batch-set {items: [{file_id, add: [...], remove: [...]}]}

## Requisitos de diseño
- Modo oscuro (fondo #0f1115, texto #e7eaf0, acento #60a5fa)
- Disposición responsiva en cuadrícula
- Mostrar filename y rating en las tarjetas miniatura
```

## Referencia de API

Para más detalles sobre todas las APIs, consulte [docs/api/](../api/README.md).
