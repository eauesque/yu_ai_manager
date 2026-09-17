# LAN MCP 存取與說明端點規格

**實作版本**：3.1.0
**相關文件**：`docs/zh-tw/features/mcp-integration-guide.md`
**相關檔案**：`routes/mcp_endpoint.py`、`routes/help.py`、`mcp_server/help_tools.py`

---

## 概述

1. **LAN MCP 存取** — 啟用 LAN 共享模式時，允許區域網路上的 MCP 客戶端透過 IP 位址連線到 MCP 端點
2. **`/help` 端點** — 提供應用程式的內建網頁手冊（同時作為 MCP 資源發佈）

---

## 1. LAN MCP 存取

### 1-1. 架構

透過區域網路，MCP 客戶端使用 HTTP/SSE 傳輸直接連線到 YU AI Manager `/mcp` 端點。

### 1-2. MCP SSE 端點

| 項目 | 詳情 |
|------|------|
| 端點 | `/mcp`（SSE + 訊息發送） |
| 傳輸 | HTTP + Server-Sent Events (SSE) |
| 認證 | 從 localhost 不需要。從 LAN IP 需要 API 金鑰 |

### 1-3. API 金鑰認證

重用現有的 API 金鑰管理機制（`/api/keys`）。

### 1-4. 設定 UI

在設定 > API Keys 分頁中新增 LAN MCP 連線設定片段（HTTP 版本）。

---

## 2. `/help` 端點

### 2-1. 設計原則

- 完全離線
- 兼作 MCP 資源
- 無需認證

### 2-2. 端點

| 端點 | 內容 |
|----------------|------|
| `GET /help` | 手冊首頁 |
| `GET /help/<section>` | 章節頁面 |
| `GET /api/help/toc` | 目錄 JSON |
| `GET /api/help/content/<section>` | 章節正文 JSON |

### 2-3. MCP 工具

- `help_search`：關鍵字搜尋
- `help_get_section`：章節取得
