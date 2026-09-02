# Tools API

用於重複偵測、雜湊計算、相似圖片搜尋、快取管理、資料夾選擇、資料庫備份、壓縮檔清理及除錯日誌的工具 API。

---

## 重複 / 雜湊 / 掃描

### GET /api/tools/find-duplicates

根據檔案雜湊或檔案名稱偵測重複檔案。

#### Rate Limit

HEAVY

#### 參數

| 參數 | 類型 | 預設值 | 說明 |
|------|------|--------|------|
| `cross_directory` | string | `"false"` | 設為 `"true"` 以跨不同目錄偵測重複 |
| `method` | string | `"hash"` | 偵測方法：`"hash"` 或 `"name"` |
| `threshold` | int | `5` | 相似度閾值 |

#### 回應

```json
{
  "groups": [
    {
      "hash": "abc123...",
      "files": [
        { "id": 1, "path": "/images/photo.png", "filename": "photo.png" },
        { "id": 2, "path": "/backup/photo.png", "filename": "photo.png" }
      ]
    }
  ],
  "total_groups": 1,
  "total_duplicates": 2
}
```

### POST /api/tools/compute-hashes

為尚無雜湊值的檔案啟動背景雜湊計算。

#### Rate Limit

HEAVY

#### 請求

```json
{
  "type": "both",
  "limit": 5000
}
```

| 參數 | 類型 | 預設值 | 說明 |
|------|------|--------|------|
| `type` | string | `"both"` | 雜湊類型：`"md5"`、`"sha256"` 或 `"both"` |
| `limit` | int | `5000` | 最大處理檔案數 |

#### 回應

```json
{
  "started": true,
  "type": "both",
  "limit": 5000
}
```

### POST /api/tools/delete-duplicates

從重複群組中刪除指定檔案。

#### Rate Limit

DESTRUCTIVE

#### 請求

```json
{
  "groups": [
    {
      "keep": 1,
      "delete": [2, 3]
    }
  ],
  "mode": "soft"
}
```

| 參數 | 類型 | 預設值 | 說明 |
|------|------|--------|------|
| `groups` | array | 必填 | 刪除目標。`keep` = 要保留的檔案 ID，`delete` = 要移除的檔案 ID 陣列 |
| `mode` | string | `"soft"` | `"soft"` = 邏輯刪除，`"hard"` = 實體刪除 |

#### 回應

```json
{
  "deleted": 2,
  "errors": []
}
```

### GET /api/tools/normalize-tags

正規化標籤（合併重複、去除空白等）。

#### 參數

| 參數 | 類型 | 預設值 | 說明 |
|------|------|--------|------|
| `dry_run` | string | `"false"` | 設為 `"true"` 以預覽變更而不實際套用 |

#### 回應

```json
{
  "normalized": 15,
  "removed": 3,
  "dry_run": false
}
```

### GET /api/tools/find-similar

尋找與指定檔案相似的圖片（基於雜湊）。

#### Rate Limit

HEAVY

#### 參數

| 參數 | 類型 | 是否必填 | 說明 |
|------|------|----------|------|
| `file_id` | int | 是 | 參考檔案 ID |
| `threshold` | int | 否 | 相似度閾值（1-20，預設 `5`） |

#### 回應

```json
{
  "file_id": 42,
  "threshold": 5,
  "results": [
    {
      "id": 43,
      "filename": "similar.png",
      "distance": 3
    }
  ],
  "count": 1
}
```

#### 錯誤

- `400` — `file_id` 缺失或無效
- `404` — 找不到指定檔案

### POST /api/tools/scan

掃描目錄中的檔案並註冊到資料庫。

#### Rate Limit

HEAVY

#### 請求

```json
{
  "path": "/path/to/images",
  "recursive": true,
  "scan_zips": false,
  "compute_hash": false
}
```

| 參數 | 類型 | 預設值 | 說明 |
|------|------|--------|------|
| `path` | string | 必填 | 要掃描的目錄路徑 |
| `recursive` | bool | `true` | 遞迴掃描子目錄 |
| `scan_zips` | bool | `false` | 同時掃描 ZIP 壓縮檔內部 |
| `compute_hash` | bool | `false` | 掃描時計算檔案雜湊 |

#### 回應

```json
{
  "scanned": 150,
  "new": 42,
  "updated": 5,
  "errors": []
}
```

---

## 檔案搜尋 / 中繼資料檢視

### GET /api/tools/file-search

透過關鍵字搜尋資料庫中的檔案。

#### 參數

