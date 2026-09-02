# Tagger Server Registry API

API для управления несколькими рабочими потоками вывода тегов (Hailo Remote, ONNX Local, Ryzen AI и т.д.) как единого кластера, с распределенной пакетной теговкой через модель параллельного выполнения с работой-кража из общей очереди.

## Overview

Реестр Tagger Server выходит за пределы одного удаленного теггера Hailo путем управления несколькими разнородными бэкендами вывода как кластером. Каждый сервер имеет настраиваемый приоритет, и задачи распределяются в соответствии с выбранным режимом распределения (single / parallel / idle_first).

### Architecture

```
┌─────────────────────────────────────────────────────┐
│                   eauesque Host                      │
│  ┌──────────────────────────────────────────────┐   │
│  │         Tagger Orchestrator                  │   │
│  │  - Shared queue (work-stealing)              │   │
│  │  - Progress aggregation -> JobManager -> SSE │   │
│  └──────────┬──────────────┬──────────────────┘   │
│    ┌────────▼───┐   ┌──────▼────────────┐          │
│    │ Local ONNX │   │ Hailo HTTP Client │          │
│    │ Worker     │   │ Worker            │          │
│    └────────────┘   └──────────┬────────┘          │
└────────────────────────────────│────────────────────┘
              ┌──────────────────┼──────────────────┐
     ┌────────▼───┐    ┌────────▼───┐    ┌────────▼───┐
     │ Pi A       │    │ Pi B       │    │ Future     │
     │ Hailo 10H  │    │ Hailo 10H  │    │ NPU Server │
     └────────────┘    └────────────┘    └────────────┘
```

### Server Types

| Type | Description |
|------|-------------|
| `hailo_remote` | Удаленное устройство Hailo-10H (например Raspberry Pi 5) |
| `onnx_local` | Локальный ONNX Runtime вывод |
| `onnx_remote` | Удаленный сервер вывода ONNX |
| `ryzen_ai` | AMD Ryzen AI NPU |

### Distribution Modes

| Mode | Description |
|------|-------------|
| `single` | Использовать только сервер с наивысшим приоритетом |
| `parallel` | Запускать на всех включенных серверах параллельно (work-stealing) |
| `idle_first` | Предпочитать неиспользуемые серверы в первую очередь |

---

## Server Entry Format

```json
{
  "id": "pi-hailo-a",
  "name": "Pi5 Hailo A",
  "type": "hailo_remote",
  "priority": 10,
  "enabled": true,
  "config": {
    "endpoint_url": "http://192.168.1.101:8080",
    "bearer_token": "enc:gAAAAABm...",
    "threshold": 0.35,
    "timeout": 30
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Идентификатор сервера (автогенерируемый или вручную указанный) |
| `name` | string | Отображаемое имя |
| `type` | string | Тип сервера (`hailo_remote` / `onnx_local` / `onnx_remote` / `ryzen_ai`) |
| `priority` | int | Приоритет (ниже = выше приоритет, по умолчанию: 50) |
| `enabled` | bool | Включено/отключено |
| `config` | object | Конфигурация для конкретного типа (см. ниже) |

### config Fields (for remote servers)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `endpoint_url` | string | Yes | URL удаленного сервера |
| `bearer_token` | string | No | Bearer токен (автоматически зашифрован с префиксом `enc:` при сохранении) |
| `threshold` | float | No | Порог доверия тега (по умолчанию: 0.35) |
| `timeout` | int | No | Timeout запроса в секундах (по умолчанию: 30) |

---

## Authentication

Взаимодействие с удаленными серверами (`hailo_remote` / `onnx_remote`) поддерживает опциональную аутентификацию Bearer токена.

### Host → Remote Server

Когда установлен `config.bearer_token`, все HTTP запросы (проверки здоровья и теговка) автоматически включают заголовок `Authorization: Bearer <token>`. Токены хранятся в `config.json` с Fernet шифрованием (префикс `enc:`) и замаскированы в ответах API.

### Remote Server Side

`deploy/hailo_tagger_server.py` предоставляет эталонную реализацию с проверкой токена. Установите токен при запуске любым из способов:

```bash
# Command line argument
python hailo_tagger_server.py --token "my-secret-token"

