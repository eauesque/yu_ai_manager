# API распределенного вывода

REST API для реестра сервера распределенного вывода. Распределяет рабочие нагрузки семантического индексирования CLIP по нескольким узлам, используя стратегию общей очереди.

## Конечные точки

### GET /api/inference-servers

Возвращает список зарегистрированных серверов и текущий режим отправки.

**Ответ:**

```json
{
  "status": "ok",
  "mode": "single",
  "servers": [
    {
      "id": 1,
      "name": "Hailo Worker 1",
      "endpoint_url": "http://192.168.1.10:9090",
      "inference_types": ["clip"],
      "priority": 50,
      "enabled": true,
      "timeout": 30
    }
  ]
}
```

- `mode`: `"single"` | `"parallel"` | `"idle_first"`
- `servers`: массив объектов конфигурации сервера

---

### POST /api/inference-servers

Регистрация нового сервера вывода.

**Тело запроса:**

| Поле | Тип | Обязательное | По умолчанию | Описание |
|---|---|---|---|---|
| `name` | string | ✓ | — | Отображаемое имя |
| `endpoint_url` | string | ✓ | — | Базовый URL воркера |
| `inference_types` | string[] | — | `["clip"]` | Поддерживаемые типы вывода |
| `priority` | int | — | `50` | Приоритет (меньшее значение = более высокий приоритет) |
| `bearer_token` | string | — | — | Токен аутентификации |
| `timeout` | int | — | `30` | Таймаут запроса в секундах |

**Ответ:**

```json
{
  "status": "ok",
  "server": { ... }
}
```

---

### PUT /api/inference-servers/{server_id}

Обновление конфигурации существующего сервера. Принимает частичное тело с теми же полями, что и POST.

---

### DELETE /api/inference-servers/{server_id}

Удаление сервера из реестра.

**Ответ:**

```json
{ "status": "ok" }
```

---

### POST /api/inference-servers/{server_id}/test

Проверка здоровья указанного сервера.

**Ответ:**

```json
{
  "status": "ok",
  "server_id": 1,
  "healthy": true,
  "latency_ms": 12.5
}
```

---

### GET /api/inference-servers/health

Проверка здоровья всех включенных серверов одновременно.

**Ответ:**

```json
{
  "status": "ok",
  "results": [
    { "server_id": 1, "healthy": true, "latency_ms": 12.5 },
    { "server_id": 2, "healthy": false, "error": "Connection refused" }
  ]
}
```

---

### POST /api/inference-servers/mode

Установка режима отправки.

**Тело запроса:**

| Поле | Тип | Обязательное | Описание |
|---|---|---|---|
| `mode` | string | ✓ | `"single"` \| `"parallel"` \| `"idle_first"` |

**Ответ:**

```json
{ "status": "ok", "mode": "parallel" }
```

---

## Режимы отправки

| Режим | Описание |
|---|---|
| `single` | Использование только сервера с наивысшим приоритетом (наименьшее значение приоритета) |
| `parallel` | Распределение работы по всем включенным серверам, используя общую очередь |
| `idle_first` | Проверка здоровья в первую очередь, затем распределение по отзывчивым серверам только |

## Распределенное семантическое индексирование

Добавьте `distributed: true` в тело запроса `POST /api/index/start` (расширение семантического поиска), чтобы включить распределенное индексирование с использованием зарегистрированных рабочих серверов.

```json
{
  "batch_size": 32,
  "distributed": true
}
```

## Настройка сервера воркера

```bash
python deploy/hailo_tagger_server.py --port 9090
```

Поддерживаемые конечные точки:

| Путь | Описание |
|---|---|
| `GET /health` | Проверка здоровья |
| `POST /tag` | Вывод WD-Tagger |
| `POST /clip-encode` | Кодирование вектора CLIP |

## MCP инструменты

| Инструмент | Описание |
|---|---|
| `inference-servers-list` | Список серверов и получение текущего режима |
| `inference-server-add` | Регистрация нового сервера |
| `inference-server-update` | Обновление конфигурации сервера |
| `inference-server-remove` | Удаление сервера |
| `inference-server-health` | Проверка здоровья |
| `inference-dispatch-mode-set` | Установка режима отправки |
