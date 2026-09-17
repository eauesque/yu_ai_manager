# API Шлюза безопасности агента

API для управления элементами управления безопасностью агента AI. Предоставляет Kill Switch, Circuit Breaker, Budget, Action Journal, Approval Gate, Scope Fence, Auto-Approve, Tool Classification, Undo, Anomaly Detection и Audit Bureau.

Все конечные точки POST/DELETE требуют заголовка `X-Requested-With` (кроме использования API Key Bearer).

---

## Kill Switch

### POST /api/agent/kill

Активировать Kill Switch для немедленного остановления всех операций агента.

#### Лимит частоты запросов

WRITE

#### Запрос

```json
{
  "reason": "Manual kill via API"
}
```

| Параметр | Тип | Обязательно | Описание |
|-----------|------|----------|-------------|
| `reason` | string | Нет | Причина остановки. По умолчанию `"Manual kill via API"` |

#### Ответ

```json
{
  "ok": true,
  "status": {
    "killed": true,
    "reason": "Manual kill via API",
    "killed_at": "2026-03-22T12:00:00"
  }
}
```

### POST /api/agent/resume

Деактивировать Kill Switch для возобновления операций агента.

#### Лимит частоты запросов

WRITE

#### Запрос

Нет (пустое тело)

#### Ответ

```json
{
  "ok": true,
  "status": {
    "killed": false,
    "reason": "",
    "killed_at": ""
  }
}
```

### GET /api/agent/status

Получить объединенный статус Kill Switch, Circuit Breaker и Budget.

#### Параметры

Нет

#### Ответ

```json
{
  "kill_switch": {
    "killed": false,
    "reason": "",
    "killed_at": ""
  },
  "circuit_breaker": {
    "enabled": true,
    "state": "closed",
    "failure_count": 0,
    "threshold": 5
  },
  "budget": {
    "session_id": "abc123",
    "used": 10,
    "limit": 100,
    "remaining": 90
  },
  "killed": false,
  "reason": "",
  "killed_at": ""
}
```

| Поле | Тип | Описание |
|-------|------|-------------|
| `kill_switch` | object | Подробный статус Kill Switch |
| `circuit_breaker` | object | Подробный статус Circuit Breaker. Возвращает `{"enabled": false, "state": "unknown"}` при ошибке |
| `budget` | object | Подробный статус Budget. Возвращает пустой объект при ошибке |
| `killed` | boolean | Флаг активности Kill Switch (верхний уровень для обратной совместимости) |
| `reason` | string | Причина Kill Switch (обратная совместимость) |
| `killed_at` | string | Время активации Kill Switch (обратная совместимость) |

---

## Circuit Breaker

### GET /api/agent/circuit-breaker

Получить состояние Circuit Breaker.

#### Параметры

Нет

#### Ответ

```json
{
  "enabled": true,
  "state": "closed",
  "failure_count": 0,
  "threshold": 5
}
```

| Поле | Тип | Описание |
|-------|------|-------------|
| `enabled` | boolean | Включен ли Circuit Breaker |
| `state` | string | Состояние: `"closed"` (нормально), `"open"` (сработал), `"half_open"` (проверка) |
| `failure_count` | int | Счетчик последовательных ошибок |
| `threshold` | int | Порог счетчика ошибок для срабатывания |

### POST /api/agent/circuit-breaker/reset

Сбросить Circuit Breaker в закрытое состояние.

#### Лимит частоты запросов

WRITE

#### Запрос

Нет (пустое тело)

#### Ответ

```json
{
  "ok": true,
  "status": {
    "enabled": true,
    "state": "closed",
    "failure_count": 0,
    "threshold": 5
  }
}
```

---

## Budget

### GET /api/agent/budget

Получить оставшейся бюджет для текущей сессии.

#### Параметры

Нет

#### Ответ

```json
{
  "session_id": "abc123",
  "used": 10,
  "limit": 100,
  "remaining": 90
}
```

| Поле | Тип | Описание |
|-------|------|-------------|
| `session_id` | string | ID сессии |
| `used` | int | Количество использованных действий |
| `limit` | int | Максимально допустимых действий |
| `remaining` | int | Оставшихся действий |

### POST /api/agent/budget/reset

Сбросить счетчик бюджета.

#### Лимит частоты запросов

