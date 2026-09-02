# Gateway — руководство по границе аутентификации LAN

> Целевая версия: Gateway Phase 1 (v4.75.0 и выше) / Gradio добавлен (v4.255.11 и выше)

## Что такое Gateway

Gateway — это обратный прокси, который защищает доступ к **инструментам бэкэнда без встроенной аутентификации** (SD WebUI, ComfyUI, Ollama, Gradio и т.д.)  
с помощью **Bearer токена + модели областей доступа**.

```
Внешний клиент / машина в LAN
    │
    │  Authorization: Bearer <api_key>
    ▼
 yu_ai_manager  (/v1/*, /sd/*, /comfy/*, /gradio/<name>/*)
 ┌────────────────────────────────────────────────────────┐
 │                      Gateway                          │
 │          проверка области доступа ──► выбор бэкэнда   │
 └────────────────────────────────────────────────────────┘
    │          │            │            │
    ▼          ▼            ▼            ▼
 Ollama    SD WebUI     ComfyUI      Gradio
 :11434     :7860         :8188        :7861
```

### Отличие от LLM Router

| | Gateway | LLM Router |
|---|---|---|
| **Охват** | SD WebUI, ComfyUI, Ollama, Gradio вместе | Только LLM (Ollama) |
| **Аутентификация** | Bearer обязателен на основе области доступа | loopback может быть обойден |
| **Прокси-назначение** | `/sd/*`, `/comfy/*`, `/v1/*`, `/gradio/<name>/*` | Только `/v1/*` |
| **Основное использование** | Безопасное раскрытие генеративных инструментов для внешних сетей / LAN | Бэкэнд для инструментов AI-кодирования |

Вы можете включить оба одновременно на одной машине.

---

## Установка

### 1. Создание первого ключа API (CLI)

```bash
uv run python -m core.gateway.cli create-key --id admin-local --scopes "*"
```

Пример выходных данных:
```
id:      admin-local
secret:  gw_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
(этот секрет отображается только один раз. обязательно скопируйте его)
```

### 2. Добавление конфигурации в config.json

```json
{
  "gateway": {
    "auth": {
      "mode": "api_key",
      "allow_loopback_bypass": true,
      "api_keys": [
        {
          "id": "admin-local",
          "secret_enc": "enc:v2:...",
          "scopes": ["*"],
          "allowed_models": null
        }
      ]
    },
    "backends": {
      "ollama":       {"type": "ollama",   "base_url": "http://127.0.0.1:11434"},
      "sd_webui":     {"type": "sd_webui", "base_url": "http://127.0.0.1:7860"},
      "comfyui":      {"type": "comfyui",  "base_url": "http://127.0.0.1:8188", "ws_url": "ws://127.0.0.1:8188/ws"},
      "irodori-tts":  {"type": "gradio",   "base_url": "http://127.0.0.1:7861"}
    },
    "health_probe": {"enabled": true, "interval_seconds": 10}
  }
}
```

> Поле `secret_enc` должно содержать зашифрованное значение в формате `enc:v2:...`, выведенное CLI.  
> Не записывайте открытый текст секрета прямо в `config.json`.

### 3. Перезагрузка приложения и проверка

```bash
GW_HOST=<LAN IP этой машины>
GW_PORT=5000
BEARER=<api-key-secret>

# Без аутентификации — 401
curl -i http://$GW_HOST:$GW_PORT/v1/models

# С правильным Bearer — 200
curl http://$GW_HOST:$GW_PORT/v1/models   -H "Authorization: Bearer $BEARER"

# Статус бэкэндов
curl http://$GW_HOST:$GW_PORT/v1/router/capabilities   -H "Authorization: Bearer $BEARER"

# Список сервисов узлов
curl http://$GW_HOST:$GW_PORT/v1/node/services   -H "Authorization: Bearer $BEARER"
```

---

## WebUI (страница /gateway)

Панель управления, открываемая по адресу `/gateway`.

### Список бэкэндов

Отображает список зарегистрированных бэкэндов и их статус работы.

| Столбец | Описание |
|---|---|
| **Тип** | Тип бэкэнда (`ollama`, `sd_webui`, `comfyui`, `gradio`)|
| **Порт** | Номер порта прокси-назначения |
| **Статус** | `online` / `offline` / `unknown` |
| **Действия** | Probe (проверка подключения) • Изменить конфигурацию |

### Автоматическое сканирование бэкэндов

Нажмите кнопку "Сканировать" для автоматического обнаружения и регистрации работающих инструментов путем сканирования общих локальных портов (7860, 8188, 11434, 7861 и т.д.).

### Управление ключами API

Ключи API также можно добавлять и отзывать из WebUI (требуется ключ с областью доступа `*`).

---

## Список областей доступа

