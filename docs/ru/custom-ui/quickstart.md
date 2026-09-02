# Быстрый старт для Custom UI

Пошаговое руководство по созданию минимального пользовательского UI.

## 1. Создание директории

```bash
mkdir -p ui/custom/templates ui/custom/static
```

## 2. Создание manifest.json

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

## 3. Создание минимального шаблона

### Главная страница (`index.html`)

`ui/custom/templates/index.html`:

```html
<!DOCTYPE html>
<html lang="ru">
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
        card.dataset.id = f.id;
        const img = document.createElement('img');
        img.src = `/api/thumbnail/${f.id}`;
        img.loading = 'lazy';
        img.alt = f.filename;
        card.appendChild(img);
        const name = document.createElement('span');
        name.className = 'filename';
        name.textContent = f.filename;
        card.appendChild(name);
        if (f.rating) {
          const rating = document.createElement('span');
          rating.className = 'rating';
          rating.textContent = '★'.repeat(f.rating);
          card.appendChild(rating);
        }
        grid.appendChild(card);
      });
    }

    document.getElementById('searchBtn').addEventListener('click', doSearch);
    // Первоначальный показ
    doSearch();
  </script>
</body>
</html>
```

`window.detailModalApi.showDetail(id)` следует использовать в качестве основного публичного API. Безопаснее не зависеть от старых глобальных имён вроде `window.showDetail(id)`.

Дополнительно:

- Для feature API предпочтительно использовать `window.<feature>Api.*`
- `window.tr`, `window.apiFetch`, `window.apiUrl`, `window.escapeHtml` остаются доступными глобальными функциями фреймворка

### Таблица стилей

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

## 4. Активация

При перезапуске сервера `ui/custom/` будет автоматически обнаружен.

```bash
python web_ui.py --db ./tags.db --port 5000
```

Для явного указания добавьте в `config.json`:

```json
{
  "ui": "custom"
}
```

## 5. Поддерживаемые маршруты страниц

Flask-маршрутизация соответствует следующим именам шаблонов:

| Маршрут | Шаблон | Описание |
|---------|--------|----------|
| `/` | `index.html` | Главная страница поиска |
| `/stats` | `stats.html` | Дашборд статистики |
| `/tools` | `tools.html` | Страница инструментов |
| `/settings` | `settings.html` | Страница настроек |
| `/extensions` | `extensions.html` | Управление Extension |
| `/story` | `story.html` | Страница Your Story |
| `/inspect` | `inspect.html` | Страница инспекции метаданных |

Если разместить шаблоны с этими именами в пользовательском UI, они будут отображаться по тому же URL.
При обращении к маршруту без соответствующего шаблона будет ошибка.

## 6. Пример страницы статистики

`ui/custom/templates/stats.html`:

```html
<!DOCTYPE html>
<html lang="ru">
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
          const val = document.createElement('div');
          val.className = 'stat-value';
          val.textContent = item.value;
          const lbl = document.createElement('div');
          lbl.className = 'stat-label';
          lbl.textContent = item.label;
          card.appendChild(val);
          card.appendChild(lbl);
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

## 7. Поддержка CSRF-защиты

Для вызовов API с POST / PUT / DELETE необходим заголовок `X-Requested-With`:

```javascript
// Пример установки рейтинга
async function setRating(fileId, rating) {
  const res = await fetch('/api/ratings/set', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Requested-With': 'XMLHttpRequest'  // CSRF-защита
    },
    body: JSON.stringify({ file_id: fileId, rating: rating })
  });
  return res.json();
}

// Добавить в избранное
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

**Совет**: Удобно создать вспомогательную функцию, оборачивающую все вызовы API:

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

// Пример использования
const results = await api('/api/search?q=landscape&limit=20');
await api('/api/ratings/set', {
  method: 'POST',
  body: JSON.stringify({ file_id: 42, rating: 5 }),
});
```

## Создание UI с помощью ИИ

Пример инструкции для Claude или ChatGPT для генерации пользовательского UI:

```
Пожалуйста, создайте пользовательский UI для YU AI Manager.

## Структура файлов
- ui/custom/manifest.json — метаданные UI
- ui/custom/templates/index.html — главная страница поиска
- ui/custom/templates/stats.html — страница статистики
- ui/custom/static/style.css — таблица стилей

## Основные API (все GET без аутентификации)
- GET /api/search?q=...&limit=50&sort=date — поиск изображений (результат: {results: [{id, filename, rating, ...}]})
- GET /api/thumbnail/<id> — миниатюра (WebP)
- GET /api/original/<id> — оригинальное изображение
- GET /api/file/<id> — детальные метаданные файла
- GET /api/stats/all — статистика
- GET /api/suggest?q=... — подсказки тегов
- GET /api/collections — список коллекций

## API записи (POST требует заголовок X-Requested-With: XMLHttpRequest)
- POST /api/ratings/set {file_id, rating} — установка рейтинга
- POST /api/favorites/add {file_id} — добавить в избранное
- POST /api/tags/batch-set {items: [{file_id, add: [...], remove: [...]}]}

## Требования к дизайну
- Тёмный режим (фон #0f1115, текст #e7eaf0, акцент #60a5fa)
- Адаптивный сеточный макет
- Карточки с миниатюрами, отображающие filename и rating
```

## Справочник API

Полная документация по всем API: [docs/api/](../api/README.md).
