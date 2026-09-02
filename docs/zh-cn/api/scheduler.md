# Scheduler API

任务调度器管理 API。可查询状态、添加/删除调度任务、暂停/恢复、立即触发执行，以及查询执行历史。

## 配置

在 `config.json` 中启用调度器并配置内置任务的调度：

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

### 内置任务

| 任务 ID | 说明 | 默认调度 |
|---------|------|---------|
| `db_vacuum` | 数据库 VACUUM（回收空间） | 每周日 03:00 |
| `db_integrity_check` | 数据库完整性检查 | 每天 04:00 |
| `thumbnail_cleanup` | 缩略图缓存清理 | 每天 05:00 |
| `github_issue_poll` | GitHub Issue 轮询 | 未设置（通过 WebUI 添加） |
| `bsky_notification_poll` | Bluesky 通知轮询 | 未设置（通过 WebUI 添加） |
| `prune_unused_tags` | 清除未使用标签 | 未设置（通过 WebUI 添加） |
| `refresh_monthly_stats` | 更新月度统计缓存 | 未设置（通过 WebUI 添加） |
| `rebuild_groups_index` | 重建分组索引 | 未设置（通过 WebUI 添加） |
| `db_backup` | 数据库备份 | 未设置（通过 WebUI 添加） |

## GET /api/scheduler/status

返回调度器状态及所有任务信息。

### 响应

| 字段 | 类型 | 说明 |
|------|------|------|
| `ok` | boolean | 成功标志 |
| `data.running` | boolean | 调度器是否正在运行 |
| `data.jobs` | array | 任务列表（含下次执行时间） |

### 示例

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

返回任务列表，包含 `next_run` 时间。

### 响应

| 字段 | 类型 | 说明 |
|------|------|------|
| `ok` | boolean | 成功标志 |
| `data.jobs` | array | 任务对象数组 |
| `data.jobs[].job_id` | string | 任务 ID |
| `data.jobs[].func_name` | string | 执行函数名 |
| `data.jobs[].trigger` | string | 触发类型（`cron`、`interval`、`date`） |
| `data.jobs[].next_run` | string | 下次调度执行时间（ISO 8601） |
| `data.jobs[].paused` | boolean | 是否已暂停 |

### 示例

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

添加自定义任务。

### 请求体

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `job_id` | string | Yes | 唯一的任务 ID |
| `func_name` | string | Yes | 要执行的函数名 |
| `trigger` | string | Yes | 触发类型（`cron`、`interval`、`date`） |
| `trigger_args` | object | Yes | 触发参数（`hour`、`minute`、`day_of_week` 等） |

### 示例

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

删除指定任务。适用 **DESTRUCTIVE** 层级速率限制。

### 路径参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `id` | string | 任务 ID |

### 示例

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

暂停任务。

### 示例

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

恢复已暂停的任务。

### 示例

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

立即触发任务执行。适用 **WRITE** 层级速率限制。

### 示例

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

返回执行历史，按最新排序（最多 100 条）。

### 响应

| 字段 | 类型 | 说明 |
|------|------|------|
| `ok` | boolean | 成功标志 |
| `data.history` | array | 执行历史数组 |
| `data.history[].job_id` | string | 任务 ID |
| `data.history[].executed_at` | string | 执行时间（ISO 8601） |
| `data.history[].status` | string | 结果（`success`、`error`） |
| `data.history[].duration_ms` | number | 执行耗时（毫秒） |
| `data.history[].error` | string\|null | 错误消息（仅失败时） |

### 示例

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

调度器相关事件通过 SSE 共享引擎传递。

| 事件 | 数据 | 说明 |
|------|------|------|
| `scheduler.job_executed` | `{ job_id, result }` | 任务执行完成 |
| `scheduler.job_error` | `{ job_id, error }` | 任务执行错误 |

```javascript
window.sseSubscribe('scheduler.job_executed', (data) => {
  console.log(`Job ${data.job_id} completed: ${data.result}`);
});
```

## MCP 工具

| 工具名称 | 说明 |
|---------|------|
| `get_scheduler_status` | 获取调度器运行状态 |
| `list_scheduled_jobs` | 列出已注册的任务 |
| `trigger_scheduled_job` | 立即触发任务执行 |
| `pause_scheduled_job` | 暂停任务 |
| `resume_scheduled_job` | 恢复任务 |
| `get_scheduler_history` | 获取执行历史 |

## 速率限制

| 端点 | 方法 | 层级 |
|------|------|------|
| `/api/scheduler/status` | GET | READ（无限制） |
| `/api/scheduler/jobs` | GET | READ（无限制） |
| `/api/scheduler/jobs` | POST | WRITE（~120 req/min） |
| `/api/scheduler/jobs/<id>` | DELETE | DESTRUCTIVE（~12 req/min） |
| `/api/scheduler/jobs/<id>/pause` | POST | WRITE（~120 req/min） |
| `/api/scheduler/jobs/<id>/resume` | POST | WRITE（~120 req/min） |
| `/api/scheduler/jobs/<id>/trigger` | POST | WRITE（~120 req/min） |
| `/api/scheduler/history` | GET | READ（无限制） |
