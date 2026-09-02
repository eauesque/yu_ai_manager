# Démarrage rapide — UI personnalisée

Procédure pour créer une UI personnalisée minimale et vérifier son fonctionnement.

## 1. Créer les répertoires

```bash
mkdir -p ui/custom/templates ui/custom/static
```

## 2. Créer le manifest.json

`ui/custom/manifest.json` :

```json
{
  "name": "my-custom-ui",
  "version": "1.0.0",
  "description": "My custom UI for YU AI Manager",
  "author": "Your Name",
  "api_version": "1"
}
```

## 3. Créer le template minimal

### Page principale (`index.html`)

`ui/custom/templates/index.html` :

```html
<!DOCTYPE html>
<html lang="fr">
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
      <button id="searchBtn">Search</button>
    </div>
    <div id="results" class="grid"></div>
  </main>

  <script>
    document.getElementById('searchBtn').addEventListener('click', doSearch);

    async function doSearch() {
      const q = document.getElementById('query').value;
      const res = await fetch(`/api/search?q=${encodeURIComponent(q)}&limit=50`);
      const json = await res.json();
      const items = json.results || json.data?.results || [];
      const grid = document.getElementById('results');
      // Clear existing content using DOM methods (safe)
      while (grid.firstChild) grid.removeChild(grid.firstChild);
      items.forEach(f => {
        const card = document.createElement('div');
        card.className = 'card';
        card.addEventListener('click', () => showDetail(f.id));
        const img = document.createElement('img');
        img.src = `/api/thumbnail/${f.id}`;
        img.loading = 'lazy';
        img.alt = f.filename;
        const span = document.createElement('span');
        span.className = 'filename';
        span.textContent = f.filename; // textContent is safe
        card.appendChild(img);
        card.appendChild(span);
        if (f.rating) {
          const rating = document.createElement('span');
          rating.className = 'rating';
          rating.textContent = '★'.repeat(f.rating);
          card.appendChild(rating);
        }
        grid.appendChild(card);
      });
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

    // Initial display
    doSearch();
  </script>
</body>
</html>
```

Utilisez `window.detailModalApi.showDetail(id)` comme API publique principale.
Remarques :
- Préférez `window.<feature>Api.*` pour les API de fonctionnalités
- `window.tr`, `window.apiFetch`, `window.apiUrl`, `window.escapeHtml` restent disponibles comme globals de base

### Feuille de style

`ui/custom/static/style.css` :

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

## 4. Activation

Redémarrez le serveur pour que `ui/custom/` soit automatiquement détecté.

```bash
python web_ui.py --db ./tags.db --port 5000
```

Pour spécifier explicitement, ajoutez à `config.json` :

```json
{
  "ui": "custom"
}
```

## 5. Routes de pages prises en charge

Le routage Flask correspond aux noms de templates suivants :

| Route | Template | Description |
|--------|------------|------|
| `/` | `index.html` | Page de recherche principale |
| `/stats` | `stats.html` | Tableau de bord des statistiques |
| `/tools` | `tools.html` | Page des outils |
| `/settings` | `settings.html` | Page des paramètres |
| `/extensions` | `extensions.html` | Gestion des extensions |
| `/story` | `story.html` | Page Your Story |
| `/inspect` | `inspect.html` | Page d'inspection des métadonnées |

Si un template n'existe pas et que la route est accédée, une erreur sera retournée.

## 6. Exemple de page de statistiques

`ui/custom/templates/stats.html` :

```html
<!DOCTYPE html>
<html lang="fr">
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
        const container = document.getElementById('stats');
        [
          { value: stats.total_files ?? 0, label: 'Total Files' },
          { value: stats.total_tags ?? 0, label: 'Total Tags' },
          { value: stats.rated_count ?? 0, label: 'Rated' },
        ].forEach(item => {
          const card = document.createElement('div');
          card.className = 'stat-card';
          const val = document.createElement('div');
          val.className = 'stat-value';
          val.textContent = item.value.toLocaleString();
          const lbl = document.createElement('div');
          lbl.className = 'stat-label';
          lbl.textContent = item.label;
          card.appendChild(val);
          card.appendChild(lbl);
          container.appendChild(card);
        });
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

## 7. Gestion de la protection CSRF

Les appels API utilisant POST / PUT / DELETE nécessitent l'en-tête `X-Requested-With` :

```javascript
async function setRating(fileId, rating) {
  const res = await fetch('/api/ratings/set', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Requested-With': 'XMLHttpRequest'  // CSRF protection
    },
    body: JSON.stringify({ file_id: fileId, rating: rating })
  });
  return res.json();
}
```

**Conseil** : Préparez une fonction helper qui encapsule tous les appels API :

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
```

## Référence API

Pour les détails complets de l'API, consultez [docs/api/](../api/README.md).
