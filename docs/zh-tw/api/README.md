# YU AI Manager API 參考文件

本 REST API 文件涵蓋了 YU AI Manager 的所有功能，可供自訂 UI 及腳本使用。

## 通用慣例

### Base URL

```
http://<host>:<port>
```

預設值：`http://127.0.0.1:5000`
測試環境：`http://127.0.0.1:5100`（使用 `config_test.json` 時）

### 認證

支援四種認證方式：

| 方式 | 用途 | 標頭範例 |
|--------|----------|----------------|
| PIN 認證 | 瀏覽器工作階段 | Cookie: `session=...` |
| API Key | 機器間通訊 | `Authorization: Bearer sk_...` |
| Trusted Proxy | 反向代理後端 | `X-Remote-User: username` |
| LAN Share Token | 訪客存取 | URL 路徑 `/s/<token>/...` |

使用 `config_test.json`（無 PIN）啟動可完全略過認證。

### CSRF 保護

所有對 `/api/` 端點的 `POST` / `PUT` / `DELETE` 請求都需要 `X-Requested-With` 標頭：

```
X-Requested-With: XMLHttpRequest
```

**例外**：使用 `Authorization: Bearer` 標頭的 API Key 請求不需要 CSRF。

### 速率限制

| 層級 | 範圍 | 速率 | 突發 |
|------|-------|------|-------|
| READ | 所有 GET | 無限制 | - |
| WRITE | POST/PUT/DELETE（標準） | ~120 req/min | 30 |
| HEAVY | 相似搜尋、雜湊計算、AI 分析、掃描 | ~20 req/min | 5 |
| DESTRUCTIVE | 清除、硬刪除、快取清理、設定寫入 | ~12 req/min | 3 |

429 回應附帶 `Retry-After` 標頭。

### 回應格式

**成功**（新 API）：
```json
{
  "ok": true,
  "error": null,
  "data": { ... }
}
```

**錯誤**：
```json
{
  "ok": false,
  "error": "Error message",
  "code": "ERROR_CODE",
  "detail": "Additional details (optional)"
}
```

部分舊版 API 回傳 `{ "success": true, "message": "..." }` 格式。

### 分頁

**基於偏移量**（預設）：
```
GET /api/search?offset=0&limit=50
```

**基於游標**（適用於大型資料集）：
```
GET /api/search?cursor=<opaque_token>&limit=50
```

回應包含 `next_cursor` 欄位。

### 批次操作

批次 API 每次請求最多支援 500 個操作。支援部分成功：

```json
POST /api/ratings/batch-set
{
  "items": [
    { "file_id": 1, "rating": 5 },
    { "file_id": 999, "rating": 3 }
  ]
}
```

## API 分類

| 文件 | 內容 |
|----------|---------|
| [search.md](search.md) | 搜尋、建議、群組 |
| [files.md](files.md) | 檔案詳情、縮圖、媒體取得 |
| [scan.md](scan.md) | 掃描控制、掃描根目錄管理 |
| [events.md](events.md) | SSE 事件串流 |
| [theming.md](theming.md) | CSS 變數、佈景主題自訂 |
| [source.md](source.md) | 原始碼瀏覽（MCP 唯讀） |
| [github.md](github.md) | GitHub Integration（帳號管理・Issue・PR・通知・Discussion・Release） |
| [scheduler.md](scheduler.md) | 任務排程器（任務管理・執行歷史） |
| [ratings.md](ratings.md) | 評分（設定・批量設定・取得・統計） |
| [favorites.md](favorites.md) | 收藏（切換・檢查・清單） |
| [collections.md](collections.md) | 集合（CRUD・排序・批量新增/移除・CSV 匯出） |
| [tags.md](tags.md) | 標籤（批量設定・建議） |
| [sns.md](sns.md) | SNS 分享 & Bluesky 監控（發帖・通知・分類・自動回覆） |
| [hailo-remote-tagger.md](hailo-remote-tagger.md) | Hailo Remote Tagger（設定・單一/批次標記・標籤 CRUD） |
| [tagger-servers.md](tagger-servers.md) | Tagger Server Registry (分散標籤推論叢集・伺服器管理・批次執行) |
| [svg.md](svg.md) | SVG 光柵化 (SVG 轉 PNG/WebP、img2img 管線支援) |
| [system-update.md](system-update.md) | 系統更新（版本檢查・套用更新・統合更新管理器） |
| [tools.md](tools.md) | 工具 (重複偵測・雜湊計算・相似搜尋・快取管理・備份・封存清理・除錯日誌) |
| [agent.md](agent.md) | Agent Safety Gateway (Kill Switch・Circuit Breaker・Budget・Approval・Scope Fence・Undo・異常偵測) |
| [profiles.md](profiles.md) | 設定檔管理 (CRUD・複製・QR 匯出/匯入) |
| [wd-tagger.md](wd-tagger.md) | WD-Tagger (Danbooru 自動標記・模型管理・VLM・XMP) |
| [ocr.md](ocr.md) | OCR (文字辨識・翻譯・影片/PDF 支援・基準測試・設定檔) |
| [apikeys.md](apikeys.md) | API Key 管理 (建立・列表・範圍・撤銷) |
| [debug.md](debug.md) | 除錯 (中繼資料檢查・SQL 查詢・模型驗證) |
| [ui.md](ui.md) | UI 管理 (列表・切換・安裝・解除安裝) |
| [video-analysis.md](video-analysis.md) | 影片分析 (設定・狀態・關鍵幀擷取) |
| [extensions.md](extensions.md) | Extension 管理 (列表・啟用・設定・安裝・安全性・市場・創作) |
| [settings.md](settings.md) | 設定管理 (綱要・取得/更新值・密鑰加密・1Password/Bitwarden 整合) |
| [analysis.md](analysis.md) | AI 分析 (設定・單一/批次分析・趨勢分析・統計・伺服器註冊) |

## 快速開始 (curl)

```bash
# 搜尋（無 PIN 環境）
curl "http://localhost:5100/api/search?q=landscape&limit=10"

# 取得縮圖
curl "http://localhost:5100/api/thumbnail/42" -o thumb.webp

# 使用 API Key 搜尋
curl -H "Authorization: Bearer sk_your_key_here" \
     "http://localhost:5100/api/search?q=portrait"

# 設定評分
curl -X POST "http://localhost:5100/api/ratings/set" \
     -H "X-Requested-With: XMLHttpRequest" \
     -H "Content-Type: application/json" \
     -d '{"file_id": 42, "rating": 5}'
```
