# Custom UI Quickstart

最小構成のカスタム UI を作成し、動作確認するまでの手順です。

## 1. ディレクトリ作成

```bash
mkdir -p ui/custom/templates ui/custom/static
```

## 2. manifest.json 作成

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

## 3. 最小テンプレート作成

### メインページ (`index.html`)

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

    // 初回表示
    doSearch();
  </script>
</body>
</html>
```

`window.detailModalApi.showDetail(id)` を正面の公開 API として使ってください。`window.showDetail(id)` のような旧グローバル名には依存しない前提で書くのが安全です。

補足:

- feature API は `window.<feature>Api.*` を優先してください
- `window.tr`, `window.apiFetch`, `window.apiUrl`, `window.escapeHtml` は基盤 global として引き続き利用可能です

### スタイルシート

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

## 4. 有効化

サーバーを再起動すると `ui/custom/` が自動検出されます。

```bash
python web_ui.py --db ./tags.db --port 5000
```

明示的に指定する場合は `config.json` に追加:

```json
{
  "ui": "custom"
}
```

## 5. 対応ページルート

Flask のルーティングは以下のテンプレート名に対応しています:

| ルート | テンプレート | 説明 |
|--------|------------|------|
| `/` | `index.html` | メイン検索ページ |
| `/stats` | `stats.html` | 統計ダッシュボード |
| `/tools` | `tools.html` | ツールページ |
| `/settings` | `settings.html` | 設定ページ |
| `/extensions` | `extensions.html` | Extension 管理 |
| `/story` | `story.html` | Your Story ページ |
| `/inspect` | `inspect.html` | メタデータ検査ページ |

カスタム UI でこれらの名前のテンプレートを配置すると、同じ URL で表示されます。
存在しないテンプレートのルートにアクセスした場合はエラーになります。

## 6. 統計ページの例

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

## 7. CSRF 保護に対応する

POST / PUT / DELETE を使う API 呼び出しには `X-Requested-With` ヘッダが必要です:

```javascript
// レーティング設定の例
async function setRating(fileId, rating) {
  const res = await fetch('/api/ratings/set', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Requested-With': 'XMLHttpRequest'  // CSRF 保護
    },
    body: JSON.stringify({ file_id: fileId, rating: rating })
  });
  return res.json();
}

// お気に入り追加
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

**ヒント**: すべての API 呼び出しをラップするヘルパー関数を用意すると便利です:

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

// 使用例
const results = await api('/api/search?q=landscape&limit=20');
await api('/api/ratings/set', {
  method: 'POST',
  body: JSON.stringify({ file_id: 42, rating: 5 }),
});
```

## AI で UI を作る

Claude や ChatGPT にカスタム UI の生成を依頼する場合の指示例:

```
YU AI Manager のカスタム UI を作成してください。

## ファイル構成
- ui/custom/manifest.json — UI メタデータ
- ui/custom/templates/index.html — メイン検索ページ
- ui/custom/templates/stats.html — 統計ページ
- ui/custom/static/style.css — スタイルシート

## 主要 API (すべて GET は認証不要)
- GET /api/search?q=...&limit=50&sort=date — 画像検索 (結果: {results: [{id, filename, rating, ...}]})
- GET /api/thumbnail/<id> — サムネイル画像 (WebP)
- GET /api/original/<id> — オリジナル画像
- GET /api/file/<id> — ファイル詳細メタデータ
- GET /api/stats/all — 統計情報
- GET /api/suggest?q=... — タグサジェスト
- GET /api/collections — コレクション一覧

## 書き込み API (POST には X-Requested-With: XMLHttpRequest ヘッダ必須)
- POST /api/ratings/set {file_id, rating} — レーティング設定
- POST /api/favorites/add {file_id} — お気に入り追加
- POST /api/tags/batch-set {items: [{file_id, add: [...], remove: [...]}]}

## デザイン要件
- ダークモード (背景 #0f1115、テキスト #e7eaf0、アクセント #60a5fa)
- レスポンシブグリッドレイアウト
- サムネイルカードに filename と rating を表示
```

## API リファレンス

全 API の詳細は [docs/api/](../api/README.md) を参照してください。
