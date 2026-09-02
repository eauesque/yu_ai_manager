# Scheduler API

任務排程器管理 API。可查詢狀態、新增/刪除排程任務、暫停/恢復、立即觸發執行，以及查詢執行歷史。

## 設定

在 `config.json` 中啟用排程器並設定內建任務的排程：

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

### 內建任務

| 任務 ID | 說明 | 預設排程 |
|---------|------|---------|
| `db_vacuum` | 資料庫 VACUUM（回收空間） | 每週日 03:00 |
| `db_integrity_check` | 資料庫完整性檢查 | 每天 04:00 |
| `thumbnail_cleanup` | 縮圖快取清理 | 每天 05:00 |
| `github_issue_poll` | GitHub Issue 輪詢 | 未設定（透過 WebUI 新增） |
| `bsky_notification_poll` | Bluesky 通知輪詢 | 未設定（透過 WebUI 新增） |
| `prune_unused_tags` | 清除未使用標籤 | 未設定（透過 WebUI 新增） |
| `refresh_monthly_stats` | 更新月度統計快取 | 未設定（透過 WebUI 新增） |
| `rebuild_groups_index` | 重建群組索引 | 未設定（透過 WebUI 新增） |
| `db_backup` | 資料庫備份 | 未設定（透過 WebUI 新增） |

## GET /api/scheduler/status

回傳排程器狀態及所有任務資訊。

### 回應

| 欄位 | 型別 | 說明 |
|------|------|------|
| `ok` | boolean | 成功旗標 |
| `data.running` | boolean | 排程器是否正在執行 |
| `data.jobs` | array | 任務清單（含下次執行時間） |

### 範例

```bash
curl "http://localhost:5100/api/scheduler/status"
```

```json
{
  "ok": true,
  "data": {
    "running": true,
    "jobs": [
      {
        "job_id": "db_vacuum",
        "trigger": "cron",
        "next_run": "2026-03-22T03:00:00",
        "paused": false
      },
      {
        "job_id": "db_integrity_check",
        "trigger": "cron",
        "next_run": "2026-03-16T04:00:00",
        "paused": false
      }
    ]
  }
}
```

## GET /api/scheduler/jobs

回傳任務清單，包含 `next_run` 時間。

### 回應

| 欄位 | 型別 | 說明 |
|------|------|------|
| `ok` | boolean | 成功旗標 |
| `data.jobs` | array | 任務物件陣列 |
| `data.jobs[].job_id` | string | 任務 ID |
| `data.jobs[].func_name` | string | 執行函式名稱 |
| `data.jobs[].trigger` | string | 觸發類型（`cron`、`interval`、`date`） |
| `data.jobs[].next_run` | string | 下次排程執行時間（ISO 8601） |
| `data.jobs[].paused` | boolean | 是否已暫停 |

### 範例

```bash
curl "http://localhost:5100/api/scheduler/jobs"
```

```json
{
  "ok": true,
  "data": {
    "jobs": [
      {
        "job_id": "db_vacuum",
        "func_name": "db_vacuum",
        "trigger": "cron",
        "next_run": "2026-03-22T03:00:00",
        "paused": false
      }
    ]
  }
}
```

## POST /api/scheduler/jobs

新增自訂任務。

### 請求主體

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `job_id` | string | Yes | 唯一的任務 ID |
| `func_name` | string | Yes | 要執行的函式名稱 |
| `trigger` | string | Yes | 觸發類型（`cron`、`interval`、`date`） |
| `trigger_args` | object | Yes | 觸發參數（`hour`、`minute`、`day_of_week` 等） |

### 範例

```bash
curl -X POST "http://localhost:5100/api/scheduler/jobs" \
     -H "X-Requested-With: XMLHttpRequest" \
     -H "Content-Type: application/json" \
     -d '{
       "job_id": "custom_cleanup",
       "func_name": "thumbnail_cleanup",
       "trigger": "cron",
       "trigger_args": { "hour": 6, "minute": 30 }
     }'
```

```json
{
  "ok": true,
  "data": {
    "job_id": "custom_cleanup",
    "next_run": "2026-03-16T06:30:00"
  }
}
```

## DELETE /api/scheduler/jobs/\<id\>

刪除指定任務。適用 **DESTRUCTIVE** 層級速率限制。

### 路徑參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `id` | string | 任務 ID |

