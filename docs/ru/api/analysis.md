# AI Analysis API

API для AI-анализа изображений, анализа тенденций подсказок и управления сервером.

Все конечные точки POST/PUT/DELETE требуют заголовка `X-Requested-With` (не требуется при использовании Bearer API Key).

## Rate Limit

Конечные точки записи в `/api/analysis/` используют уровень **HEAVY** (~20 req/min, burst 5). GET конечные точки без ограничений.

---

## Конфигурация

### GET /api/analysis/config

Получить текущую конфигурацию AI анализа. API ключи возвращаются замаскированными.

#### Ответ

```json
{
  "engine": "ollama",
  "api_key": "sk-T...xy",
  "model": "claude-sonnet-4-6",
  "ollama_url": "http://localhost:11434",
  "ollama_model": "llava:latest",
  "openai_api_key": "sk-...xy",
  "openai_model": "gpt-4o-mini",
  "openai_compat_url": "http://localhost:8080/v1",
  "openai_compat_api_key": "***...ey",
  "openai_compat_model": "qwen2-vl",
  "hailo_vlm_model": "qwen2-vl-2b-instruct",
  "fallback_local_only": false,
  "language": "ja",
  "is_local": true,
  "has_servers": true,
  "servers": [],
  "active_server": "ollama-main"
}
```

| Поле | Тип | Описание |
|-------|------|-------------|
| `engine` | string | Тип текущего двигателя (`claude_api`, `openai`, `ollama`, `openai_compat`, `hailo_vlm`) |
| `api_key` | string | Claude API ключ (замаскирован) |
| `model` | string | Имя модели Claude API |
| `ollama_url` | string | URL сервера Ollama |
| `ollama_model` | string | Имя модели Ollama |
| `openai_api_key` | string | OpenAI API ключ (замаскирован) |
| `openai_model` | string | Имя модели OpenAI |
| `openai_compat_url` | string | URL сервера совместимого с OpenAI |
| `openai_compat_api_key` | string | API ключ совместимого с OpenAI (замаскирован) |
| `openai_compat_model` | string | Имя модели совместимого с OpenAI |
| `hailo_vlm_model` | string | Имя модели Hailo VLM |
| `fallback_local_only` | boolean | Ограничивать ли только локальными двигателями |
| `language` | string | Язык для результатов анализа (`ja`, `en`, etc.) |
| `is_local` | boolean | Является ли текущий двигатель локальным (бесплатный) |
| `has_servers` | boolean | Настроен ли реестр сервера |
| `servers` | array | Список серверов (только если `has_servers` истина) |
| `active_server` | string | ID активного сервера (только если `has_servers` истина) |

### POST /api/analysis/config

Сохранить конфигурацию AI анализа. Замаскированные значения (строки содержащие `...`) не перезаписываются. API ключи автоматически зашифровываются.

#### Rate Limit

HEAVY

#### Запрос

```json
{
  "engine": "ollama",
  "ollama_url": "http://localhost:11434",
  "ollama_model": "llava:latest",
  "language": "ja"
}
```

| Параметр | Тип | Обязательный | Описание |
|-----------|------|----------|-------------|
| `engine` | string | Нет | Тип двигателя |
| `api_key` | string | Нет | Claude API ключ |
| `model` | string | Нет | Модель Claude API |
| `ollama_url` | string | Нет | URL сервера Ollama |
| `ollama_model` | string | Нет | Имя модели Ollama |
| `openai_api_key` | string | Нет | OpenAI API ключ |
| `openai_model` | string | Нет | Имя модели OpenAI |
| `openai_compat_url` | string | Нет | URL сервера совместимого с OpenAI |
| `openai_compat_api_key` | string | Нет | API ключ совместимого с OpenAI |
| `openai_compat_model` | string | Нет | Имя модели совместимого с OpenAI |
| `hailo_vlm_model` | string | Нет | Имя модели Hailo VLM |
| `fallback_local_only` | boolean | Нет | Ограничивать ли только локальными двигателями |
| `language` | string | Нет | Язык для результатов анализа |

#### Ответ

```json
{
  "success": true
}
```

---

## Обнаружение двигателей

### GET /api/analysis/available-engines

Получить список настроенных и доступных двигателей. Облачные двигатели исключаются, когда `fallback_local_only` включён.

