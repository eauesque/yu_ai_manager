# 任務排程器

## 概述

任務排程器自動執行資料庫維護和外部服務輪詢等定期任務。基於 APScheduler 的背景排程器使用 cron 和 interval 觸發器管理任務。

透過 WebUI 的排程器頁面 (`/scheduler`)，您可以查看、新增、刪除、暫停和立即執行任務。

## 設定

排程器預設為啟用。可在 `config.json` 的 `scheduler.enabled` 中控制：

```json
{
  "scheduler": {
    "enabled": true,
    "jobs": {
      "db_vacuum": { "enabled": true, "trigger": "cron", "day_of_week": "sun", "hour": 3, "minute": 0 },
      "db_integrity_check": { "enabled": true, "trigger": "cron", "hour": 4, "minute": 0 },
      "thumbnail_cleanup": { "enabled": true, "trigger": "cron", "hour": 5, "minute": 0 }
    }
  }
}
```

在 `config.json` 中定義的任務會在伺服器啟動時自動註冊。透過 WebUI 新增的任務僅在當前伺服器工作階段有效，重啟後會消失。

## 內建任務一覽

### 資料庫維護

| 任務 ID | 說明 | 建議頻率 |
|---------|------|---------|
| `db_vacuum` | 執行 SQLite VACUUM 回收未使用空間 | 每週 |
| `db_integrity_check` | 使用 `PRAGMA integrity_check` 驗證資料庫完整性 | 每天 |
| `db_backup` | 建立資料庫備份（透過 builtin-backup 擴充套件） | 每天 |

### 快取與索引管理

| 任務 ID | 說明 | 建議頻率 |
|---------|------|---------|
| `thumbnail_cleanup` | 刪除過期的縮圖快取檔案 | 每天 |
| `prune_unused_tags` | 刪除未關聯任何檔案的孤立標籤記錄 | 每週至每月 |
| `refresh_monthly_stats` | 更新月度統計預計算快取 | 每天 |
| `rebuild_groups_index` | 重建資料夾/壓縮檔群組索引快取 | 每週 |

### 外部服務整合

| 任務 ID | 說明 | 建議頻率 |
|---------|------|---------|
| `github_issue_poll` | 輪詢 GitHub API 並將新 Issue 加入本地佇列 | 5 分鐘至 1 小時 |
| `bsky_notification_poll` | 輪詢 Bluesky API 取得新通知 | 5 分鐘至 1 小時 |

## 觸發器設定

### Cron 觸發器

在指定的時間、日期執行。語法類似 Unix cron。

| 參數 | 範例 | 說明 |
|------|------|------|
| `hour` | `3`, `*/6`, `1,13` | 小時 (0-23)。`*` 為每小時 |
| `minute` | `0`, `30`, `0,30` | 分鐘 (0-59)。`*` 為每分鐘 |
| `day` | `1`, `15`, `1,15` | 日期 (1-31)。`*` 為每天 |
| `day_of_week` | `sun`, `mon-fri`, `0-4` | 星期。`*` 為每天 |

**範例**：每月 1 日和 15 日凌晨 2:30 執行

```json
{ "trigger": "cron", "day": "1,15", "hour": 2, "minute": 30 }
```

### Interval 觸發器

以固定間隔重複執行。

| 參數 | 範例 | 說明 |
|------|------|------|
| `hours` | `2` | 小時間隔 |
| `minutes` | `30` | 分鐘間隔 |

**範例**：每 30 分鐘執行

```json
{ "trigger": "interval", "minutes": 30 }
```

## WebUI 使用方式

### 任務列表

排程器頁面顯示所有已註冊的任務，包括狀態（啟用/暫停）、觸發器設定和下次執行時間。

### 新增任務

1. 點擊 **新增任務** 按鈕
2. 輸入唯一的任務 ID
3. 從下拉選單中選擇函式
4. 選擇觸發器類型（cron / interval）
5. 設定排程參數（可用 `*` 作為萬用字元）
6. 點擊 **新增**

### 任務操作

- **立即執行**：在排程外立即執行一次任務
- **暫停 / 恢復**：暫時停止或重新啟動定期執行
- **刪除**：永久移除任務（config.json 中的任務會在下次啟動時恢復）

### 執行歷史

頁面下方顯示最近的執行歷史（最多 50 筆），包含成功/失敗狀態和結果訊息。任務完成時透過 SSE 自動更新顯示。

## MCP 工具

您可以透過 MCP 用戶端（如 Claude Desktop）管理排程器：

| 工具 | 說明 |
|------|------|
| `get_scheduler_status` | 取得排程器執行狀態 |
| `list_scheduled_jobs` | 列出已註冊的任務 |
| `trigger_scheduled_job` | 立即觸發任務執行 |
| `pause_scheduled_job` | 暫停任務 |
| `resume_scheduled_job` | 恢復任務 |
| `get_scheduler_history` | 取得執行歷史 |

## 提示

- **輪詢型任務**（`github_issue_poll`、`bsky_notification_poll`）適合使用 interval 觸發器。使用 cron 固定時間可能導致輪詢間隔過長
- **`db_vacuum`** 會取得寫入鎖定，建議安排在低流量時段（如深夜）
- **`db_backup`** 遵循 builtin-backup 擴充套件的冷卻設定。即使設定較短的 interval，在冷卻期間也會跳過備份
- **執行歷史儲存於記憶體**（最多 100 筆），伺服器重啟後會清除