### 範例

```bash
curl -X DELETE "http://localhost:5100/api/scheduler/jobs/custom_cleanup" \
     -H "X-Requested-With: XMLHttpRequest"
```

```json
{
  "ok": true,
  "data": { "removed": "custom_cleanup" }
}
```

## POST /api/scheduler/jobs/\<id\>/pause

暫停任務。

### 範例

```bash
curl -X POST "http://localhost:5100/api/scheduler/jobs/db_vacuum/pause" \
     -H "X-Requested-With: XMLHttpRequest"
```

```json
{
  "ok": true,
  "data": { "job_id": "db_vacuum", "paused": true }
}
```

## POST /api/scheduler/jobs/\<id\>/resume

恢復已暫停的任務。

### 範例

```bash
curl -X POST "http://localhost:5100/api/scheduler/jobs/db_vacuum/resume" \
     -H "X-Requested-With: XMLHttpRequest"
```

```json
{
  "ok": true,
  "data": { "job_id": "db_vacuum", "paused": false }
}
```

## POST /api/scheduler/jobs/\<id\>/trigger

立即觸發任務執行。適用 **WRITE** 層級速率限制。

### 範例

```bash
curl -X POST "http://localhost:5100/api/scheduler/jobs/db_vacuum/trigger" \
     -H "X-Requested-With: XMLHttpRequest"
```

```json
{
  "ok": true,
  "data": { "job_id": "db_vacuum", "triggered": true }
}
```

## GET /api/scheduler/history

回傳執行歷史，依最新排序（最多 100 筆）。

### 回應

| 欄位 | 型別 | 說明 |
|------|------|------|
| `ok` | boolean | 成功旗標 |
| `data.history` | array | 執行歷史陣列 |
| `data.history[].job_id` | string | 任務 ID |
| `data.history[].executed_at` | string | 執行時間（ISO 8601） |
| `data.history[].status` | string | 結果（`success`、`error`） |
| `data.history[].duration_ms` | number | 執行耗時（毫秒） |
| `data.history[].error` | string\|null | 錯誤訊息（僅失敗時） |

### 範例

```bash
curl "http://localhost:5100/api/scheduler/history"
```

```json
{
  "ok": true,
  "data": {
    "history": [
      {
        "job_id": "db_integrity_check",
        "executed_at": "2026-03-15T04:00:02",
        "status": "success",
        "duration_ms": 1234,
        "error": null
      },
      {
        "job_id": "thumbnail_cleanup",
        "executed_at": "2026-03-15T05:00:01",
        "status": "success",
        "duration_ms": 567,
        "error": null
      }
    ]
  }
}
```

## SSE 事件

排程器相關事件透過 SSE 共用引擎傳遞。

| 事件 | 資料 | 說明 |
|------|------|------|
| `scheduler.job_executed` | `{ job_id, result }` | 任務執行完成 |
| `scheduler.job_error` | `{ job_id, error }` | 任務執行錯誤 |

```javascript
window.sseSubscribe('scheduler.job_executed', (data) => {
  console.log(`Job ${data.job_id} completed: ${data.result}`);
});
```

## MCP 工具

| 工具名稱 | 說明 |
|---------|------|
| `get_scheduler_status` | 取得排程器執行狀態 |
| `list_scheduled_jobs` | 列出已註冊的任務 |
| `trigger_scheduled_job` | 立即觸發任務執行 |
| `pause_scheduled_job` | 暫停任務 |
| `resume_scheduled_job` | 恢復任務 |
| `get_scheduler_history` | 取得執行歷史 |

## 速率限制

| 端點 | 方法 | 層級 |
|------|------|------|
| `/api/scheduler/status` | GET | READ（無限制） |
| `/api/scheduler/jobs` | GET | READ（無限制） |
| `/api/scheduler/jobs` | POST | WRITE（~120 req/min） |
| `/api/scheduler/jobs/<id>` | DELETE | DESTRUCTIVE（~12 req/min） |
| `/api/scheduler/jobs/<id>/pause` | POST | WRITE（~120 req/min） |
| `/api/scheduler/jobs/<id>/resume` | POST | WRITE（~120 req/min） |
| `/api/scheduler/jobs/<id>/trigger` | POST | WRITE（~120 req/min） |
| `/api/scheduler/history` | GET | READ（無限制） |