#### Ответ

```json
{
  "engines": [
    {
      "type": "ollama",
      "label": "Ollama",
      "model": "llava:latest",
      "models": ["llava:latest", "llava:13b", "bakllava:latest"]
    },
    {
      "type": "hailo_vlm",
      "label": "Hailo VLM",
      "model": "qwen2-vl-2b-instruct",
      "models": ["qwen2-vl-2b-instruct"]
    }
  ]
}
```

| Поле | Тип | Описание |
|-------|------|-------------|
| `engines[].type` | string | Идентификатор типа двигателя |
| `engines[].label` | string | Метка отображения |
| `engines[].model` | string | Текущая настроенная модель |
| `engines[].models` | string[] | Список доступных моделей |

---

## Анализ одного файла

### POST /api/analysis/analyze/\<file_id\>

Анализировать один файл с помощью AI двигателя. Поддерживает изображения, видео и изображения внутри архивов.

#### Rate Limit

HEAVY

#### Параметры

| Параметр | Тип | Описание |
|-----------|------|-------------|
| `file_id` | int | ID файла (параметр пути) |

#### Запрос

JSON тело опционально. Когда опущено, используются настройки по умолчанию.

```json
{
  "mode": "full",
  "engine": "ollama",
  "model": "llava:latest",
  "server_id": "ollama-main"
}
```

| Параметр | Тип | Обязательный | Описание |
|-----------|------|----------|-------------|
| `mode` | string | Нет | Режим анализа. По умолчанию `"full"` |
| `engine` | string | Нет | Переопределить тип двигателя |
| `model` | string | Нет | Переопределить имя модели |
| `server_id` | string | Нет | Указать ID сервера для использования |

#### Ответ (200)

```json
{
  "success": true,
  "result": {
    "description": "A landscape painting with mountains...",
    "style": "digital art",
    "quality_score": 8,
    "tags": ["landscape", "mountains", "sunset"]
  },
  "engine": "Ollama (llava:latest)"
}
```

#### Ответы об ошибках

- `400`: Двигатель не настроен / указан неверный двигатель
- `404`: Файл не найден / файл не существует на диске
- `500`: Ошибка во время анализа

### GET /api/analysis/result/\<file_id\>

Получить сохранённые результаты анализа для файла. Возвращает все результаты, когда использовались несколько двигателей/режимов.

#### Параметры

| Параметр | Тип | Описание |
|-----------|------|-------------|
| `file_id` | int | ID файла (параметр пути) |

#### Ответ (200) -- Результаты найдены

```json
{
  "found": true,
  "result": {
    "engine": "Ollama (llava:latest)",
    "description": "A landscape painting...",
    "style": "digital art",
    "quality_score": 8,
    "analyzed_at": 1709500000
  },
  "results": [
    {
      "engine": "Ollama (llava:latest)",
      "description": "A landscape painting...",
      "style": "digital art",
      "quality_score": 8,
      "analyzed_at": 1709500000
    }
  ]
}
```

| Поле | Тип | Описание |
|-------|------|-------------|
| `found` | boolean | Существуют ли результаты анализа |
| `result` | object | Самый свежий результат анализа (обратная совместимость) |
| `results` | array | Массив всех результатов анализа |

#### Ответ (200) -- Результаты не найдены

```json
{
  "found": false
}
```

---

## Пакетный анализ

### POST /api/analysis/batch

Начать пакетное задание AI анализа на неанализированных файлах. Работает в фоне.

#### Rate Limit

HEAVY

#### Запрос

```json
{
  "limit": 10,
  "scan_root": "",
  "file_ids": [],
  "server_ids": ["ollama-main", "openai-compat"]
}
```

| Параметр | Тип | Обязательный | Описание |
|-----------|------|----------|-------------|
| `limit` | int | Нет | Максимальное количество файлов для анализа. По умолчанию 10. Ограничено 10 для облачных двигателей. 0 означает все файлы для локальных двигателей |
| `scan_root` | string | Нет | Ограничить цели конкретной корневой папкой сканирования |
| `file_ids` | int[] | Нет | Прямо указать ID файлов для анализа |
| `server_ids` | string[] | Нет | ID серверов для использования. Несколько серверов включают параллельный анализ |

#### Ответ (200)

