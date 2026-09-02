# Advanced Guide — SSE・バッチ操作・セキュリティ

カスタム UI の高度な機能と実装パターンです。

## リアルタイム更新 (SSE)

Server-Sent Events でスキャン進捗、お気に入り変更、AI 分析の進捗等をリアルタイムに受信できます。

### 接続方法

```javascript
// EventSource を直接使う (カスタム UI ではこれが安全)
const sse = new EventSource('/api/events/stream');

// イベントの購読
sse.addEventListener('scan.progress', (e) => {
  const data = JSON.parse(e.data);
  console.log(`Scan: ${data.scanned}/${data.total}`);
});

sse.addEventListener('scan.complete', (e) => {
  const data = JSON.parse(e.data);
  console.log(`Scan done: ${data.added_count} added`);
  // グリッドを再読み込み
  reloadResults();
});
```

**注意**: リファレンス UI (`ui/default/`) では `window.EventSource` が Proxy で上書きされているため
`new EventSource()` が使えません。カスタム UI ではこの制限は適用されないため、直接利用できます。

### 主要イベント一覧

| イベント | データ | UI での用途 |
|---------|--------|------------|
| `scan.progress` | `{ scanned, total, current_file }` | プログレスバー表示 |
| `scan.complete` | `{ added_count, updated_count }` | 検索結果の再読み込み |
| `favorite.add` | `{ file_id, collection_id }` | お気に入りアイコン更新 |
| `favorite.remove` | `{ file_id, collection_id }` | お気に入りアイコン更新 |
| `collection.create` | `{ id, name }` | コレクションリスト更新 |

全イベント型は [events.md](../api/events.md) を参照してください。

### 接続管理

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
      // 再接続 (指数バックオフ)
      setTimeout(() => this.connect(), 3000);
    };
    // 登録済みハンドラを再設定
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

// 使用例
const sse = new SSEConnection();
sse.on('scan.progress', (data) => updateProgressBar(data));
sse.on('scan.complete', () => reloadResults());
```

### Visibility-aware 接続

タブが非表示になったときに接続を抑制し、リソースを節約:

```javascript
document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    sse.close();
  } else {
    sse.connect();
  }
});
```

## バッチ操作

複数ファイルに対する操作を一括で実行する API パターンです。

### レーティング一括設定

```javascript
async function batchRate(items) {
  // items: [{file_id: 1, rating: 5}, {file_id: 2, rating: 3}]
  // 最大 500 件
  const res = await api('/api/ratings/batch-set', {
    method: 'POST',
    body: JSON.stringify({ items }),
  });
  return res;
}
```

### タグ一括操作

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

### コレクション一括操作

```javascript
// コレクションに追加
async function addToCollection(collectionId, fileIds) {
  return api(`/api/collections/${collectionId}/batch-add`, {
    method: 'POST',
    body: JSON.stringify({ file_ids: fileIds }),
  });
}