| 參數 | 類型 | 預設值 | 說明 |
|------|------|--------|------|
| `q` / `query` | string | `""` | 搜尋關鍵字 |
| `meta` / `meta_filter` | string | `"all"` | 依中繼資料來源篩選（`"all"`、`"a1111_png"`、`"novelai_v4_png"` 等） |
| `limit` / `n` / `page_size` | int | `100` | 結果數量（1-500） |

#### 回應

```json
{
  "results": [
    {
      "id": 1,
      "filename": "image.png",
      "path": "/images/image.png"
    }
  ],
  "count": 1
}
```

### POST /api/inspect

檢視上傳檔案的中繼資料。提取中繼資料但不會將檔案註冊到資料庫。

#### Rate Limit

WRITE

#### 請求

`multipart/form-data`：

| 欄位 | 類型 | 是否必填 | 說明 |
|------|------|----------|------|
| `file` | file | 是 | 要檢視的檔案 |
| `zip_entry` | string | 否 | ZIP 壓縮檔內的路徑（用於 ZIP 檔案） |

#### 回應

```json
{
  "filename": "image.png",
  "meta_source": "novelai_v4_png",
  "positive": "1girl, landscape",
  "negative": "bad anatomy",
  "parameters": { ... }
}
```

#### 錯誤

- `400` — 未上傳檔案

---

## 資料夾選擇 / 目錄列表

### GET /api/tools/select-folder

開啟作業系統原生資料夾選擇對話框。**僅限從 localhost 存取。**

#### 參數

| 參數 | 類型 | 說明 |
|------|------|------|
| `initial` / `path` / `dir` | string | 對話框的初始目錄 |

#### 回應

```json
{
  "path": "C:\\Users\\user\\Pictures",
  "cancelled": false
}
```

從遠端存取時：

```json
{
  "path": null,
  "error": "remote_client_no_gui",
  "cancelled": false,
  "message": "Native folder dialog is not available for remote access. Please use the server folder browser."
}
```

### GET /api/tools/list-dirs

列出伺服器上的目錄。**僅限從 localhost 存取。**

#### 參數

| 參數 | 類型 | 說明 |
|------|------|------|
| `path` / `dir` / `initial` | string | 要列出的目錄。留空則回傳根目錄 |

#### 回應

```json
{
  "current": "C:\\Users",
  "parent": "C:\\",
  "dirs": ["user1", "Public"],
  "roots": ["C:\\", "D:\\"]
}
```

#### 錯誤

- `403` — 遠端存取

---

## 快取管理

### GET /api/tools/cache-info

取得縮圖快取狀態。

#### 回應

```json
{
  "count": 1234,
  "size_mb": 56.7
}
```

### POST /api/tools/clear-cache

清除所有縮圖快取。

#### Rate Limit

DESTRUCTIVE

#### 回應

```json
{
  "cleared": 1234
}
```

### POST /api/tools/rebuild-groups

強制重建群組索引快取。

#### Rate Limit

DESTRUCTIVE

#### 回應

```json
{
  "status": "rebuilt",
  "folders": 42,
  "zips": 5,
  "file_count": 1500
}
```

### POST /api/tools/faststart-prescan

在背景為所有 MP4/MOV 檔案預先產生 faststart 快取。立即回傳 202。

#### Rate Limit

WRITE

#### 回應 (202)

```json
{
  "ok": true,
  "started": true,
  "message": "faststart prescan started"
}
```

正在執行時 (200)：

```json
{
  "ok": true,
  "started": false,
  "message": "already running"
}
```

---

## 設定

### GET /api/settings/config

取得與預設值合併後的目前設定。

#### 回應

```json
{
  "port": 5000,
  "pin": "",
  "scan_roots": [],
  "theme": "dark",
  "backup": {
    "enabled": true,
    "periodic_interval_hours": 24
  }
}
```

### POST /api/settings/config

部分更新設定。對現有巢狀物件進行深度合併。

#### Rate Limit

DESTRUCTIVE

#### 請求

```json
{
  "theme": "light",
  "backup": {
    "enabled": false
  }
}
```

#### 回應

```json
{
  "status": "saved"
}
```

#### 錯誤

- `400` — 空資料

---

## 資料庫備份 / 還原

### GET /api/tools/backup-download

直接下載資料庫檔案。**僅限從 localhost 存取。**

#### 回應

- Content-Type: `application/x-sqlite3`
- Content-Disposition: `attachment; filename="tags_backup_20260322_120000.db"`
- 找不到資料庫時回傳 404

### POST /api/tools/restore

