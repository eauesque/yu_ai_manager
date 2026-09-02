# API WD Tagger

API для WD Tagger (Waifu Diffusion Tagger) Danbooru автотегирования. Предоставляет управление конфигурацией, одиночное/пакетное тегирование, CRUD тегов, управление моделями, чтение XMP и тестирование подключения VLM.

## GET /api/wd-tagger/config

Получить текущую конфигурацию WD Tagger.

### Parameters

None

### Response

```json
{
  "config": {
    "model": "SmilingWolf/wd-swinv2-tagger-v3",
    "threshold": 0.35,
    "...": "..."
  }
}
```

## POST /api/wd-tagger/config

Сохранить/обновить конфигурацию WD Tagger.

### Rate Limit

WRITE

### Request

```json
{
  "model": "SmilingWolf/wd-swinv2-tagger-v3",
  "threshold": 0.35
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| *(any key)* | any | No | Поле конфигурации. Неизвестные ключи или неверные значения возвращают `400` |

### Response

```json
{
  "config": {
    "model": "SmilingWolf/wd-swinv2-tagger-v3",
    "threshold": 0.35,
    "...": "..."
  }
}
```

### Errors

| Code | Status | Description |
|------|--------|-------------|
| `invalid_json` | 400 | Тело запроса не является JSON объектом |
| `invalid_value` | 400 | Неверное значение конфигурации |

## POST /api/wd-tagger/tag/<file_id>

Запустить WD Tagger вывод на одном файле для предсказания и назначения Danbooru тегов.

### Rate Limit

HEAVY

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `file_id` | int | ID файла (параметр пути) |

### Request

```json
{
  "force": false
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `force` | boolean | No | Если `true`, перезаписать существующие теги и повторно запустить вывод. По умолчанию `false` |

### Response

```json
{
  "file_id": 42,
  "model": "SmilingWolf/wd-swinv2-tagger-v3",
  "tags": [
    {"tag": "1girl", "score": 0.98, "category": "general"},
    {"tag": "solo", "score": 0.95, "category": "general"}
  ]
}
```

### Errors

| Code | Status | Description |
|------|--------|-------------|
| `tag_error` | 400 | Тегирование не удалось (файл не найден, ошибка загрузки изображения и т. д.) |

## GET /api/wd-tagger/tags/<file_id>

Получить сохранённые WD Tagger теги для конкретного файла.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | ID файла (параметр пути) |
| `model` | string | No | Фильтр по имени модели (параметр запроса) |
| `all` | boolean | No | When `1`, `true`, or `yes`, return tags from all models and ignore the active model and `model` filter |

### Response

```json
{
  "file_id": 42,
  "tags": [
    {"tag": "1girl", "score": 0.98, "category": "general", "model": "SmilingWolf/wd-swinv2-tagger-v3"},
    {"tag": "solo", "score": 0.95, "category": "general", "model": "SmilingWolf/wd-swinv2-tagger-v3"}
  ]
}
```

## DELETE /api/wd-tagger/tags/<file_id>

Удалить WD Tagger теги для конкретного файла.

### Rate Limit

WRITE

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | ID файла (параметр пути) |
| `model` | string | No | Фильтр по имени модели (параметр запроса). Если не указано, удаляет теги из всех моделей |

### Response

```json
{
  "file_id": 42,
  "deleted": 15
}
```

## DELETE /api/wd-tagger/tags/batch

Удалить WD Tagger теги для нескольких файлов одновременно.

### Rate Limit

WRITE

### Request

```json
{
  "file_ids": [1, 2, 3],
  "model": "wd-swinv2-tagger-v3"
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_ids` | list | Yes | Массив ID файлов (максимум 500) |
| `model` | string | No | Фильтр по имени модели. Если не указано, удаляет теги из всех моделей |

### Response

```json
{
  "deleted_files": 3,
  "deleted_tags": 45
}
```

## Active model (v4.192.0+)

Если один и тот же файл повторно тегируется несколькими моделями WD Tagger,
`file_wd_tags` хранит теги каждой модели как историю. Если задан active model,
детальный просмотр, поиск `ai_analyzed` и внутренняя проверка WD Tagger
"уже тегирован" используют только теги этой модели. Если active model не задан,
сохраняется прежнее поведение: теги всех моделей рассматриваются вместе.

### Настройка в UI

В верхней части retag modal отображается текущий `Active model`. Через dropdown
`Change` можно выбрать доступную модель. Пункт `(none / reset)` сбрасывает active
model.

После retag использованная модель становится active model по умолчанию. Отключите
флажок "Сделать активной моделью после перетегирования" в retag modal, чтобы
сохранить текущий active model.

Rows старых моделей не удаляются автоматически. Они остаются в базе как история.
Чтобы удалить их явно, включите "Также удалить теги других моделей" в retag
modal и подтвердите диалог после retag.


### GET /api/wd-tagger/profiles

Returns registered WD Tagger profiles and the current active model. Requires admin scope.

```json
{
  "profiles": [
    {
      "id": "camie_tagger_v2",
      "display_name": "Camie Tagger v2",
      "model_id": "Camais03/camie-tagger-v2",
      "adapter_family": "camie",
      "backend": "onnx",
      "builtin": true,
      "has_tags": false
    }
  ],
  "active_model_id": "Camais03/camie-tagger-v2"
}
```

### GET /api/wd-tagger/active-model

Возвращает текущий active model и список моделей, присутствующих в базе данных.
Требуется admin scope.

```json
{
  "active_model_id": "SmilingWolf/wd-eva02-large-tagger-v3",
  "available_models": [
    {"model_id": "SmilingWolf/wd-eva02-large-tagger-v3", "file_count": 120},
    {"model_id": "SmilingWolf/wd-swinv2-tagger-v3", "file_count": 340}
  ]
}
```

### PUT /api/wd-tagger/active-model

Изменяет active model. Требуется admin scope. Передайте `null` или пустую строку
в `model_id`, чтобы сбросить настройку.

```json
{
  "model_id": "SmilingWolf/wd-eva02-large-tagger-v3"
}
```

| Code | Status | Description |
|------|--------|-------------|
| `invalid_model_id` | 400 | model_id слишком длинный или содержит управляющие символы |
| `unknown_model` | 400 | В базе данных нет тегов для указанной модели |

## POST /api/wd-tagger/batch

Запустить пакетное тегирование нескольких файлов. Если указано `file_ids`, обрабатываются только эти файлы. Если не указано, автоматически выбирают необозначенные файлы до `limit`.

### Rate Limit

HEAVY

### Request

```json
{
  "file_ids": [1, 2, 3],
  "limit": 100,
  "force": false,
  "scan_root": ""
}
```

| Parameter | Type | Required | Limit | Description |
|-----------|------|----------|-------|-------------|
| `file_ids` | int[] | No | Max 500 | Массив целевых ID файлов. Если не указано, необозначенные файлы выбираются автоматически |
| `limit` | int | No | - | Максимум файлов для обработки, когда `file_ids` не указано. По умолчанию `100` |
| `force` | boolean | No | - | Если `true`, перезаписать существующие теги. По умолчанию `false` |
| `scan_root` | string | No | - | Фильтр по пути корня сканирования. Пустая строка для всех файлов |

### Response

```json
{
  "job_id": "wd_tagger",
  "total": 100,
  "status": "started"
}
```

### Errors

| Code | Status | Description |
|------|--------|-------------|
| `batch_too_large` | 400 | `file_ids` превышает 500 элементов |
| `batch_error` | 409 | Задача пакетного тегирования уже запущена |

## POST /api/wd-tagger/batch/cancel

Отменить запущенную задачу пакетного тегирования.

### Rate Limit

WRITE

### Request

No body required.

### Response

```json
{
  "status": "cancelling",
  "message": "Batch tagging cancel requested"
}
```

### Errors

| Code | Status | Description |
|------|--------|-------------|
| `job_not_running` | 404 | Нет запущенной задачи пакетного тегирования |

## GET /api/wd-tagger/stats

Получить статистику WD Tagger тегирования.

### Parameters

None

### Response

```json
{
  "total_tagged": 1234,
  "total_tags": 56789,
  "models": {
    "SmilingWolf/wd-swinv2-tagger-v3": 1200
  },
  "untagged_unknown": 42
}
```

| Field | Type | Description |
|-------|------|-------------|
| `total_tagged` | int | Количество помеченных файлов |
| `total_tags` | int | Общее количество сохранённых тегов |
| `models` | object | Количество помеченных файлов по модели |
| `untagged_unknown` | int | Количество файлов без метаданных (`unknown`) и без WD тегов |

## GET /api/wd-tagger/untagged

Список файлов без метаданных (`unknown`), которые ещё не помечены. Поддерживает постраничное разбиение.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `limit` | int | No | Количество результатов. 1-500, по умолчанию `100` |
| `offset` | int | No | Количество результатов для пропуска. По умолчанию `0` |

### Response

```json
{
  "files": [
    {"id": 10, "filepath": "/images/photo.png", "filename": "photo.png"}
  ],
  "total": 42
}
```

## GET /api/wd-tagger/xmp/<file_id>

Прочитать XMP метаданные из конкретного файла.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `file_id` | int | ID файла (параметр пути) |

### Response

```json
{
  "file_id": 42,
  "xmp": {
    "subject": ["1girl", "solo", "blue_eyes"],
    "description": "...",
    "creator": "..."
  }
}
```

### Errors

| Code | Status | Description |
|------|--------|-------------|
| `file_not_found` | 404 | Файл не существует или мягко удалён |

## GET /api/wd-tagger/vlm/test

Проверить подключение к VLM (Vision Language Model) серверу. Проверяет доступность конечной точки OpenAI-совместимого API.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `url` | string | Yes | URL VLM сервера (параметр запроса) |

### Response

```json
{
  "ok": true,
  "message": "Connection successful",
  "server_info": "..."
}
```

### Errors

| Code | Status | Description |
|------|--------|-------------|
| `missing_url` | 400 | Параметр `url` не предоставлен |
| `invalid_url` | 400 | Формат URL неверен |

## GET /api/wd-tagger/vlm/models

Список доступных моделей на VLM сервере. Запрашивает конечную точку `/v1/models` OpenAI-совместимого сервера.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `url` | string | Yes | URL VLM сервера (параметр запроса) |

### Response

```json
{
  "models": [
    {"id": "llava-v1.6", "object": "model"}
  ]
}
```

### Errors

| Code | Status | Description |
|------|--------|-------------|
| `missing_url` | 400 | Параметр `url` не предоставлен |
| `invalid_url` | 400 | Формат URL неверен |
| `vlm_connection_error` | 502 | Не удалось подключиться к VLM серверу |

## POST /api/wd-tagger/model/download

Загрузить модель WD Tagger. Получает файлы модели из Hugging Face и сохраняет их локально.

### Rate Limit

HEAVY

### Request

```json
{
  "repo": "SmilingWolf/wd-swinv2-tagger-v3"
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `repo` | string | No | Имя репозитория Hugging Face. Если не указано, использует значение `model` из конфигурации |

### Response

```json
{
  "repo": "SmilingWolf/wd-swinv2-tagger-v3",
  "path": "/path/to/model/directory",
  "ready": true
}
```

### Errors

| Code | Status | Description |
|------|--------|-------------|
| `unknown_model` | 400 | Неизвестный репозиторий модели. `hint` содержит список известных моделей |
| `download_failed` | 500 | Загрузка не удалась |

## GET /api/wd-tagger/model/status

Проверить статус загрузки модели WD Tagger.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `repo` | string | No | Имя репозитория Hugging Face (параметр запроса). Если не указано, использует значение `model` из конфигурации |

### Response

```json
{
  "repo": "SmilingWolf/wd-swinv2-tagger-v3",
  "downloaded": true,
  "path": "/path/to/model/directory",
  "known_models": {
    "SmilingWolf/wd-swinv2-tagger-v3": "SwinV2 (recommended)",
    "SmilingWolf/wd-convnext-tagger-v3": "ConvNeXt",
    "SmilingWolf/wd-vit-tagger-v3": "ViT"
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `repo` | string | Проверяемое имя репозитория |
| `downloaded` | boolean | Загружена ли модель локально |
| `path` | string/null | Локальный путь модели, если загружена |
| `known_models` | object | Все поддерживаемые модели (имя репозитория -> имя дисплея) |

## User profile CRUD (v4.197.0+)

API для CRUD tagger profiles, созданных пользователем, из UI страницы Tools. Для всех эндпоинтов требуется admin scope. Общая форма ошибки: `{ok: false, error, code, ...extra}`. Для body запроса действует **жёсткий лимит 1MB** (`code: profile_too_large`, 413). `id` должен соответствовать regex `^[a-z0-9][a-z0-9_-]{0,63}$`.

### POST /api/wd-tagger/profiles

Создать новый пользовательский profile.

**Запрос**: profile JSON (schema v2, `profile_version: "2"`). Поле `builtin` принудительно перезаписывается в `false` на стороне сервера.

**Ответ (200)**:
```json
{
  "ok": true,
  "profile": { "...": "...サニタイズ済 profile JSON..." },
  "origin": "user",
  "overrides_builtin": false
}
```

| Field | Description |
|---|---|
| `profile` | Сохранённый profile (гарантированно `builtin: false`) |
| `origin` | Всегда `"user"` |
| `overrides_builtin` | `true`, если существует builtin profile с тем же id (advanced путь) |

**Ошибки**:

| status | code | условие |
|---|---|---|
| 400 | `validation_failed` | JSON нарушает schema v2 (`extra.errors=[{path, message}, ...]`) |
| 400 | `invalid_id` | `id` в body не соответствует regex |
| 409 | `id_conflict` | Такой id уже существует у пользовательского profile |
| 413 | `profile_too_large` | body > 1MB |

### GET /api/wd-tagger/profiles/{id}

Получить полный schema v2 profile для указанного id (UI вызывает при редактировании / дублировании / Export).

**path**: `id` (обязательна проверка regex)

**Ответ (200)**:
{Та же форма, что и у POST: profile / origin / overrides_builtin}

**Ошибки**:
- 400 `invalid_id` (id в path не соответствует regex)
- 404 `not_found`

### PUT /api/wd-tagger/profiles/{id}

Обновить существующий пользовательский profile.

**path**: `id` (обязательна проверка regex)

**Запрос**: profile JSON. `body.id` должен совпадать с id в path (для переименования направляйте UI на `Duplicate → Delete`).

**Ответ (200)**: Та же форма, что и у POST.

**Ошибки**:

| status | code | условие |
|---|---|---|
| 400 | `id_immutable` | id в path и id в body не совпадают |
| 400 | `invalid_id` | id в path не соответствует regex |
| 400 | `validation_failed` | нарушение schema |
| 403 | `builtin_read_only` | id в path — builtin profile (нет соответствующего пользовательского файла) |
| 404 | `not_found` | id не зарегистрирован |
| 413 | `profile_too_large` | body > 1MB |

### DELETE /api/wd-tagger/profiles/{id}

Удалить пользовательский profile.

**path**: `id`

**Ответ (200)**:
```json
{"ok": true, "deleted": true}
```

**Ошибки**:

| status | code | условие |
|---|---|---|
| 400 | `invalid_id` | неверный id в path |
| 403 | `builtin_read_only` | только builtin, без пользовательского override |
| 404 | `not_found` | id не зарегистрирован |
| 409 | `in_use` | Этот profile — активная модель (включает `extra.active_model_id`). В UI сначала переключите активный profile через `PUT /api/wd-tagger/active-model`, затем повторите |

### POST /api/wd-tagger/profiles/{id}/test

dry-run download. Делает HEAD для каждого `files[]` на HuggingFace и для элементов с `required: true` выполняет атомарную загрузку на уровне файла (кэш переиспользует существующий путь).

**path**: `id`

**body**: не требуется

**Поведение**:
- per-file timeout: 30s
- общий timeout: 60s
- redirect: только allowlist поддоменов `huggingface.co` / `hf.co`, максимум 5 hops; userinfo (`user:pass@`) — SSRFBlocked

**Ответ (200, успех)**:
```json
{
  "ok": true,
  "files": [
    {"name": "model.onnx", "status": "downloaded", "size": 1234567},
    {"name": "tags.csv",   "status": "cached",     "size": 89012},
    {"name": "optional.json", "status": "skipped_optional", "size": null}
  ]
}
```

Значения `status`:
- `downloaded`: загружено в этом запуске
- `cached`: уже существует локально (только HEAD)
- `skipped_optional`: `required: false` и 404 / HEAD не удался

**Ошибки (status / code)**:

| status | code | условие |
|---|---|---|
| 400 | `invalid_id` / `required_missing` | неверный id в path / required файл — 404 на HF |
| 404 | `not_found` | profile не зарегистрирован |
| 408 | `timeout` | превышен общий лимит 60s |
| 502 | `ssrf_blocked` | redirect вне allowlist HF / содержит userinfo / scheme не http(s) |
| 502 | `hf_unavailable` | HF вернул 5xx |

При ошибке body имеет форму `{"ok": false, "code": ..., "error": ..., "files": [...частичные результаты...], "detail": "..."}`.

### Формат profile JSON (schema v2)

```typescript
interface ProfileV2 {
  profile_version: "2";
  id: string;
  display_name: string;
  adapter_family: "wd" | "camie" | "oppai" | "generic_onnx";
  backend: "onnx";
  model_id: string;                        // Путь репозитория HF "<owner>/<name>"
  hf_subdir: string | null;
  files: { name: string; required: boolean; size_hint_mb?: number }[];
  default_thresholds: Record<string, number>;
  tag_source: TagSourceSpec;               // type=csv/json_list/json_dict/composite
  threshold_source: ThresholdSourceSpec;   // type=global_per_category/per_tag_json
  preprocess_spec: PreprocessSpec;
  supports_categories: string[];
  categories_mode: "from_tag_source" | "all_general";
  builtin?: boolean;                       // всегда false для пользовательского происхождения (сервер принудительно)
}
```

Подробнее см. `extensions/builtin_wd_tagger/core_impl/adapters/base.py` (`TaggerProfile`) или builtin reference implementation (`extensions/builtin_wd_tagger/core_impl/profiles/*.json`).
