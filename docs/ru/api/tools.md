# API Инструментов

Утилиты API для обнаружения дубликатов, вычисления хешей, поиска похожих изображений, управления кэшем, выбора папки, резервной копии БД, очистки архивов и логирования отладки.

---

## Дубликаты / Хеши / Сканирование

### GET /api/tools/find-duplicates

Обнаружить файлы-дубликаты на основе хеша файла или имени файла.

#### Лимит частоты запросов

HEAVY

#### Параметры

| Параметр | Тип | По умолчанию | Описание |
|-----------|------|---------|-------------|
| `cross_directory` | string | `"false"` | Установить на `"true"` для обнаружения дубликатов в разных каталогах |
| `method` | string | `"hash"` | Метод обнаружения: `"hash"` или `"name"` |
| `threshold` | int | `5` | Порог сходства |

#### Ответ

```json
{
  "groups": [
    {
      "hash": "abc123...",
      "files": [
        { "id": 1, "path": "/images/photo.png", "filename": "photo.png" },
        { "id": 2, "path": "/backup/photo.png", "filename": "photo.png" }
      ]
    }
  ],
  "total_groups": 1,
  "total_duplicates": 2
}
```

### POST /api/tools/compute-hashes

Начать фоновое вычисление хешей для файлов без хешей.

#### Лимит частоты запросов

HEAVY

#### Запрос

```json
{
  "type": "both",
  "limit": 5000
}
```

| Параметр | Тип | По умолчанию | Описание |
|-----------|------|---------|-------------|
| `type` | string | `"both"` | Тип хеша: `"md5"`, `"sha256"`, или `"both"` |
| `limit` | int | `5000` | Максимальное количество файлов для обработки |

#### Ответ

```json
{
  "started": true,
  "type": "both",
  "limit": 5000
}
```

### POST /api/tools/delete-duplicates

Удалить указанные файлы из групп дубликатов.

#### Лимит частоты запросов

DESTRUCTIVE

#### Запрос

```json
{
  "groups": [
    {
      "keep": 1,
      "delete": [2, 3]
    }
  ],
  "mode": "soft"
}
```

| Параметр | Тип | По умолчанию | Описание |
|-----------|------|---------|-------------|
| `groups` | array | Обязательно | Цели удаления. `keep` = ID файла для сохранения, `delete` = массив ID файлов для удаления |
| `mode` | string | `"soft"` | `"soft"` = логическое удаление, `"hard"` = физическое удаление |

#### Ответ

```json
{
  "deleted": 2,
  "errors": []
}
```

### GET /api/tools/normalize-tags

Нормализировать теги (объединить дубликаты, обрезать пробелы и т.д.).

#### Параметры

| Параметр | Тип | По умолчанию | Описание |
|-----------|------|---------|-------------|
| `dry_run` | string | `"false"` | Установить на `"true"` для предварительного просмотра изменений без применения |

#### Ответ

```json
{
  "normalized": 15,
  "removed": 3,
  "dry_run": false
}
```

### GET /api/tools/find-similar

Найти изображения, похожие на указанный файл (на основе хеша).

#### Лимит частоты запросов

HEAVY

#### Параметры

| Параметр | Тип | Обязательно | Описание |
|-----------|------|----------|-------------|
| `file_id` | int | Да | ID файла-ссылки |
| `threshold` | int | Нет | Порог сходства (1-20, по умолчанию `5`) |

#### Ответ

```json
{
  "file_id": 42,
  "threshold": 5,
  "results": [
    {
      "id": 43,
      "filename": "similar.png",
      "distance": 3
    }
  ],
  "count": 1
}
```

#### Ошибки

- `400` — `file_id` отсутствует или неправильный
- `404` — Указанный файл не найден

### POST /api/tools/scan

Сканировать файлы в каталоге и зарегистрировать их в базе данных.

#### Лимит частоты запросов

HEAVY

#### Запрос

```json
{
  "path": "/path/to/images",
  "recursive": true,
  "scan_zips": false,
  "compute_hash": false
}
```

| Параметр | Тип | По умолчанию | Описание |
|-----------|------|---------|-------------|
| `path` | string | Обязательно | Путь каталога для сканирования |
| `recursive` | bool | `true` | Рекурсивное сканирование подкаталогов |
| `scan_zips` | bool | `false` | Также сканировать внутри ZIP архивов |
| `compute_hash` | bool | `false` | Вычислять хеши файлов во время сканирования |

#### Ответ

```json
{
  "scanned": 150,
  "new": 42,
  "updated": 5,
  "errors": []
}
```

---

## Поиск файлов / Проверка метаданных

### GET /api/tools/file-search

Поиск файлов в базе данных по ключевому слову.