上傳 `.db` 檔案以還原資料庫。**僅限從 localhost 存取。** 還原前會自動建立現有資料庫的備份。

#### Rate Limit

WRITE

#### 請求

`multipart/form-data`：

| 欄位 | 類型 | 是否必填 | 說明 |
|------|------|----------|------|
| `file` | file | 是 | 副檔名為 `.db` 的 SQLite 檔案 |

#### 驗證

- 檢查 SQLite magic bytes
- 確認 `files` 資料表存在
- 拒絕包含 trigger 或 view 的資料庫

#### 回應

```json
{
  "success": true,
  "message": "Database restored successfully",
  "backup": "tags.db.backup_1711100000"
}
```

#### 錯誤

- `400` — 未上傳檔案、副檔名錯誤或無效的 SQLite
- `403` — 遠端存取
- `500` — 備份或還原失敗

### POST /api/tools/backup/create

手動建立受管理的備份。**僅限從 localhost 存取。**

#### Rate Limit

DESTRUCTIVE

#### 回應

```json
{
  "success": true,
  "filename": "tags_backup_20260322_120000.db",
  "reason": "manual"
}
```

### GET /api/tools/backup/list

列出可用的備份。

#### 回應

```json
{
  "backups": [
    {
      "filename": "tags_backup_20260322_120000.db",
      "size": 1048576,
      "created": "2026-03-22T12:00:00"
    }
  ],
  "count": 1
}
```

### POST /api/tools/backup/restore

從指定的備份還原資料庫。**僅限從 localhost 存取。**

#### Rate Limit

DESTRUCTIVE

#### 請求

```json
{
  "filename": "tags_backup_20260322_120000.db"
}
```

| 參數 | 類型 | 是否必填 | 說明 |
|------|------|----------|------|
| `filename` | string | 是 | 要還原的備份檔案名稱 |

#### 回應

```json
{
  "success": true,
  "message": "Backup restored",
  "filename": "tags_backup_20260322_120000.db"
}
```

#### 錯誤

- `400` — 缺少檔案名稱或找不到備份
- `403` — 遠端存取

### POST /api/tools/backup/delete

刪除指定的備份。**僅限從 localhost 存取。**

#### Rate Limit

DESTRUCTIVE

#### 請求

```json
{
  "filename": "tags_backup_20260322_120000.db"
}
```

| 參數 | 類型 | 是否必填 | 說明 |
|------|------|----------|------|
| `filename` | string | 是 | 要刪除的備份檔案名稱 |

#### 回應

```json
{
  "success": true,
  "deleted": "tags_backup_20260322_120000.db"
}
```

### GET /api/tools/backup/status

取得備份系統狀態。

#### 回應

```json
{
  "enabled": true,
  "backup_on_scan_complete": true,
  "periodic_interval_hours": 24,
  "max_generations": 5,
  "cooldown_minutes": 5,
  "scheduler_running": true,
  "last_backup_time": "2026-03-22T11:00:00",
  "within_cooldown": false
}
```

---

## 除錯日誌

### GET /api/tools/debug-log

取得除錯日誌的末尾。除錯模式停用時回傳 `enabled: false`。

#### 參數

| 參數 | 類型 | 預設值 | 說明 |
|------|------|--------|------|
| `limit` | int | `200` | 要擷取的行數（1-5000） |
| `filter` | string | `""` | 行篩選字串（子字串比對） |

#### 回應

```json
{
  "enabled": true,
  "lines": ["2026-03-22 12:00:00 [INFO] Server started", "..."],
  "total_lines": 5000,
  "log_path": "/path/to/debug.log",
  "log_size_kb": 128.5
}
```

### GET /api/tools/debug-log/download

下載除錯日誌檔案。**僅限從 localhost 存取。**

#### 回應

- Content-Type: `text/plain`
- Content-Disposition: `attachment; filename="debug.log"`

#### 錯誤

- `400` — 除錯模式未啟用
- `403` — 遠端存取
- `404` — 找不到日誌檔案

### POST /api/tools/debug-log/clear

清除除錯日誌。**僅限從 localhost 存取。**

#### Rate Limit

WRITE

#### 回應

```json
{
  "success": true,
  "message": "Log cleared"
}
```

#### 錯誤

- `400` — 除錯模式未啟用
- `403` — 遠端存取
- `404` — 找不到日誌檔案

---

## 壓縮檔清理

用於偵測和清理重複壓縮檔及其解壓縮資料夾的工具。所有端點**僅限從 localhost 存取。**

### POST /api/tools/archive-cleanup/scan