// コレクションから削除
async function removeFromCollection(collectionId, fileIds) {
  return api(`/api/collections/${collectionId}/batch-remove`, {
    method: 'POST',
    body: JSON.stringify({ file_ids: fileIds }),
  });
}
```

### 部分成功の処理

バッチ操作は部分的に成功する場合があります:

```javascript
const result = await batchRate(items);
if (result.failed && result.failed.length > 0) {
  console.warn(`${result.failed.length} items failed:`, result.failed);
  showToast(`${result.succeeded} succeeded, ${result.failed.length} failed`);
}
```

## エラーハンドリング

### HTTP ステータスコード

| コード | 意味 | 対処 |
|--------|------|------|
| 200 | 成功 | - |
| 304 | Not Modified | キャッシュを使用 (サムネイル) |
| 400 | リクエスト不正 | 入力を確認 |
| 403 | 認証失敗 / CSRF 不正 | `X-Requested-With` ヘッダ確認 |
| 404 | リソースなし | ファイル ID を確認 |
| 429 | レートリミット | `Retry-After` ヘッダ秒数待機 |
| 500 | サーバーエラー | リトライまたはログ確認 |

### レートリミット対応

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

### レスポンス形式の判定

新旧 2 種類のレスポンス形式があります:

```javascript
function parseApiResponse(json) {
  // 新形式: { ok, error, data }
  if ('ok' in json) {
    if (!json.ok) throw new Error(json.error || 'Unknown error');
    return json.data ?? json;
  }
  // 旧形式: { success, message }
  if ('success' in json) {
    if (!json.success) throw new Error(json.message || 'Unknown error');
    return json;
  }
  // 直接データ形式 (results 等)
  return json;
}
```

## セキュリティ

### CSRF 保護

すべての書き込み操作 (POST / PUT / DELETE) には `X-Requested-With` ヘッダが必須です:

```javascript
// 良い例: ヘッダを含む
fetch('/api/ratings/set', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-Requested-With': 'XMLHttpRequest',
  },
  body: JSON.stringify({ file_id: 42, rating: 5 }),
});
```

**例外**: `Authorization: Bearer sk_...` ヘッダ付きの API Key リクエストは CSRF ヘッダ不要。

### XSS 防止

ユーザー入力やファイル名を DOM に挿入する際はサニタイズが必要です:

```javascript
function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// 悪い例: ファイル名をそのまま挿入
card.innerHTML = `<p>${file.filename}</p>`;  // XSS リスク

// 良い例: エスケープ
card.innerHTML = `<p>${escapeHtml(file.filename)}</p>`;

// さらに良い例: DOM API を使用
const p = document.createElement('p');
p.textContent = file.filename;  // 自動エスケープ
card.appendChild(p);
```

### API Key の取り扱い

カスタム UI から API Key を使う場合、クライアントサイドに Key を埋め込まないでください。
ブラウザベースの UI では通常 PIN / セッション認証を使用し、CSRF ヘッダで保護します。

## 検索機能の実装

### 基本検索

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

### オートコンプリート

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

### ソート切り替え

```javascript
const SORT_OPTIONS = [
  { value: 'date', label: 'Date (New)' },
  { value: 'name', label: 'Name' },
  { value: 'size', label: 'Size' },
  { value: 'rating', label: 'Rating' },
  { value: 'random', label: 'Random' },
];
```

## コレクション管理

```javascript
// コレクション一覧取得
async function getCollections() {
  const res = await fetch('/api/collections');
  return res.json();
}

// コレクション作成
async function createCollection(name) {
  return api('/api/collections', {
    method: 'POST',
    body: JSON.stringify({ name }),
  });
}

// コレクション内検索
async function searchInCollection(collectionId, query = '') {
  return search(query, { collection: collectionId });
}
```

## プロンプト変換

A1111 / NAI 間のプロンプト形式変換:

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

## デプロイ

### カスタム UI の配布

カスタム UI を他のユーザーに配布する場合:

1. **Git リポジトリ**: GitHub 等にプッシュ → Settings UI からインストール
2. **ZIP アーカイブ**: ファイルを ZIP 化してダウンロード URL を共有
3. **手動配置**: `ui/<name>/` ディレクトリに直接コピー

### インストール

Settings ページの「UI」タブ、または API からインストール:

```bash
# curl でインストール
curl -X POST http://localhost:5000/api/ui/install \
  -H "X-Requested-With: XMLHttpRequest" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://github.com/user/my-custom-ui.git"}'
```

### manifest.json の要件

配布する UI の `manifest.json` には以下を含めてください:

```json
{
  "name": "my-custom-ui",
  "version": "1.0.0",
  "description": "A beautiful custom UI for YU AI Manager",
  "author": "Your Name",
  "api_version": "1"
}
```

- `name` と `version` は必須
- `name` はインストール先のディレクトリ名にもなります
- `"default"` は予約名のため使用不可