| Область доступа | Разрешенные эндпоинты |
|---|---|
| `llm:chat` | `POST /v1/chat/completions` |
| `llm:messages` | `POST /v1/messages` (совместима с Anthropic) |
| `llm:models` | `GET /v1/models` |
| `sd:generate` | `POST /sd/sdapi/v1/txt2img` и т.д. |
| `sd:query` | `GET /sd/sdapi/v1/samplers` и т.д. |
| `sd:admin` | `POST /sd/sdapi/v1/options` и т.д. |
| `comfy:generate` | `POST /comfy/api/prompt` и т.д. |
| `comfy:query` | `GET /comfy/api/queue` и т.д. |
| `memory:read` | `GET /agentmemory/memories` и т.д. (чтение) |
| `memory:write` | `POST /agentmemory/observe` и т.д. (запись) |
| `memory:admin` | `POST /agentmemory/migrate` и т.д. (администрирование) |
| `ollama:proxy` | `GET/POST /ollama/<name>/*` (полная прозрачность для встроенного API Ollama + совместимости с OpenAI) |
| `gradio:proxy` | `GET/POST /gradio/<name>/*` (полная прозрачность всех эндпоинтов) |
| `gateway:admin` | Управление ключами API, изменение конфигурации (автоматически предоставляется с loopback) |
| `node:status` | `GET /v1/node/services` |
| `*` | Все области доступа (только для администраторов) |

### Примеры ключей по назначению

```json
"api_keys": [
  {
    "id": "claude-code",
    "secret_enc": "enc:v2:...",
    "scopes": ["llm:chat", "llm:messages", "llm:models"],
    "allowed_models": null
  },
  {
    "id": "comfy-client",
    "secret_enc": "enc:v2:...",
    "scopes": ["comfy:generate", "comfy:query"],
    "allowed_models": null
  }
]
```

---

## Прокси Ollama

Отдельно от `/v1/*` LLM Router, это прокси полностью прозрачно перенаправляет встроенный API Ollama (`/api/*`) и совместимый с OpenAI API (`/v1/*`). Просто измените направление `OLLAMA_HOST` на Gateway, и аутентификация будет добавлена.

### URL прокси

```
/ollama/<backend_name>/<subpath>  →  переводится на /<subpath> зарегистрированного base_url
```

### Пример конфигурации

```json
"backends": {
  "ollama": {"type": "ollama", "base_url": "http://127.0.0.1:11434"}
}
```

### Конфигурация клиента (способ `OLLAMA_HOST`)

```bash
export OLLAMA_HOST=http://<gateway-host>:5000/ollama/ollama
# с этого момента все команды ollama проходят через Gateway
ollama list
ollama run llama3.3:70b
```

> Если клиент не может передать Bearer через `OLLAMA_HOST`, используйте `allow_loopback_bypass: true` +  
> для прохождения без ключа через loopback или используйте ключ с областью доступа `*` как альтернативу.

### Передача больших файлов

Модельные объекты (`/api/blobs/*`) передаются потоком без таймаута (другие пути имеют таймаут 300 секунд).  
Работает без проблем с загрузкой и выгрузкой моделей объемом в гигабайты.

---

## Прокси Gradio

Позволяет безопасно получить доступ к WebUI на основе Gradio (например, Irodori-TTS) через Gateway с аутентификацией.  
Минимальная реализация с полной прозрачностью всех эндпоинтов (без ограничений по эндпоинтам, только ограничение тела на 50 МиБ).

### URL прокси

```
/gradio/<backend_name>/<subpath>  →  переводится на /<subpath> зарегистрированного base_url
```

Имя бэкэнда (`<backend_name>`) — это ключ, зарегистрированный в `backends` в `config.json`.

### Пример конфигурации

```json
"backends": {
  "irodori-tts": {"type": "gradio", "base_url": "http://127.0.0.1:7861"}
}
```

### Проверка

```bash
GW=http://localhost:5000
KEY=<api-key-secret>

# получение информации о Gradio приложении
curl -H "Authorization: Bearer $KEY" "$GW/gradio/irodori-tts/"

# Gradio 3.x совместимый predict
curl -H "Authorization: Bearer $KEY"   -X POST "$GW/gradio/irodori-tts/run/predict"   -H "Content-Type: application/json"   -d '{"data": ["Hello"], "fn_index": 0}'
```

### Ограничения

- WebSocket (`/queue/join`) не поддерживается (только HTTP)
- Gradio 4.x SSE потоком (`GET /call/{api_name}/{event_id}`) полностью буферизируется, поэтому  
  при длительной генерации может возникнуть таймаут

---

## Прокси Agent Memory (agentmemory)

Gateway также предоставляет прокси для безопасного использования клиентов agentmemory  
(таких как `@agentmemory/mcp`) через LAN.

### Эндпоинты

```
/agentmemory/livez       → аутентификация не требуется (проверка здоровья)
/agentmemory/health      → требуется область доступа memory:read
/agentmemory/memories    → memory:read
/agentmemory/observe     → memory:write
/agentmemory/migrate     → memory:admin
...（полный список см. в официальном API agentmemory）
```

### Использование на одной машине

Когда `allow_loopback_bypass: true`, с loopback (127.0.0.1) доступ проходит без ключа API.  
Изменение конфигурации MCP **не требуется**.

