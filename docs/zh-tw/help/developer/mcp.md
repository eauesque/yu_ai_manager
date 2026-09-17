# MCP 整合

YU AI Manager 內建 MCP（Model Context Protocol）伺服器，
允許從 Claude Desktop、Claude Code、Cline 等 AI 用戶端直接操作。
提供超過 137 個工具，可完整存取從圖片管理到 AI 分析的所有功能。

## 支援的 MCP 用戶端

| 用戶端 | 連線方式 | 備註 |
|--------|----------|------|
| Claude Desktop | stdio / HTTP | 建議用戶端 |
| Claude Code | stdio | CLI 環境 |
| Cline (VS Code) | stdio | VS Code 擴充功能 |
| Open WebUI | HTTP/SSE | 基於 Web |

## 本機連線 (stdio)

從同一台機器上的 Claude Desktop / Claude Code 連線：

1. 在設定 > API Keys 標籤頁中建立 API 金鑰
2. 將以下內容加入用戶端的設定檔

### Claude Desktop

`claude_desktop_config.json`：

```json
{
  "mcpServers": {
    "yu-ai-manager": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "/path/to/yu_ai_manager",
      "env": {
        "YU_BASE_URL": "http://localhost:5000",
        "YU_API_KEY": "sk_your_api_key_here"
      }
    }
  }
}
```

### Claude Code

`.mcp.json`：

```json
{
  "mcpServers": {
    "yu-ai-manager": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "/path/to/yu_ai_manager",
      "env": {
        "YU_BASE_URL": "http://localhost:5000",
        "YU_API_KEY": "sk_your_api_key_here"
      }
    }
  }
}
```

## LAN 連線 (HTTP/SSE)

從 LAN 上的另一台機器連線：

1. 在 YU AI Manager 中啟用 LAN 存取
2. 建立 API 金鑰
3. 從設定 > API Keys 標籤頁的「MCP Connection Snippet」中複製連線設定

```json
{
  "mcpServers": {
    "yu-ai-manager": {
      "type": "http",
      "url": "http://192.168.x.x:5000/mcp",
      "headers": {
        "Authorization": "Bearer sk_your_api_key_here"
      }
    }
  }
}
```

## 可用工具（依類別）

### 圖片搜尋與管理

| 工具 | 說明 |
|------|------|
| `search_images` | 按標籤、日期、評分等篩選搜尋 |
| `get_image_detail` | 取得詳細圖片中繼資料 |
| `get_library_stats` | 圖庫統計（檔案數、標籤分布等） |
| `find_similar` | 使用感知雜湊偵測相似圖片 |
| `rate_images` | 批次設定星級評分 |
| `set_tags` | 新增或移除標籤 |
| `set_annotations` | 設定註解 |
| `get_annotations` | 取得註解 |

### 收藏集

| 工具 | 說明 |
|------|------|
| `list_collections` | 列出收藏集 |
| `create_collection` | 建立收藏集 |
| `add_to_collection` | 將圖片加入收藏集 |
| `remove_from_collection` | 從收藏集移除圖片 |
| `delete_collection` | 刪除收藏集 |

### 掃描

| 工具 | 說明 |
|------|------|
| `trigger_scan` | 執行掃描 |
| `get_scan_status` | 檢查掃描進度 |
| `list_scan_roots` | 列出掃描根目錄 |
| `add_scan_root` | 新增掃描根目錄 |
| `scan_directory` | 掃描特定目錄 |

### AI 分析

| 工具 | 說明 |
|------|------|
| `analyze_image` | AI 圖片分析（單一） |
| `analyze_batch` | AI 圖片分析（批次） |
| `wd_tagger_tag_file` | WD-Tagger 推理（單一） |
| `wd_tagger_batch` | WD-Tagger 推理（批次） |
| `semantic_search` | CLIP 語意搜尋 |
| `s2t_transcribe_video` | 語音辨識 |

### Bridge 整合

| 工具 | 說明 |
|------|------|
| `sd_generate` | 使用 SD WebUI 生成圖片 |
| `sd_list_models` | 列出 SD WebUI 模型 |
| `comfyui_generate` | 使用 ComfyUI 生成圖片 |
| `comfyui_generate_json` | 執行 ComfyUI 工作流程 JSON |

### 提示詞庫

| 工具 | 說明 |
|------|------|
| `create_prompt` | 建立提示詞 |
| `search_prompts` | 搜尋提示詞 |
| `get_prompt` | 取得提示詞 |
| `update_prompt` | 更新提示詞 |

### 設定

| 工具 | 說明 |
|------|------|
| `settings_get_schema` | 取得設定架構 |
| `settings_get` | 取得設定值 |
| `settings_set` | 更新設定值 |
| `secrets_status` | 檢查加密金鑰狀態 |

### Agent Safety

| 工具 | 說明 |
|------|------|
| `agent_kill` / `agent_resume` | Kill Switch 控制 |
| `agent_status` | 安全機制狀態 |
| `agent_journal` | 搜尋操作日誌 |
| `agent_undo` | 復原操作 |
| `agent_circuit_breaker_status` | Circuit Breaker 狀態 |
| `agent_budget_status` | Budget tracker 狀態 |
| `agent_scope_set` | 設定範圍 |
| `agent_anomaly_status` | 異常偵測狀態 |

### 其他

| 工具 | 說明 |
|------|------|
| `find_duplicates` | 偵測重複檔案 |
| `search_chat_logs` | 搜尋聊天記錄 |
| `search_md_files` | 搜尋 Markdown 檔案 |
| `help_search` | 搜尋說明文件 |
| `share_to_bluesky` | 發布到 Bluesky |
| `list_trophies` | 列出獎盃 |
| `get_monthly_report` | 月報 |

## 環境變數

| 變數 | 說明 | 預設值 |
|------|------|--------|
| `YU_BASE_URL` | 伺服器 URL | `http://localhost:5000` |
| `YU_API_KEY` | API 金鑰 | （必要） |
| `YU_DEBUG_MODE` | 啟用除錯工具 | `0` |

設定 `YU_DEBUG_MODE=1` 會新增直接 DB 查詢和健康檢查等僅除錯工具。

## 疑難排解

### 無法連線

1. 驗證 YU AI Manager 正在執行
2. 驗證 API 金鑰正確（必須有 `sk_` 前綴）
3. 驗證 `YU_BASE_URL` 正確
4. 對於 LAN 連線，驗證已啟用 LAN 存取

### 找不到工具

- 如果 Extension 被停用，其工具將無法使用
- 使用 `list_extensions` 檢查啟用狀態

### 逾時

- 大型圖庫的搜尋和批次操作可能需要一些時間
- 使用 `limit` 參數限制結果數量
