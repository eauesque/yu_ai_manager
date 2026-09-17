# API Planificateur

Management API for the task scheduler. Allows checking status, adding/removing jobs, pausing/resuming, triggering immediate execution, and retrieving execution history.

## Configuration

Activer the scheduler and configure built-in job schedules in `config.json`:

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

### Built-in Jobs

| Job ID | Description | Défaut Schedule |
|--------|-------------|-----------------|
| `db_vacuum` | Database VACUUM (reclaim space) | Every Sunday at 03:00 |
| `db_integrity_check` | Database integrity check | Daily at 04:00 |
| `thumbnail_cleanup` | Thumbnail cache cleanup | Daily at 05:00 |
| `github_issue_poll` | GitHub issue polling | Not set (add via WebUI) |
| `bsky_notification_poll` | Bluesky notification polling | Not set (add via WebUI) |
| `prune_unused_tags` | Prune unused tags | Not set (add via WebUI) |
| `refresh_monthly_stats` | Refresh monthly stats cache | Not set (add via WebUI) |
| `rebuild_groups_index` | Rebuild groups index | Not set (add via WebUI) |
| `db_backup` | Database backup | Not set (add via WebUI) |

## GET /api/scheduler/status

Returns the scheduler status and information about all jobs.

### Réponse

| Champ | Type | Description |
|-------|------|-------------|
| `ok` | boolean | Success flag |
| `data.running` | boolean | Si the scheduler is running |
| `data.jobs` | array | Job list (including next run times) |

### Example

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

Returns the job list with `next_run` times.

### Réponse

| Champ | Type | Description |
|-------|------|-------------|
| `ok` | boolean | Success flag |
| `data.jobs` | array | Tableau of job objects |
| `data.jobs[].job_id` | string | Job ID |
| `data.jobs[].func_name` | string | Function name to execute |
| `data.jobs[].trigger` | string | Trigger type (`cron`, `interval`, `date`) |
| `data.jobs[].next_run` | string | Next scheduled execution time (ISO 8601) |
| `data.jobs[].paused` | boolean | Si the job is paused |

### Example

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

Add a custom job.

### Requête Body

| Champ | Type | Requis | Description |
|-------|------|----------|-------------|
| `job_id` | string | Yes | Unique job ID |
| `func_name` | string | Yes | Function name to execute |
| `trigger` | string | Yes | Trigger type (`cron`, `interval`, `date`) |
| `trigger_args` | object | Yes | Trigger arguments (`hour`, `minute`, `day_of_week`, etc.) |

### Example

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

Remove a job. Subject to **DESTRUCTIVE** tier rate limiting.

### Path Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `id` | string | Job ID |

### Example

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

Pause a job.

### Example

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

Resume a paused job.

### Example

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

Trigger immediate execution of a job. Subject to **WRITE** tier rate limiting.

### Example

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

Returns execution history in newest-first order (max 100 entries).

### Réponse

| Champ | Type | Description |
|-------|------|-------------|
| `ok` | boolean | Success flag |
| `data.history` | array | Tableau of execution history entries |
| `data.history[].job_id` | string | Job ID |
| `data.history[].executed_at` | string | Execution timestamp (ISO 8601) |
| `data.history[].status` | string | Result (`success`, `error`) |
| `data.history[].duration_ms` | number | Execution duration (milliseconds) |
| `data.history[].error` | string\|null | Error message (only on failure) |

### Example

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

## SSE Events

Scheduler-related events are delivered via the SSE shared engine.

| Event | Data | Description |
|-------|------|-------------|
| `scheduler.job_executed` | `{ job_id, result }` | Job execution completed |
| `scheduler.job_error` | `{ job_id, error }` | Job execution error |

```javascript
window.sseSubscribe('scheduler.job_executed', (data) => {
  console.log(`Job ${data.job_id} completed: ${data.result}`);
});
```

## MCP Tools

| Tool | Description |
|------|-------------|
| `get_scheduler_status` | Get scheduler running status |
| `list_scheduled_jobs` | List registered jobs |
| `trigger_scheduled_job` | Trigger immediate job execution |
| `pause_scheduled_job` | Pause a job |
| `resume_scheduled_job` | Resume a job |
| `get_scheduler_history` | Get execution history |

## Rate Limiting

| Endpoint | Method | Tier |
|----------|--------|------|
| `/api/scheduler/status` | GET | READ (unlimited) |
| `/api/scheduler/jobs` | GET | READ (unlimited) |
| `/api/scheduler/jobs` | POST | WRITE (~120 req/min) |
| `/api/scheduler/jobs/<id>` | DELETE | DESTRUCTIVE (~12 req/min) |
| `/api/scheduler/jobs/<id>/pause` | POST | WRITE (~120 req/min) |
| `/api/scheduler/jobs/<id>/resume` | POST | WRITE (~120 req/min) |
| `/api/scheduler/jobs/<id>/trigger` | POST | WRITE (~120 req/min) |
| `/api/scheduler/history` | GET | READ (unlimited) |