### Использование с другой машины в LAN

`@agentmemory/mcp` передает переменную среды `AGENTMEMORY_SECRET`  
как `Authorization: Bearer <secret>` в upstream.

**Пример изменения конфигурации MCP (`claude_desktop_config.json` / `.mcp.json`):**

```json
{
  "agentmemory": {
    "command": "npx",
    "args": ["-y", "@agentmemory/mcp"],
    "env": {
      "AGENTMEMORY_URL": "http://<gateway-host>:5000/agentmemory",
      "AGENTMEMORY_SECRET": "<api-key-secret>"
    }
  }
}
```

Требуемые области доступа (указывается при создании ключа API):

```json
"scopes": ["memory:read", "memory:write"]
```

Если также требуются операции администрирования (`/migrate`, `/governance/*` и т.д.), добавьте `memory:admin`.

### Проверка

```bash
GW=http://<gateway-host>:5000
KEY=<api-key-secret>

# аутентификация не требуется (livez)
curl $GW/agentmemory/livez

# получение memories с Bearer
curl -H "Authorization: Bearer $KEY" "$GW/agentmemory/memories?limit=3"

# работает также с Basic аутентификацией (совместимость с SD клиентом)
curl -u "user:$KEY" "$GW/agentmemory/health"
```

---

## Режимы аутентификации

| Режим | Поведение |
|---|---|
| `api_key` | Bearer токен обязателен (`allow_loopback_bypass: true` освобождает только loopback) |
| `loopback` | С loopback (127.0.0.1) аутентификация не требуется. С LAN работает как `api_key` |
| `none` | Без аутентификации (только для разработки/тестирования. непригодно для production) |

Установка `allow_loopback_bypass: true` позволяет инструментам на одной машине (Claude Code CLI и т.д.)  
проходить через Gateway без ключа API.

---

## Health Probe

Когда `health_probe.enabled: true`, автоматически проверяет доступность бэкэндов с установленным интервалом.

```json
"health_probe": {
  "enabled": true,
  "interval_seconds": 10
}
```

Офлайновые бэкэнды отображаются как `"status": "offline"` в поле `backends`  
ответа `/v1/router/capabilities`.

---

## Частые проблемы

| Симптом | Причина / решение |
|---|---|
| Все запросы возвращают 401 | `allow_loopback_bypass` установлен на `false` и ключ требуется даже с loopback. Или значение Bearer неправильно |
| Прокси на SD WebUI возвращает 404 | Неправильный порт в `sd_webui.base_url` (по умолчанию 7860). Запустите Probe на странице `/gateway` |
| WebSocket ComfyUI не подключается | Убедитесь, что установлена `ws_url` (`ws://127.0.0.1:8188/ws`) |
| Прокси Gradio возвращает 404 | Убедитесь, что `backend_name` совпадает с именем ключа backends в `config.json`. Также требуется `type: "gradio"` |
| SSE поток Gradio истекает | При длительной генерации (видео и т.д.) есть ограничения полной буферизации. Короткие рассуждения (TTS и т.д.) работают без проблем |
| Недостаточно областей доступа для 403 | Областей доступа используемого ключа недостаточно. Используйте ключ с областью доступа `*` для добавления из управления ключами API |
| Требуется разрешить только определенные модели в `allowed_models` | Укажите как массив: `"allowed_models": ["qwen2.5:7b", "llama3.3:70b"]` |

---

## Вне области Phase 1

- Запуск/остановка/перезагрузка бэкэндов (выполняется через SSH + systemctl)
- `/v1/responses` (Codex совместимый façade) — Phase 2 и позже
- Балансировка нагрузки между несколькими экземплярами Gateway — используйте распределенные рассуждения LAN Cowork

---

## Связанная документация

- [Справочник API Gateway](../api/gateway.md) — подробные сведения о эндпоинтах `/api/gateway/*`
- [Установка LLM Router](../llm-router/setup.md) — облегченный прокси, только для LLM
- [Обзор LAN Cowork](../lan-cowork/README.md) — взаимодействие нескольких узлов

## Управление ключами API в WebUI

На странице конфигурации на вкладке **«Gateway API ключи»** можно создавать, просматривать и удалять ключи API.  
На странице [Gateway](/gateway) также есть ссылка.

### Создание ключа API

1. Введите **Метку** (например: `Claude Desktop`) — ID будет автоматически преобразован в slug (например: `claude-desktop`)
2. Выберите **Области доступа** с помощью значков (требуется как минимум одна)
3. При выборе `*` (полный доступ) установите флажок подтверждения
4. Нажмите кнопку «Создать»
5. Скопируйте отображаемый секрет — **после выхода со страницы он больше не будет отображаться**

### Примечания

- Последний ключ с областью доступа `*` невозможно удалить (предотвращение блокировки Bearer пути)
- Сначала создайте другой ключ с областью доступа `*`, прежде чем удалять

### Использование

```bash
curl -H "Authorization: Bearer <secret>" http://localhost:5000/v1/chat/completions ...
```
