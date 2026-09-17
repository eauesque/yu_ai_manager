# API LLM Router

LLM Router в YU AI Manager предоставляет единый интерфейс для нескольких локальных LLM бэкендов (Ollama, hailo-ollama и т.д.) через API протоколы Anthropic Messages API и OpenAI Chat Completions API.

Базовый URL: `http://localhost:5000/v1`

## Конечные точки

### POST /v1/messages

Совместимо с Anthropic Messages API. Подключитесь через `ANTHROPIC_BASE_URL=http://localhost:5000/v1` из Claude Code / Claude Desktop.

Запрос:
```json
{
  "model": "local-coder-big",
  "messages": [{"role": "user", "content": "..."}],
  "system": "...",
  "max_tokens": 1024,
  "stream": false
}
```

Ответ: формат Anthropic Messages.

### POST /v1/chat/completions

Совместимо с OpenAI Chat Completions API. Для клиентов, совместимых с OpenAI, таких как Continue / Aider.

### GET /v1/models

Возвращает комбинированный список всех моделей и псевдонимов из всех бэкендов в формате OpenAI `/v1/models`. Поле `yu_metadata` содержит собственную информацию, такую как context_window / size_b / backend_status.

### GET /v1/router/health

Возвращает состояние маршрутизатора и сводку бэкенда. Для диагностики.

### POST /v1/router/refresh

Используйте `{"backend": "ollama-mac"}` для обновления одного бэкенда или отправьте пустое тело для принудительного переоткрытия всех бэкендов.

### POST /v1/router/estimate

Оценка количества токенов (аппроксимация tiktoken cl100k).

### GET /v1/router/capabilities/{target}

Отобранные метаданные модели, включая good_at / weak_at / notes.

## Аутентификация

`config.json` `llm_router.auth.mode`:

| mode | Поведение |
|---|---|
| `loopback` (по умолчанию) | Позволяет неаутентифицированный доступ только с 127.0.0.1 / ::1 |
| `api_key` | Проверяет заголовок `x-api-key` или `Authorization: Bearer` |
| `none` | Без аутентификации |

Подробности см. в `docs/en/llm-router/setup.md`.