#### Параметры

| Параметр | Тип | По умолчанию | Описание |
|-----------|------|---------|-------------|
| `q` / `query` | string | `""` | Поисковое слово |
| `meta` / `meta_filter` | string | `"all"` | Фильтр по источнику метаданных (`"all"`, `"a1111_png"`, `"novelai_v4_png"`, и т.д.) |
| `limit` / `n` / `page_size` | int | `100` | Количество результатов (1-500) |

#### Ответ

```json
{
  "results": [
    {
      "id": 1,
      "filename": "image.png",
      "path": "/images/image.png"
    }
  ],
  "count": 1
}
```

### POST /api/inspect

Проверить метаданные загруженного файла. Извлекает метаданные без регистрации файла в базе данных.

#### Лимит частоты запросов

WRITE

#### Запрос

`multipart/form-data`:

| Поле | Тип | Обязательно | Описание |
|-------|------|----------|-------------|
| `file` | file | Да | Файл для проверки |
| `zip_entry` | string | Нет | Путь внутри ZIP архива (для ZIP файлов) |

#### Ответ

```json
{
  "filename": "image.png",
  "meta_source": "novelai_v4_png",
  "positive": "1girl, landscape",
  "negative": "bad anatomy",
  "parameters": { ... }
}
```

#### Ошибки

- `400` — Файл не загружен

---

## Выбор папки / Список каталогов

### GET /api/tools/select-folder

Открыть диалоговое окно выбора папки ОС. **Доступно только с localhost.**

#### Параметры

| Параметр | Тип | Описание |
|-----------|------|-------------|
| `initial` / `path` / `dir` | string | Начальный каталог для диалога |

#### Ответ

```json
{
  "path": "C:\\Users\\user\\Pictures",
  "cancelled": false
}
```

При удаленном доступе:

```json
{
  "path": null,
  "error": "remote_client_no_gui",
  "cancelled": false,
  "message": "Native folder dialog is not available for remote access. Please use the server folder browser."
}
```

### GET /api/tools/list-dirs

Список каталогов на сервере. **Доступно только с localhost.**

#### Параметры

| Параметр | Тип | Описание |
|-----------|------|-------------|
| `path` / `dir` / `initial` | string | Каталог для списка. Пусто возвращает корневые каталоги |

#### Ответ

```json
{
  "current": "C:\\Users",
  "parent": "C:\\",
  "dirs": ["user1", "Public"],
  "roots": ["C:\\", "D:\\"]
}
```

#### Ошибки

- `403` — Удаленный доступ

---

## Управление кэшем

### GET /api/tools/cache-info

Получить статус кэша миниатюр.

#### Ответ

```json
{
  "count": 1234,
  "size_mb": 56.7
}
```

### POST /api/tools/clear-cache

Очистить весь кэш миниатюр.

#### Лимит частоты запросов

DESTRUCTIVE

#### Ответ

```json
{
  "cleared": 1234
}
```

### POST /api/tools/rebuild-groups

Принудительное перестроение индекса кэша групп.

#### Лимит частоты запросов

DESTRUCTIVE

#### Ответ

```json
{
  "status": "rebuilt",
  "folders": 42,
  "zips": 5,
  "file_count": 1500
}
```

### POST /api/tools/faststart-prescan

Предварительно сгенерировать кэш faststart для всех MP4/MOV файлов в фоне. Возвращает 202 сразу же.

#### Лимит частоты запросов

WRITE

#### Ответ (202)

```json
{
  "ok": true,
  "started": true,
  "message": "faststart prescan started"
}
```

При уже запущенном (200):

```json
{
  "ok": true,
  "started": false,
  "message": "already running"
}
```

---

## Настройки

### GET /api/settings/config

Получить текущую конфигурацию объединенную со значениями по умолчанию.

#### Ответ

```json
{
  "port": 5000,
  "pin": "",
  "scan_roots": [],
  "theme": "dark",
  "backup": {
    "enabled": true,
    "periodic_interval_hours": 24
  }
}
```

### POST /api/settings/config

Частичное обновление настроек. Глубокое объединение применяется к существующим вложенным объектам.

#### Лимит частоты запросов

DESTRUCTIVE

#### Запрос

```json
{
  "theme": "light",
  "backup": {
    "enabled": false
  }
}
```

#### Ответ

```json
{
  "status": "saved"
}
```

#### Ошибки

- `400` — Пустые данные

---

## Резервная копия / Восстановление БД

### GET /api/tools/backup-download

Скачать файл базы данных напрямую. **Доступно только с localhost.**

#### Ответ

- Content-Type: `application/x-sqlite3`
- Content-Disposition: `attachment; filename="tags_backup_20260322_120000.db"`
- Возвращает 404 если база данных не найдена

