# API: /api/llm_router (Администратор)

Административные конечные точки для операций управления LLM Router. Защищены стандартной аутентификацией сеанса WebUI (PIN/session), полностью отделены от поверхности OpenAI `/v1/*`.

> **Примечание**: Это административные конечные точки, отличные от конечных точек вывода, таких как `/v1/chat/completions`.

---

## Общий формат ответа

Все конечные точки используют обертку `api_result`. При успехе тело вложено под ключ `data`.

```json
{
  "status": "ok",
  "data": { ... }
}
```

При ошибке:

```json
{
  "status": "error",
  "error": "Описание ошибки"
}
```

---

## GET /api/llm_router/status

Снимок для отображения всей панели управления в одном запросе. Возвращает всю информацию о бэкенде и карту псевдонимов.

### Запрос

```
GET /api/llm_router/status
```

Нет параметров.

### Ответ `200 OK`

```json
{
  "status": "ok",
  "data": {
    "router": {
      "version": "1.0.0",
      "alias_count": 2
    },
    "backends": [
      {
        "alias": "ollama-mac",
        "base_url": "http://192.168.1.10:11434",
        "source": "static",
        "status": "ready",
        "slo_state": null,
        "disabled": false,
        "model_count": 3,
        "models": [
          {
            "name": "qwen2.5:7b",
            "context_window": 32768,
            "size_b": 7.6
          },
          {
            "name": "llama3.2:3b",
            "context_window": 128000,
            "size_b": 3.2
          }
        ],
        "last_seen": "2026-04-09T12:34:56.789123",
        "last_error": null
      },
      {
        "alias": "mdns-pi5-hailo",
        "base_url": "http://192.168.1.20:8080",
        "source": "mdns",
        "status": "unreachable",
        "slo_state": "unknown",
        "disabled": false,
        "model_count": 0,
        "models": [],
        "last_seen": null,
        "last_error": "Connection refused"
      }
    ],
    "aliases": {
      "default-llm": "ollama-mac/qwen2.5:7b",
      "fast-chat": "ollama-mac/llama3.2:3b"
    }
  }
}
```

### Описание полей

**`router`**

| Поле | Тип | Описание |
|---|---|---|
| `version` | string | Версия схемы маршрутизатора (в настоящее время `"1.0.0"`) |
| `alias_count` | int | Количество определенных псевдонимов |

**`backends[]`**

| Поле | Тип | Описание |
|---|---|---|
| `alias` | string | Уникальный идентификатор бэкенда |
| `base_url` | string | Базовый URL конечной точки OpenAI совместимой |
| `source` | string | `"static"` (файл конфигурации) или `"mdns"` (автоматически обнаруженный) |
| `status` | string | `"ready"` / `"unreachable"` / `"unknown"` |
| `slo_state` | string \| null | `"vision_idle"` / `"vision_active"` / `"unknown"` / `null` |
| `disabled` | bool | `true` если исключен из маршрутизации |
| `model_count` | int | Количество открытых моделей |
| `models[]` | array | Список моделей (`name`, `context_window`, `size_b`) |
| `last_seen` | string \| null | Последняя успешная проверка подключения (ISO 8601) |
| `last_error` | string \| null | Последнее сообщение об ошибке |

**`aliases`**

Карта логических имен псевдонимов к физическим ID моделей (`backend-alias/model-name`).

---

## POST /api/llm_router/refresh

Принуждает проверку всех бэкендов или указанного бэкенда, обновляя `status` и список моделей.

### Запрос

**Обновление всех бэкендов (без тела):**

```
POST /api/llm_router/refresh
Content-Type: application/json

{}
```

Также принимается пустое тело без заголовка Content-Type.

**Обновление конкретного бэкенда только:**

```json
{
  "alias": "ollama-mac"
}
```

### Ответ `200 OK`

```json
{
  "status": "ok",
  "data": {
    "refreshed": [
      {
        "alias": "ollama-mac",
        "status": "ready",
        "model_count": 3,
        "disabled": false,
        "last_error": null
      },
      {
        "alias": "mdns-pi5-hailo",
        "status": "unreachable",
        "model_count": 0,
        "disabled": false,
        "last_error": "Connection refused"
      }
    ]
  }
}
```

Массив `refreshed` содержит только легкие результаты обновления (используйте `/status` для полных деталей).

### Ошибка `404 Not Found`

Когда `alias` указан, но не существует:

```json
{
  "status": "error",
  "error": "unknown backend: nonexistent-alias"
}
```

### Примечания

- Проверки выполняются синхронно (ответ возвращается после завершения)
- Проверки также выполняются для бэкендов с `disabled: true` (статус все еще обновляется)
- Включены автоматически обнаруженные bэкенды mDNS

---

## POST /api/llm_router/backends/`<alias>`/disable

Отключение указанного бэкенда. Отключенные бэкенды исключены из маршрутизации, а состояние сохраняется в `data/llm_router_state.json`.

### Запрос

```
POST /api/llm_router/backends/ollama-mac/disable
```

Тело не требуется.

### Ответ `200 OK`

```json
{
  "status": "ok",
  "data": {
    "alias": "ollama-mac",
    "disabled": true
  }
}
```

### Ошибка `404 Not Found`

```json
{
  "status": "error",
  "error": "unknown backend: nonexistent-alias"
}
```

### Ошибка `500 Internal Server Error`

Когда сохранение на диск не удается (ошибка разрешений, диск заполнен и т.д.). Состояние в памяти откатывается.

```json
{
  "status": "error",
  "error": "failed to persist disabled state"
}
```

### Механизм сохранения

1. Установить флаг `disabled` в `true` в каталоге в памяти
2. Атомарно записать в `data/llm_router_state.json` (через файл `.tmp` и `os.replace`)
3. Если запись не удается, шаг 1 откатывается и возвращается `500`

Отключенное состояние сохраняется при перезагрузке приложения. Если бэкенд, обнаруженный mDNS, был отключен до запуска, отключенное состояние автоматически применяется после обнаружения.

---

## POST /api/llm_router/backends/`<alias>`/enable

Включение указанного бэкенда. Обратное действие `disable`.

### Запрос

```
POST /api/llm_router/backends/ollama-mac/enable
```

Тело не требуется.

### Ответ `200 OK`

```json
{
  "status": "ok",
  "data": {
    "alias": "ollama-mac",
    "disabled": false
  }
}
```

### Ошибки

Те же, что и конечная точка `disable` (`404` / `500`). Сохранено с `disabled: false`.

---

## Сводка конечной точки

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/api/llm_router/status` | Получить снимок всех бэкендов и псевдонимов |
| `POST` | `/api/llm_router/refresh` | Принудить проверку всех или отдельных бэкендов |
| `POST` | `/api/llm_router/backends/<alias>/disable` | Отключить бэкенд (сохранено) |
| `POST` | `/api/llm_router/backends/<alias>/enable` | Включить бэкенд (сохранено) |

## Связанная документация

- [LLM Router WebUI Guide](../llm-router/webui.md)
- [LLM Router Setup](../llm-router/setup.md)
