# Task Scheduler

## Overview

The task scheduler automatically runs periodic tasks such as database maintenance and external service polling. An APScheduler-based background scheduler manages jobs with cron and interval triggers.

From the scheduler page (`/scheduler`) in the WebUI, you can view, add, delete, pause, and immediately run jobs.

## Setup

The scheduler is enabled by default. Control it via `scheduler.enabled` in `config.json`:

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

Jobs defined in `config.json` are automatically registered on server startup. Jobs added via the WebUI are valid only for the current server session and are lost on restart.

## Built-in Jobs

### Database Maintenance

| Job ID | Description | Recommended Frequency |
|--------|-------------|----------------------|
| `db_vacuum` | Run SQLite VACUUM to reclaim unused space | Weekly |
| `db_integrity_check` | Verify database integrity with `PRAGMA integrity_check` | Daily |
| `db_backup` | Create a database backup (via builtin-backup extension) | Daily |

### Cache & Index Management

| Job ID | Description | Recommended Frequency |
|--------|-------------|----------------------|
| `thumbnail_cleanup` | Remove expired thumbnail cache files | Daily |
| `prune_unused_tags` | Delete orphaned tag records not associated with any files | Weekly to monthly |
| `refresh_monthly_stats` | Refresh the pre-computed monthly statistics cache | Daily |
| `rebuild_groups_index` | Rebuild the folder/archive group index cache | Weekly |

### External Service Integration

| Job ID | Description | Recommended Frequency |
|--------|-------------|----------------------|
| `github_issue_poll` | Poll GitHub API and enqueue new issues locally | 5 min to 1 hour |
| `bsky_notification_poll` | Poll Bluesky API for new notifications | 5 min to 1 hour |

## Trigger Configuration

### Cron Trigger

Run at specific times, days, or dates. Similar to Unix cron syntax.

| Parameter | Example | Description |
|-----------|---------|-------------|
| `hour` | `3`, `*/6`, `1,13` | Hour (0-23). `*` for every hour |
| `minute` | `0`, `30`, `0,30` | Minute (0-59). `*` for every minute |
| `day` | `1`, `15`, `1,15` | Day of month (1-31). `*` for every day |
| `day_of_week` | `sun`, `mon-fri`, `0-4` | Day of week. `*` for every day |

**Example**: Run on the 1st and 15th of every month at 2:30 AM

```json
{ "trigger": "cron", "day": "1,15", "hour": 2, "minute": 30 }
```

### Interval Trigger

Run repeatedly at a fixed interval.

| Parameter | Example | Description |
|-----------|---------|-------------|
| `hours` | `2` | Hour interval |
| `minutes` | `30` | Minute interval |

**Example**: Run every 30 minutes

```json
{ "trigger": "interval", "minutes": 30 }
```

## Using the WebUI

### Job List

The scheduler page shows all registered jobs with their status (active/paused), trigger settings, and next run time.

### Adding a Job

1. Click the **Add Job** button
2. Enter a unique Job ID
3. Select the function from the dropdown
4. Choose the trigger type (cron / interval)
5. Set the schedule parameters (use `*` for wildcards)
6. Click **Add**

### Job Actions

- **Run Now**: Execute the job immediately outside its schedule
- **Pause / Resume**: Temporarily stop or restart periodic execution
- **Delete**: Permanently remove the job (config.json jobs are restored on next startup)

### Execution History

The bottom of the page shows recent execution history (up to 50 entries) with success/failure status and result messages. The display auto-refreshes via SSE when jobs complete.

## MCP Tools

You can manage the scheduler from MCP clients (e.g., Claude Desktop):

| Tool | Description |
|------|-------------|
| `get_scheduler_status` | Get scheduler running status |
| `list_scheduled_jobs` | List registered jobs |
| `trigger_scheduled_job` | Trigger immediate job execution |
| `pause_scheduled_job` | Pause a job |
| `resume_scheduled_job` | Resume a job |
| `get_scheduler_history` | Get execution history |

## Tips

- **Polling jobs** (`github_issue_poll`, `bsky_notification_poll`) work best with interval triggers. Using cron at fixed times can result in overly long polling gaps
- **`db_vacuum`** acquires a write lock, so schedule it during low-traffic hours (e.g., late night)
- **`db_backup`** respects the builtin-backup extension's cooldown setting. Even with short intervals, backups are skipped during the cooldown period
- **Execution history is stored in memory** (max 100 entries) and is cleared on server restart
