# Расширения (Extensions)

YU AI Manager поддерживает добавление функциональности через систему Extension.
В настоящее время встроено 43 builtin-Extension, разбитых на 6 категорий.

## Список встроенных Extension

### Извлечение метаданных (metadata)

| Extension | Описание |
|-----------|---------|
| builtin-a1111 | Извлечение метаданных из PNG/WebP/WebM Automatic1111 / SD WebUI |
| builtin-novelai-v3 | Извлечение метаданных NovelAI V3 и ранее |
| builtin-novelai-v4 | Извлечение метаданных NovelAI V4 (поддержка Character Prompts, Vibe Transfer) |
| builtin-comfyui | Разбор JSON воркфлоу ComfyUI |
| builtin-annotations | Сохранение, поиск и массовые операции с аннотациями файлов |
| builtin-ratings | Система звёздного рейтинга (1–5 звёзд) |
| builtin-tag-dictionary | Поиск, импорт и разбивка словаря тегов Danbooru |

### Интеграция Bridge (bridge)

| Extension | Описание |
|-----------|---------|
| builtin-sd-webui-bridge | Интеграция SD WebUI / Forge (генерация изображений, управление моделями) |
| builtin-nai-bridge | Интеграция NovelAI API (генерация изображений) |
| builtin-comfyui-bridge | Интеграция ComfyUI (выполнение воркфлоу) |

### Промпты (prompt)

| Extension | Описание |
|-----------|---------|
| builtin-prompt-library | Библиотека промптов и организация |
| builtin-prompt-syntax | Подсветка синтаксиса промптов и обнаружение ошибок (NAI/SD/DP) |
| builtin-prompt-simulator | Симулятор Dynamic Prompts, расчёт весов, конвертация |
| builtin-sd-nai-convert | Взаимная конвертация промптов SD ↔ NovelAI |

### AI (ai)

| Extension | Описание |
|-----------|---------|
| builtin-analysis | AI-анализ изображений (Claude, OpenAI, Ollama, Hailo VLM) |
| builtin-wd-tagger | Автоматическое тегирование WD-Tagger (ONNX + VLM) |
| builtin-ocr | VLM OCR — извлечение текста, структурированный анализ, перевод |
| builtin-clip-search | Движок семантического поиска изображений CLIP |
| builtin-clip-onnx | ONNX Runtime бэкенд CLIP-энкодера |
| builtin-clip-coreml | Core ML бэкенд CLIP-энкодера (Apple Neural Engine) |
| builtin-hailo-semantic-search | Семантический поиск на Hailo-10H |
| builtin-hailo-yolo-detect | Обнаружение объектов YOLO на Hailo-10H |
| builtin-hailo-genai | Hailo-10H GenAI (LLM/VLM/S2T) |
| builtin-speech-to-text | Транскрипция речи в текст (Hailo NPU / CUDA / ROCm / CPU) |
| builtin-inference | Обнаружение провайдеров ONNX Runtime, GPU-ускорение |

### Библиотека (library)

| Extension | Описание |
|-----------|---------|
| builtin-favorites-manager | Управление избранным и коллекциями |
| builtin-freeze-pullback | Генерация видео Freeze & Pull-back (эффект Ken Burns) |
| builtin-download | Массовая загрузка выбранных изображений в ZIP |
| builtin-chatlog | Импортёр и вьювер чат-логов (Claude / ChatGPT) |
| builtin-md-viewer | Вьювер Markdown-файлов (полнотекстовый поиск FTS5) |
| builtin-cross-search | Кросс-поиск (MD, чат-логи, промпты, текст) |
| builtin-lan-share | Общий доступ к коллекциям по LAN (аутентификация с токенами с ограничением по времени) |
| builtin-stats | Статистика и инсайты (временные шкалы, вехи) |
| builtin-trophy | Система трофеев и достижений |

### Система (system)

| Extension | Описание |
|-----------|---------|
| builtin-auto-scan-watcher | Автоматическое обнаружение изменений файлов и инкрементные обновления |
| builtin-mcp-client | Управление подключением к внешним MCP-серверам |
| builtin-backup | Резервное копирование/восстановление DB, планировщик |
| builtin-sns-share | Публикация в SNS (Bluesky, X/Twitter) |
| builtin-webhook | Диспетчер Webhook (HTTP-доставка событий) |
| builtin-github-integration | Мониторинг Issue GitHub, триаж, отслеживание PR/Discussion/Release |

## Управление Extension

На вкладке Settings > Extensions доступны следующие операции:

- **Включение/отключение**: Мгновенное переключение тумблером
- **Новая установка**: Установка по URL Git-репозитория
- **Marketplace**: Поиск и установка в один клик
- **Обновление**: Обновление Extension на базе Git до последней версии
- **Удаление**: Удаление сторонних Extension

### Управление через API

```bash
# Список Extension
curl -H "Authorization: Bearer sk_xxx" \
     http://localhost:5000/api/extensions

# Включение/отключение
curl -X POST -H "Authorization: Bearer sk_xxx" \
     http://localhost:5000/api/extensions/builtin_wd_tagger/toggle

# Установка из Git
curl -X POST -H "Authorization: Bearer sk_xxx" \
     -H "Content-Type: application/json" \
     -d '{"url": "https://github.com/user/my-extension.git"}' \
     http://localhost:5000/api/extensions/install
```

## Extension Sandbox

Сторонние Extension защищены в песочнице.

### Уровни доверия

| Уровень | Целевые | Ограничения |
|---------|---------|------------|
| L0 (TRUSTED) | `builtin-*` | Без ограничений |
| L2 (UNTRUSTED) | Остальные | Ограничения DB/FS/сети |

### 4 фазы песочницы

1. **Capability Token**: Управление разрешениями через подписанный HMAC-SHA256 токен с сроком действия 24 часа
2. **SandboxedDB / SandboxedFS**: Extension только с `db:read` разрешает только SELECT. Доступ к файлам управляется на основе пути
3. **SandboxedHTTPClient / ImportGuard**: Защита от SSRF, мониторинг runtime import, обнаружение фальсификации SHA-256
4. **Изоляция процессов (Linux)**: L2 Extension выполняется в отдельном процессе. JSON-RPC 2.0 IPC через Unix socket

## Структура директорий

```
extensions/builtin_<name>/
  extension.json            # Манифест (имя, версия, разрешения и т.д.)
  <name>_ext.py             # Точка входа (публикует get_blueprint())
  templates/<name>/          # Jinja2-шаблоны
  core_impl/                 # Бизнес-логика (опционально)
```

### Обязательные поля extension.json

```json
{
  "name": "my-extension",
  "version": "1.0.0",
  "entrypoint": "my_extension_ext.py",
  "has_blueprint": true,
  "category": "library"
}
```

Категории: `metadata`, `bridge`, `prompt`, `ai`, `library`, `system`.

## Extension Module API v2 (поддержка ES Module)

С v4.29.0 Extension может быть написан с использованием паттерна ES Module с `<script type="module">` и Import Maps.

### Публичный API

| Функция | Описание |
|---------|---------|
| `showToast(message, isError?)` | Показать toast-уведомление |
| `sseSubscribe(eventType, handler)` | Подписаться на SSE-событие |
| `sseUnsubscribe(eventType, handler)` | Отписаться от SSE-события |
| `tr(path, a?, b?)` | Разрешить ключ i18n-перевода |
| `apiFetch(path, opts?)` | Обёртка fetch с CSRF |
| `apiUrl(path)` | Построить URL API |
| `escapeHtml(text)` | Экранировать специальные HTML-символы |
