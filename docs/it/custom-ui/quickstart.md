# Quickstart per UI Personalizzate

Procedura per creare una UI personalizzata minimale e verificarne il funzionamento.

## 1. Creazione della Directory

```bash
mkdir -p ui/custom/templates ui/custom/static
```

## 2. Creazione di manifest.json

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

## 3. Creazione del Template Minimale

### Pagina Principale (`index.html`)

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

    // Visualizzazione iniziale
    doSearch();
  </script>
</body>
</html>
```

Usa `window.detailModalApi.showDetail(id)` come API pubblica esposta. È preferibile non dipendere dai vecchi nomi globali come `window.showDetail(id)`.

Note aggiuntive:

- Per le feature API, usa preferibilmente `window.<feature>Api.*`
- `window.tr`, `window.apiFetch`, `window.apiUrl`, `window.escapeHtml` continuano ad essere disponibili come globali di base

### Foglio di Stile

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

## 4. Attivazione

Riavvia il server e `ui/custom/` verrà rilevato automaticamente.

```bash
python web_ui.py --db ./tags.db --port 5000
```

Per specificarlo esplicitamente, aggiungilo a `config.json`:

```json
{
  "ui": "custom"
}
```

## 5. Route delle Pagine Supportate

Il routing di Flask supporta i seguenti nomi di template:

| Route | Template | Descrizione |
|-------|----------|-------------|
| `/` | `index.html` | Pagina di ricerca principale |
| `/stats` | `stats.html` | Dashboard statistiche |
| `/tools` | `tools.html` | Pagina strumenti |
| `/settings` | `settings.html` | Pagina impostazioni |
| `/extensions` | `extensions.html` | Gestione Extension |
| `/story` | `story.html` | Pagina Your Story |
| `/inspect` | `inspect.html` | Pagina ispezione metadati |

Posizionando template con questi nomi nell'UI personalizzata, vengono visualizzati agli stessi URL.
Se si accede a una route per cui il template non esiste, viene restituito un errore.

## 6. Esempio di Pagina Statistiche

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

## 7. Gestione della Protezione CSRF

Le chiamate API che utilizzano POST / PUT / DELETE richiedono l'header `X-Requested-With`:

```javascript
// Esempio di impostazione rating
async function setRating(fileId, rating) {
  const res = await fetch('/api/ratings/set', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Requested-With': 'XMLHttpRequest'  // Protezione CSRF
    },
    body: JSON.stringify({ file_id: fileId, rating: rating })
  });
  return res.json();
}

// Aggiunta ai preferiti
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

**Suggerimento**: È conveniente predisporre una funzione helper che racchiude tutte le chiamate API:

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

// Esempio di utilizzo
const results = await api('/api/search?q=landscape&limit=20');
await api('/api/ratings/set', {
  method: 'POST',
  body: JSON.stringify({ file_id: 42, rating: 5 }),
});
```

## Creazione di UI con l'AI

Esempio di istruzioni per richiedere a Claude o ChatGPT la generazione di una UI personalizzata:

```
Crea una UI personalizzata per YU AI Manager.

## Struttura dei File
- ui/custom/manifest.json — Metadati dell'UI
- ui/custom/templates/index.html — Pagina di ricerca principale
- ui/custom/templates/stats.html — Pagina statistiche
- ui/custom/static/style.css — Foglio di stile

## API Principali (tutte le GET non richiedono autenticazione)
- GET /api/search?q=...&limit=50&sort=date — Ricerca immagini (risultato: {results: [{id, filename, rating, ...}]})
- GET /api/thumbnail/<id> — Immagine thumbnail (WebP)
- GET /api/original/<id> — Immagine originale
- GET /api/file/<id> — Metadati dettagliati del file
- GET /api/stats/all — Informazioni statistiche
- GET /api/suggest?q=... — Suggerimenti tag
- GET /api/collections — Lista collezioni

## API di Scrittura (POST richiede l'header X-Requested-With: XMLHttpRequest)
- POST /api/ratings/set {file_id, rating} — Impostazione rating
- POST /api/favorites/add {file_id} — Aggiunta ai preferiti
- POST /api/tags/batch-set {items: [{file_id, add: [...], remove: [...]}]}

## Requisiti di Design
- Dark mode (sfondo #0f1115, testo #e7eaf0, accento #60a5fa)
- Layout a griglia responsive
- Le card thumbnail mostrano filename e rating
```

## Riferimento API

Per i dettagli di tutte le API, consulta [docs/api/](../api/README.md).
