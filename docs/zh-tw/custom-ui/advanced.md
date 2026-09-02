# 進階指南 -- SSE、批次操作與安全性

本指南介紹了自訂 UI 的進階功能和實作模式。

## 即時更新 (SSE)

Server-Sent Events 允許 UI 接收掃描進度、我的最愛變更、AI 分析進度等即時通知。

### 連線

```javascript
// 直接使用 EventSource（在自訂 UI 中是安全的）
const sse = new EventSource('/api/events/stream');

// 訂閱事件
sse.addEventListener('scan.progress', (e) => {
  const data = JSON.parse(e.data);
  console.log(`掃描: ${data.scanned}/${data.total}`);
});

sse.addEventListener('scan.complete', (e) => {
  const data = JSON.parse(e.data);
  console.log(`掃描完成: 新增 ${data.added_count} 個`);
  // 重新載入格線
  reloadResults();
});
```

**注意**：參考 UI（`ui/default/`）用 Proxy 覆寫了 `window.EventSource`，因此 `new EventSource()` 在那裡無法運作。此限制不適用於自訂 UI，可以直接使用 EventSource。

### 關鍵事件

| 事件 | 資料 | UI 用途 |
|------|------|---------|
| `scan.progress` | `{ scanned, total, current_file }` | 進度列 |
| `scan.complete` | `{ added_count, updated_count }` | 重新載入搜尋結果 |
| `favorite.add` | `{ file_id, collection_id }` | 更新我的最愛圖示 |
| `favorite.remove` | `{ file_id, collection_id }` | 更新我的最愛圖示 |
| `collection.create` | `{ id, name }` | 更新收藏集清單 |

所有事件類型請參閱 [events.md](../api/events.md)。

### 連線管理

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
      // 指數退避重新連線
      setTimeout(() => this.connect(), 3000);
    };
    // 重新註冊現有處理器
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

// 使用範例
const sse = new SSEConnection();
sse.on('scan.progress', (data) => updateProgressBar(data));
sse.on('scan.complete', () => reloadResults());
```

### 可見性感知連線

當標籤頁隱藏時關閉連線，重新可見時重新連線，以節省資源：

```javascript
document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    sse.close();
  } else {
    sse.connect();
  }
});
```

## 批次操作

這些 API 模式可以一次對多個檔案執行操作。

### 批次評分

```javascript
async function batchRate(items) {
  // items: [{file_id: 1, rating: 5}, {file_id: 2, rating: 3}]
  // 最多 500 項
  const res = await api('/api/ratings/batch-set', {
    method: 'POST',
    body: JSON.stringify({ items }),
  });
  return res;
}
```

### 批次標籤操作

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

### 批次收藏集操作

```javascript
// 新增至收藏集
async function addToCollection(collectionId, fileIds) {
  return api(`/api/collections/${collectionId}/batch-add`, {
    method: 'POST',
    body: JSON.stringify({ file_ids: fileIds }),
  });
}

