# API 概述

YU AI Manager 提供 REST API，允許您以程式化方式執行所有 WebUI 操作。
擁有超過 320 個端點，涵蓋從圖片管理到 AI 分析的廣泛操作。

> **提示**：有關驗證、CSRF、速率限制、回應格式等詳細通用慣例，請參閱「API Reference」部分。

## 驗證

支援 4 種驗證方式。

| 方式 | 用途 | 標頭/參數 |
|------|------|-----------|
| PIN 驗證 | 瀏覽器工作階段 | 在 `/_pin` 登入 -> 工作階段 cookie |
| API Key | 機器間通訊 / MCP | `Authorization: Bearer sk_xxxx` |
| Trusted Proxy | 反向代理 | `X-Remote-User` 標頭 |
| LAN Share 權杖 | 訪客存取 | `/s/<token>` 路徑 |

### 使用 curl 測試

```bash
# API Key 驗證（無需 CSRF 標頭）
curl -H "Authorization: Bearer sk_your_key" \
     http://localhost:5000/api/search?tags=1girl

# PIN 驗證需要 2 步
# 1. 取得 CSRF 權杖
curl -c cookies.txt http://localhost:5000/_pin
# 2. 提交 PIN
curl -b cookies.txt -X POST \
     -H "X-Requested-With: XMLHttpRequest" \
     -d "pin=1234" http://localhost:5000/_pin_check
```

### CSRF 保護

所有 POST/PUT/DELETE `/api/` 端點需要 `X-Requested-With` 標頭。
Bearer API Key 請求不需要。

## 主要端點

### 圖片搜尋與檢視

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/api/search` | 按標籤、日期、評分等篩選搜尋 |
| GET | `/api/search-grouped` | 按資料夾/ZIP 分組搜尋 |
| GET | `/api/file/<id>` | 取得詳細圖片中繼資料 |
| GET | `/api/thumbnail/<id>` | 取得縮圖（WebP，ETag 快取） |
| GET | `/api/original/<id>` | 取得原始圖片（支援 Range 請求） |
| GET | `/api/suggest` | 標籤自動補全建議 |

### 評分、標籤與註解

| 方法 | 路徑 | 說明 |
|------|------|------|
| POST | `/api/ratings/batch-set` | 批次設定評分 |
| POST | `/api/tags/batch-set` | 批次編輯標籤 |
| POST | `/api/annotations/batch-set` | 批次設定註解 |
| GET | `/api/annotations/<id>` | 取得註解 |
| GET | `/api/annotations/search` | 搜尋註解 |

### 收藏集

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/api/collections` | 列出收藏集 |
| POST | `/api/collections` | 建立收藏集 |
| PUT | `/api/collections/<id>` | 重新命名收藏集 |
| DELETE | `/api/collections/<id>` | 刪除收藏集 |
| POST | `/api/collections/<id>/batch-add` | 批次新增檔案 |
| POST | `/api/collections/<id>/batch-remove` | 批次移除檔案 |

### 掃描

| 方法 | 路徑 | 說明 |
|------|------|------|
| POST | `/api/scan/start` | 開始掃描 |
| GET | `/api/scan/status` | 取得掃描進度 |
| POST | `/api/scan/cancel` | 取消掃描 |
| POST | `/api/scan/resume` | 恢復中斷的掃描 |
| GET | `/api/scan-roots` | 列出掃描根目錄 |
| POST | `/api/scan-roots` | 新增掃描根目錄 |

### AI 分析

| 方法 | 路徑 | 說明 |
|------|------|------|
| POST | `/api/analysis/analyze/<id>` | 執行 AI 圖片分析 |
| GET | `/api/analysis/result/<id>` | 取得分析結果 |
| POST | `/api/analysis/batch` | 批次分析 |
| POST | `/api/wd-tagger/tag/<id>` | WD-Tagger 推理 |
| POST | `/api/wd-tagger/batch` | WD-Tagger 批次推理 |
| POST | `/api/analysis/batch/cancel` | 取消AI分析批次 |
| POST | `/api/wd-tagger/batch/cancel` | 取消WD-Tagger批次 |
| POST | `/api/tagger-servers/batch/cancel` | 取消標籤伺服器叢集批次 |
| POST | `/api/ocr/<id>` | 執行 OCR |

### 設定

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/api/settings/schema` | 取得設定架構 |
| GET | `/api/settings/all` | 取得所有設定 |
| GET | `/api/settings/<key>` | 取得設定值 |
| PUT | `/api/settings/<key>` | 更新設定值 |

### Extension 管理

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/api/extensions` | 列出 Extension |
| POST | `/api/extensions/<name>/toggle` | 啟用/停用切換 |
| POST | `/api/extensions/install` | 從 Git 儲存庫安裝 |
| DELETE | `/api/extensions/<name>/uninstall` | 解除安裝 |

### Agent Safety

| 方法 | 路徑 | 說明 |
|------|------|------|
| POST | `/api/agent/kill` | 啟動 Kill Switch |
| POST | `/api/agent/resume` | 釋放 Kill Switch |
| GET | `/api/agent/status` | 安全機制狀態 |
| GET | `/api/agent/journal` | 操作日誌 |
| POST | `/api/agent/undo/<journal_id>` | 復原操作 |

## 回應格式

所有 API 以統一的 JSON 格式回應。

```json
{
  "ok": true,
  "data": { ... },
  "error": null
}
```

錯誤時：

```json
{
  "ok": false,
  "data": null,
  "error": "Error message"
}
```

## 速率限制

使用 3 層權杖桶系統。

| 層級 | 目標 | 限制 | 突發 |
|------|------|------|------|
| READ | 所有 GET 請求 | 無限制 | - |
| WRITE | POST/PUT/DELETE | ~120 req/min | 30 |
| HEAVY | 相似搜尋、AI 分析、掃描 | ~20 req/min | 5 |
| DESTRUCTIVE | purge、hard-delete、設定寫入 | ~12 req/min | 3 |

超出時回傳 HTTP 429。檢查 `Retry-After` 標頭取得重試等待時間（秒）。

## SSE（Server-Sent Events）

即時事件透過 `/api/events/stream` 的 SSE 傳遞。
詳情請參閱「SSE Events」部分。

> **注意**：每 IP 最多 10 個並行連線。上傳大小限制為 100 MB。

## 內部設計文件

API 的詳細設計原理、SQLite 效能最佳化、DB 架構設計及其他開發洞見可在 [MD Viewer](/ext/md-viewer/) 中檢視。