```json
{
  "started": true,
  "count": 10,
  "parallel": false
}
```

| Поле | Тип | Описание |
|-------|------|-------------|
| `started` | boolean | Было ли задание запущено |
| `count` | int | Количество файлов для анализа |
| `parallel` | boolean | Работает ли параллельно (несколько `server_ids`) |
| `worker` | boolean | True если направлено через рабочий вывод |
| `subprocess` | boolean | True если работает в подпроцессе (Hailo VLM) |

#### Ответы об ошибках

- `400`: Нет файлов для анализа
- `409`: Задание AI анализа уже выполняется

### POST /api/analysis/batch/cancel

Отменить выполняющееся пакетное задание AI анализа.

#### Rate Limit

HEAVY

#### Запрос

Тело не требуется.

#### Ответ (200)

```json
{
  "status": "cancelling",
  "message": "AI analysis cancel requested"
}
```

#### Ответы об ошибках

- `404`: Нет выполняющегося задания AI анализа

---

## Анализ тенденций подсказок

### POST /api/analysis/trends

Запустить анализ тенденций на 50 самых свежих подсказках. Результаты автоматически сохраняются в историю.

#### Rate Limit

HEAVY

#### Запрос

Тело не требуется.

#### Ответ (200)

```json
{
  "success": true,
  "result": {
    "summary": "Recent prompts focus on landscape and character art...",
    "top_themes": ["landscape", "character", "fantasy"],
    "trend_direction": "increasing variety"
  }
}
```

#### Ответы об ошибках

- `400`: API ключ не настроен (при использовании облачных двигателей)
- `500`: Ошибка во время анализа тенденций

### GET /api/analysis/trends/history

Получить историю анализа тенденций подсказок. Отсортировано от новейшего. Максимум 50 записей сохраняется.

#### Параметры

| Параметр | Тип | По умолчанию | Описание |
|-----------|------|---------|-------------|
| `limit` | int | 20 | Количество записей для извлечения (макс 50) |
| `offset` | int | 0 | Смещение |

#### Ответ

```json
{
  "items": [
    {
      "id": 5,
      "engine": "ollama",
      "analyzed_at": 1709500000,
      "prompt_count": 50,
      "result": {
        "summary": "Recent prompts focus on...",
        "top_themes": ["landscape", "character"]
      }
    }
  ]
}
```

| Поле | Тип | Описание |
|-------|------|-------------|
| `items[].id` | int | ID записи истории |
| `items[].engine` | string | Использованный тип двигателя |
| `items[].analyzed_at` | int | UNIX timestamp анализа |
| `items[].prompt_count` | int | Количество проанализированных подсказок |
| `items[].result` | object | Результат анализа тенденций |

### DELETE /api/analysis/trends/history/\<history_id\>

Удалить одну запись истории анализа тенденций.

#### Rate Limit

HEAVY

#### Параметры

| Параметр | Тип | Описание |
|-----------|------|-------------|
| `history_id` | int | ID записи истории (параметр пути) |

#### Ответ

```json
{
  "deleted": true
}
```

#### Ответы об ошибках

- `404`: Запись истории не найдена

---

## Статистика

### GET /api/analysis/stats

Получить статистику AI анализа.

#### Ответ

```json
{
  "total_analyzed": 150,
  "total_files": 1200,
  "styles": [
    { "style": "digital art", "count": 45 },
    { "style": "anime", "count": 30 }
  ],
  "quality_distribution": [
    { "tier": "excellent", "count": 20, "avg_score": 8.5 },
    { "tier": "good", "count": 60, "avg_score": 6.8 },
    { "tier": "average", "count": 50, "avg_score": 4.9 },
    { "tier": "low", "count": 20, "avg_score": 2.3 }
  ]
}
```

| Поле | Тип | Описание |
|-------|------|-------------|
| `total_analyzed` | int | Количество анализированных файлов |
| `total_files` | int | Общее количество файлов (исключая удалённые) |
| `styles` | array | Разбор стиля (топ 10) |
| `styles[].style` | string | Имя стиля |
| `styles[].count` | int | Количество файлов |
| `quality_distribution` | array | Распределение оценки качества |
| `quality_distribution[].tier` | string | Уровень качества (`excellent` >= 8, `good` >= 6, `average` >= 4, `low` < 4) |
| `quality_distribution[].count` | int | Количество файлов |
| `quality_distribution[].avg_score` | float | Средняя оценка |

