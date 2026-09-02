# Scan API

檔案掃描和掃描根目錄管理的 API。

## 掃描控制

### POST /api/scan/start

啟動掃描。

### 請求

```json
{
  "root_indices": [0, 1],
  "force": false
}
```

| 欄位 | 類型 | 說明 |
|-------|------|-------------|
| `root_indices` | int[] | 要掃描的根目錄索引（省略則掃描所有根目錄） |
| `force` | bool | 重新掃描已有檔案 |

### 回應

```json
{
  "ok": true,
  "message": "Scan started"
}
```

### GET /api/scan/status

取得掃描進度。

### 回應

```json
{
  "scanning": true,
  "progress": 45,
  "total": 1500,
  "current_file": "/images/output/00042.png",
  "errors": 0,
  "started_at": 1709500000
}
```

### POST /api/scan/cancel

取消正在執行的掃描。

### GET /api/scan/interrupted

取得被中斷的掃描資訊。

### POST /api/scan/resume

恢復被中斷的掃描。

### POST /api/scan/dismiss

捨棄中斷的掃描狀態。

## Scan Worker CLI

自 v3.27.0 起，掃描在獨立的處理程序（worker）中執行。
除了 WebUI API 外，也可以透過 CLI 直接控制 worker。

```bash
# 啟動掃描
python -m core.scan.scan_worker start --db ./tags.db --root /path/to/images [--scan-zips] [--force] [--resume]

# 停止掃描（SIGTERM -> 優雅關閉）
python -m core.scan.scan_worker stop

# 檢查狀態
python -m core.scan.scan_worker status
```

### IPC 檔案

| 檔案 | 內容 |
|------|---------|
| `/tmp/yu-scan/worker.pid` | Worker PID |
| `/tmp/yu-scan/progress.json` | 進度（JSON: running, phase, current, total, percent, message, detail, error） |

WebUI 輪詢此進度檔案，並透過 `GET /api/scan/status` 和 SSE 事件（`scan.progress`、`scan.complete`）傳遞資料。

## 掃描錯誤

### GET /api/scan-errors

掃描期間發生的錯誤清單。

| 參數 | 類型 | 說明 |
|-----------|------|-------------|
| `type` | string | 錯誤類型篩選 |
| `resolved` | bool | 僅已解決的錯誤 |
| `limit` | int | 結果數量 |

### POST /api/scan-errors/<id>/resolve

將錯誤標記為已解決。

### POST /api/scan-errors/clear

一次刪除所有已解決的錯誤。

## 掃描根目錄管理

### GET /api/scan-roots

列出已註冊的掃描根目錄。

### 回應

```json
{
  "roots": [
    {
      "path": "O:\\webui\\outputs",
      "enabled": true,
      "file_count": 15000
    }
  ]
}
```

### POST /api/scan-roots

新增掃描根目錄。

```json
{
  "path": "O:\\webui\\outputs"
}
```

### PUT /api/scan-roots/<index>

更新掃描根目錄（變更路徑、切換啟用/停用）。

### DELETE /api/scan-roots/<index>

刪除掃描根目錄。

## 雜湊回填

### POST /api/hash-backfill/start

啟動現有檔案的背景雜湊計算。

### GET /api/hash-backfill/status

取得進度。

### POST /api/hash-backfill/cancel

取消計算。

## 背景工作

### GET /api/jobs/status

所有背景工作的狀態。用於 UI 橫幅顯示。

```json
{
  "jobs": [
    {
      "type": "scan",
      "status": "running",
      "progress": 45,
      "total": 1500
    }
  ]
}
```
