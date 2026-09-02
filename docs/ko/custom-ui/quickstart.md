# 커스텀 UI 퀵스타트

이 가이드는 최소한의 커스텀 UI를 만들고 동작을 확인하는 과정을 안내합니다.

## 1. 디렉토리 생성

```bash
mkdir -p ui/custom/templates ui/custom/static
```

## 2. manifest.json 생성

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

## 3. 최소 템플릿 생성

### 메인 페이지 (`index.html`)

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
          ${f.rating ? '<span class="rating">' + '\u2605'.repeat(f.rating) + '</span>' : ''}
        </div>
      `).join('');
    }

    async function showDetail(id) {
      const res = await fetch(`/api/file/${id}`);
      const file = await res.json();
      alert(JSON.stringify(file, null, 2));
    }

    // 초기 로드
    doSearch();
  </script>
</body>
</html>
```

### 스타일시트

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

## 4. 활성화

서버 재시작 시 `ui/custom/`이 자동으로 감지됩니다.

```bash
python web_ui.py --db ./tags.db --port 5000
```

`config.json`에서 UI를 명시적으로 지정할 수도 있습니다:

```json
{
  "ui": "custom"
}
```

## 5. 지원되는 페이지 라우트

Flask 라우팅은 다음 템플릿 이름에 매핑됩니다:

| 라우트 | 템플릿 | 설명 |
|--------|--------|------|
| `/` | `index.html` | 메인 검색 페이지 |
| `/stats` | `stats.html` | 통계 대시보드 |
| `/tools` | `tools.html` | 도구 페이지 |
| `/settings` | `settings.html` | 설정 페이지 |
| `/extensions` | `extensions.html` | 확장 관리 |
| `/story` | `story.html` | Your Story 페이지 |
| `/inspect` | `inspect.html` | 메타데이터 인스펙터 페이지 |

이 이름의 템플릿을 배치하면 커스텀 UI가 동일한 URL에 표시됩니다. 템플릿이 존재하지 않는 라우트에 사용자가 접근하면 오류가 발생합니다.

## 6. 통계 페이지 예시

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

## 7. CSRF 보호 처리

POST / PUT / DELETE를 사용하는 API 호출에는 `X-Requested-With` 헤더가 필요합니다:

```javascript
// 예: 평가 설정
async function setRating(fileId, rating) {
  const res = await fetch('/api/ratings/set', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Requested-With': 'XMLHttpRequest'  // CSRF 보호
    },
    body: JSON.stringify({ file_id: fileId, rating: rating })
  });
  return res.json();
}

// 즐겨찾기에 추가
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

**팁**: 모든 API 호출을 래핑하는 헬퍼 함수를 만들면 편리합니다:

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

// 사용 예
const results = await api('/api/search?q=landscape&limit=20');
await api('/api/ratings/set', {
  method: 'POST',
  body: JSON.stringify({ file_id: 42, rating: 5 }),
});
```

## AI로 UI 생성하기

Claude나 ChatGPT에 다음과 같은 프롬프트를 전달하여 커스텀 UI를 생성할 수 있습니다:

```
Create a custom UI for YU AI Manager.

## File structure
- ui/custom/manifest.json -- UI metadata
- ui/custom/templates/index.html -- Main search page
- ui/custom/templates/stats.html -- Statistics page
- ui/custom/static/style.css -- Stylesheet

## Key APIs (all GETs require no auth)
- GET /api/search?q=...&limit=50&sort=date -- Image search (response: {results: [{id, filename, rating, ...}]})
- GET /api/thumbnail/<id> -- Thumbnail image (WebP)
- GET /api/original/<id> -- Original image
- GET /api/file/<id> -- File detail metadata
- GET /api/stats/all -- Statistics
- GET /api/suggest?q=... -- Tag suggestions
- GET /api/collections -- Collection list

## Write APIs (POST requires X-Requested-With: XMLHttpRequest header)
- POST /api/ratings/set {file_id, rating} -- Set rating
- POST /api/favorites/add {file_id} -- Add to favorites
- POST /api/tags/batch-set {items: [{file_id, add: [...], remove: [...]}]}

## Design requirements
- Dark mode (background #0f1115, text #e7eaf0, accent #60a5fa)
- Responsive grid layout
- Thumbnail cards showing filename and rating
```

## API 레퍼런스

전체 API 문서는 [docs/api/](../api/README.md)를 참조하세요.
