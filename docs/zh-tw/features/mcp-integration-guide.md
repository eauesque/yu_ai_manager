# MCP 整合指南 — 從 LLM 操作 YU AI Manager

YU AI Manager 內建了 **MCP (Model Context Protocol)** 伺服器，讓 LLM 應用可以使用自然語言操作圖片庫。

本應用沒有內建聊天 UI。
要使用自然語言進行互動，請從您偏好的 MCP 相容客戶端連線。

---

## 什麼是 MCP？

MCP (Model Context Protocol) 是一種標準協定，使 LLM 應用能夠存取外部工具和資料來源。
YU AI Manager 作為 MCP 伺服器，LLM 客戶端（如 Claude Desktop）連線至此，將自然語言指令轉換為 API 操作。

```
┌─────────────────┐      MCP (stdio)       ┌─────────────────────┐
│  LLM Client     │ <--------------------> │  YU AI Manager      │
│  (Claude Desktop │                        │  MCP Server         │
│   / Open WebUI   │                        │  (python -m         │
│   / Cline etc.)  │                        │   mcp_server)       │
└─────────────────┘                        └────────┬────────────┘
                                                     │ HTTP API
                                                     v
                                           ┌─────────────────────┐
                                           │  YU AI Manager      │
                                           │  Web Server          │
                                           │  (localhost:5000)    │
                                           └─────────────────────┘
```

## 支援的 MCP 客戶端

以下是具代表性的 MCP 相容客戶端。所有客戶端的設定步驟都很類似。

| 客戶端 | 提供者 | 特點 |
|---|---|---|
| **Claude Desktop** | Anthropic | 直接存取 Claude。原生 MCP 支援 |
| **Claude Code** | Anthropic | 面向開發者的終端客戶端 |
| **Cline** | VS Code Extension | 編輯器整合。多 LLM 支援 |
| **Open WebUI** | Open Source | 自架。可與 Ollama 等本機 LLM 結合 |

注意：MCP 相容客戶端的數量正在快速增長。
任何支援 stdio 傳輸的客戶端都應該能夠連線。

## 設定

### 1. 啟動 YU AI Manager

MCP 伺服器透過 Web 伺服器的 API 進行操作，因此必須先啟動 YU AI Manager。

```bash
python web_ui.py --db ./tags.db --port 5000
```

### 2. 簽發 API 金鑰（建議）

簽發 API 金鑰後，MCP 伺服器可以在使用 LAN 共享或 PIN 驗證時繞過 PIN 驗證。

可從設定 -> API Keys 簽發 API 金鑰。

在不使用 PIN 的環境下（`config_test.json`）不需要 API 金鑰。

### 3. 在 MCP 客戶端中新增連線設定

#### Claude Desktop

編輯 `claude_desktop_config.json`：

**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "yu-ai-manager": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "C:/path/to/yu_ai_manager",
      "env": {
        "YU_BASE_URL": "http://127.0.0.1:5000",
        "YU_API_KEY": "sk_your_api_key_here"
      }
    }
  }
}
```

#### Claude Code

在專案根目錄的 `.mcp.json` 中新增設定，或使用 `claude mcp add` 命令：

```json
{
  "mcpServers": {
    "yu-ai-manager": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "/path/to/yu_ai_manager",
      "env": {
        "YU_BASE_URL": "http://127.0.0.1:5000",
        "YU_API_KEY": "sk_your_api_key_here"
      }
    }
  }
}
```

#### Cline (VS Code)

透過 Cline 的 MCP Settings 輸入相同的資訊。

#### 環境變數

| 變數 | 必填 | 預設值 | 說明 |
|---|---|---|---|
| `YU_BASE_URL` | - | `http://localhost:5000` | Web 伺服器 URL |
| `YU_API_KEY` | - | 無 | API 金鑰（PIN 環境中必要） |
| `YU_DEBUG_MODE` | - | `0` | 設為 `1` 新增除錯工具 |

## 使用範例

連線後，您可以透過向 LLM 發出自然語言指令來操作圖片庫。

### 搜尋與瀏覽

```
"顯示最近 20 張藍色眼睛女孩的圖片"
"只篩選用 NovelAI 產生的圖片"
"顯示上週掃描的圖片統計資料"
```

### 整理與分類

```
"將這 10 張圖片評為 5 星"
"將標記為 'landscape' 的圖片加入 '風景收藏集'"
"列出所有評分 3 分以下的圖片"
```

### 分析與註解

```
"評估最近新增圖片的品質並儲存到註解中"
"顯示圖片 ID 12345 的所有註解"
"搜尋來源為 agent:claude 的註解"
```

### 掃描操作

```
"掃描新的圖片"
"檢查掃描進度"
"顯示掃描錯誤"
```

## 可用工具

MCP 伺服器向 LLM 公開以下工具：

### 搜尋與瀏覽（4 個工具）

| 工具名稱 | 說明 |
|---|---|
| `search_images` | 依標籤、日期、格式、評分等搜尋圖片 |
| `get_image_detail` | 取得圖片的所有中繼資料 |
| `get_library_stats` | 圖片庫統計（檔案數、標籤數、來源分佈等） |
| `find_similar` | 使用感知雜湊搜尋相似圖片 |

### 收藏集（4 個工具）

| 工具名稱 | 說明 |
|---|---|
| `list_collections` | 列出收藏集 |
| `create_collection` | 建立收藏集 |
| `delete_collection` | 刪除收藏集 |
| `add_to_collection` / `remove_from_collection` | 新增/移除圖片 |

### 標籤與評分（2 個工具）

| 工具名稱 | 說明 |
|---|---|
| `rate_images` | 一次為多張圖片設定星級評分 |
| `set_tags` | 一次為多張圖片新增/移除標籤 |

### 註解（4 個工具）

| 工具名稱 | 說明 |
|---|---|
| `set_annotations` | 將 AI 分析結果儲存為註解 |
| `get_annotations` | 取得圖片的註解 |
| `search_annotations` | 依來源、鍵值和信心度搜尋註解 |
| `delete_annotations` | 刪除註解 |

### 掃描（3 個工具）

| 工具名稱 | 說明 |
|---|---|
| `trigger_scan` | 啟動掃描 |
| `get_scan_status` | 檢查掃描進度 |
| `get_scan_errors` | 列出掃描錯誤 |

### 其他

也包含提示詞庫、備份和 MCP 客戶端管理等工具。

## FAQ

### Q：應用程式裡沒有聊天功能嗎？

A：沒有。YU AI Manager 專注於圖片中繼資料管理，對話式 AI 介面委託給 MCP 相容客戶端。只要同時執行 Claude Desktop 或類似的客戶端，就可以透過自然語言執行所有操作。

### Q：應該使用哪個 LLM？

A：任何 LLM 都可以，只要 MCP 客戶端支援即可。
為了穩定的工具參數處理，Claude 或 GPT-4 等級的大型模型表現最為一致。

### Q：可以使用本機 LLM 嗎？

A：可以，透過 Open WebUI + Ollama 等組合即可使用本機 LLM，前提是它們支援 MCP。但工具呼叫的準確性取決於模型的能力。

### Q：YU AI Manager 也有 MCP 客戶端功能？

A：`MCP Client` 擴充功能（在工具頁面上）將 YU AI Manager 連線到**其他 MCP 伺服器**。本指南描述的是相反的方向：外部 LLM -> YU AI Manager。
