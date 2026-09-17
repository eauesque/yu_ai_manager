# YU AI Manager API 参考文档

本 REST API 文档涵盖了 YU AI Manager 的所有功能，可供自定义 UI 和脚本使用。

## 通用约定

### Base URL

```
http://<host>:<port>
```

默认值：`http://127.0.0.1:5000`
测试环境：`http://127.0.0.1:5100`（使用 `config_test.json` 时）

### 认证

支持四种认证方式：

| 方式 | 用途 | 请求头示例 |
|--------|----------|----------------|
| PIN 认证 | 浏览器会话 | Cookie: `session=...` |
| API Key | 机器间通信 | `Authorization: Bearer sk_...` |
| Trusted Proxy | 反向代理后端 | `X-Remote-User: username` |
| LAN Share Token | 访客访问 | URL 路径 `/s/<token>/...` |

使用 `config_test.json`（无 PIN）启动可完全跳过认证。

### CSRF 保护

所有对 `/api/` 端点的 `POST` / `PUT` / `DELETE` 请求都需要 `X-Requested-With` 请求头：

```
X-Requested-With: XMLHttpRequest
```

**例外**：使用 `Authorization: Bearer` 请求头的 API Key 请求不需要 CSRF。

### 速率限制

| 层级 | 范围 | 速率 | 突发 |
|------|-------|------|-------|
| READ | 所有 GET | 无限制 | - |
| WRITE | POST/PUT/DELETE（标准） | ~120 req/min | 30 |
| HEAVY | 相似搜索、哈希计算、AI 分析、扫描 | ~20 req/min | 5 |
| DESTRUCTIVE | 清除、硬删除、缓存清理、配置写入 | ~12 req/min | 3 |

429 响应附带 `Retry-After` 请求头。

### 响应格式

**成功**（新 API）：
```json
{
  "ok": true,
  "error": null,
  "data": { ... }
}
```

**错误**：
```json
{
  "ok": false,
  "error": "Error message",
  "code": "ERROR_CODE",
  "detail": "Additional details (optional)"
}
```

部分旧版 API 返回 `{ "success": true, "message": "..." }` 格式。

### 分页

**基于偏移量**（默认）：
```
GET /api/search?offset=0&limit=50
```

**基于游标**（适用于大数据集）：
```
GET /api/search?cursor=<opaque_token>&limit=50
```

响应包含 `next_cursor` 字段。

### 批量操作

批量 API 每次请求最多支持 500 个操作。支持部分成功：

```json
POST /api/ratings/batch-set
{
  "items": [
    { "file_id": 1, "rating": 5 },
    { "file_id": 999, "rating": 3 }
  ]
}
```

## API 分类

| 文档 | 内容 |
|----------|---------|
| [search.md](search.md) | 搜索、建议、分组 |
| [files.md](files.md) | 文件详情、缩略图、媒体获取 |
| [scan.md](scan.md) | 扫描控制、扫描根目录管理 |
| [events.md](events.md) | SSE 事件流 |
| [theming.md](theming.md) | CSS 变量、主题自定义 |
| [source.md](source.md) | 源代码浏览（MCP 只读） |
| [github.md](github.md) | GitHub Integration（账号管理・Issue・PR・通知・Discussion・Release） |
| [scheduler.md](scheduler.md) | 任务调度器（任务管理・执行历史） |
| [ratings.md](ratings.md) | 评分（设置・批量设置・获取・统计） |
| [favorites.md](favorites.md) | 收藏（切换・检查・列表） |
| [collections.md](collections.md) | 集合（CRUD・排序・批量添加/移除・CSV 导出） |
| [tags.md](tags.md) | 标签（批量设置・建议） |
| [sns.md](sns.md) | SNS 分享 & Bluesky 监控（发帖・通知・分类・自动回复） |
| [hailo-remote-tagger.md](hailo-remote-tagger.md) | Hailo Remote Tagger（配置・单个/批量标记・标签 CRUD） |
| [tagger-servers.md](tagger-servers.md) | Tagger Server Registry (分布式标签推理集群・服务器管理・批量执行) |
| [svg.md](svg.md) | SVG 光栅化 (SVG 转 PNG/WebP、img2img 管线支持) |
| [system-update.md](system-update.md) | 系统更新（版本检查・应用更新・统合更新管理器） |
| [tools.md](tools.md) | 工具 (重复检测・哈希计算・相似搜索・缓存管理・备份・归档清理・调试日志) |
| [agent.md](agent.md) | Agent Safety Gateway (Kill Switch・Circuit Breaker・Budget・Approval・Scope Fence・Undo・异常检测) |
| [profiles.md](profiles.md) | 配置文件管理 (CRUD・复制・QR 导出/导入) |
| [wd-tagger.md](wd-tagger.md) | WD-Tagger (Danbooru 自动标签・模型管理・VLM・XMP) |
| [ocr.md](ocr.md) | OCR (文字识别・翻译・视频/PDF 支持・基准测试・配置文件) |
| [apikeys.md](apikeys.md) | API Key 管理 (创建・列表・范围・撤销) |
| [debug.md](debug.md) | 调试 (元数据检查・SQL 查询・模型验证) |
| [ui.md](ui.md) | UI 管理 (列表・切换・安装・卸载) |
| [video-analysis.md](video-analysis.md) | 视频分析 (配置・状态・关键帧提取) |
| [extensions.md](extensions.md) | Extension 管理 (列表・启用・配置・安装・安全・市场・创作) |
| [settings.md](settings.md) | 设置管理 (模式・获取/更新值・密钥加密・1Password/Bitwarden 集成) |
| [analysis.md](analysis.md) | AI 分析 (配置・单一/批量分析・趋势分析・统计・服务器注册) |

## 快速开始 (curl)

```bash
# 搜索（无 PIN 环境）
curl "http://localhost:5100/api/search?q=landscape&limit=10"

# 获取缩略图
curl "http://localhost:5100/api/thumbnail/42" -o thumb.webp

# 使用 API Key 搜索
curl -H "Authorization: Bearer sk_your_key_here" \
     "http://localhost:5100/api/search?q=portrait"

# 设置评分
curl -X POST "http://localhost:5100/api/ratings/set" \
     -H "X-Requested-With: XMLHttpRequest" \
     -H "Content-Type: application/json" \
     -d '{"file_id": 42, "rating": 5}'
```
