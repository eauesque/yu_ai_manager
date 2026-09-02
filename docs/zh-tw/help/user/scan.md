# 掃描

## 註冊掃描資料夾

前往 Settings > Scan 分頁新增掃描對象資料夾。

- 可透過拖放重新排序
- 透過核取方塊切換啟用/停用
- 可註冊多個資料夾

## 執行掃描

- 新增資料夾後會自動開始掃描
- 手動掃描可從 Tools 頁面或 MCP 的 `trigger_scan` 執行
- 掃描中的進度會透過 SSE 即時通知

## 自動掃描（Watcher）

啟用 Auto Scan Watcher 擴充功能後，可自動偵測已註冊資料夾內的檔案變更並進行掃描。

## 遠端檔案系統

掃描 WSL / NAS / SMB 等遠端路徑時，請在 Settings > Remote FS 分頁調整逾時設定。

## 大規模圖庫的掃描

掃描數十萬～100 萬件以上檔案時的注意事項：

- **掃描中仍可搜尋圖片**：搜尋 API 使用唯讀 DB 連線，不受掃描中寫入鎖定的影響
- **WAL 自動管理**：掃描中每 2000 個檔案會自動執行 WAL 檢查點，防止 WAL 檔案過度膨脹
- **scan.db_busy 事件**：掃描開始/完成時會發送 SSE 事件，前端可據此顯示忙碌狀態

## 掃描 Worker 程序

自 v3.27.0 起，掃描在獨立於 web_ui.py 的另一個程序中執行。
因此**即使重新啟動 web_ui，掃描也不會中斷**。

### 運作機制

- 從 WebUI 開始掃描時，會在背景啟動 Worker 程序
- Worker 會在 `/tmp/yu-scan/` 寫入進度檔案 (JSON) 和 PID 檔案
- WebUI 會輪詢此進度檔案，並透過 SSE 轉發給前端
- 重新啟動 WebUI 時，會自動偵測執行中的 Worker 並重新連接進度顯示

### 從 CLI 操作

Worker 也可從 CLI 直接操作。即使 WebUI 停止時也可使用。

```bash
# 檢查狀態
python -m core.scan.scan_worker status

# 停止執行中的掃描（優雅關閉 — 將中斷位置儲存至 DB）
python -m core.scan.scan_worker stop

# 從 CLI 直接開始掃描
python -m core.scan.scan_worker start --db ./tags.db --root /path/to/images

# 選項
#   --recursive / --no-recursive  是否包含子目錄（預設：recursive）
#   --scan-zips                   掃描 ZIP/7z 內的圖片
#   --force                       重新掃描已存在的檔案
#   --resume                      恢復中斷的掃描
#   --config config.json          指定設定檔
```

### 安全機制

- **父程序監控**：從 WebUI 啟動的 Worker 會每 60 秒監控 WebUI 程序的存活狀態。若 WebUI 異常終止，Worker 會自動儲存中斷位置並停止
- **SIGTERM 處理**：收到 `stop` 指令或 `kill` 的 SIGTERM 時，會完成目前的處理後提交至 DB，儲存中斷位置後結束
- **防止重複**：不會同時啟動多個 Worker

### 疑難排解

若 Worker 無回應：

```bash
# 確認 PID
cat /tmp/yu-scan/worker.pid

# 強制終止程序
kill -9 $(cat /tmp/yu-scan/worker.pid)

# 清除殘留檔案
rm -f /tmp/yu-scan/worker.pid /tmp/yu-scan/progress.json
```

## 掃描錯誤

掃描中發生錯誤時，可透過 MCP 的 `get_scan_errors` 確認。
