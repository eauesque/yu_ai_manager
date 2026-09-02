# Интеграция MCP

YU AI Manager имеет встроенный MCP (Model Context Protocol) сервер, позволяющий
управлять им напрямую из Claude Desktop, Claude Code, Cline и других AI-клиентов.
Предоставляет более 137 инструментов с полным доступом ко всем функциям.

## Поддерживаемые MCP-клиенты

| Клиент | Тип подключения | Примечания |
|--------|----------------|-----------|
| Claude Desktop | stdio / HTTP | Рекомендуемый клиент |
| Claude Code | stdio | CLI-окружение |
| Cline (VS Code) | stdio | Расширение VS Code |
| Open WebUI | HTTP/SSE | Веб-based |

## Локальное подключение (stdio)

Для подключения из Claude Desktop / Claude Code на том же компьютере:

1. Создать API-ключ на вкладке Settings > API Keys
2. Добавить следующее в конфигурационный файл клиента

### Claude Desktop

`claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "yu-ai-manager": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "/path/to/yu_ai_manager",
      "env": {
        "YU_BASE_URL": "http://localhost:5000",
        "YU_API_KEY": "sk_your_api_key_here"
      }
    }
  }
}
```

### Claude Code

`.mcp.json`:

```json
{
  "mcpServers": {
    "yu-ai-manager": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "/path/to/yu_ai_manager",
      "env": {
        "YU_BASE_URL": "http://localhost:5000",
        "YU_API_KEY": "sk_your_api_key_here"
      }
    }
  }
}
```

## Подключение по LAN (HTTP/SSE)

Для подключения с другой машины в LAN:

1. Включить LAN Access в настройках YU AI Manager
2. Создать API-ключ
3. Скопировать настройки подключения из «MCP Connection Snippet» на вкладке Settings > API Keys

```json
{
  "mcpServers": {
    "yu-ai-manager": {
      "type": "http",
      "url": "http://192.168.x.x:5000/mcp",
      "headers": {
        "Authorization": "Bearer sk_your_api_key_here"
      }
    }
  }
}
```

## Доступные инструменты (по категориям)

### Поиск и управление изображениями

| Инструмент | Описание |
|-----------|---------|
| `search_images` | Поиск с фильтрами по тегам, дате, рейтингу и т.д. |
| `get_image_detail` | Детальные метаданные изображения |
| `get_library_stats` | Статистика библиотеки |
| `find_similar` | Поиск похожих изображений по перцептивному хэшу |
| `rate_images` | Массовая установка рейтинга |
| `set_tags` | Добавление/удаление тегов |
| `set_annotations` | Установка аннотаций |

### Bridge-интеграции

| Инструмент | Описание |
|-----------|---------|
| `sd_generate` | Генерация изображений в SD WebUI |
| `comfyui_generate` | Генерация изображений в ComfyUI |
| `comfyui_generate_json` | Выполнение JSON-воркфлоу ComfyUI |

### Шлюз безопасности агента

| Инструмент | Описание |
|-----------|---------|
| `agent_kill` / `agent_resume` | Управление Kill Switch |
| `agent_status` | Статус механизмов безопасности |
| `agent_journal` | Поиск по журналу операций |
| `agent_undo` | Отмена операции |
| `agent_circuit_breaker_status` | Состояние Circuit Breaker |
| `agent_budget_status` | Состояние Budget Tracker |
| `agent_scope_set` | Установка области видимости |
| `agent_anomaly_status` | Статус обнаружения аномалий |

## Переменные окружения

| Переменная | Описание | По умолч. |
|-----------|---------|----------|
| `YU_BASE_URL` | URL сервера | `http://localhost:5000` |
| `YU_API_KEY` | API-ключ | (обязателен) |
| `YU_DEBUG_MODE` | Включить инструменты отладки | `0` |

`YU_DEBUG_MODE=1` добавляет специальные инструменты отладки: прямые запросы к DB, проверки работоспособности и т.д.

## Устранение неполадок

### Невозможно подключиться

1. Убедиться, что YU AI Manager запущен
2. Проверить корректность API-ключа (с префиксом `sk_`)
3. Проверить корректность `YU_BASE_URL`
4. При LAN-подключении — убедиться, что LAN Access включён

### Инструмент не найден

- Если Extension отключён, его инструменты тоже недоступны
- Проверить статус включения через `list_extensions`

### Таймаут

- Поиск в большой библиотеке и пакетные операции могут занимать время
- Ограничить количество результатов параметром `limit`
