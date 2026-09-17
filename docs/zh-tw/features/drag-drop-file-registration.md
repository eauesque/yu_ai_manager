# 拖放檔案註冊

將圖片/影片檔案拖放到主媒體庫頁面（`/`）即可儲存到設定的 **Drop Inbox**
目錄並自動註冊到媒體庫。使用一般掃描路徑（`scan_one`），因此中繼資料擷取、
縮圖生成、標籤等處理都會照常執行。

## 行為

1. 在主頁面開啟狀態下，從檔案總管或其他瀏覽器拖曳檔案
2. 視窗上會顯示覆蓋層並顯示目標（Drop Inbox）路徑
3. 放開後，每個檔案會被複製到 Drop Inbox 並註冊到媒體庫
4. Toast 會顯示成功與失敗數量

## Drop Inbox 的決定邏輯

Drop Inbox 以下列優先順序決定：

1. `config.json` 的 `drop_inbox_dir`（明確指定）
2. 未設定時：直接使用第一個已啟用的掃描根目錄

**限制**：`drop_inbox_dir` 必須位於 `scan_roots` 的某個項目之下。外部目錄會
以 HTTP 400 拒絕。這是為了維持「掃描根目錄 = 媒體庫檔案的單一事實來源」
的不變條件。

## 設定範例

```json
{
  "scan_roots": [
    { "path": "D:/Pictures/AI", "enabled": true, "recursive": true }
  ],
  "drop_inbox_dir": "D:/Pictures/AI/inbox"
}
```

若 `drop_inbox_dir` 不存在則會自動建立（父目錄仍需在 `scan_roots` 之下）。

## 檔名衝突處理

若 inbox 中已有同名檔案，會自動加上 `_1`、`_2` 等後綴儲存。絕不覆寫既有檔案。

## 允許的副檔名

| 類別 | 副檔名 |
|---|---|
| 圖片 | `.png` `.jpg` `.jpeg` `.webp` `.gif` `.bmp` `.tiff` `.tif` `.svg` |
| 影片 | `.mp4` `.webm` `.mov` `.avi` `.mkv` `.m4v` |

壓縮檔（`.zip` / `.7z` / `.rar`）**不支援** 拖放。請將壓縮檔直接放入掃描
根目錄，然後執行一般掃描。

## 限制

- 單一請求的總大小上限為 `MAX_CONTENT_LENGTH`（預設 **100 MB**）
- 含路徑穿越（`..`）的檔名會被拒絕
- 目前不支援整個目錄的拖放（僅支援個別檔案）

## HTTP API

### `POST /api/dnd-upload`

以 multipart 接收多個檔案，儲存到 Drop Inbox 並註冊到媒體庫。

### `GET /api/dnd-inbox`

回傳目前解析的 Drop Inbox 資訊，供 UI 覆蓋層顯示。

### `POST /api/files/register-path`

以路徑指定方式註冊已在磁碟上的檔案（不需上傳）。路徑必須在 `scan_roots`
之下。MCP 工具 `register_file` 也使用此 API。

## MCP 工具

| 工具 | 說明 |
|---|---|
| `register_file(path)` | 以絕對路徑將檔案註冊到媒體庫 |
| `drop_inbox_info()` | 取得目前解析的 Drop Inbox 目錄 |