掃描壓縮檔與資料夾配對。

#### Rate Limit

HEAVY

#### 請求

```json
{
  "path": "/path/to/check",
  "recursive": false
}
```

| 參數 | 類型 | 預設值 | 說明 |
|------|------|--------|------|
| `path` | string | 必填 | 要掃描的目錄 |
| `recursive` | bool | `false` | 遞迴掃描子目錄 |

#### 路徑驗證

- 以 `~` 開頭的路徑會被拒絕
- 包含 `..` 的路徑會被拒絕

#### 回應

```json
{
  "pairs": [
    {
      "archive_path": "/data/images.zip",
      "folder_path": "/data/images",
      "archive_size": 10485760,
      "folder_size": 12582912,
      "file_count": 42
    }
  ],
  "count": 1
}
```

### POST /api/tools/archive-cleanup/execute

對掃描到的配對執行清理操作。

#### Rate Limit

DESTRUCTIVE

#### 請求

```json
{
  "actions": [
    { "action": "delete_archive", "archive_path": "/data/images.zip" },
    { "action": "delete_folder", "folder_path": "/data/images" },
    { "action": "skip" }
  ]
}
```

| 參數 | 類型 | 說明 |
|------|------|------|
| `actions` | array | 操作陣列 |
| `actions[].action` | string | `"delete_archive"`、`"delete_folder"` 或 `"skip"` 之一 |
| `actions[].archive_path` | string | 操作為 `delete_archive` 時必填 |
| `actions[].folder_path` | string | 操作為 `delete_folder` 時必填 |

#### 回應

```json
{
  "results": [
    { "action": "delete_archive", "success": true },
    { "action": "delete_folder", "success": true },
    { "action": "skip", "success": true }
  ]
}
```

### POST /api/tools/archive-cleanup/llm-verify

使用 LLM 驗證壓縮檔與資料夾配對的一致性（單一配對）。

#### Rate Limit

HEAVY

#### 請求

```json
{
  "archive_path": "/data/images.zip",
  "folder_path": "/data/images",
  "pair_info": {
    "archive_size": 10485760,
    "folder_size": 12582912
  }
}
```

| 參數 | 類型 | 是否必填 | 說明 |
|------|------|----------|------|
| `archive_path` | string | 是 | 壓縮檔路徑 |
| `folder_path` | string | 是 | 解壓縮資料夾路徑 |
| `pair_info` | object | 否 | 額外的配對中繼資料 |

#### 回應

```json
{
  "verdict": "same",
  "confidence": 0.95,
  "reasoning": "File counts and sizes match exactly."
}
```

### POST /api/tools/archive-cleanup/llm-verify-batch

使用 LLM 批次驗證多個配對。最多 50 個配對。

#### Rate Limit

HEAVY

#### 請求

```json
{
  "pairs": [
    {
      "archive_path": "/data/a.zip",
      "folder_path": "/data/a",
      "pair_info": {}
    }
  ]
}
```

| 參數 | 類型 | 限制 | 說明 |
|------|------|------|------|
| `pairs` | array | 最多 50 | 要驗證的配對陣列 |

#### 回應

```json
{
  "results": [
    { "result": { "verdict": "same", "confidence": 0.95, "reasoning": "..." } }
  ]
}
```

### GET /api/tools/archive-cleanup/llm-config

取得壓縮檔清理的 LLM 設定。

#### 回應

```json
{
  "engine": "ollama",
  "base_url": "http://localhost:11434",
  "model": "llama3",
  "api_key": ""
}
```

### POST /api/tools/archive-cleanup/llm-config

儲存壓縮檔清理的 LLM 設定。

#### Rate Limit

WRITE

#### 請求

```json
{
  "engine": "ollama",
  "base_url": "http://localhost:11434",
  "model": "llama3"
}
```

#### 回應

```json
{
  "success": true
}
```

### POST /api/tools/archive-cleanup/list-models

列出指定引擎的可用模型。

#### 請求

```json
{
  "engine": "ollama",
  "base_url": "http://localhost:11434"
}
```

| 參數 | 類型 | 是否必填 | 說明 |
|------|------|----------|------|
| `engine` | string | 是 | `"ollama"` 或 `"openai_compat"` |
| `base_url` | string | 是 | 引擎 API URL |
| `api_key` | string | 否 | `openai_compat` 的 API Key |

#### 回應

```json
{
  "models": ["llama3", "mistral", "codellama"]
}
```

#### 錯誤

- `400` — 無效的引擎或缺少 `base_url`