# Read from file
python hailo_tagger_server.py --token-file /etc/tagger/token

# Environment variable
TAGGER_BEARER_TOKEN=my-secret-token python hailo_tagger_server.py
```

Когда токен не сконфигурирован, сервер работает в режиме открытого доступа (модель доверия LAN) для обратной совместимости. Неверные токены получают ответы 401/403.

---

## GET /api/tagger-servers

Список зарегистрированных серверов и текущий режим распределения.

### Rate Limit

READ (unlimited)

### Response

```json
{
  "ok": true,
  "data": {
    "servers": [
      {
        "id": "pi-hailo-a",
        "name": "Pi5 Hailo A",
        "type": "hailo_remote",
        "priority": 10,
        "enabled": true,
        "config": {
          "endpoint_url": "http://192.168.1.101:8080",
          "threshold": 0.35,
          "timeout": 30
        }
      }
    ],
    "mode": "parallel"
  }
}
```

---

## POST /api/tagger-servers

Добавить новый сервер теговки.

### Rate Limit

DESTRUCTIVE (~12 req/min, burst 3)

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Отображаемое имя |
| `type` | string | Yes | Тип сервера |
| `config` | object | Yes | Конфигурация для конкретного типа |
| `priority` | int | No | Приоритет (по умолчанию: 50) |
| `enabled` | bool | No | Включено/отключено (по умолчанию: `true`) |

### Request Example

```json
{
  "name": "Pi5 Hailo A",
  "type": "hailo_remote",
  "config": {
    "endpoint_url": "http://192.168.1.101:8080",
    "threshold": 0.35,
    "timeout": 30
  },
  "priority": 10
}
```

### Response

```json
{
  "ok": true,
  "data": {
    "server": {
      "id": "pi-hailo-a",
      "name": "Pi5 Hailo A",
      "type": "hailo_remote",
      "priority": 10,
      "enabled": true,
      "config": {
        "endpoint_url": "http://192.168.1.101:8080",
        "threshold": 0.35,
        "timeout": 30
      }
    }
  }
}
```

### Errors

| Status | Description |
|--------|-------------|
| 400 | Отсутствуют обязательные поля или неверный тип |

---

## PUT /api/tagger-servers/{server_id}

Обновить параметры существующего сервера. Поддерживаются частичные обновления.

### Rate Limit

DESTRUCTIVE (~12 req/min, burst 3)

### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `server_id` | string | ID целевого сервера |

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | No | Отображаемое имя |
| `type` | string | No | Тип сервера |
| `config` | object | No | Конфигурация для конкретного типа |
| `priority` | int | No | Приоритет |
| `enabled` | bool | No | Включено/отключено |

### Response

```json
{
  "ok": true,
  "data": {
    "server": { "..." }
  }
}
```

### Errors

| Status | Description |
|--------|-------------|
| 404 | Сервер не найден |

---

## DELETE /api/tagger-servers/{server_id}

Удалить сервер.

### Rate Limit

DESTRUCTIVE (~12 req/min, burst 3)

### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `server_id` | string | ID целевого сервера |

### Response

```json
{
  "ok": true,
  "data": {
    "deleted": "pi-hailo-a"
  }
}
```

### Errors

| Status | Description |
|--------|-------------|
| 404 | Сервер не найден |

---

## POST /api/tagger-servers/reorder

Переупорядочить приоритеты серверов в пакетном режиме.

### Rate Limit

DESTRUCTIVE (~12 req/min, burst 3)

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `order` | string[] | Yes | Массив ID серверов в порядке приоритета |

### Request Example

```json
{
  "order": ["pi-hailo-a", "local-onnx", "pi-hailo-b"]
}
```

### Response

```json
{
  "ok": true,
  "data": {
    "servers": [ "..." ]
  }
}
```

---

## POST /api/tagger-servers/mode

Изменить режим распределения.

### Rate Limit

DESTRUCTIVE (~12 req/min, burst 3)

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `mode` | string | Yes | `single` / `parallel` / `idle_first` |

### Response

```json
{
  "ok": true,
  "data": {
    "mode": "parallel"
  }
}
```

### Errors

| Status | Description |
|--------|-------------|
| 400 | Неверное значение режима |

---

## POST /api/tagger-servers/{server_id}/test

Проверить подключение к конкретному серверу.

### Rate Limit

HEAVY (~20 req/min, burst 5)

### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `server_id` | string | ID целевого сервера |

### Response (success)

```json
{
  "ok": true,
  "data": {
    "server_id": "pi-hailo-a",
    "reachable": true,
    "latency_ms": 45
  }
}
```

### Response (unreachable)

```json
{
  "ok": true,
  "data": {
    "server_id": "pi-hailo-a",
    "reachable": false,
    "reason": "Connection refused"
  }
}
```

### Errors

| Status | Description |
|--------|-------------|
| 404 | Сервер не найден |

---

## GET /api/tagger-servers/health

Проверка здоровья всех включенных серверов.

### Rate Limit

READ (unlimited)

### Response

```json
{
  "ok": true,
  "data": {
    "results": [
      {
        "server_id": "pi-hailo-a",
        "name": "Pi5 Hailo A",
        "type": "hailo_remote",
        "reachable": true,
        "latency_ms": 45
      },
      {
        "server_id": "local-onnx",
        "name": "Local ONNX",
        "type": "onnx_local",
        "reachable": true,
        "latency_ms": 2
      }
    ]
  }
}
```

---

## POST /api/tagger-servers/batch

Выполнить распределенную пакетную теговку с использованием модели work-stealing из общей очереди. Выполняется как фоновая задача с ходом выполнения, сообщаемым через SSE.

### Rate Limit

HEAVY (~20 req/min, burst 5)

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file_ids` | int[] | No | Список целевых ID файлов. Автоматически выбирает файлы без тегов, если опущено |
| `limit` | int | No | Максимум файлов для автоматического выбора (по умолчанию: 500) |
| `force` | bool | No | Перезаписать существующие теги (по умолчанию: `false`) |
| `threshold` | float | No | Переопределить порог доверия тега (использует конфигурацию сервера, если опущено) |