WRITE

#### Запрос

Нет (пустое тело)

#### Ответ

```json
{
  "ok": true,
  "status": {
    "session_id": "abc123",
    "used": 0,
    "limit": 100,
    "remaining": 100
  }
}
```

---

## Action Journal

### GET /api/agent/journal

Поиск в Action Journal. Возвращает историю действий, выполненных агентами.

#### Параметры

| Параметр | Тип | Обязательно | Описание |
|-----------|------|----------|-------------|
| `tool_name` | string | Нет | Фильтр по имени инструмента |
| `status` | string | Нет | Фильтр по статусу |
| `session_id` | string | Нет | Фильтр по ID сессии |
| `limit` | int | Нет | Макс результатов (по умолчанию: 50, макс: 200) |
| `offset` | int | Нет | Смещение (по умолчанию: 0) |

#### Ответ

```json
{
  "entries": [
    {
      "id": 1,
      "tool_name": "add_tags",
      "session_id": "abc123",
      "status": "completed",
      "params": {"file_id": 42, "tags": ["landscape"]},
      "result": {"ok": true},
      "created_at": "2026-03-22T12:00:00"
    }
  ],
  "total": 1
}
```

### GET /api/agent/journal/stats

Получить статистику Action Journal.

#### Параметры

Нет

#### Ответ

```json
{
  "total_entries": 150,
  "by_tool": {"add_tags": 50, "delete_tags": 30, "scan": 70},
  "by_status": {"completed": 140, "failed": 10}
}
```

---

## Approval Gate

### GET /api/agent/approval

Получить список запросов ожидающих одобрения.

#### Параметры

Нет

#### Ответ

```json
{
  "pending": [
    {
      "request_id": "req_abc123",
      "tool_name": "purge_deleted",
      "params": {},
      "requested_at": "2026-03-22T12:00:00"
    }
  ],
  "count": 1
}
```

### POST /api/agent/approval/\<request_id\>

Ответить на запрос одобрения.

#### Лимит частоты запросов

WRITE

#### Параметры

| Параметр | Тип | Описание |
|-----------|------|-------------|
| `request_id` | string | ID запроса (параметр пути) |

#### Запрос

```json
{
  "decision": "allow"
}
```

| Параметр | Тип | Обязательно | Описание |
|-----------|------|----------|-------------|
| `decision` | string | Да | `"allow"` (разрешить), `"deny"` (отклонить), `"always_allow"` (всегда разрешать) |

#### Ответ

```json
{
  "ok": true,
  "request_id": "req_abc123",
  "decision": "allow"
}
```

#### Ошибки

- `400`: `decision` не является одним из `allow`/`deny`/`always_allow`
- `404`: Запрос не найден или уже ответ дан

### GET /api/agent/approval/history

Получить историю одобрений.

#### Параметры

| Параметр | Тип | Обязательно | Описание |
|-----------|------|----------|-------------|
| `limit` | int | Нет | Макс результатов (по умолчанию: 50, макс: 200) |

#### Ответ

```json
{
  "history": [
    {
      "request_id": "req_abc123",
      "tool_name": "purge_deleted",
      "decision": "allow",
      "decided_at": "2026-03-22T12:01:00"
    }
  ]
}
```

---

## Scope Fence

### GET /api/agent/scope

Получить состояние Scope Fence для всех сессий.

#### Параметры

Нет

#### Ответ

```json
{
  "sessions": {
    "abc123": {
      "preset": "tagger",
      "denied": ["purge_deleted", "hard_delete"],
      "name": "Tagger Bot",
      "expires_at": "2026-03-22T14:00:00"
    }
  },
  "count": 1
}
```

### GET /api/agent/scope/\<session_id\>

Получить область для конкретной сессии.

#### Параметры

| Параметр | Тип | Описание |
|-----------|------|-------------|
| `session_id` | string | ID сессии (параметр пути) |

#### Ответ

```json
{
  "preset": "tagger",
  "denied": ["purge_deleted", "hard_delete"],
  "name": "Tagger Bot",
  "expires_at": "2026-03-22T14:00:00"
}
```

#### Ошибки

- `404`: Область сессии не найдена

### POST /api/agent/scope/\<session_id\>

Установить область сессии.

#### Лимит частоты запросов

WRITE

#### Параметры

