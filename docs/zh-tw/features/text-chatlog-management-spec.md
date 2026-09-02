# YU AI Manager 文字與聊天紀錄管理規格

建立日期：2026-03-01
目標版本：TBD（實作時機考慮中）

## 概述

為 YU AI Manager 新增三項功能：

- **MD 檢視器** — 本機檢視 Markdown 檔案
- **聊天紀錄管理** — 匯入、檢視和搜尋來自 Claude/ChatGPT/Open WebUI 的紀錄
- **全文搜尋** — 基於 FTS5 的跨內容搜尋

設計理念與現有功能相同：「完全本機，不依賴雲端。」

---

## 1. MD 檢視器

### 目的

OS 檔案檢視器的 Markdown 渲染效果不佳。此功能將 Markdown 檢視完全整合到 YU AI Manager 中，作為開發筆記、設計文件和 TODO 清單的日常參考工具。

### 掃描目標

- 副檔名：`.md`、`.markdown`
- 復用現有的掃描根目錄
- 排除：`.git/` 和 `node_modules/` 下的檔案

### DB Schema

```sql
CREATE TABLE md_files (
    id          INTEGER PRIMARY KEY,
    path        TEXT NOT NULL UNIQUE,
    mtime       INTEGER NOT NULL,
    size        INTEGER NOT NULL,
    title       TEXT,        -- 從第一個 # 標題擷取
    content     TEXT,        -- 原始 Markdown 文字
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

### 檢視器 UI

- 整合到現有的彈窗或側邊面板
- 渲染：marked.js（本機打包，不使用 CDN）
- 程式碼區塊：語法高亮（highlight.js）
- 提供原始文字檢視切換按鈕

### MCP 支援

- `search_md_files(query, path_filter)` -> 檔案清單
- `get_md_content(file_id)` -> 原始文字

---

## 2. 聊天紀錄管理

### 目的

此功能作為開發歷程的搜尋引擎，可以用模糊關鍵字找到過去的討論。範例：「那個 bug 的討論在哪裡？」或「那個設計決策的原因是什麼？」

### 支援的格式

| 服務 | 匯出格式 | 取得方式 |
|---|---|---|
| Claude | conversations.json | Settings -> Export Data |
| ChatGPT | conversations.json | Settings -> Export Data |
| Open WebUI | JSON export | Chat History -> Export |

### DB Schema

```sql
-- 每個對話
CREATE TABLE chat_conversations (
    id            INTEGER PRIMARY KEY,
    source        TEXT NOT NULL,  -- 'claude' / 'chatgpt' / 'openwebui'
    external_id   TEXT,           -- 來自原始服務的對話 ID
    title         TEXT,
    model         TEXT,           -- 使用的模型名稱
    created_at    INTEGER,
    updated_at    INTEGER,
    message_count INTEGER,
    imported_at   INTEGER NOT NULL
);

-- 每則訊息
CREATE TABLE chat_messages (
    id              INTEGER PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES chat_conversations(id),
    role            TEXT NOT NULL,  -- 'user' / 'assistant' / 'system'
    content         TEXT NOT NULL,
    created_at      INTEGER,
    seq             INTEGER         -- 對話中的順序
);

-- FTS5 全文搜尋
CREATE VIRTUAL TABLE chat_messages_fts USING fts5(
    content,
    content='chat_messages',
    content_rowid='id',
    tokenize='unicode61'
);
```

### 匯入器

各服務的 JSON 轉換為共通中間格式後插入 DB。

**Claude JSON 結構（關鍵欄位）：**

```json
{
  "uuid": "...",
  "name": "對話標題",
  "created_at": "2026-01-01T00:00:00Z",
  "chat_messages": [
    {"role": "human", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}
```

**ChatGPT JSON 結構（關鍵欄位）：**

```json
{
  "id": "...",
  "title": "對話標題",
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

**Open WebUI JSON 結構：**

- 遵循 OpenAI 相容 API 格式
- messages 陣列包含 role/content

### 匯入 UI

- 在設定頁面新增匯入區段
- 可透過拖放或檔案選擇器選擇 JSON 檔案
- 以 `external_id` 對先前匯入的對話進行去重複（具冪等性）
- 顯示匯入摘要（新增數量和跳過數量）

### 檢視器 UI

- 對話清單頁面（標題、日期、模型、來源）
- 對話詳情頁面（回合制顯示，依角色進行色彩編碼）
- 依模型名稱、來源和日期範圍篩選
- 附件圖片僅儲存路徑參考（不複製檔案）

### MCP 支援

- `search_chat_logs(query, source, model, date_from, date_to)` -> 對話清單
- `get_conversation(conversation_id)` -> 訊息清單
- `import_chat_log(source, json_path)` -> 執行匯入

---

## 3. 全文搜尋

### 搜尋目標

- MD 檔案（`md_files_fts`）
- 聊天紀錄（`chat_messages_fts`）
- 現有提示詞庫（`prompt_library_fts`，已實作）

### 搜尋 UI

- 擴充現有搜尋列或提供專用的文字搜尋頁面
- 切換搜尋目標（MD / 聊天紀錄 / 提示詞庫）
- 結果依 BM25 分數排名
- 命中片段顯示（約 50 字元的周圍上下文）

### 搜尋 API

```
GET /api/text-search?q=keyword&target=md,chat,prompt&limit=20
```

回應：

```json
{
  "results": [
    {
      "type": "chat",
      "conversation_id": 123,
      "title": "對話標題",
      "snippet": "...命中周圍的文字...",
      "score": 0.95,
      "date": "2026-01-01"
    }
  ]
}
```

---

## 實作優先順序

1. MD 檢視器（實作成本低，即時價值高）
2. 聊天紀錄匯入器（先支援 Claude/ChatGPT）
3. 聊天紀錄檢視器
4. Open WebUI 支援
5. 跨內容文字搜尋 UI

---

## 未來擴充

- 自動定期聊天紀錄匯入（將匯出檔案放入監控資料夾以自動匯入）
- 將圖片生成提示詞與產生它們的聊天紀錄討論連結
- 透過 Ollama 自動進行聊天紀錄摘要和標籤

---

## 注意事項

- FTS5 模式可復用現有的 `prompt_library_fts` 實作
- marked.js 本機打包而非從 CDN 載入（遵循本機化設計理念）
- 聊天紀錄中的附件圖片（DALL-E 產生的圖片等）因 URL 過期不在本機儲存