---

## Соединение Ollama

### GET /api/analysis/ollama/models

Подключиться к настроенному серверу Ollama и вывести список доступных моделей.

#### Ответ

```json
{
  "available": true,
  "models": [
    { "name": "llava:latest", "size": 4700000000 }
  ]
}
```

#### Ответы об ошибках

- `400`: Неверный URL Ollama

### POST /api/analysis/ollama/test

Протестировать соединение с сервером Ollama по указанному URL.

#### Rate Limit

HEAVY

#### Запрос

```json
{
  "ollama_url": "http://localhost:11434"
}
```

| Параметр | Тип | Обязательный | Описание |
|-----------|------|----------|-------------|
| `ollama_url` | string | Да | URL сервера Ollama для тестирования |

#### Ответ

```json
{
  "available": true,
  "models": [
    { "name": "llava:latest", "size": 4700000000 }
  ]
}
```

#### Ответы об ошибках

- `400`: URL пуст / URL неверен

---

## Соединение с сервером совместимым с OpenAI

### GET /api/analysis/openai-compat/models

Подключиться к настроенному серверу совместимому с OpenAI и вывести список доступных моделей.

#### Ответ

```json
{
  "available": true,
  "models": [
    { "id": "qwen2-vl-7b-instruct" }
  ]
}
```

#### Ответы об ошибках

- `400`: URL не настроен / URL неверен

### POST /api/analysis/openai-compat/test

Протестировать соединение с сервером совместимым с OpenAI по указанному URL.

#### Rate Limit

HEAVY

#### Запрос

```json
{
  "url": "http://localhost:8080/v1",
  "api_key": "optional-key"
}
```

| Параметр | Тип | Обязательный | Описание |
|-----------|------|----------|-------------|
| `url` | string | Да | URL для тестирования |
| `api_key` | string | Нет | API ключ (если требуется) |

#### Ответ

```json
{
  "available": true,
  "models": [
    { "id": "qwen2-vl-7b-instruct" }
  ]
}
```

#### Ответы об ошибках

- `400`: URL пуст / URL неверен

---

## Реестр AI сервера

Регистрировать и управлять несколькими AI серверами с приоритетной резервной копией и параллельным анализом.

### GET /api/analysis/servers

Список всех зарегистрированных серверов со статусом. API ключи замаскированы.

#### Ответ

```json
{
  "servers": [
    {
      "id": "ollama-main",
      "name": "Ollama (llava:latest)",
      "type": "ollama",
      "priority": 10,
      "enabled": true,
      "config": {
        "base_url": "http://localhost:11434",
        "model": "llava:latest"
      },
      "is_active": true,
      "status": "unknown"
    }
  ]
}
```

| Поле | Тип | Описание |
|-------|------|-------------|
| `servers[].id` | string | ID сервера (неизменяемо) |
| `servers[].name` | string | Имя отображения |
| `servers[].type` | string | Тип двигателя (`claude_api`, `openai`, `ollama`, `openai_compat`, `hailo_vlm`) |
| `servers[].priority` | int | Приоритет (меньше = выше приоритет) |
| `servers[].enabled` | boolean | Включено/отключено |
| `servers[].config` | object | Конфигурация, специфичная для двигателя |
| `servers[].is_active` | boolean | Является ли это текущим активным сервером |
| `servers[].status` | string | Статус соединения (всегда `"unknown"` в представлении списка) |

### POST /api/analysis/servers

Зарегистрировать новый сервер. Первый сервер автоматически устанавливается как активный.

#### Rate Limit

HEAVY

#### Запрос

```json
{
  "name": "Local Ollama",
  "type": "ollama",
  "config": {
    "base_url": "http://localhost:11434",
    "model": "llava:latest"
  }
}
```

| Параметр | Тип | Обязательный | Описание |
|-----------|------|----------|-------------|
| `name` | string | Да | Имя сервера |
| `type` | string | Да | Тип двигателя |
| `config` | object | Да | Конфигурация, специфичная для двигателя |
| `priority` | int | Нет | Приоритет |
| `enabled` | boolean | Нет | Включено/отключено. По умолчанию true |

