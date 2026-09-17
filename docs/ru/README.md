# Центр документации

Используйте этот файл как «документационный вход (основной хаб)».

**Последнее обновление**: 2026-05-13

## Важно

- Project README: [`../../README.ja.md`](../../README.ja.md)
- Changelog: [`../../CHANGELOG.ja.md`](../../CHANGELOG.ja.md)
- Master TODO (единый источник истины): [`../../TODO.md`](../../TODO.md)

## Рекомендации по разработке

Рекомендации по разработке расположены в виде отдельных файлов в `development/development_docs/`.

- **[Правила TODO](TODO_RULES.md)** — Правила написания TODO (P0/P1/P2/P3 + категория обязательны)

### Основные документы (`development/development_docs/`)

| Документ | Содержание |
|---|---|
| [CODE_SIZE_GUIDELINES](development/development_docs/CODE_SIZE_GUIDELINES.md) | Начните обдумать разделение при 300 строк, разделение обязательно при 500 строк |
| [MODULE_ORGANIZATION_GUIDELINES](development/development_docs/MODULE_ORGANIZATION_GUIDELINES.md) | Каталог feature-unit, идеально 100-250 строк |
| [MODULE_SAFETY](development/development_docs/MODULE_SAFETY.md) | Трёхуровневая модель защиты (статическая/парсинг/проверка времени выполнения) |
| [ERROR_HANDLING](development/development_docs/ERROR_HANDLING.md) | Единый `api_error()`, `{ok, error, code, detail, hint}` |
| [API_RESPONSE_GUIDELINES](development/development_docs/API_RESPONSE_GUIDELINES.md) | `api_success()` / `api_error()` / `api_result()` |
| [ENTRYPOINT_MAP](development/development_docs/ENTRYPOINT_MAP.md) | Список всех входных точек модулей |
| [ACCIDENT_POINTS](development/development_docs/ACCIDENT_POINTS_AND_COMMON_LAYER_SPEED_GUIDE.md) | Стратегии предотвращения 6 критических ошибок |
| [UI_BUTTON_PRIORITY_GUIDELINES](development/development_docs/UI_BUTTON_PRIORITY_GUIDELINES.md) | Проектирование кнопок Tier A/B/C |
| [UI_STATE_SPEC](development/development_docs/UI_STATE_SPEC.md) | Шаблон гибридный Explorer/Library |
| [DOCUMENT_LIFECYCLE](development/development_docs/DOCUMENT_LIFECYCLE.md) | Правила расположения документов |
| [FUZZ_BURN_IN_TEST](development/development_docs/FUZZ_BURN_IN_TEST.md) | Тестирование фаззинга и burn-in API + UI |

### Другие документы по разработке

| Документ | Содержание |
|---|---|
| [ai-driven-development-principles](development/development_docs/ai-driven-development-principles.md) | Принципы проектирования AI-ориентированной разработки |
| [BATCH_API_STANDARD](development/development_docs/BATCH_API_STANDARD.md) | Договор пакетных операций |
| [EXTENSION_HOOKS_SPEC](development/development_docs/EXTENSION_HOOKS_SPEC.md) | Жизненный цикл хуков расширений |
| [REUSABLE_UI_WIDGETS](development/development_docs/REUSABLE_UI_WIDGETS.md) | Список переиспользуемых UI виджетов |
| [SD_NAI_PROMPT_SYNTAX_SPEC](development/development_docs/SD_NAI_PROMPT_SYNTAX_SPEC.md) | Спецификация синтаксиса промптов SD/NAI |
| [ENCODING_FALLBACK](development/development_docs/ENCODING_FALLBACK.md) | Кодировка имён файлов архива |
| [VISION_API_IMAGE_FORMATS](development/development_docs/VISION_API_IMAGE_FORMATS.md) | Таблица совместимости форматов изображений Vision API |
| [QA_HANDOFF](development/development_docs/QA_HANDOFF.md) | Результаты раунда QA и оставшиеся задачи |

### Журналы разработки и спецификации