### Request Example

```json
{
  "file_ids": [1, 2, 3, 4, 5],
  "force": false,
  "threshold": 0.35
}
```

### Response

```json
{
  "ok": true,
  "data": {
    "started": true,
    "job_id": "tagger_servers_batch",
    "total_files": 5,
    "active_servers": ["pi-hailo-a", "local-onnx"]
  }
}
```

### Errors

| Status | Code | Description |
|--------|------|-------------|
| 400 | `no_servers` | Нет доступных включенных серверов |
| 400 | `batch_too_large` | file_ids превышает лимит |
| 409 | `job_running` | Пакетная задача уже запущена |

---

## POST /api/tagger-servers/batch/cancel

Отменить запущенную пакетную задачу кластера теговки.

### Response

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | `"cancelling"` |
| `message` | string | Сообщение о статусе |

### Error Codes

| Status | Code | Description |
|--------|------|-------------|
| 404 | `job_not_running` | Нет запущенной пакетной задачи для отмены |

---

## GET /api/tagger-servers/tags/{file_id}

Получить теги теговки для файла.

### Rate Limit

READ (unlimited)

### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `file_id` | int | ID файла в базе данных |

### Response

```json
{
  "ok": true,
  "data": {
    "file_id": 42,
    "tags": [
      {"tag_name": "1girl", "confidence": 0.95, "source": "hailo_remote:pi-hailo-a", "created_at": 1710720000},
      {"tag_name": "solo", "confidence": 0.88, "source": "hailo_remote:pi-hailo-a", "created_at": 1710720000}
    ]
  }
}
```

