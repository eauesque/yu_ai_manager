# API 参考 -- 自定义 UI 开发者链接与快速参考

本页面汇集了 API 文档链接以及常用 API 的快速参考表。

## 文档索引

### 通用约定

- [API 通用约定](../api/README.md) -- 基础 URL、认证（4 种方式）、CSRF 保护、速率限制、响应格式、分页

### 按端点分类

- [Search API](../api/search.md) -- GET /api/search、建议、分组、server-info
- [Files API](../api/files.md) -- 文件详情、缩略图、原始文件、提示词转换
- [Scan API](../api/scan.md) -- 扫描控制、扫描根管理、哈希回填
- [Events API](../api/events.md) -- SSE 实时事件、日志流

### 主题

- [CSS 变量列表](../api/theming.md) -- 主题自定义属性（浅色/深色）

## 快速参考

### 读取操作（GET，无需认证*）

| 端点 | 用途 | 关键参数 |
|------|------|----------|
| `/api/search` | 文件搜索 | `q`、`sort`、`limit`、`cursor`、`rating_min`、`collection_id` |
| `/api/thumbnail/<id>` | 缩略图（WebP） | `size`（默认 300） |
| `/api/original/<id>` | 原始文件 | 支持 Range |
| `/api/file/<id>` | 文件详情 | -- |
| `/api/suggest` | 标签建议 | `q`、`limit` |
| `/api/stats/all` | 统计信息 | -- |
| `/api/collections` | 收藏集列表 | -- |
| `/api/server-info` | 服务器信息 | -- |
| `/api/events/stream` | SSE 流 | `types` |

*在无 PIN 环境或已认证的会话中适用

### 写入操作（POST，需要 `X-Requested-With` 头）

| 端点 | 用途 | Body 示例 |
|------|------|-----------|
| `/api/ratings/set` | 设置评分 | `{file_id: 42, rating: 5}` |
| `/api/ratings/batch-set` | 批量评分 | `{items: [{file_id, rating}, ...]}` |
| `/api/favorites/add` | 添加到收藏 | `{file_id: 42}` |
| `/api/favorites/remove` | 从收藏移除 | `{file_id: 42}` |
| `/api/tags/batch-set` | 批量标签操作 | `{items: [{file_id, add: [], remove: []}]}` |
| `/api/collections` | 创建收藏集 | `{name: "My Collection"}` |
| `/api/collections/<id>/batch-add` | 添加到收藏集 | `{file_ids: [1, 2, 3]}` |
| `/api/scan-all` | 开始扫描 | `{}` |
| `/api/convert` | 提示词转换 | `{prompt, direction}` |

### UI 管理

| 端点 | 方法 | 用途 |
|------|------|------|
| `/api/ui/list` | GET | 列出 UI |
| `/api/ui/switch` | POST | 切换 UI |
| `/api/ui/install` | POST | 安装 UI（仅限 localhost） |
| `/api/ui/<name>/uninstall` | DELETE | 卸载 UI（仅限 localhost） |

## 响应格式

### 搜索结果

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
      rating: 4,                 // 0-5（0 = 未评分）
      is_favorite: true,
      tags: ["landscape", "sunset"]
    }
  ],
  total: 1500,
  next_cursor: "base64token..."  // null = 最后一页
}
```

### 缩略图

```
GET /api/thumbnail/42
→ Content-Type: image/webp
→ ETag: "abc123"
→ Cache-Control: max-age=86400
```

浏览器会自动缓存缩略图。可以直接在 `<img>` 标签中引用：

```html
<img src="/api/thumbnail/42" loading="lazy" alt="thumbnail">
```

### 错误响应

```javascript
{
  ok: false,
  error: "Rate limit exceeded",
  code: "RATE_LIMIT",      // 可选
  detail: "Retry after 5s"  // 可选
}
```

## CSRF 头注意事项

```javascript
// 通用头辅助工具
const API_HEADERS = {
  'Content-Type': 'application/json',
  'X-Requested-With': 'XMLHttpRequest',
};

// GET：不需要头
fetch('/api/search?q=test');

// POST：需要 X-Requested-With
fetch('/api/ratings/set', {
  method: 'POST',
  headers: API_HEADERS,
  body: JSON.stringify({ file_id: 42, rating: 5 }),
});
```