// 從收藏集移除
async function removeFromCollection(collectionId, fileIds) {
  return api(`/api/collections/${collectionId}/batch-remove`, {
    method: 'POST',
    body: JSON.stringify({ file_ids: fileIds }),
  });
}
```

### 處理部分失敗

批次操作可能部分成功：

```javascript
const result = await batchRate(items);
if (result.failed && result.failed.length > 0) {
  console.warn(`${result.failed.length} 項失敗:`, result.failed);
  showToast(`${result.succeeded} 項成功，${result.failed.length} 項失敗`);
}
```

## 錯誤處理

### HTTP 狀態碼

| 狀態碼 | 含義 | 處理 |
|--------|------|------|
| 200 | 成功 | -- |
| 304 | 未修改 | 使用快取（縮圖） |
| 400 | 錯誤請求 | 驗證輸入 |
| 403 | 驗證失敗 / CSRF 無效 | 檢查 `X-Requested-With` 標頭 |
| 404 | 找不到資源 | 驗證檔案 ID |
| 429 | 速率限制 | 等待 `Retry-After` 標頭中指定的秒數 |
| 500 | 伺服器錯誤 | 重試或檢查記錄檔 |

### 速率限制處理

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
      console.warn(`速率限制，${retryAfter} 秒後重試`);
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

### 回應格式偵測

存在兩種回應格式（舊版和目前版）：

```javascript
function parseApiResponse(json) {
  // 目前格式: { ok, error, data }
  if ('ok' in json) {
    if (!json.ok) throw new Error(json.error || 'Unknown error');
    return json.data ?? json;
  }
  // 舊版格式: { success, message }
  if ('success' in json) {
    if (!json.success) throw new Error(json.message || 'Unknown error');
    return json;
  }
  // 直接資料格式（results 等）
  return json;
}
```

## 安全性

### CSRF 保護

所有寫入操作（POST / PUT / DELETE）都需要 `X-Requested-With` 標頭：

```javascript
// 正確：包含標頭
fetch('/api/ratings/set', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-Requested-With': 'XMLHttpRequest',
  },
  body: JSON.stringify({ file_id: 42, rating: 5 }),
});
```

**例外**：帶有 `Authorization: Bearer sk_...` 標頭的 API Key 請求不需要 CSRF 標頭。

### XSS 防護

在將使用者輸入和檔案名稱插入 DOM 之前進行跳脫：

```javascript
function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// 錯誤：直接插入檔案名稱
card.innerHTML = `<p>${file.filename}</p>`;  // XSS 風險

// 較好：先跳脫
card.innerHTML = `<p>${escapeHtml(file.filename)}</p>`;

// 最佳：使用 DOM API
const p = document.createElement('p');
p.textContent = file.filename;  // 自動跳脫
card.appendChild(p);
```

### API Key 處理

建構自訂 UI 時，不要在用戶端程式碼中嵌入 API Key。基於瀏覽器的 UI 應使用由 CSRF 標頭保護的 PIN / 工作階段驗證。

## 搜尋實作

### 基本搜尋

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

### 自動補全

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

### 排序選項

```javascript
const SORT_OPTIONS = [
  { value: 'date', label: 'Date (New)' },
  { value: 'name', label: 'Name' },
  { value: 'size', label: 'Size' },
  { value: 'rating', label: 'Rating' },
  { value: 'random', label: 'Random' },
];
```

## 收藏集管理

```javascript
// 列出收藏集
async function getCollections() {
  const res = await fetch('/api/collections');
  return res.json();
}

// 建立收藏集
async function createCollection(name) {
  return api('/api/collections', {
    method: 'POST',
    body: JSON.stringify({ name }),
  });
}

// 在收藏集中搜尋
async function searchInCollection(collectionId, query = '') {
  return search(query, { collection: collectionId });
}
```

## 提示詞轉換

在 A1111 和 NAI 格式之間轉換提示詞：

```javascript
async function convertPrompt(prompt, direction) {
  // direction: "a1111_to_nai" 或 "nai_to_a1111"
  const res = await api('/api/convert', {
    method: 'POST',
    body: JSON.stringify({ prompt, direction }),
  });
  return res.converted;
}
```

## 部署

### 發布自訂 UI

有多種方式可以將自訂 UI 發布給其他使用者：

1. **Git 儲存庫**：推送到 GitHub，然後透過設定 UI 安裝
2. **ZIP 歸檔**：將檔案打包為 ZIP 並分享下載 URL
3. **手動放置**：直接複製到 `ui/<name>/` 目錄

### 安裝

透過設定頁面的「UI」標籤頁或 API 安裝：

```bash
# 使用 curl 安裝
curl -X POST http://localhost:5000/api/ui/install \
  -H "X-Requested-With: XMLHttpRequest" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://github.com/user/my-custom-ui.git"}'
```

### manifest.json 要求

在發布的 UI 的 `manifest.json` 中包含以下內容：

```json
{
  "name": "my-custom-ui",
  "version": "1.0.0",
  "description": "A beautiful custom UI for YU AI Manager",
  "author": "Your Name",
  "api_version": "1"
}
```

- `name` 和 `version` 是必要的
- `name` 同時作為安裝目錄名稱
- `"default"` 是保留名稱，不可使用