Поле `source` использует формат `{type}:{server_id}` (например `hailo_remote:pi-hailo-a`, `onnx_local:local-onnx`).

---

## DELETE /api/tagger-servers/tags/{file_id}

Удалить все теги теговки для файла.

### Rate Limit

DESTRUCTIVE (~12 req/min, burst 3)

### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `file_id` | int | ID файла в базе данных |

### Response

```json
{
  "ok": true,
  "data": {
    "file_id": 42,
    "deleted": 15
  }
}
```

---

## GET /api/tagger-servers/stats

Получить статистику теговки.

### Rate Limit

READ (unlimited)

### Response

```json
{
  "ok": true,
  "data": {
    "total_files": 10000,
    "tagged_files": 8500,
    "untagged_files": 1500,
    "servers": {
      "pi-hailo-a": {"tagged": 5000, "type": "hailo_remote"},
      "local-onnx": {"tagged": 3500, "type": "onnx_local"}
    }
  }
}
```

---

## POST /api/tagger-servers/migrate

Мигрировать конфигурацию старого `hailo_tagger` в формат Tagger Server Registry. Преобразует существующую запись `hailo_tagger` в `config.json` в запись массива `tagger_servers`.

### Rate Limit

DESTRUCTIVE (~12 req/min, burst 3)

### Response

```json
{
  "ok": true,
  "data": {
    "migrated": true,
    "server": {
      "id": "legacy-hailo",
      "name": "Hailo Remote (migrated)",
      "type": "hailo_remote",
      "priority": 50,
      "enabled": true,
      "config": {
        "endpoint_url": "http://192.168.1.50:8080",
        "threshold": 0.35,
        "timeout": 30
      }
    }
  }
}
```

### Response (no migration needed)

```json
{
  "ok": true,
  "data": {
    "migrated": false,
    "reason": "No legacy config found"
  }
}
```

---

## Configuration

Связанные ключи в `config.json`:

```json
{
  "tagger_servers": [
    {
      "id": "pi-hailo-a",
      "name": "Pi5 Hailo A",
      "type": "hailo_remote",
      "priority": 10,
      "enabled": true,
      "config": {
        "endpoint_url": "http://192.168.1.101:8080",
        "bearer_token": "enc:gAAAAABm...",
        "threshold": 0.35,
        "timeout": 30
      }
    },
    {
      "id": "local-onnx",
      "name": "Local ONNX",
      "type": "onnx_local",
      "priority": 20,
      "enabled": true,
      "config": {
        "threshold": 0.35
      }
    }
  ],
  "tagger_servers_mode": "parallel"
}
```

| Key | Type | Description |
|-----|------|-------------|
| `tagger_servers` | array | Массив записей сервера |
| `tagger_servers_mode` | string | Режим распределения (`single` / `parallel` / `idle_first`) |

Также может быть изменено со страницы Settings.

---

## DB Schema

Теги хранятся в таблице `file_hailo_tags`. Столбец `source` использует формат `{type}:{server_id}` для идентификации сервера, который присвоил тег.

```sql
CREATE TABLE file_hailo_tags (
    id         INTEGER PRIMARY KEY,
    file_id    INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    tag_name   TEXT NOT NULL,
    confidence REAL NOT NULL,
    source     TEXT NOT NULL DEFAULT 'hailo_remote',
    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    UNIQUE(file_id, tag_name)
);
```

| Column | Description |
|--------|-------------|
| `file_id` | Внешний ключ к таблице files |
| `tag_name` | Название тега Danbooru (например `1girl`, `solo`) |
| `confidence` | Доверие вывода (0.0-1.0) |
| `source` | Идентификатор источника тега (формат `{type}:{server_id}`, например `hailo_remote:pi-hailo-a`) |
| `created_at` | UNIX timestamp |
