# API 參考 -- 自訂 UI 開發者連結與快速參考

本頁面彙集了 API 文件連結以及常用 API 的快速參考表。

## 文件索引

### 通用慣例

- [API 通用慣例](../api/README.md) -- 基礎 URL、驗證（4 種方式）、CSRF 保護、速率限制、回應格式、分頁

### 依端點分類

- [Search API](../api/search.md) -- GET /api/search、建議、群組、server-info
- [Files API](../api/files.md) -- 檔案詳情、縮圖、原始檔案、提示詞轉換
- [Scan API](../api/scan.md) -- 掃描控制、掃描根管理、雜湊回填
- [Events API](../api/events.md) -- SSE 即時事件、記錄檔串流

### 主題

- [CSS 變數清單](../api/theming.md) -- 主題自訂屬性（淺色/深色）

## 快速參考

### 讀取操作（GET，無需驗證*）

| 端點 | 用途 | 關鍵參數 |
|------|------|----------|
| `/api/search` | 檔案搜尋 | `q`、`sort`、`limit`、`cursor`、`rating_min`、`collection_id` |
| `/api/thumbnail/<id>` | 縮圖（WebP） | `size`（預設 300） |
| `/api/original/<id>` | 原始檔案 | 支援 Range |
| `/api/file/<id>` | 檔案詳情 | -- |
| `/api/suggest` | 標籤建議 | `q`、`limit` |
| `/api/stats/all` | 統計資訊 | -- |
| `/api/collections` | 收藏集清單 | -- |
| `/api/server-info` | 伺服器資訊 | -- |
| `/api/events/stream` | SSE 串流 | `types` |

*在無 PIN 環境或已驗證的工作階段中適用

### 寫入操作（POST，需要 `X-Requested-With` 標頭）

| 端點 | 用途 | Body 範例 |
|------|------|-----------|
| `/api/ratings/set` | 設定評分 | `{file_id: 42, rating: 5}` |
| `/api/ratings/batch-set` | 批次評分 | `{items: [{file_id, rating}, ...]}` |
| `/api/favorites/add` | 新增至我的最愛 | `{file_id: 42}` |
| `/api/favorites/remove` | 從我的最愛移除 | `{file_id: 42}` |
| `/api/tags/batch-set` | 批次標籤操作 | `{items: [{file_id, add: [], remove: []}]}` |
| `/api/collections` | 建立收藏集 | `{name: "My Collection"}` |
| `/api/collections/<id>/batch-add` | 新增至收藏集 | `{file_ids: [1, 2, 3]}` |
| `/api/scan-all` | 開始掃描 | `{}` |
| `/api/convert` | 提示詞轉換 | `{prompt, direction}` |

### UI 管理

| 端點 | 方法 | 用途 |
|------|------|------|
| `/api/ui/list` | GET | 列出 UI |
| `/api/ui/switch` | POST | 切換 UI |
| `/api/ui/install` | POST | 安裝 UI（僅限 localhost） |
| `/api/ui/<name>/uninstall` | DELETE | 解除安裝 UI（僅限 localhost） |

## 回應格式

### 搜尋結果

```javascript
{
  results: [
    {
      id: 42,
      path: "/images/00042.png",
      filename: "00042.png",
      width: 1024,
      height: 1536,
      meta_type: "a1111_png",   // a1111_png, novelai_v4_png, comfy_png, unknown
      model_name: "animagine-xl-3.1",
      positive: "1girl, landscape",
      rating: 4,                 // 0-5（0 = 未評分）
      is_favorite: true,
      tags: ["landscape", "sunset"]
    }
  ],
  total: 1500,
  next_cursor: "base64token..."  // null = 最後一頁
}
```

### 縮圖

```
GET /api/thumbnail/42
→ Content-Type: image/webp
→ ETag: "abc123"
→ Cache-Control: max-age=86400
```

瀏覽器會自動快取縮圖。可以直接在 `<img>` 標籤中參照：

```html
<img src="/api/thumbnail/42" loading="lazy" alt="thumbnail">
```

### 錯誤回應

```javascript
{
  ok: false,
  error: "Rate limit exceeded",
  code: "RATE_LIMIT",      // 選用
  detail: "Retry after 5s"  // 選用
}
```

## CSRF 標頭注意事項

```javascript
// 通用標頭輔助工具
const API_HEADERS = {
  'Content-Type': 'application/json',
  'X-Requested-With': 'XMLHttpRequest',
};

// GET：不需要標頭
fetch('/api/search?q=test');

// POST：需要 X-Requested-With
fetch('/api/ratings/set', {
  method: 'POST',
  headers: API_HEADERS,
  body: JSON.stringify({ file_id: 42, rating: 5 }),
});
```