#### Ответ (201)

```json
{
  "success": true,
  "server": {
    "id": "local-ollama",
    "name": "Local Ollama",
    "type": "ollama",
    "priority": 10,
    "enabled": true,
    "config": { "base_url": "http://localhost:11434", "model": "llava:latest" }
  }
}
```

#### Ответы об ошибках

- `400`: Ошибка валидации / достигнут лимит сервера

### PUT /api/analysis/servers/\<server_id\>

Обновить параметры сервера. Поле `id` не может быть изменено.

#### Rate Limit

HEAVY

#### Параметры

| Параметр | Тип | Описание |
|-----------|------|-------------|
| `server_id` | string | ID сервера (параметр пути) |

#### Запрос

```json
{
  "name": "Updated Name",
  "type": "ollama",
  "priority": 20,
  "enabled": true,
  "config": { "base_url": "http://192.168.1.100:11434", "model": "llava:13b" }
}
```

Все поля опциональны. Обновляются только указанные поля.

#### Ответ

```json
{
  "success": true,
  "server": { "id": "ollama-main", "name": "Updated Name", "..." : "..." }
}
```

#### Ответы об ошибках

- `400`: Неверный тип / сервер не найден

### DELETE /api/analysis/servers/\<server_id\>

Удалить сервер. Если активный сервер удаляется, следующий сервер с наивысшим приоритетом автоматически становится активным.

#### Rate Limit

HEAVY

#### Параметры

| Параметр | Тип | Описание |
|-----------|------|-------------|
| `server_id` | string | ID сервера (параметр пути) |

#### Ответ

```json
{
  "success": true
}
```

#### Ответы об ошибках

- `400`: Сервер не найден

### POST /api/analysis/servers/\<server_id\>/activate

Переключить активный сервер.

#### Rate Limit

HEAVY

#### Параметры

| Параметр | Тип | Описание |
|-----------|------|-------------|
| `server_id` | string | ID сервера (параметр пути) |

#### Ответ

```json
{
  "success": true,
  "active": "ollama-main"
}
```

#### Ответы об ошибках

- `400`: Сервер не найден

### POST /api/analysis/servers/\<server_id\>/test

Запустить тест соединения на сервере. Также измеряется время ответа.

#### Rate Limit

HEAVY

#### Параметры

| Параметр | Тип | Описание |
|-----------|------|-------------|
| `server_id` | string | ID сервера (параметр пути) |

#### Ответ

```json
{
  "success": true,
  "available": true,
  "elapsed_ms": 45,
  "server": {
    "id": "ollama-main",
    "name": "Local Ollama",
    "type": "ollama",
    "config": { "..." : "..." }
  }
}
```

| Поле | Тип | Описание |
|-------|------|-------------|
| `available` | boolean | Доступен ли сервер |
| `elapsed_ms` | int | Время ответа теста соединения в миллисекундах |
| `server` | object | Информация о сервере |

#### Ответы об ошибках

- `400`: Сервер не найден

### PUT /api/analysis/servers/reorder

Массовое обновление приоритетов серверов.

#### Rate Limit

HEAVY

#### Запрос

```json
{
  "server_ids": ["ollama-main", "openai-compat", "claude-api"]
}
```

| Параметр | Тип | Обязательный | Описание |
|-----------|------|----------|-------------|
| `server_ids` | string[] | Да | Массив ID серверов. Указанный порядок становится новым порядком приоритетов |

#### Ответ

```json
{
  "success": true
}
```

#### Ответы об ошибках

- `400`: `server_ids` не является массивом

### POST /api/analysis/servers/migrate

Автоматическая миграция из старой конфигурации `ai_analysis` в новый формат реестра серверов. Отказывает, если серверы уже существуют.

#### Rate Limit

HEAVY

#### Запрос

Тело не требуется.

#### Ответ

```json
{
  "success": true,
  "servers": [
    { "id": "ollama", "name": "Ollama (llava:latest)", "type": "ollama", "..." : "..." }
  ],
  "migrated": 3
}
```

| Поле | Тип | Описание |
|-------|------|-------------|
| `servers` | array | Серверы созданные миграцией |
| `migrated` | int | Количество созданных серверов |

#### Ответы об ошибках

- `400`: `ai_servers` уже существует