### POST /api/tools/restore

Восстановить базу данных путем загрузки файла `.db`. **Доступно только с localhost.** Автоматически создает резервную копию существующей базы данных перед восстановлением.

#### Лимит частоты запросов

WRITE

#### Запрос

`multipart/form-data`:

| Поле | Тип | Обязательно | Описание |
|-------|------|----------|-------------|
| `file` | file | Да | SQLite файл с расширением `.db` |

#### Валидация

- Проверяет волшебные байты SQLite
- Проверяет наличие таблицы `files`
- Отклоняет базы данных содержащие триггеры или представления

#### Ответ

```json
{
  "success": true,
  "message": "Database restored successfully",
  "backup": "tags.db.backup_1711100000"
}
```

#### Ошибки

- `400` — Файл не загружен, неправильное расширение, или неправильный SQLite
- `403` — Удаленный доступ
- `500` — Ошибка резервной копии или восстановления

### POST /api/tools/backup/create

Вручную создать управляемую резервную копию. **Доступно только с localhost.**

#### Лимит частоты запросов

DESTRUCTIVE

#### Ответ

```json
{
  "success": true,
  "filename": "tags_backup_20260322_120000.db",
  "reason": "manual"
}
```

### GET /api/tools/backup/list

Список доступных резервных копий.

#### Ответ

```json
{
  "backups": [
    {
      "filename": "tags_backup_20260322_120000.db",
      "size": 1048576,
      "created": "2026-03-22T12:00:00"
    }
  ],
  "count": 1
}
```

### POST /api/tools/backup/restore

Восстановить базу данных из именованной резервной копии. **Доступно только с localhost.**

#### Лимит частоты запросов

DESTRUCTIVE

#### Запрос

```json
{
  "filename": "tags_backup_20260322_120000.db"
}
```

| Параметр | Тип | Обязательно | Описание |
|-----------|------|----------|-------------|
| `filename` | string | Да | Имя файла резервной копии для восстановления |

#### Ответ

```json
{
  "success": true,
  "message": "Backup restored",
  "filename": "tags_backup_20260322_120000.db"
}
```

#### Ошибки

- `400` — Имя файла отсутствует или резервная копия не найдена
- `403` — Удаленный доступ

### POST /api/tools/backup/delete

Удалить конкретную резервную копию. **Доступно только с localhost.**

#### Лимит частоты запросов

DESTRUCTIVE

#### Запрос

```json
{
  "filename": "tags_backup_20260322_120000.db"
}
```

| Параметр | Тип | Обязательно | Описание |
|-----------|------|----------|-------------|
| `filename` | string | Да | Имя файла резервной копии для удаления |

#### Ответ

```json
{
  "success": true,
  "deleted": "tags_backup_20260322_120000.db"
}
```

### GET /api/tools/backup/status

Получить статус системы резервного копирования.

#### Ответ

```json
{
  "enabled": true,
  "backup_on_scan_complete": true,
  "periodic_interval_hours": 24,
  "max_generations": 5,
  "cooldown_minutes": 5,
  "scheduler_running": true,
  "last_backup_time": "2026-03-22T11:00:00",
  "within_cooldown": false
}
```

---

## Логирование отладки

### GET /api/tools/debug-log

Получить конец логов отладки. Возвращает `enabled: false` когда режим отладки отключен.

#### Параметры

| Параметр | Тип | По умолчанию | Описание |
|-----------|------|---------|-------------|
| `limit` | int | `200` | Количество строк для получения (1-5000) |
| `filter` | string | `""` | Фильтр строк (поиск подстроки) |

#### Ответ

```json
{
  "enabled": true,
  "lines": ["2026-03-22 12:00:00 [INFO] Server started", "..."],
  "total_lines": 5000,
  "log_path": "/path/to/debug.log",
  "log_size_kb": 128.5
}
```

### GET /api/tools/debug-log/download

Скачать файл логов отладки. **Доступно только с localhost.**

#### Ответ

- Content-Type: `text/plain`
- Content-Disposition: `attachment; filename="debug.log"`

#### Ошибки

- `400` — Режим отладки не включен
- `403` — Удаленный доступ
- `404` — Файл логов не найден

### POST /api/tools/debug-log/clear

Очистить логи отладки. **Доступно только с localhost.**

#### Лимит частоты запросов

WRITE

#### Ответ

```json
{
  "success": true,
  "message": "Log cleared"
}
```

#### Ошибки

- `400` — Режим отладки не включен
- `403` — Удаленный доступ
- `404` — Файл логов не найден

---

## Очистка архивов

