# Custom UI Quickstart

Anleitung zum Erstellen einer minimalen benutzerdefinierten UI und Überprüfung der Funktionsfähigkeit.

## 1. Verzeichnis erstellen

```bash
mkdir -p ui/custom/templates ui/custom/static
```

## 2. manifest.json erstellen

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

## 3. Minimale Vorlage erstellen

### Hauptseite (`index.html`)

`ui/custom/templates/index.html`:

```html
<!DOCTYPE html>
<html lang="de">
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
    async function doSearch() {
      const q = document.getElementById('query').value;
      const res = await fetch(`/api/search?q=${encodeURIComponent(q)}&limit=50`);
      const json = await res.json();
      const items = json.results || json.data?.results || [];
      const grid = document.getElementById('results');
      grid.textContent = '';
      items.forEach(f => {
        const card = document.createElement('div');
        card.className = 'card';
        card.setAttribute('data-id', f.id);
        const img = document.createElement('img');
        img.src = `/api/thumbnail/${f.id}`;
        img.loading = 'lazy';
        img.alt = f.filename;
        const name = document.createElement('span');
        name.className = 'filename';
        name.textContent = f.filename;
        card.appendChild(img);
        card.appendChild(name);
        if (f.rating) {
          const rating = document.createElement('span');
          rating.className = 'rating';
          rating.textContent = '★'.repeat(f.rating);
          card.appendChild(rating);
        }
        card.addEventListener('click', () => showDetail(f.id));
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

    document.getElementById('searchBtn').addEventListener('click', doSearch);

    // Erste Anzeige
    doSearch();
  </script>
</body>
</html>
```

`window.detailModalApi.showDetail(id)` als offizielle öffentliche API verwenden. Nicht von alten globalen Namen wie `window.showDetail(id)` abhängen.

Hinweise:
- Feature-APIs bevorzugen: `window.<feature>Api.*`
- `window.tr`, `window.apiFetch`, `window.apiUrl`, `window.escapeHtml` sind weiterhin als globale Basis-APIs verfügbar

### Stylesheet

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

## 4. Aktivierung

Nach einem Server-Neustart wird `ui/custom/` automatisch erkannt.

```bash
python web_ui.py --db ./tags.db --port 5000
```

Für explizite Angabe in `config.json` hinzufügen:

```json
{
  "ui": "custom"
}
```

## 5. Unterstützte Seiten-Routen

Das Flask-Routing ist fest und wird automatisch den folgenden Template-Namen zugeordnet:

| Route | Template | Beschreibung |
|--------|------------|------|
| `/` | `index.html` | Haupt-Suchseite |
| `/stats` | `stats.html` | Statistik-Dashboard |
| `/tools` | `tools.html` | Tools-Seite |
| `/settings` | `settings.html` | Einstellungsseite |
| `/extensions` | `extensions.html` | Extension-Verwaltung |
| `/story` | `story.html` | Your Story-Seite |
| `/inspect` | `inspect.html` | Metadaten-Prüfseite |

Wenn Templates mit diesen Namen in der benutzerdefinierten UI vorhanden sind, werden sie unter derselben URL angezeigt.
Wenn auf eine Route ohne Template zugegriffen wird, tritt ein Fehler auf.

## 6. Beispiel für die Statistikseite

`ui/custom/templates/stats.html`:

```html
<!DOCTYPE html>
<html lang="de">
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
        const grid = document.getElementById('stats');

        const items = [
          { value: (stats.total_files ?? 0).toLocaleString(), label: 'Total Files' },
          { value: (stats.total_tags ?? 0).toLocaleString(), label: 'Total Tags' },
          { value: (stats.rated_count ?? 0).toLocaleString(), label: 'Rated' },
        ];

        items.forEach(item => {
          const card = document.createElement('div');
          card.className = 'stat-card';
          const valueEl = document.createElement('div');
          valueEl.className = 'stat-value';
          valueEl.textContent = item.value;
          const labelEl = document.createElement('div');
          labelEl.className = 'stat-label';
          labelEl.textContent = item.label;
          card.appendChild(valueEl);
          card.appendChild(labelEl);
          grid.appendChild(card);
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

## 7. CSRF-Schutz implementieren

POST / PUT / DELETE API-Aufrufe benötigen den `X-Requested-With`-Header:

```javascript
// Hilfsfunktion für alle API-Aufrufe
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

## API-Referenz

Für die vollständige API-Dokumentation siehe [docs/api/](../api/README.md).
