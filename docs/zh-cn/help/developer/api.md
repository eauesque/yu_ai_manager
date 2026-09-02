# API 概述

YU AI Manager 提供 REST API，允许您以编程方式执行所有 WebUI 操作。
拥有超过 320 个端点，涵盖从图片管理到 AI 分析的广泛操作。

> **提示**：有关认证、CSRF、速率限制、响应格式等详细通用约定，请参阅"API Reference"部分。

## 认证

支持 4 种认证方式。

| 方式 | 用途 | 头/参数 |
|------|------|---------|
| PIN 认证 | 浏览器会话 | 在 `/_pin` 登录 -> 会话 cookie |
| API Key | 机器间通信 / MCP | `Authorization: Bearer sk_xxxx` |
| Trusted Proxy | 反向代理 | `X-Remote-User` 头 |
| LAN Share 令牌 | 访客访问 | `/s/<token>` 路径 |

### 使用 curl 测试

```bash
# API Key 认证（无需 CSRF 头）
curl -H "Authorization: Bearer sk_your_key" \
     http://localhost:5000/api/search?tags=1girl

# PIN 认证需要 2 步
# 1. 获取 CSRF 令牌
curl -c cookies.txt http://localhost:5000/_pin
# 2. 提交 PIN
curl -b cookies.txt -X POST \
     -H "X-Requested-With: XMLHttpRequest" \
     -d "pin=1234" http://localhost:5000/_pin_check
```

### CSRF 保护

所有 POST/PUT/DELETE `/api/` 端点需要 `X-Requested-With` 头。
Bearer API Key 请求不需要。

## 主要端点

### 图片搜索与查看

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/search` | 按标签、日期、评分等筛选搜索 |
| GET | `/api/search-grouped` | 按文件夹/ZIP 分组搜索 |
| GET | `/api/file/<id>` | 获取详细图片元数据 |
| GET | `/api/thumbnail/<id>` | 获取缩略图（WebP，ETag 缓存） |
| GET | `/api/original/<id>` | 获取原始图片（支持 Range 请求） |
| GET | `/api/suggest` | 标签自动补全建议 |

### 评分、标签与注释

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/ratings/batch-set` | 批量设置评分 |
| POST | `/api/tags/batch-set` | 批量编辑标签 |
| POST | `/api/annotations/batch-set` | 批量设置注释 |
| GET | `/api/annotations/<id>` | 获取注释 |
| GET | `/api/annotations/search` | 搜索注释 |

### 收藏集

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/collections` | 列出收藏集 |
| POST | `/api/collections` | 创建收藏集 |
| PUT | `/api/collections/<id>` | 重命名收藏集 |
| DELETE | `/api/collections/<id>` | 删除收藏集 |
| POST | `/api/collections/<id>/batch-add` | 批量添加文件 |
| POST | `/api/collections/<id>/batch-remove` | 批量移除文件 |

### 扫描

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/scan/start` | 开始扫描 |
| GET | `/api/scan/status` | 获取扫描进度 |
| POST | `/api/scan/cancel` | 取消扫描 |
| POST | `/api/scan/resume` | 恢复中断的扫描 |
| GET | `/api/scan-roots` | 列出扫描根目录 |
| POST | `/api/scan-roots` | 添加扫描根目录 |

### AI 分析

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/analysis/analyze/<id>` | 运行 AI 图片分析 |
| GET | `/api/analysis/result/<id>` | 获取分析结果 |
| POST | `/api/analysis/batch` | 批量分析 |
| POST | `/api/wd-tagger/tag/<id>` | WD-Tagger 推理 |
| POST | `/api/wd-tagger/batch` | WD-Tagger 批量推理 |
| POST | `/api/analysis/batch/cancel` | 取消AI分析批处理 |
| POST | `/api/wd-tagger/batch/cancel` | 取消WD-Tagger批处理 |
| POST | `/api/tagger-servers/batch/cancel` | 取消标签服务器集群批处理 |
| POST | `/api/ocr/<id>` | 运行 OCR |

### 设置

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/settings/schema` | 获取设置架构 |
| GET | `/api/settings/all` | 获取所有设置 |
| GET | `/api/settings/<key>` | 获取设置值 |
| PUT | `/api/settings/<key>` | 更新设置值 |

### Extension 管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/extensions` | 列出 Extension |
| POST | `/api/extensions/<name>/toggle` | 启用/禁用切换 |
| POST | `/api/extensions/install` | 从 Git 仓库安装 |
| DELETE | `/api/extensions/<name>/uninstall` | 卸载 |

### Agent Safety

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/agent/kill` | 激活 Kill Switch |
| POST | `/api/agent/resume` | 释放 Kill Switch |
| GET | `/api/agent/status` | 安全机制状态 |
| GET | `/api/agent/journal` | 操作日志 |
| POST | `/api/agent/undo/<journal_id>` | 撤销操作 |

## 响应格式

所有 API 以统一的 JSON 格式响应。

```json
{
  "ok": true,
  "data": { ... },
  "error": null
}
```

错误时：

```json
{
  "ok": false,
  "data": null,
  "error": "Error message"
}
```

## 速率限制

使用 3 层令牌桶系统。

| 层级 | 目标 | 限制 | 突发 |
|------|------|------|------|
| READ | 所有 GET 请求 | 无限制 | - |
| WRITE | POST/PUT/DELETE | ~120 req/min | 30 |
| HEAVY | 相似搜索、AI 分析、扫描 | ~20 req/min | 5 |
| DESTRUCTIVE | purge、hard-delete、配置写入 | ~12 req/min | 3 |

超出时返回 HTTP 429。检查 `Retry-After` 头获取重试等待时间（秒）。

## SSE（Server-Sent Events）

实时事件通过 `/api/events/stream` 的 SSE 传递。
详情请参阅"SSE Events"部分。

> **注意**：每 IP 最多 10 个并发连接。上传大小限制为 100 MB。

## 内部设计文档

API 的详细设计原理、SQLite 性能优化、DB 架构设计及其他开发见解可在 [MD Viewer](/ext/md-viewer/) 中查看。
