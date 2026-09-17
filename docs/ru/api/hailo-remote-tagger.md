# API удаленного теггера Hailo

API для отправки изображений на удаленный сервер вывода Hailo AI HAT (например, Raspberry Pi 5) по сети, запуска логического вывода тегов Danbooru и сохранения результатов в базу данных.

## Обзор

Даже без локального GPU или среды выполнения ONNX вы можете использовать устройство Hailo-10H в вашей локальной сети в качестве удаленного теггера. Изображения отправляются как multipart/form-data, а JSON тегов возвращается в качестве ответа.

---

## GET /api/hailo-tagger/config

Получить текущую конфигурацию.

### Ограничение частоты запросов

READ (неограниченно)

### Ответ

```json
{
  "ok": true,
  "data": {
    "config": {
      "enabled": false,
      "endpoint_url": "",
      "threshold": 0.35,
      "timeout": 30
    }
  }
}
```

| Поле | Тип | Описание |
|-------|------|-------------|
| `enabled` | bool | Включен ли удаленный теггер Hailo |
| `endpoint_url` | string | URL конечной точки Pi (например `http://192.168.1.50:8080`) |
| `threshold` | float | Порог уверенности теега (сохраняются только теги выше этого значения) |
| `timeout` | int | Временное ограничение запроса в секундах |

---

## POST /api/hailo-tagger/config

Сохранить конфигурацию. Поддерживаются частичные обновления (изменяются только указанные поля).

### Ограничение частоты запросов

DESTRUCTIVE (~12 req/min, burst 3)

### Тело запроса

| Поле | Тип | Требуется | Описание |
|-------|------|----------|-------------|
| `enabled` | bool | Нет | Включить/отключить |
| `endpoint_url` | string | Нет | URL конечной точки Pi |
| `threshold` | float | Нет | Порог уверенности теега |
| `timeout` | int | Нет | Временное ограничение запроса (секунды) |

### Пример запроса

```json
{
  "enabled": true,
  "endpoint_url": "http://192.168.1.50:8080",
  "threshold": 0.35
}
```

### Ответ

```json
{
  "ok": true,
  "data": {
    "config": {
      "enabled": true,
      "endpoint_url": "http://192.168.1.50:8080",
      "threshold": 0.35,
      "timeout": 30
    }
  }
}
```

### Ошибки

| Статус | Описание |
|--------|-------------|
| 400 | Неверный JSON объект |

---

## GET /api/hailo-tagger/status

Проверить соединение с конечной точкой Hailo. Отправляет GET запрос на конечную точку `/health` для проверки доступности.

### Ограничение частоты запросов

READ (неограниченно)

### Ответ (успех)

```json
{
  "ok": true,
  "data": {
    "enabled": true,
    "reachable": true,
    "endpoint_url": "http://192.168.1.50:8080"
  }
}
```

### Ответ (не настроена / недостижима)

```json
{
  "ok": true,
  "data": {
    "enabled": true,
    "reachable": false,
    "reason": "Connection refused",
    "endpoint_url": "http://192.168.1.50:8080"
  }
}
```

---

## POST /api/hailo-tagger/tag/{file_id}

Теггировать один файл.

### Ограничение частоты запросов

HEAVY (~20 req/min, burst 5)

### Параметры пути

| Параметр | Тип | Описание |
|-----------|------|-------------|
| `file_id` | int | ID целевого файла в базе данных |

### Тело запроса

| Поле | Тип | Требуется | Описание |
|-------|------|----------|-------------|
| `force` | bool | Нет | Перезаписать существующие теги (по умолчанию: `false`) |

### Ответ

```json
{
  "ok": true,
  "data": {
    "file_id": 42,
    "filepath": "/images/test.png",
    "tag_count": 15,
    "tags": [
      {"tag": "1girl", "confidence": 0.95},
      {"tag": "solo", "confidence": 0.88}
    ]
  }
}
```

### Ошибки

| Статус | Код | Описание |
|--------|------|-------------|
| 400 | `disabled` | Теггер Hailo отключен |
| 400 | `not_configured` | URL конечной точки не настроен |
| 400 | `file_not_found` | Файл не найден в базе данных |
| 400 | `file_missing` | Файл не существует на диске |
| 400 | `unsupported_type` | Тип файла не поддерживается для теггирования |
| 502 | `request_failed` | Не удалось подключиться к удаленному серверу |

---

## POST /api/hailo-tagger/batch

Теггировать несколько файлов в пакете. Запускается как фоновая задача.

### Ограничение частоты запросов

HEAVY (~20 req/min, burst 5)

### Тело запроса

| Поле | Тип | Требуется | Описание |
|-------|------|----------|-------------|
| `file_ids` | int[] | Нет | Список целевых ID файлов (максимум 500). Автоматически выбирает неотеггированные файлы, если опущено |
| `limit` | int | Нет | Максимум файлов для автоматического выбора (по умолчанию: 100) |
| `force` | bool | Нет | Перезаписать существующие теги (по умолчанию: `false`) |

### Пример запроса

```json
{
  "file_ids": [1, 2, 3, 4, 5],
  "force": false
}
```

### Ответ

```json
{
  "ok": true,
  "data": {
    "started": true,
    "job_id": "hailo_tagger"
  }
}
```

### Ошибки

| Статус | Код | Описание |
|--------|------|-------------|
| 400 | `batch_too_large` | file_ids превышает 500 |
| 409 | `job_running` | Пакетная задача уже запущена |

---

## GET /api/hailo-tagger/tags/{file_id}

Получить теги Hailo для файла.

### Ограничение частоты запросов

READ (неограниченно)

### Ответ

```json
{
  "ok": true,
  "data": {
    "file_id": 42,
    "tags": [
      {"tag_name": "1girl", "confidence": 0.95, "source": "hailo_remote", "created_at": 1710720000},
      {"tag_name": "solo", "confidence": 0.88, "source": "hailo_remote", "created_at": 1710720000}
    ]
  }
}
```

---

## DELETE /api/hailo-tagger/tags/{file_id}

Удалить все теги Hailo для файла.

### Ограничение частоты запросов

DESTRUCTIVE (~12 req/min, burst 3)

### Ответ

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

## Схема БД

Теги Hailo хранятся в отдельной таблице `file_hailo_tags` (независимо от `file_wd_tags`).

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

| Столбец | Описание |
|--------|-------------|
| `file_id` | Внешний ключ к таблице files |
| `tag_name` | Имя теета Danbooru (например `1girl`, `solo`) |
| `confidence` | Уверенность логического вывода (0.0-1.0) |
| `source` | Идентификатор источника теага (`hailo_remote` или `hailo_remote:<server_id>` при использовании реестра) |
| `created_at` | UNIX временная метка |

---

## Конфигурация

Секция `hailo_tagger` в `config.json`:

```json
{
  "hailo_tagger": {
    "enabled": true,
    "endpoint_url": "http://192.168.1.50:8080",
    "threshold": 0.35,
    "timeout": 30
  }
}
```

Также можно изменить на странице Параметры.

> **Примечание**: Для управления несколькими серверами теггеров используйте [API реестра серверов теггеров](tagger-servers.md). Устаревшую конфигурацию можно автоматически перенести через `/api/tagger-servers/migrate`. Реестр серверов теггеров также поддерживает аутентификацию с помощью маркера Bearer.
