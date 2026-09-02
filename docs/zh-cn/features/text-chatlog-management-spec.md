# YU AI Manager 文本与聊天记录管理规格

创建日期：2026-03-01
目标版本：待定（实施时间考虑中）

## 概述

YU AI Manager 新增三项功能：

- **MD 查看器** — 本地查看 Markdown 文件
- **聊天记录管理** — 导入、查看和搜索来自 Claude/ChatGPT/Open WebUI 的日志
- **全文搜索** — 基于 FTS5 的跨内容搜索

设计理念与现有功能相同："完全本地，不依赖云端。"

---

## 1. MD 查看器

### 目的

操作系统的文件查看器对 Markdown 的渲染效果较差。此功能将 Markdown 查看完全集成到 YU AI Manager 中，作为开发笔记、设计文档和 TODO 列表的日常参考工具。

### 扫描目标

- 扩展名：`.md`、`.markdown`
- 复用现有的扫描根目录
- 排除：`.git/` 和 `node_modules/` 下的文件

### DB 模式

```sql
CREATE TABLE md_files (
    id          INTEGER PRIMARY KEY,
    path        TEXT NOT NULL UNIQUE,
    mtime       INTEGER NOT NULL,
    size        INTEGER NOT NULL,
    title       TEXT,        -- 从第一个 # 标题提取
    content     TEXT,        -- 原始 Markdown 文本
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    indexed_at  INTEGER
);

CREATE VIRTUAL TABLE md_files_fts USING fts5(
    title,
    content,
    content='md_files',
    content_rowid='id'
);
```

### 查看器 UI

- 集成到现有的弹窗或侧面板中
- 渲染：marked.js（本地打包，非 CDN）
- 代码块：语法高亮（highlight.js）
- 提供原始文本查看切换按钮

### MCP 支持

- `search_md_files(query, path_filter)` -> 文件列表
- `get_md_content(file_id)` -> 原始文本

---

## 2. 聊天记录管理

### 目的

此功能作为开发历史的搜索引擎，能够通过模糊关键词找到过去的讨论。例如："那个 bug 讨论在哪里？"或"那个设计决策的理由是什么？"

### 支持的格式

| 服务 | 导出格式 | 获取方式 |
|---|---|---|
| Claude | conversations.json | 设置 -> 导出数据 |
| ChatGPT | conversations.json | 设置 -> 导出数据 |
| Open WebUI | JSON 导出 | 聊天历史 -> 导出 |

### DB 模式

```sql
-- 每个对话
CREATE TABLE chat_conversations (
    id            INTEGER PRIMARY KEY,
    source        TEXT NOT NULL,  -- 'claude' / 'chatgpt' / 'openwebui'
    external_id   TEXT,           -- 原始服务的对话 ID
    title         TEXT,
    model         TEXT,           -- 使用的模型名称
    created_at    INTEGER,
    updated_at    INTEGER,
    message_count INTEGER,
    imported_at   INTEGER NOT NULL
);

-- 每条消息
CREATE TABLE chat_messages (
    id              INTEGER PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES chat_conversations(id),
    role            TEXT NOT NULL,  -- 'user' / 'assistant' / 'system'
    content         TEXT NOT NULL,
    created_at      INTEGER,
    seq             INTEGER         -- 对话内的顺序
);

-- FTS5 全文搜索
CREATE VIRTUAL TABLE chat_messages_fts USING fts5(
    content,
    content='chat_messages',
    content_rowid='id',
    tokenize='unicode61'
);
```

### 导入器

将各服务的 JSON 转换为通用中间格式并插入 DB。

**Claude JSON 结构（关键字段）：**

```json
{
  "uuid": "...",
  "name": "对话标题",
  "created_at": "2026-01-01T00:00:00Z",
  "chat_messages": [
    {"role": "human", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}
```

**ChatGPT JSON 结构（关键字段）：**

```json
{
  "id": "...",
  "title": "对话标题",
  "create_time": 1234567890,
  "mapping": {
    "node_id": {
      "message": {
        "author": {"role": "user"},
        "content": {"parts": ["..."]}
      }
    }
  }
}
```

**Open WebUI JSON 结构：**

- 遵循兼容 OpenAI 的 API 格式
- 包含 role/content 的 messages 数组

### 导入 UI

- 在设置页面添加导入区域
- 支持拖放或文件选择器选择 JSON 文件
- 通过 `external_id` 对已导入的对话进行去重（幂等）
- 显示导入摘要（已添加数和已跳过数）

### 查看器 UI

- 对话列表页面（标题、日期、模型、来源）
- 对话详情页面（按轮次显示，基于角色的颜色编码）
- 按模型名称、来源和日期范围过滤
- 附件图片仅存储路径引用（不复制文件）

### MCP 支持

- `search_chat_logs(query, source, model, date_from, date_to)` -> 对话列表
- `get_conversation(conversation_id)` -> 消息列表
- `import_chat_log(source, json_path)` -> 执行导入

---

## 3. 全文搜索

### 目标

- MD 文件（`md_files_fts`）
- 聊天记录（`chat_messages_fts`）
- 现有提示词库（`prompt_library_fts`，已实现）

### 搜索 UI

- 扩展现有搜索栏或提供专用的文本搜索页面
- 切换搜索目标（MD / 聊天记录 / 提示词库）
- 结果按 BM25 分数排名
- 命中片段显示（约 50 字符的上下文）

### 搜索 API

```
GET /api/text-search?q=keyword&target=md,chat,prompt&limit=20
```

响应：

```json
{
  "results": [
    {
      "type": "chat",
      "conversation_id": 123,
      "title": "对话标题",
      "snippet": "...命中点周围的文本...",
      "score": 0.95,
      "date": "2026-01-01"
    }
  ]
}
```

---

## 实现优先级

1. MD 查看器（实现成本低，即时价值高）
2. 聊天记录导入器（先支持 Claude/ChatGPT）
3. 聊天记录查看器
4. Open WebUI 支持
5. 跨内容文本搜索 UI

---

## 未来扩展

- 自动定期聊天记录导入（将导出文件放入监视文件夹自动摄取）
- 将图片生成提示词与产生它们的聊天记录讨论关联
- 通过 Ollama 自动聊天记录摘要和标签

---

## 备注

- FTS5 模式可以复用现有 `prompt_library_fts` 的实现
- marked.js 本地打包而非从 CDN 加载（遵循本地化设计理念）
- 聊天记录中的附件图片（DALL-E 生成的图片等）不在本地保存，因为其 URL 会过期
