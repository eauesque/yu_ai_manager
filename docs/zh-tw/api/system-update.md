# 系統更新 API

用於在 GitHub 上檢查新版本及套用應用程式更新的 API。
自動偵測安裝方式（git / tauri / docker / portable），並提供適當的更新方法。

## GET /api/system/update/check

檢查 GitHub 儲存庫是否有新版本可用。

- **速率限制**：無 (GET)
- **認證**：PIN 工作階段或 API Key

### 回應

```json
{
  "current": "4.21.0",
  "latest": "4.22.0",
  "update_available": true,
  "release_url": "https://github.com/...",
  "release_notes": "## What's New\n...",
  "published_at": "2026-03-20T12:00:00Z",
  "install_type": "git",
  "docker_command": null,
  "portable_download_url": null
}
```

| 欄位 | 類型 | 說明 |
|------|------|------|
| `current` | string | 目前版本 |
| `latest` | string | GitHub 上的最新版本 |
| `update_available` | bool | 是否有新版本可用 |
| `release_url` | string | GitHub Release 頁面 URL |
| `release_notes` | string | 版本說明 (Markdown) |
| `published_at` | string | 發佈日期 (ISO 8601) |
| `install_type` | string | 安裝方式 (`"git"`, `"tauri"`, `"docker"`, `"portable"`) |
| `docker_command` | string \| null | 僅 Docker 環境：更新用指令 |
| `portable_download_url` | string \| null | 僅 Portable 環境：下載 URL |

---

## GET /api/system/update/status

取得目前安裝方式及版本資訊。

- **速率限制**：無 (GET)
- **認證**：PIN 工作階段或 API Key

### 回應

```json
{
  "version": "4.21.0",
  "install_type": "git",
  "update_in_progress": false
}
```

| 欄位 | 類型 | 說明 |
|------|------|------|
| `version` | string | 目前版本 |
| `install_type` | string | 安裝方式 (`"git"` \| `"tauri"` \| `"docker"` \| `"portable"`) |
| `update_in_progress` | bool | 更新是否正在進行中 |

---

## POST /api/system/update/apply

套用可用的更新。僅支援 git clone 及 portable 安裝。

- **速率限制**：DESTRUCTIVE
- **認證**：PIN 工作階段 (localhost) 或重新啟動權杖
- **CSRF**：需要 `X-Requested-With: XMLHttpRequest`

### 請求主體

| 參數 | 類型 | 必填 | 說明 |
|------|------|------|------|
| `confirm` | string | 是 | 確認字串。必須為 `"update"` |

### 請求範例

```json
{
  "confirm": "update"
}
```

### 回應

```json
{
  "ok": true,
  "message": "Update started"
}
```

### SSE 事件

更新過程中會透過 SSE 傳送 `update.progress` 事件。

```
event: update.progress
data: {"step": "backup", "status": "running", "detail": "Creating backup..."}
```

| 欄位 | 類型 | 說明 |
|------|------|------|
| `step` | string | 進度步驟（請見下方） |
| `status` | string | `"running"` \| `"done"` \| `"error"` |
| `detail` | string | 步驟詳細資訊 |

#### 步驟一覽

| 步驟 | 說明 |
|------|------|
| `backup` | 建立備份 |
| `fetch` | 執行 git fetch |
| `pull` | 執行 git pull |
| `download` | 下載檔案 (portable) |
| `extract` | 解壓縮封存 (portable) |
| `replace` | 替換檔案 (portable) |
| `pip_install` | 安裝 Python 依賴套件 |
| `ts_build` | TypeScript 建置 |
| `complete` | 更新完成 |

### 錯誤回應

**Docker 環境** (400)：
```json
{
  "ok": false,
  "error": "Docker installs cannot be updated from the web UI. Pull the latest image instead.",
  "code": "DOCKER_UPDATE_NOT_SUPPORTED"
}
```

**Tauri 環境** (400)：
```json
{
  "ok": false,
  "error": "Tauri updates are handled by the desktop app's built-in updater.",
  "code": "TAURI_UPDATE_NOT_SUPPORTED"
}
```

---

## 注意事項

- Docker 環境無法使用 `/api/system/update/apply`。請使用 `docker pull` 取得最新映像
- Tauri 桌面應用程式的更新由應用程式內建的更新程式處理
- 僅 git 及 portable 安裝支援透過 Web UI 進行更新
- 更新過程中可能會發生伺服器重新啟動