| Параметр | Тип | Описание |
|-----------|------|-------------|
| `session_id` | string | ID сессии (параметр пути) |

#### Запрос

```json
{
  "preset": "tagger",
  "denied": ["purge_deleted"],
  "name": "Tagger Bot",
  "duration_hours": 2.0
}
```

| Параметр | Тип | Обязательно | Описание |
|-----------|------|----------|-------------|
| `preset` | string | Нет | Имя предустановки: `"read_only"`, `"tagger"`, `"organizer"`, `"full_access"` |
| `denied` | string[] | Нет | Список имен запрещенных инструментов |
| `name` | string | Нет | Отображаемое имя для области |
| `duration_hours` | number | Нет | Истечение области в часах |

#### Ответ

```json
{
  "ok": true,
  "scope": {
    "preset": "tagger",
    "denied": ["purge_deleted"],
    "name": "Tagger Bot",
    "expires_at": "2026-03-22T14:00:00"
  }
}
```

#### Ошибки

- `400`: `denied` не является массивом

### DELETE /api/agent/scope/\<session_id\>

Удалить область сессии.

#### Лимит частоты запросов

WRITE

#### Параметры

| Параметр | Тип | Описание |
|-----------|------|-------------|
| `session_id` | string | ID сессии (параметр пути) |

#### Ответ

```json
{
  "ok": true
}
```

---

## Правила автоматического одобрения

### GET /api/agent/auto-approve

Получить список правил автоматического одобрения.

#### Параметры

Нет

#### Ответ

```json
{
  "rules": [
    {
      "index": 0,
      "tool": "add_tags",
      "conditions": {"max_count": 10}
    }
  ]
}
```

### POST /api/agent/auto-approve

Добавить правило автоматического одобрения.

#### Лимит частоты запросов

WRITE

#### Запрос

```json
{
  "tool": "add_tags",
  "conditions": {"max_count": 10}
}
```

| Параметр | Тип | Обязательно | Описание |
|-----------|------|----------|-------------|
| `tool` | string | Да | Имя целевого инструмента |
| `conditions` | object | Нет | Условия для автоматического одобрения. Опустить для безусловного одобрения |

#### Ответ

```json
{
  "ok": true,
  "rule": {
    "index": 1,
    "tool": "add_tags",
    "conditions": {"max_count": 10}
  }
}
```

#### Ошибки

- `400`: `tool` не указан
- `400`: `conditions` не является словарем

### DELETE /api/agent/auto-approve/\<index\>

Удалить правило автоматического одобрения.

#### Лимит частоты запросов

WRITE

#### Параметры

| Параметр | Тип | Описание |
|-----------|------|-------------|
| `index` | int | Индекс правила (параметр пути) |

#### Ответ

```json
{
  "ok": true
}
```

#### Ошибки

- `404`: Правило не найдено

---

## Классификация инструментов

### GET /api/agent/tool-levels

Получить информацию о классификации инструментов. Когда указан параметр `tool`, возвращает уровень для конкретного инструмента. Иначе возвращает сводку всех инструментов и любых переопределений.

#### Параметры

| Параметр | Тип | Обязательно | Описание |
|-----------|------|----------|-------------|
| `tool` | string | Нет | Имя инструмента. Если указано, возвращает только уровень этого инструмента |

#### Ответ (конкретный инструмент)

```json
{
  "tool": "purge_deleted",
  "level": "destructive"
}
```

#### Ответ (все инструменты)

```json
{
  "summary": {
    "safe": ["list_files", "search_files"],
    "write": ["add_tags", "remove_tags"],
    "destructive": ["purge_deleted", "hard_delete"]
  },
  "overrides": {
    "custom_tool": "safe"
  }
}
```

---

## Отмена

### POST /api/agent/undo/\<journal_id\>

Отменить записанное действие.

#### Лимит частоты запросов

WRITE

#### Параметры

| Параметр | Тип | Описание |
|-----------|------|-------------|
| `journal_id` | int | ID записи журнала (параметр пути) |

#### Ответ

```json
{
  "ok": true,
  "journal_id": 1,
  "undone_action": "add_tags"
}
```

#### Ошибки

- `400`: Отмена не удалась (действие не может быть отменено, уже отменено, и т.д.)

### GET /api/agent/undoable

Получить список действий, которые можно отменить.

