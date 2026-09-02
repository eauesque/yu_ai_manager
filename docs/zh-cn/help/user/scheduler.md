# 任务调度器

## 概述

任务调度器自动执行数据库维护和外部服务轮询等定期任务。基于 APScheduler 的后台调度器使用 cron 和 interval 触发器管理任务。

通过 WebUI 的调度器页面 (`/scheduler`)，您可以查看、添加、删除、暂停和立即执行任务。

## 设置

调度器默认启用。可在 `config.json` 的 `scheduler.enabled` 中控制：

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

在 `config.json` 中定义的任务会在服务器启动时自动注册。通过 WebUI 添加的任务仅在当前服务器会话有效，重启后会消失。

## 内置任务一览

### 数据库维护

| 任务 ID | 说明 | 建议频率 |
|---------|------|---------|
| `db_vacuum` | 执行 SQLite VACUUM 回收未使用空间 | 每周 |
| `db_integrity_check` | 使用 `PRAGMA integrity_check` 验证数据库完整性 | 每天 |
| `db_backup` | 创建数据库备份（通过 builtin-backup 扩展） | 每天 |

### 缓存与索引管理

| 任务 ID | 说明 | 建议频率 |
|---------|------|---------|
| `thumbnail_cleanup` | 删除过期的缩略图缓存文件 | 每天 |
| `prune_unused_tags` | 删除未关联任何文件的孤立标签记录 | 每周至每月 |
| `refresh_monthly_stats` | 更新月度统计预计算缓存 | 每天 |
| `rebuild_groups_index` | 重建文件夹/压缩包分组索引缓存 | 每周 |

### 外部服务集成

| 任务 ID | 说明 | 建议频率 |
|---------|------|---------|
| `github_issue_poll` | 轮询 GitHub API 并将新 Issue 加入本地队列 | 5 分钟至 1 小时 |
| `bsky_notification_poll` | 轮询 Bluesky API 获取新通知 | 5 分钟至 1 小时 |

## 触发器配置

### Cron 触发器

在指定的时间、日期执行。语法类似 Unix cron。

| 参数 | 示例 | 说明 |
|------|------|------|
| `hour` | `3`, `*/6`, `1,13` | 小时 (0-23)。`*` 为每小时 |
| `minute` | `0`, `30`, `0,30` | 分钟 (0-59)。`*` 为每分钟 |
| `day` | `1`, `15`, `1,15` | 日期 (1-31)。`*` 为每天 |
| `day_of_week` | `sun`, `mon-fri`, `0-4` | 星期。`*` 为每天 |

**示例**：每月 1 日和 15 日凌晨 2:30 执行

```json
{ "trigger": "cron", "day": "1,15", "hour": 2, "minute": 30 }
```

### Interval 触发器

以固定间隔重复执行。

| 参数 | 示例 | 说明 |
|------|------|------|
| `hours` | `2` | 小时间隔 |
| `minutes` | `30` | 分钟间隔 |

**示例**：每 30 分钟执行

```json
{ "trigger": "interval", "minutes": 30 }
```

## WebUI 使用方式

### 任务列表

调度器页面显示所有已注册的任务，包括状态（活跃/暂停）、触发器设置和下次执行时间。

### 添加任务

1. 点击 **添加任务** 按钮
2. 输入唯一的任务 ID
3. 从下拉菜单中选择函数
4. 选择触发器类型（cron / interval）
5. 设置调度参数（可用 `*` 作为通配符）
6. 点击 **添加**

### 任务操作

- **立即执行**：在调度外立即执行一次任务
- **暂停 / 恢复**：暂时停止或重新启动定期执行
- **删除**：永久移除任务（config.json 中的任务会在下次启动时恢复）

### 执行历史

页面下方显示最近的执行历史（最多 50 条），包含成功/失败状态和结果消息。任务完成时通过 SSE 自动更新显示。

## MCP 工具

您可以通过 MCP 客户端（如 Claude Desktop）管理调度器：

| 工具 | 说明 |
|------|------|
| `get_scheduler_status` | 获取调度器运行状态 |
| `list_scheduled_jobs` | 列出已注册的任务 |
| `trigger_scheduled_job` | 立即触发任务执行 |
| `pause_scheduled_job` | 暂停任务 |
| `resume_scheduled_job` | 恢复任务 |
| `get_scheduler_history` | 获取执行历史 |

## 提示

- **轮询型任务**（`github_issue_poll`、`bsky_notification_poll`）适合使用 interval 触发器。使用 cron 固定时间可能导致轮询间隔过长
- **`db_vacuum`** 会获取写入锁，建议安排在低流量时段（如深夜）
- **`db_backup`** 遵循 builtin-backup 扩展的冷却设置。即使设置较短的 interval，在冷却期间也会跳过备份
- **执行历史存储于内存**（最多 100 条），服务器重启后会清除
