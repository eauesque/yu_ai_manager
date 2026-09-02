# 高级指南 -- SSE、批量操作与安全

本指南介绍了自定义 UI 的高级功能和实现模式。

## 实时更新 (SSE)

Server-Sent Events 允许 UI 接收扫描进度、收藏变更、AI 分析进度等实时通知。

### 连接

```javascript
// 直接使用 EventSource（在自定义 UI 中是安全的）
const sse = new EventSource('/api/events/stream');

// 订阅事件
sse.addEventListener('scan.progress', (e) => {
  const data = JSON.parse(e.data);
  console.log(`扫描: ${data.scanned}/${data.total}`);
});

sse.addEventListener('scan.complete', (e) => {
  const data = JSON.parse(e.data);
  console.log(`扫描完成: 新增 ${data.added_count} 个`);
  // 重新加载网格
  reloadResults();
});
```

**注意**：参考 UI（`ui/default/`）用 Proxy 覆盖了 `window.EventSource`，因此 `new EventSource()` 在那里不起作用。此限制不适用于自定义 UI，可以直接使用 EventSource。

### 关键事件

| 事件 | 数据 | UI 用途 |
|------|------|---------|
| `scan.progress` | `{ scanned, total, current_file }` | 进度条 |
| `scan.complete` | `{ added_count, updated_count }` | 重新加载搜索结果 |
| `favorite.add` | `{ file_id, collection_id }` | 更新收藏图标 |
| `favorite.remove` | `{ file_id, collection_id }` | 更新收藏图标 |
| `collection.create` | `{ id, name }` | 更新收藏集列表 |

所有事件类型请参阅 [events.md](../api/events.md)。

### 连接管理

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
      // 指数退避重连
      setTimeout(() => this.connect(), 3000);
    };
    // 重新注册现有处理器
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

// 使用示例
const sse = new SSEConnection();
sse.on('scan.progress', (data) => updateProgressBar(data));
sse.on('scan.complete', () => reloadResults());
```

### 可见性感知连接

当标签页隐藏时关闭连接，重新可见时重新连接，以节省资源：

```javascript
document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    sse.close();
  } else {
    sse.connect();
  }
});
```

## 批量操作

这些 API 模式可以一次对多个文件执行操作。

### 批量评分

```javascript
async function batchRate(items) {
  // items: [{file_id: 1, rating: 5}, {file_id: 2, rating: 3}]
  // 最多 500 项
  const res = await api('/api/ratings/batch-set', {
    method: 'POST',
    body: JSON.stringify({ items }),
  });
  return res;
}
```

### 批量标签操作

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

### 批量收藏集操作

```javascript
// 添加到收藏集
async function addToCollection(collectionId, fileIds) {
  return api(`/api/collections/${collectionId}/batch-add`, {
    method: 'POST',
    body: JSON.stringify({ file_ids: fileIds }),
  });
}

// 从收藏集移除
async function removeFromCollection(collectionId, fileIds) {
  return api(`/api/collections/${collectionId}/batch-remove`, {
    method: 'POST',
    body: JSON.stringify({ file_ids: fileIds }),
  });
}
```

### 处理部分失败

批量操作可能部分成功：

```javascript
const result = await batchRate(items);
if (result.failed && result.failed.length > 0) {
  console.warn(`${result.failed.length} 项失败:`, result.failed);
  showToast(`${result.succeeded} 项成功，${result.failed.length} 项失败`);
}
```

## 错误处理

### HTTP 状态码

| 状态码 | 含义 | 处理 |
|--------|------|------|
| 200 | 成功 | -- |
| 304 | 未修改 | 使用缓存（缩略图） |
| 400 | 错误请求 | 验证输入 |
| 403 | 认证失败 / CSRF 无效 | 检查 `X-Requested-With` 头 |
| 404 | 资源未找到 | 验证文件 ID |
| 429 | 速率限制 | 等待 `Retry-After` 头中指定的秒数 |
| 500 | 服务器错误 | 重试或检查日志 |

### 速率限制处理

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
      console.warn(`速率限制，${retryAfter} 秒后重试`);
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

### 响应格式检测

存在两种响应格式（旧版和当前版）：

```javascript
function parseApiResponse(json) {
  // 当前格式: { ok, error, data }
  if ('ok' in json) {
    if (!json.ok) throw new Error(json.error || 'Unknown error');
    return json.data ?? json;
  }
  // 旧版格式: { success, message }
  if ('success' in json) {
    if (!json.success) throw new Error(json.message || 'Unknown error');
    return json;
  }
  // 直接数据格式（results 等）
  return json;
}
```

## 安全

### CSRF 保护

所有写操作（POST / PUT / DELETE）都需要 `X-Requested-With` 头：

```javascript
// 正确：包含头
fetch('/api/ratings/set', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-Requested-With': 'XMLHttpRequest',
  },
  body: JSON.stringify({ file_id: 42, rating: 5 }),
});
```

**例外**：带有 `Authorization: Bearer sk_...` 头的 API Key 请求不需要 CSRF 头。

### XSS 防护

在将用户输入和文件名插入 DOM 之前进行转义：

```javascript
function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// 错误：直接插入文件名
card.innerHTML = `<p>${file.filename}</p>`;  // XSS 风险

// 较好：先转义
card.innerHTML = `<p>${escapeHtml(file.filename)}</p>`;

// 最佳：使用 DOM API
const p = document.createElement('p');
p.textContent = file.filename;  // 自动转义
card.appendChild(p);
```

### API Key 处理

构建自定义 UI 时，不要在客户端代码中嵌入 API Key。基于浏览器的 UI 应使用由 CSRF 头保护的 PIN / 会话认证。

## 搜索实现

### 基本搜索

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

### 自动补全

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

### 排序选项

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

// 创建收藏集
async function createCollection(name) {
  return api('/api/collections', {
    method: 'POST',
    body: JSON.stringify({ name }),
  });
}

// 在收藏集中搜索
async function searchInCollection(collectionId, query = '') {
  return search(query, { collection: collectionId });
}
```

## 提示词转换

在 A1111 和 NAI 格式之间转换提示词：

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

### 分发自定义 UI

有多种方式可以将自定义 UI 分发给其他用户：

1. **Git 仓库**：推送到 GitHub，然后通过设置 UI 安装
2. **ZIP 归档**：将文件打包为 ZIP 并分享下载 URL
3. **手动放置**：直接复制到 `ui/<name>/` 目录

### 安装

通过设置页面的"UI"标签页或 API 安装：

```bash
# 使用 curl 安装
curl -X POST http://localhost:5000/api/ui/install \
  -H "X-Requested-With: XMLHttpRequest" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://github.com/user/my-custom-ui.git"}'
```

### manifest.json 要求

在分发的 UI 的 `manifest.json` 中包含以下内容：

```json
{
  "name": "my-custom-ui",
  "version": "1.0.0",
  "description": "A beautiful custom UI for YU AI Manager",
  "author": "Your Name",
  "api_version": "1"
}
```

- `name` 和 `version` 是必需的
- `name` 同时作为安装目录名称
- `"default"` 是保留名称，不可使用