Инструменты для обнаружения и очистки дублированных архивов и их извлеченных папок. Все конечные точки **доступны только с localhost.**

### POST /api/tools/archive-cleanup/scan

Сканировать пары архив-папка.

#### Лимит частоты запросов

HEAVY

#### Запрос

```json
{
  "path": "/path/to/check",
  "recursive": false
}
```

| Параметр | Тип | По умолчанию | Описание |
|-----------|------|---------|-------------|
| `path` | string | Обязательно | Каталог для сканирования |
| `recursive` | bool | `false` | Рекурсивное сканирование подкаталогов |

#### Валидация пути

- Пути начинающиеся с `~` отклоняются
- Пути содержащие `..` отклоняются

#### Ответ

```json
{
  "pairs": [
    {
      "archive_path": "/data/images.zip",
      "folder_path": "/data/images",
      "archive_size": 10485760,
      "folder_size": 12582912,
      "file_count": 42
    }
  ],
  "count": 1
}
```

### POST /api/tools/archive-cleanup/execute

Выполнить действия очистки для сканированных пар.

#### Лимит частоты запросов

DESTRUCTIVE

#### Запрос

```json
{
  "actions": [
    { "action": "delete_archive", "archive_path": "/data/images.zip" },
    { "action": "delete_folder", "folder_path": "/data/images" },
    { "action": "skip" }
  ]
}
```

| Параметр | Тип | Описание |
|-----------|------|-------------|
| `actions` | array | Массив действий |
| `actions[].action` | string | Одно из `"delete_archive"`, `"delete_folder"`, `"skip"` |
| `actions[].archive_path` | string | Обязательно когда action это `delete_archive` |
| `actions[].folder_path` | string | Обязательно когда action это `delete_folder` |

#### Ответ

```json
{
  "results": [
    { "action": "delete_archive", "success": true },
    { "action": "delete_folder", "success": true },
    { "action": "skip", "success": true }
  ]
}
```

### POST /api/tools/archive-cleanup/llm-verify

Проверить идентичность пары архив-папка используя LLM (одна пара).

#### Лимит частоты запросов

HEAVY

#### Запрос

```json
{
  "archive_path": "/data/images.zip",
  "folder_path": "/data/images",
  "pair_info": {
    "archive_size": 10485760,
    "folder_size": 12582912
  }
}
```

| Параметр | Тип | Обязательно | Описание |
|-----------|------|----------|-------------|
| `archive_path` | string | Да | Путь файла архива |
| `folder_path` | string | Да | Путь извлеченной папки |
| `pair_info` | object | Нет | Дополнительные метаданные пары |

#### Ответ

```json
{
  "verdict": "same",
  "confidence": 0.95,
  "reasoning": "File counts and sizes match exactly."
}
```

### POST /api/tools/archive-cleanup/llm-verify-batch

Пакетная проверка нескольких пар используя LLM. Максимум 50 пар.

#### Лимит частоты запросов

HEAVY

#### Запрос

```json
{
  "pairs": [
    {
      "archive_path": "/data/a.zip",
      "folder_path": "/data/a",
      "pair_info": {}
    }
  ]
}
```

| Параметр | Тип | Лимит | Описание |
|-----------|------|-------|-------------|
| `pairs` | array | Макс 50 | Массив пар для проверки |

#### Ответ

```json
{
  "results": [
    { "result": { "verdict": "same", "confidence": 0.95, "reasoning": "..." } }
  ]
}
```

### GET /api/tools/archive-cleanup/llm-config

Получить конфигурацию LLM для очистки архивов.

#### Ответ

```json
{
  "engine": "ollama",
  "base_url": "http://localhost:11434",
  "model": "llama3",
  "api_key": ""
}
```

### POST /api/tools/archive-cleanup/llm-config

Сохранить конфигурацию LLM для очистки архивов.

#### Лимит частоты запросов

WRITE

#### Запрос

```json
{
  "engine": "ollama",
  "base_url": "http://localhost:11434",
  "model": "llama3"
}
```

#### Ответ

```json
{
  "success": true
}
```

### POST /api/tools/archive-cleanup/list-models

Список доступных моделей для указанного движка.

#### Запрос

```json
{
  "engine": "ollama",
  "base_url": "http://localhost:11434"
}
```

| Параметр | Тип | Обязательно | Описание |
|-----------|------|----------|-------------|
| `engine` | string | Да | `"ollama"` или `"openai_compat"` |
| `base_url` | string | Да | URL API движка |
| `api_key` | string | Нет | API ключ для `openai_compat` |

#### Ответ

```json
{
  "models": ["llama3", "mistral", "codellama"]
}
```

#### Ошибки

- `400` — Неправильный движок или отсутствует `base_url`
