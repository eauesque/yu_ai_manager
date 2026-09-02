# LAN MCP 访问与帮助端点规格

**实现版本**：3.1.0
**相关文档**：`docs/zh-cn/features/mcp-integration-guide.md`
**相关文件**：`routes/mcp_endpoint.py`、`routes/help.py`、`mcp_server/help_tools.py`

---

## 概述

1. **LAN MCP 访问** — 启用 LAN 共享模式时，允许局域网上的 MCP 客户端通过 IP 地址连接到 MCP 端点
2. **`/help` 端点** — 提供应用的内置网页手册（同时作为 MCP 资源发布）

---

## 1. LAN MCP 访问

### 1-1. 架构

通过局域网，MCP 客户端使用 HTTP/SSE 传输直接连接到 YU AI Manager `/mcp` 端点。

### 1-2. MCP SSE 端点

| 项目 | 详情 |
|------|------|
| 端点 | `/mcp`（SSE + 消息发送） |
| 传输 | HTTP + Server-Sent Events (SSE) |
| 认证 | 从 localhost 不需要。从 LAN IP 需要 API 密钥 |

### 1-3. API 密钥认证

复用现有的 API 密钥管理机制（`/api/keys`）。

### 1-4. 设置 UI

在设置 > API Keys 标签页中添加 LAN MCP 连接配置代码片段（HTTP 版本）。

---

## 2. `/help` 端点

### 2-1. 设计原则

- 完全离线
- 兼作 MCP 资源
- 无需认证

### 2-2. 端点

| 端点 | 内容 |
|----------------|------|
| `GET /help` | 手册首页 |
| `GET /help/<section>` | 章节页面 |
| `GET /api/help/toc` | 目录 JSON |
| `GET /api/help/content/<section>` | 章节正文 JSON |

### 2-3. MCP 工具

- `help_search`：关键字搜索
- `help_get_section`：章节获取
