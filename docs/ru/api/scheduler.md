# API планировщика

API управления для планировщика задач. Позволяет проверять статус, добавлять/удалять задачи, приостанавливать/возобновлять, запускать немедленное выполнение и получать историю выполнения.

## Конфигурация

Включить планировщик и настроить встроенные расписания задач в `config.json`:

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

### Встроенные задачи

| ID задачи | Описание | Расписание по умолчанию |
|--------|-------------|-----------------|
| `db_vacuum` | Вакуумирование базы данных (освобождение места) | Каждое воскресенье в 03:00 |
| `db_integrity_check` | Проверка целостности базы данных | Ежедневно в 04:00 |
| `thumbnail_cleanup` | Очистка кеша миниатюр | Ежедневно в 05:00 |
| `github_issue_poll` | Опрос проблем GitHub | Не установлено (добавить через WebUI) |
| `bsky_notification_poll` | Опрос уведомлений Bluesky | Не установлено (добавить через WebUI) |
| `prune_unused_tags` | Удалить неиспользуемые теги | Не установлено (добавить через WebUI) |
| `refresh_monthly_stats` | Обновить кеш ежемесячной статистики | Не установлено (добавить через WebUI) |
| `rebuild_groups_index` | Перестроить индекс групп | Не установлено (добавить через WebUI) |
| `db_backup` | Резервная копия базы данных | Не установлено (добавить через WebUI) |

## GET /api/scheduler/status

Возвращает статус планировщика и информацию о всех задачах.

### Ответ

| Поле | Тип | Описание |
|-------|------|-------------|
| `ok` | boolean | Флаг успеха |
| `data.running` | boolean | Запущен ли планировщик |
| `data.jobs` | array | Список задач (включая время следующего запуска) |

### Пример

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

Возвращает список задач с временем `next_run`.

### Ответ

| Поле | Тип | Описание |
|-------|------|-------------|
| `ok` | boolean | Флаг успеха |
| `data.jobs` | array | Массив объектов задач |
| `data.jobs[].job_id` | string | ID задачи |
| `data.jobs[].func_name` | string | Имя функции для выполнения |
| `data.jobs[].trigger` | string | Тип триггера (`cron`, `interval`, `date`) |
| `data.jobs[].next_run` | string | Время следующего запланированного выполнения (ISO 8601) |
| `data.jobs[].paused` | boolean | Приостановлена ли задача |

### Пример

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

Добавить пользовательскую задачу.

### Тело запроса

| Поле | Тип | Требуется | Описание |
|-------|------|----------|-------------|
| `job_id` | string | Да | Уникальный ID задачи |
| `func_name` | string | Да | Имя функции для выполнения |
| `trigger` | string | Да | Тип триггера (`cron`, `interval`, `date`) |
| `trigger_args` | object | Да | Аргументы триггера (`hour`, `minute`, `day_of_week` и т.д.) |

### Пример

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

Удалить задачу. Подлежит ограничению частоты запросов уровня **DESTRUCTIVE**.

### Параметры пути

| Параметр | Тип | Описание |
|-----------|------|-------------|
| `id` | string | ID задачи |

### Пример

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

Приостановить задачу.

### Пример

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

Возобновить приостановленную задачу.

### Пример

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

Запустить немедленное выполнение задачи. Подлежит ограничению частоты запросов уровня **WRITE**.

### Пример

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

Возвращает историю выполнения в порядке новейших-первых (максимум 100 записей).

### Ответ

| Поле | Тип | Описание |
|-------|------|-------------|
| `ok` | boolean | Флаг успеха |
| `data.history` | array | Массив записей истории выполнения |
| `data.history[].job_id` | string | ID задачи |
| `data.history[].executed_at` | string | Временная метка выполнения (ISO 8601) |
| `data.history[].status` | string | Результат (`success`, `error`) |
| `data.history[].duration_ms` | number | Длительность выполнения (миллисекунды) |
| `data.history[].error` | string\|null | Сообщение об ошибке (только при сбое) |

### Пример

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

## SSE события

События, связанные с планировщиком, передаются через общий механизм SSE.

| Событие | Данные | Описание |
|-------|------|-------------|
| `scheduler.job_executed` | `{ job_id, result }` | Выполнение задачи завершено |
| `scheduler.job_error` | `{ job_id, error }` | Ошибка выполнения задачи |

```javascript
window.sseSubscribe('scheduler.job_executed', (data) => {
  console.log(`Job ${data.job_id} completed: ${data.result}`);
});
```

## MCP инструменты

| Инструмент | Описание |
|------|-------------|
| `get_scheduler_status` | Получить статус запуска планировщика |
| `list_scheduled_jobs` | Список зарегистрированных задач |
| `trigger_scheduled_job` | Запустить немедленное выполнение задачи |
| `pause_scheduled_job` | Приостановить задачу |
| `resume_scheduled_job` | Возобновить задачу |
| `get_scheduler_history` | Получить историю выполнения |

## Ограничение частоты запросов

| Конечная точка | Метод | Уровень |
|----------|--------|------|
| `/api/scheduler/status` | GET | READ (неограниченно) |
| `/api/scheduler/jobs` | GET | READ (неограниченно) |
| `/api/scheduler/jobs` | POST | WRITE (~120 req/min) |
| `/api/scheduler/jobs/<id>` | DELETE | DESTRUCTIVE (~12 req/min) |
| `/api/scheduler/jobs/<id>/pause` | POST | WRITE (~120 req/min) |
| `/api/scheduler/jobs/<id>/resume` | POST | WRITE (~120 req/min) |
| `/api/scheduler/jobs/<id>/trigger` | POST | WRITE (~120 req/min) |
| `/api/scheduler/history` | GET | READ (неограниченно) |