#### Параметры

| Параметр | Тип | Обязательно | Описание |
|-----------|------|----------|-------------|
| `session_id` | string | Нет | Фильтр по ID сессии |
| `limit` | int | Нет | Макс результатов (по умолчанию: 50, макс: 200) |

#### Ответ

```json
{
  "items": [
    {
      "id": 1,
      "tool_name": "add_tags",
      "session_id": "abc123",
      "params": {"file_id": 42, "tags": ["landscape"]},
      "created_at": "2026-03-22T12:00:00"
    }
  ],
  "count": 1
}
```

---

## Обнаружение аномалий

### GET /api/agent/anomaly

Получить состояние Anomaly Detection.

#### Параметры

Нет

#### Ответ

```json
{
  "enabled": true,
  "window_minutes": 10,
  "thresholds": {
    "max_actions_per_window": 100,
    "max_errors_per_window": 20
  },
  "current": {
    "actions": 15,
    "errors": 0
  }
}
```

### GET /api/agent/anomaly/alerts

Получить оповещения Anomaly Detection.

#### Параметры

| Параметр | Тип | Обязательно | Описание |
|-----------|------|----------|-------------|
| `limit` | int | Нет | Макс результатов (по умолчанию: 50, макс: 200) |

#### Ответ

```json
{
  "alerts": [
    {
      "id": 1,
      "type": "high_error_rate",
      "message": "Error rate exceeded threshold",
      "severity": "warning",
      "created_at": "2026-03-22T12:00:00"
    }
  ]
}
```

### POST /api/agent/anomaly/reset

Сбросить историю и оповещения Anomaly Detection.

#### Лимит частоты запросов

WRITE

#### Запрос

Нет (пустое тело)

#### Ответ

```json
{
  "ok": true
}
```

---

## Audit Bureau

### GET /api/agent/audit

Получить состояние Audit Bureau.

#### Параметры

Нет

#### Ответ

```json
{
  "data": {
    "total_entries": 500,
    "unacknowledged": 3,
    "last_report_at": "2026-03-22T00:00:00"
  }
}
```

### GET /api/agent/audit/log

Поиск в Audit Log.

#### Параметры

| Параметр | Тип | Обязательно | Описание |
|-----------|------|----------|-------------|
| `event_type` | string | Нет | Фильтр по типу события |
| `severity` | string | Нет | Фильтр по серьезности |
| `source` | string | Нет | Фильтр по источнику |
| `unacknowledged` | string | Нет | Установить на `"1"` или `"true"` для возврата только неподтвержденных записей |
| `limit` | int | Нет | Макс результатов (по умолчанию: 50, макс: 200) |
| `offset` | int | Нет | Смещение (по умолчанию: 0) |

#### Ответ

```json
{
  "data": {
    "entries": [
      {
        "id": 1,
        "event_type": "kill_switch_activated",
        "severity": "critical",
        "source": "api",
        "message": "Kill switch activated: Manual kill via API",
        "acknowledged": false,
        "created_at": "2026-03-22T12:00:00"
      }
    ],
    "total": 1
  }
}
```

### POST /api/agent/audit/acknowledge/\<audit_id\>

Отметить запись audit log как подтвержденная пользователем.

#### Лимит частоты запросов

WRITE

#### Параметры

| Параметр | Тип | Описание |
|-----------|------|-------------|
| `audit_id` | int | ID записи audit log (параметр пути) |

#### Ответ

```json
{
  "ok": true,
  "audit_id": 1
}
```

#### Ошибки

- `404`: Запись не найдена или уже подтверждена

### POST /api/agent/audit/report

Вручную сгенерировать периодический отчет Audit Bureau.

#### Лимит частоты запросов

WRITE

#### Запрос

```json
{
  "hours": 24
}
```

| Параметр | Тип | Обязательно | Описание |
|-----------|------|----------|-------------|
| `hours` | int | Нет | Период отчета в часах. По умолчанию: 24, макс: 720 |

#### Ответ

```json
{
  "data": {
    "period_hours": 24,
    "total_events": 150,
    "by_severity": {"critical": 2, "warning": 10, "info": 138},
    "by_type": {"kill_switch_activated": 2, "approval_denied": 5},
    "generated_at": "2026-03-22T12:00:00"
  }
}
```