---

## GET /api/system/update/unified-check

一次檢查系統本體與所有 Extension 的更新狀態。

- **速率限制**：無 (GET)
- **認證**：PIN 工作階段或 API Key

### 查詢參數

| 參數 | 類型 | 說明 |
|------|------|------|
| `force` | string | `"1"` 忽略快取並重新檢查 |

### 回應

```json
{
  "system": {
    "current": "4.22.0",
    "latest": "4.23.0",
    "update_available": true,
    "install_type": "git"
  },
  "extensions": [
    {
      "name": "builtin-backup",
      "version": "1.0.0",
      "source": "builtin",
      "status": "builtin",
      "enabled": true,
      "description": "..."
    },
    {
      "name": "my-custom-ext",
      "version": "0.3.0",
      "source": "git",
      "status": "update_available",
      "enabled": true,
      "description": "...",
      "local_head": "abc12345",
      "remote_head": "def67890",
      "commits_behind": 3
    }
  ],
  "summary": {
    "total": 45,
    "up_to_date": 1,
    "update_available": 1,
    "unknown": 0,
    "builtin": 43
  }
}
```

| 欄位 | 類型 | 說明 |
|------|------|------|
| `system` | object | 系統本體的更新資訊（與 `check_for_update` 相同格式） |
| `extensions` | array | 各 Extension 的更新狀態 |
| `extensions[].status` | string | `"up_to_date"` \| `"update_available"` \| `"unknown"` \| `"builtin"` |
| `extensions[].source` | string | `"builtin"` \| `"git"` \| `"local"` |
| `extensions[].commits_behind` | int | 有可用更新時，與遠端的提交差異數 |
| `summary` | object | 各分類的統計彙總 |

---

## POST /api/system/update/unified-apply

一次更新系統本體與 Extension。更新前會自動備份 Extension 設定。

- **速率限制**：DESTRUCTIVE
- **認證**：PIN 工作階段 (localhost) 或重新啟動權杖
- **CSRF**：需要 `X-Requested-With: XMLHttpRequest`

### 請求主體

| 參數 | 類型 | 必填 | 說明 |
|------|------|------|------|
| `update_system` | bool | 否 | 是否更新系統本體（預設：true） |
| `update_extensions` | bool | 否 | 是否更新 Extension（預設：true） |
| `extension_names` | array | 否 | 要更新的 Extension 名稱清單（省略時更新所有 git Extension） |

### 請求範例

```json
{
  "update_system": true,
  "update_extensions": true,
  "extension_names": ["my-custom-ext"]
}
```

### 回應

```json
{
  "ok": true,
  "accepted": true,
  "message": "統合更新を開始しました。進捗は SSE イベント (update.progress) で通知されます。",
  "update_system": true,
  "update_extensions": true
}
```

### SSE 事件

統合更新過程中，`update.progress` 事件會附帶 `"unified": true` 標記。

```
event: update.progress
data: {"step": "ext_config_backup", "status": "done", "detail": "...", "unified": true}
event: update.progress
data: {"step": "ext_update_my-custom-ext", "status": "running", "detail": "(1/1)", "unified": true}
```

#### 額外步驟

| 步驟 | 說明 |
|------|------|
| `ext_config_backup` | Extension 設定的備份 |
| `ext_update_<name>` | 個別 Extension 的更新 |

---

## MCP 工具整合

可從 Claude Desktop 管理系統更新。

```
# Step 1: 檢查新版本
check_for_update()

# Step 2: 檢查更新狀態
get_update_status()

# Step 3: 套用更新 (僅 git/portable)
apply_system_update(confirm="update")

# 統合檢查：一次確認系統 + 所有 Extension 的更新
check_unified_updates()

# 統合更新：一次更新系統 + Extension
apply_unified_updates(update_system=True, update_extensions=True)
```

### MCP 工具一覽

| 工具 | 說明 |
|------|------|
| `check_for_update` | 檢查 GitHub 是否有新版本可用 |
| `get_update_status` | 取得目前安裝方式及版本 |
| `apply_system_update` | 套用可用的更新 (僅 git/portable) |
| `check_unified_updates` | 一次檢查系統 + 所有 Extension 的更新狀態 |
| `apply_unified_updates` | 一次更新系統 + Extension（自動備份設定） |
