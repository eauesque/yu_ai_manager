# API интеграции GitHub

API для управления учётной записью GitHub, проблемами, запросами на слияние, уведомлениями и релизами.

Предоставляется расширением `builtin-github`. Все конечные точки требуют аутентификации (сессия PIN или API Key).

## Управление учётной записью

### GET /api/github/accounts

Список зарегистрированных учётных записей GitHub. Токены маскируются в ответе.

### Response

```json
{
  "data": [
    {
      "label": "my-account",
      "token": "ghp_****...xxxx",
      "repos": ["owner/repo1", "owner/repo2"],
      "enabled": true
    }
  ]
}
```

### POST /api/github/accounts

Регистрация новой учётной записи GitHub.

### Request

```json
{
  "label": "my-account",
  "token": "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "repos": ["owner/repo1", "owner/repo2"]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `label` | string | Yes | Уникальный идентификатор учётной записи |
| `token` | string | Yes | GitHub Personal Access Token |
| `repos` | string[] | Yes | Репозитории для мониторинга (формат `owner/repo`) |

### Response

```json
{
  "data": { "label": "my-account", "status": "created" }
}
```

### PUT /api/github/accounts/<label>

Обновить параметры существующей учётной записи.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `label` | string | Метка учётной записи (параметр пути) |

### Request

```json
{
  "token": "ghp_new_token_value",
  "repos": ["owner/repo1", "owner/repo3"],
  "enabled": false
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `token` | string | No | Новое значение токена |
| `repos` | string[] | No | Обновленный список репозиториев |
| `enabled` | boolean | No | Включить или отключить учётную запись |

### DELETE /api/github/accounts/<label>

Удалить учётную запись.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `label` | string | Метка учётной записи (параметр пути) |

---

## Проблемы

### GET /api/github/issues/<label>

Получить проблемы из репозиториев учётной записи.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `label` | string | Метка учётной записи (параметр пути) |
| `state` | string | Фильтр состояния проблемы (`open`, `closed`, `all`) |
| `labels` | string | Фильтр по метке (разделённый запятыми) |
| `since` | string | Проблемы, обновлённые после этой даты (ISO 8601) |
| `repo` | string | Фильтр по конкретному репозиторию (`owner/repo`) |

### curl Example

```bash
curl -H "Authorization: Bearer sk_xxxxx" \
  "http://localhost:5000/api/github/issues/my-account?state=open&repo=owner/repo1"
```

### POST /api/github/issues/<label>

Создать новую проблему.

### Request

```json
{
  "repo": "owner/repo1",
  "title": "Bug: crash on login screen",
  "body": "Steps to reproduce:\n1. ...\n2. ...",
  "labels": ["bug", "priority:high"]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `repo` | string | Yes | Целевой репозиторий (`owner/repo`) |
| `title` | string | Yes | Название проблемы |
| `body` | string | No | Содержание проблемы (Markdown) |
| `labels` | string[] | No | Применяемые метки |

### GET /api/github/issue/<label>/<repo>/<number>

Получить детали проблемы, включая комментарии.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `label` | string | Метка учётной записи |
| `repo` | string | Имя репозитория (`owner/repo`) |
| `number` | int | Номер проблемы |

### POST /api/github/triage/<label>

Запустить сортировку проблем (классификация и приоритизация).

### Request

```json
{
  "state": "open",
  "since": "2026-03-01T00:00:00Z"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `state` | string | No | Фильтр состояния для целевых проблем |
| `since` | string | No | Сортировать только проблемы, обновлённые после этой даты (ISO 8601) |

---

## Запросы на слияние

### GET /api/github/pulls/<label>

Список запросов на слияние.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `label` | string | Метка учётной записи (параметр пути) |
| `state` | string | Состояние PR (`open`, `closed`, `all`) |
| `repo` | string | Фильтр по конкретному репозиторию (`owner/repo`) |

### GET /api/github/pull/<label>/<repo>/<number>

Получить детали PR, включая изменённые файлы.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `label` | string | Метка учётной записи |
| `repo` | string | Имя репозитория (`owner/repo`) |
| `number` | int | Номер PR |

---

## Уведомления

### GET /api/github/notifications/<label>

Список уведомлений.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `label` | string | Метка учётной записи (параметр пути) |
| `all` | string | Установить на `true` для включения прочитанных уведомлений (по умолчанию: только непрочитанные) |

### PATCH /api/github/notifications/<label>/<thread_id>

Отметить конкретную цепочку уведомлений как прочитанную.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `label` | string | Метка учётной записи |
| `thread_id` | string | ID цепочки уведомления |

### POST /api/github/notifications/<label>/mark-all-read

Отметить все уведомления как прочитанные.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `label` | string | Метка учётной записи (параметр пути) |

---

## Обсуждения

### GET /api/github/discussions/<label>

Получить GitHub Discussions (через GraphQL API).

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `label` | string | Метка учётной записи (параметр пути) |
| `repo` | string | Фильтр по конкретному репозиторию (`owner/repo`) |

---

## Релизы

### GET /api/github/releases/<label>

Список релизов.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `label` | string | Метка учётной записи (параметр пути) |
| `repo` | string | Фильтр по конкретному репозиторию (`owner/repo`) |

---

## Статистика репозитория

### GET /api/github/repo-stats/<label>/<repo>

Получить статистику для одного репозитория.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `label` | string | Метла учётной записи |
| `repo` | string | Имя репозитория (`owner/repo`) |

### GET /api/github/repo-stats-all/<label>

Получить статистику для всех зарегистрированных репозиториев одновременно.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `label` | string | Метла учётной записи (параметр пути) |

---

## Лимит скорости

### GET /api/github/rate-limit/<label>

Проверить статус лимита скорости API GitHub.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `label` | string | Метла учётной записи (параметр пути) |

### Response Example

```json
{
  "data": {
    "rate": {
      "limit": 5000,
      "remaining": 4832,
      "reset": 1710500000
    }
  }
}
```

---

## Подсказки сортировки

### GET /api/github/triage-prompts

Получить редактируемые подсказки сортировки для проблемы/PR/обсуждения вместе с их значениями по умолчанию.

### Response

```json
{
  "data": {
    "prompts": {
      "issue": "Review the following GitHub issue...",
      "pr": "Do not accept pull requests. Close automatically.",
      "discussion": "Discussions are closed. No action required."
    },
    "defaults": {
      "issue": "Review the following GitHub issue...",
      "pr": "Do not accept pull requests. Close automatically.",
      "discussion": "Discussions are closed. No action required."
    }
  }
}
```

### PUT /api/github/triage-prompts

Обновить подсказки сортировки. Обновляются только предоставленные поля.

### Request

```json
{
  "issue": "Custom issue triage prompt...",
  "pr": "Custom PR prompt...",
  "discussion": "Custom discussion prompt..."
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `issue` | string | No | Подсказка сортировки для проблем |
| `pr` | string | No | Подсказка сортировки для запросов на слияние |
| `discussion` | string | No | Подсказка сортировки для обсуждений |

---

## Очередь проблем

### GET /api/github/queue

Получить элементы очереди проблем с опциональным фильтром состояния.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `status` | string | Фильтр: `pending`, `notified`, `dismissed`, или пусто для всех |
| `limit` | int | Максимум результатов (по умолчанию 50, максимум 200) |

### Response

```json
{
  "data": {
    "items": [
      {
        "id": 1,
        "repo": "owner/repo",
        "issue_number": 42,
        "title": "Bug report title",
        "body": "Issue body...",
        "created_at": "2026-03-15T10:00:00Z",
        "fetched_at": "2026-03-15T12:00:00Z",
        "status": "pending",
        "triage_result": "pending"
      }
    ],
    "stats": { "pending": 3, "notified": 1, "dismissed": 5, "total": 9 }
  }
}
```

### GET /api/github/queue/pending

Получить ожидающие (непрочитанные) проблемы для MCP уведомления.

### Response

```json
{
  "data": {
    "items": [...],
    "count": 3
  }
}
```

### POST /api/github/queue/<queue_id>/triage

Установить результат сортировки для элемента очереди.

### Request

```json
{ "result": "valid" }
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `result` | string | Yes | `valid` или `invalid` |

### POST /api/github/queue/<queue_id>/dismiss

Отклонить элемент очереди. Опционально автоматически закрыть проблему на GitHub.

### Request

```json
{
  "auto_close": true,
  "account_label": "my-account"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `auto_close` | boolean | No | Закрыть проблему на GitHub с комментарием-шаблоном |
| `account_label` | string | No | Требуется, если `auto_close` = true |

### PUT /api/github/queue/<queue_id>/status

Обновить статус элемента очереди.

### Request

```json
{ "status": "notified" }
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `status` | string | Yes | `pending`, `notified`, или `dismissed` |

### GET /api/github/queue/config

Получить конфигурацию очереди проблем.

### Response

```json
{
  "data": {
    "poll_interval_minutes": 60,
    "auto_close_invalid": false,
    "notify_on_connect": true
  }
}
```

### PUT /api/github/queue/config

Обновить конфигурацию очереди проблем.

### Request

```json
{
  "poll_interval_minutes": 30,
  "auto_close_invalid": true,
  "notify_on_connect": true
}
```

### POST /api/github/queue/poll

Запустить немедленное опрашивание всех учётных записей на предмет новых проблем.

---

## WebUI

### GET /ext/github

GitHub Integration WebUI страница. Доступ напрямую в браузер.

Требуется аутентифицированная сессия PIN.