| Документ | Содержание |
|---|---|
| [HAILO_SEMANTIC_SEARCH_DEVLOG](development/development_docs/HAILO_SEMANTIC_SEARCH_DEVLOG.md) | Журнал разработки Hailo-10H CLIP |
| [CLIP_ONNX_DEVLOG](development/development_docs/CLIP_ONNX_DEVLOG.md) | Журнал разработки CLIP ONNX мультибэкенда |
| [HAILO_DEVICE_CONTROL](development/development_docs/HAILO_DEVICE_CONTROL.md) | Управление устройством Hailo |
| [CHATLOG_ENHANCED_SPEC](development/development_docs/CHATLOG_ENHANCED_SPEC.md) | Расширенная спецификация журнала чатов |
| [TAURI_DESKTOP_APP](development/development_docs/TAURI_DESKTOP_APP.md) | Интеграция Tauri в десктоп |
| [EXTENSION_SPEC_FREEZE_PULLBACK_GENERATOR](development/development_docs/EXTENSION_SPEC_FREEZE_PULLBACK_GENERATOR_v0_2.md) | Спецификация расширения Freeze & Pull-back |
| [VIDEO_METADATA_V2_PLAN](development/development_docs/VIDEO_METADATA_V2_PLAN.md) | План метаданных видео v2 (Draft) |

## Пути импорта

Все импорты используют пути к реальным модулям напрямую. Механизм экранирования удалён.

**Примеры основных путей:**
- `core.services_core.db_api` — Доступ к БД (старый `core.db`)
- `core.configuration.api` — Управление конфигурацией (старый `core.config`)
- `core.extensions_core.runtime` — Время выполнения расширений (старый `core.extensions`)
- Новые функции добавляются прямо в директорию `core/<feature>_core/`

## Устранение неполадок и операции

- Руководство по отладке: [`troubleshooting/debug-playbook.md`](troubleshooting/debug-playbook.md)
- Частые ошибки (устаревшие): [`troubleshooting/common-errors.md`](troubleshooting/common-errors.md)
- Ловушки кодировки CJK / двухбайтовых символов: [`troubleshooting/cjk-2byte-encoding-pitfalls.md`](troubleshooting/cjk-2byte-encoding-pitfalls.md)
- Ошибка парсинга экранированных скобок: [`troubleshooting/escaped-brackets-parse-error.md`](troubleshooting/escaped-brackets-parse-error.md)

## Функции

| Документ | Статус | Содержание |
|---|---|---|
| [Руководство интеграции MCP](features/mcp-integration-guide.md) | Текущий | Управление yu_ai_manager из LLM |
| [NovelAI V4](features/novelai-v4.md) | Текущий | Формат промптов NovelAI V4, поддержка отрицательных для каждого персонажа |
| [Семантический поиск Hailo](features/hailo-semantic-search.md) | Реализовано → переход на ONNX | Справочное руководство по реализации Hailo-10H CLIP |
| [Автогенерация тегов Danbooru](features/danbooru-tag-gen-spec.md) | Реализовано (v2.77.0) | WD-Tagger + двухэтапный VLM |
| [Управление текстом и журналом чатов](features/text-chatlog-management-spec.md) | Текущий | Импорт журнала чатов, поиск FTS |
| [QR протокол v1](features/qr-protocol-v1.md) | Текущий | QR код для совместного доступа по сети LAN |
| [Тестирование производительности регулярных выражений](features/regex-search-benchmark.md) | Текущий | Производительность Regex |
| [Совместимость браузеров](features/browser-compatibility.md) | Текущий | Список поддерживаемых браузеров |

## Справочник API

- [Обзор API (аутентификация·CSRF·ограничение скорости)](api/README.md)
- [API поиска](api/search.md)
- [API файлов](api/files.md)
- [API сканирования](api/scan.md)
- [События SSE](api/events.md)
- [Переменные CSS темы](api/theming.md)

## Пользовательский интерфейс / Разработка плагинов

- [Руководство пользовательского интерфейса](custom-ui/README.md) — Разработка пользовательского интерфейса (quickstart, design, templates, advanced)
- [Руководство по разработке плагинов](plugin-development/getting-started.md) — Введение в разработку расширений
- [Справочник манифеста](plugin-development/manifest-reference.md) — Спецификация extension.json

## Установка

- FFmpeg: [`installation/ffmpeg.md`](installation/ffmpeg.md)
- Docker: [`development/development_docs/DOCKER_SETUP.md`](development/development_docs/DOCKER_SETUP.md)

## Исторические документы

Ниже приведены заметки по реализации и записи исправлений прошлых версий (расположены в `archive/docs_history/`).

- `DEBUG_INSTRUCTIONS_v2.5.4.md` — Инструкции по отладке v2.5.4
- `DARK_MODE_TAGS_IMPROVEMENT.md` — Предложение по улучшению тёмного режима тегов (реализовано)
- `EXTENSION_DRAFT.md` — Начальный черновик системы расширений (замена в plugin-development/)
