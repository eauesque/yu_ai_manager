# Справочник инструментов MCP

Полный список инструментов, предоставляемых MCP-сервером (Model Context Protocol) YU AI Manager.
Вызывая эти инструменты из Claude Desktop или других MCP-клиентов, можно автоматизировать управление библиотекой, её анализ и генерацию.

**Общее число инструментов: 521**

## Оглавление

- [Search & Browse (10)](#search--browse-10)
- [Collections (7)](#collections-7)
- [Ratings & Tags (5)](#ratings--tags-5)
- [Favorites (8)](#favorites-8)
- [Annotations (4)](#annotations-4)
- [Scanning (14)](#scanning-14)
- [Scan Roots (9)](#scan-roots-9)
- [Hash & Duplicates (7)](#hash--duplicates-7)
- [Wait / Progress (2)](#wait--progress-2)
- [AI Analysis (25)](#ai-analysis-25)
- [WD-Tagger (15)](#wd-tagger-14)
- [Semantic Search / CLIP (12)](#semantic-search--clip-12)
- [YOLO Object Detection (17)](#yolo-object-detection-17)
- [OCR (19)](#ocr-19)
- [SD WebUI Bridge (14)](#sd-webui-bridge-14)
- [ComfyUI Bridge (13)](#comfyui-bridge-13)
- [NovelAI Bridge (8)](#novelai-bridge-8)
- [Hailo GenAI (10)](#hailo-genai-10)
- [Hailo Chat (7)](#hailo-chat-7)
- [Hailo Remote Tagger (7)](#hailo-remote-tagger-7)
- [Tagger Server Registry (13)](#tagger-server-registry-13)
- [Prompt Library (21)](#prompt-library-21)
- [Prompt Simulator (6)](#prompt-simulator-6)
- [Prompt Syntax (1)](#prompt-syntax-1)
- [SD/NAI Conversion (3)](#sdnai-conversion-3)
- [Chat Logs (16)](#chat-logs-16)
- [Markdown Viewer (8)](#markdown-viewer-8)
- [Freeze & Pull-back (6)](#freeze--pull-back-6)
- [Speech-to-Text (8)](#speech-to-text-8)
- [Statistics (6)](#statistics-6)
- [Profiles (11)](#profiles-11)
- [File Operations (4)](#file-operations-4)
- [SVG Rasterization (2)](#svg-rasterization-2)
- [Download (1)](#download-1)
- [Video Analysis (3)](#video-analysis-3)
- [Backup (5)](#backup-5)
- [Archive Cleanup (7)](#archive-cleanup-7)
- [Auto Scan Watcher (3)](#auto-scan-watcher-3)
- [Scheduler (6)](#scheduler-6)
- [Webhooks (9)](#webhooks-9)
- [Extensions (25)](#extensions-25)
- [UI Management (4)](#ui-management-4)
- [Settings (18)](#settings-18)
- [SNS Sharing (15)](#sns-sharing-15)
- [LAN Share (2)](#lan-share-2)
- [MCP Client (8)](#mcp-client-8)
- [Cross Search (9)](#cross-search-9)
- [Tag Dictionary (6)](#tag-dictionary-6)
- [Trophies (1)](#trophies-1)
- [Source Code Browsing (3)](#source-code-browsing-3)
- [Help (3)](#help-3)
- [System Info (3)](#system-info-3)
- [System Update (5)](#system-update-5)
- [Suggestions (4)](#suggestions-4)
- [Logs & Debug (9)](#logs--debug-9)
- [Agent Safety Gateway (25)](#agent-safety-gateway-25)
- [GitHub Integration (12)](#github-integration-12)
- [Debug Tools (9)](#debug-tools-9)
- [LoRA Dataset Manager (15)](#lora-dataset-manager-14)
- [LLM Endpoints (5)](#llm-endpoints-5)
- [LLM Chat (1)](#llm-chat-1)
- [Server Mode (1)](#server-mode-1)

---

## Настройка

### Переменные окружения

| Переменная | Описание | Значение по умолчанию |
|------------|----------|-----------------------|
| `YU_BASE_URL` | URL сервера YU AI Manager | `http://localhost:5000` |
| `YU_API_KEY` | API Key (Bearer-аутентификация) | (нет) |
| `YU_DEBUG_MODE` | `1` — включить отладочные инструменты | `0` |

### Пример настройки Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "yu-ai-manager": {
      "command": "/path/to/venv/bin/python",
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

### Уведомления о прогрессе

Инструменты `wait_for_scan` / `wait_for_batch` поддерживают MCP Notifications:
- **Клиенты с поддержкой progressToken**: получают прогресс в реальном времени через `notifications/progress`
- **Клиенты без поддержки**: блокирующе ожидают и по завершении возвращают итоговый результат

---

## Search & Browse (10)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `search_images` | Поиск изображений с различными фильтрами | `query`: str = '', `sort`: str = 'date', `limit`: int = 20, `cursor`: str = '', `from_date`: str = '', `to_date`: str = '', `file_format`: str = 'all', `min_rating`: str = '', `max_rating`: str = '', `in_prompt`: str = '', `fav_only`: bool = False, `collection_id`: int = 0, `also_path`: bool = False |
| `search_images_grouped` | Поиск изображений с группировкой по каталогам | `query`: str = '', `sort`: str = 'date', `limit`: int = 20, `from_date`: str = '', `to_date`: str = '' |
| `search_union` | Объединение нескольких запросов | `queries`: list |
| `get_image_detail` | Получить все метаданные изображения | `file_id`: int |
| `get_library_stats` | Статистика библиотеки | — |
| `get_file_info` | Путь к файлу и метаданные | `file_id`: int |
| `get_groups_index` | Индекс групп каталогов | — |
| `get_group_members` | Список участников группы | `group`: str |
| `get_container_members` | Список участников контейнера ZIP/RAR | `file_id`: int |
| `file_search` | Поиск файла в БД по пути/имени | `query`: str, `meta_filter`: str = "all", `limit`: int = 100 |

## Collections (7)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `list_collections` | Список всех коллекций | — |
| `create_collection` | Создать коллекцию | `name`: str |
| `rename_collection` | Переименовать коллекцию | `collection_id`: int, `name`: str |
| `delete_collection` | Удалить коллекцию | `collection_id`: int |
| `reorder_collections` | Изменить порядок коллекций | `order`: list |
| `add_to_collection` | Добавить изображения в коллекцию | `collection_id`: int, `file_ids`: list, `expected_count`: int = 0 |
| `remove_from_collection` | Удалить изображения из коллекции | `collection_id`: int, `file_ids`: list, `expected_count`: int = 0 |

## Ratings & Tags (5)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `rate_images` | Пакетно установить рейтинг нескольких изображений | `items`: list, `expected_count`: int = 0 |
| `get_ratings` | Получить рейтинги файлов | `file_ids`: str |
| `get_ratings_stats` | Статистика рейтингов | — |
| `set_tags` | Добавить/удалить пользовательские теги у нескольких изображений | `items`: list, `expected_count`: int = 0 |
| `normalize_tags` | Нормализация тегов в БД | — |

## Favorites (8)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `toggle_favorite` | Переключить избранное | `file_id`: int |
| `check_favorite` | Проверить статус избранного | `file_id`: int |
| `check_favorite_collections` | Проверить принадлежность избранного к коллекциям | `file_id`: int |
| `list_favorites` | Список избранного | `limit`: int = 50, `offset`: int = 0 |
| `fav_batch_add` | Пакетное добавление нескольких файлов в избранное | `file_ids`: list, `collection_id`: int = 1 |
| `fav_batch_remove` | Пакетное удаление файлов из избранного | `file_ids`: list, `collection_id`: int = 0 |
| `fav_export_folder` | Экспорт избранного в папку на сервере | `dest_path`: str, `collection_id`: int = 0 |
| `fav_images` | Список изображений в коллекции избранного | `collection_id`: int = 0 |

## Annotations (4)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `set_annotations` | Сохранить аннотации (upsert) | `items`: list, `expected_count`: int = 0 |
| `get_annotations` | Получить аннотации изображения | `file_id`: int, `source`: str = '', `key`: str = '' |
| `search_annotations` | Сквозной поиск по аннотациям | `source`: str = '', `key`: str = '', `min_confidence`: str = '', `max_confidence`: str = '', `limit`: int = 100, `offset`: int = 0 |
| `delete_annotations` | Удалить аннотации | `source`: str, `file_ids`: Optional = None, `key`: str = '' |

## Scanning (14)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `trigger_scan` | Запустить сканирование всех корней | — |
| `start_scan` | Запустить сканирование указанного пути или всех корней | `path`: str = '' |
| `get_scan_status` | Прогресс сканирования | — |
| `cancel_scan` | Отменить сканирование | — |
| `resume_scan` | Возобновить прерванное сканирование | — |
| `dismiss_interrupted_scan` | Отбросить состояние прерывания | — |
| `get_scan_interrupted` | Сведения о прерванных сканированиях | — |
| `get_scan_errors` | Список ошибок сканирования | `error_type`: str = '', `resolved`: str = 'false', `limit`: int = 50 |
| `resolve_scan_error` | Пометить ошибку как решённую | `error_id`: int |
| `clear_scan_errors` | Очистить решённые ошибки | — |
| `get_scanned_roots` | Список уже отсканированных корней | — |
| `scan_queue_list` | Список элементов в очереди сканирования | -- |
| `scan_queue_remove` | Удалить элемент из очереди сканирования | `queue_id`: str |
| `scan_queue_clear` | Полностью очистить очередь сканирования | -- |

## Scan Roots (9)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `list_scan_roots` | Список корней сканирования | — |
| `add_scan_root` | Добавить корень сканирования | `path`: str |
| `edit_scan_root` | Изменить путь корня сканирования | `index`: int, `path`: str |
| `remove_scan_root` | Удалить корень сканирования | `index`: int |
| `toggle_scan_root` | Включить/выключить корень сканирования | `index`: int |
| `reorder_scan_roots` | Изменить порядок корней сканирования | `order`: list |
| `scan_directory` | Сканирование конкретного каталога | `path`: str |
| `get_checkpoints` | Доступные чекпоинты моделей | — |
| `purge_scanned_roots` | Удалить записи об отсканированных корнях | — |

## Hash & Duplicates (7)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `find_duplicates` | Поиск дубликатов | `method`: str = 'hash' |
| `find_similar` | Поиск похожих изображений по перцептуальному хэшу | `file_id`: int, `threshold`: int = 5 |
| `compute_hashes` | Запустить задачу вычисления хэшей файлов | `hash_type`: str = 'both' |
| `delete_duplicates` | Удалить дубликаты | `groups`: list, `mode`: str = 'soft' |
| `start_hash_backfill` | Массовое вычисление недостающих хэшей | — |
| `cancel_hash_backfill` | Отменить вычисление хэшей | — |
| `get_hash_backfill_status` | Прогресс вычисления хэшей | — |

## Wait / Progress (2)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `wait_for_scan` | Ожидание завершения сканирования (с уведомлениями о прогрессе) | `timeout`: int = 600 |
| `wait_for_batch` | Ожидание завершения пакетной задачи (с уведомлениями о прогрессе) | `job_id`: str = 'ai_analysis', `timeout`: int = 600 |

## AI Analysis (25)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `analyze_image` | AI-анализ одного изображения | `file_id`: int |
| `analyze_batch` | Пакетный AI-анализ нескольких изображений | `file_ids`: list, `expected_count`: int = 0, `server_ids`: list = None |
| `analyze_batch_cancel` | Отмена выполняющейся пакетной задачи AI-анализа | -- |
| `get_analysis_result` | Получить результат анализа | `file_id`: int |
| `get_analysis_stats` | Статистика анализа | — |
| `get_analysis_config` | Получить настройки анализа | — |
| `save_analysis_config` | Сохранить настройки анализа | `config`: dict |
| `get_available_engines` | Список доступных движков | — |
| `get_ollama_models` | Список моделей Ollama | — |
| `test_ollama_connection` | Тест соединения с Ollama | — |
| `get_openai_compat_models` | Список моделей OpenAI-совместимого API | — |
| `test_openai_compat_connection` | Тест соединения с OpenAI-совместимым API | — |
| `list_ai_servers` | Список зарегистрированных AI-серверов | — |
| `add_ai_server` | Зарегистрировать AI-сервер | `name`: str, `type`: str, `config`: dict, `priority`: int = 50, `enabled`: bool = True |
| `update_ai_server` | Обновить настройки AI-сервера | `server_id`: str, `name`: str = '', `config`: dict = None, `priority`: int = -1, `enabled`: bool = True |
| `remove_ai_server` | Удалить AI-сервер | `server_id`: str |
| `set_active_ai_server` | Переключить активный сервер | `server_id`: str |
| `test_ai_server` | Тест соединения с AI-сервером | `server_id`: str |
| `reorder_ai_servers` | Изменить приоритет серверов | `order`: list |
| `migrate_ai_servers` | Миграция со старой конфигурации | — |
| `analyze_prompt_trends` | Анализ трендов промптов | `limit`: int = 100 |
| `get_trend_history` | История анализа трендов | `limit`: int = 20 |
| `delete_trend_history` | Удалить историю трендов | `history_id`: int |
| `analyze_video` | Мульти-кадровый анализ видео (Vision LLM) | `file_id`: int, `engine`: str = "", `model`: str = "", `keyframe_count`: int = 4 |
| `transcribe_audio` | Транскрибация аудио/видеофайла с помощью Whisper | `file_id`: int, `engine`: str = "", `model`: str = "", `language`: str = "" |
| `get_audio_analysis_status` | Проверка доступности анализа аудио (ffmpeg, whisper) | -- |

## WD-Tagger (15)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `wd_tagger_tag_file` | Инференс тегов для одного файла | `file_id`: int |
| `wd_tagger_batch` | Пакетный инференс тегов для нескольких файлов | `file_ids`: list, `expected_count`: int = 0 |
| `wd_tagger_batch_cancel` | Отмена выполняющейся пакетной задачи WD-Tagger | -- |
| `wd_tagger_get_tags` | Получить теги WD-Tagger файла | `file_id`: int |
| `wd_tagger_delete_tags` | Удалить теги WD-Tagger файла | `file_id`: int |
| `wd_tagger_delete_tags_batch` | Пакетное удаление тегов WD-Tagger у нескольких файлов | `file_ids`: list, `expected_count`: int = 0 |
| `wd_tagger_get_xmp` | Получить XMP-метаданные | `file_id`: int |
| `wd_tagger_stats` | Статистика тегов | — |
| `wd_tagger_untagged` | Список файлов без тегов | `limit`: int = 50, `offset`: int = 0 |
| `wd_tagger_get_config` | Получить настройки | — |
| `wd_tagger_save_config` | Сохранить настройки | `config`: dict |
| `wd_tagger_model_status` | Статус загрузки модели | — |
| `wd_tagger_download_model` | Загрузка модели | — |
| `wd_tagger_vlm_test` | Тест соединения с VLM-сервером | `url`: str |
| `wd_tagger_vlm_models` | Список моделей на VLM-сервере | `url`: str |

## Semantic Search / CLIP (12)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `semantic_search` | Поиск изображений на естественном языке | `query`: str, `limit`: int = 50, `threshold`: float = 0.2 |
| `semantic_status` | Статус расширения | — |
| `semantic_backend_info` | Информация о CLIP-бэкенде | — |
| `semantic_model_status` | Статус модели | — |
| `semantic_model_download` | Загрузка модели CLIP | — |
| `semantic_index_start` | Запустить построение индекса | `batch_size`: int = 32, `backend`: str = 'auto' |
| `semantic_index_status` | Прогресс индексации | — |
| `semantic_index_stop` | Остановить построение индекса | — |
| `semantic_index_clear` | Очистить индекс | — |
| `semantic_caption_start` | Запустить пакетную генерацию подписей | `batch_size`: int = 50 |
| `semantic_caption_status` | Прогресс генерации подписей | — |
| `semantic_caption_stop` | Остановить генерацию подписей | — |

## YOLO Object Detection (17)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `yolo_status` | Статус расширения | — |
| `yolo_detect_start` | Запуск детекции объектов | `file_ids`: list = None, `undetected_only`: bool = True |
| `yolo_detect_status` | Прогресс задачи детекции | — |
| `yolo_detect_stop` | Остановка детекции | — |
| `yolo_get_results` | Получить результаты детекции для файла | `file_id`: int |
| `yolo_search` | Поиск изображений по меткам | `labels`: str = '', `min_confidence`: float = 0.0, `limit`: int = 50, `offset`: int = 0 |
| `yolo_clear_results` | Очистить результаты детекции | `file_ids`: list = None |
| `yolo_model_status` | Статус модели | — |
| `yolo_model_download` | Загрузка YOLO HEF-модели | — |
| `yolo_list_labels` | Список обнаруженных меток | — |
| `yolo_stream_sources` | Список и статус источников потока | — |
| `yolo_stream_start` | Запуск источника потока | `source_id`: str |
| `yolo_stream_stop` | Остановка источника потока | `source_id`: str |
| `yolo_stream_add_source` | Добавить источник потока | `id`: str, `url`: str, `name`: str = "" |
| `yolo_stream_rules` | Список правил детекции | — |
| `yolo_stream_add_rule` | Добавить правило детекции | `id`: str, `name`: str, `classes`: list, `min_confidence`: float = 0.7, `cooldown_sec`: int = 60, `actions`: list = [] |
| `yolo_stream_status` | Общий статус потока (пайплайн, источники, правила, запись) | — |

## OCR (19)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `ocr_extract` | Извлечение текста из изображения (OCR) | `file_id`: int, `task`: str = "ocr", `language`: str = "auto", `server_id`: str = "" |
| `ocr_batch` | Пакетный OCR нескольких файлов | `file_ids`: list, `task`: str = "ocr", `language`: str = "auto", `server_id`: str = "", `expected_count`: int = 0 |
| `ocr_get_result` | Получить результат OCR файла | `file_id`: int, `task`: str = "", `engine`: str = "", `all_results`: bool = False |
| `ocr_delete` | Удалить результат OCR файла | `file_id`: int, `task`: str = "", `engine`: str = "" |
| `ocr_export` | Экспорт результата OCR в заданном формате | `file_id`: int, `format`: str = "md", `task`: str = "" |
| `ocr_translate` | Перевод результата OCR | `file_id`: int, `target_lang`: str = "en", `server_id`: str = "", `task`: str = "" |
| `ocr_get_translations` | Получить переводы файла | `file_id`: int, `target_lang`: str = "" |
| `ocr_video` | OCR по ключевым кадрам видео | `file_id`: int, `task`: str = "ocr", `language`: str = "auto", `server_id`: str = "", `keyframe_count`: int = 4 |
| `ocr_bbox` | Определение bbox для результатов OCR | `file_id`: int, `task`: str = "", `server_id`: str = "" |
| `ocr_overlay` | Генерация наложения OCR на изображение | `file_id`: int, `mode`: str = "translated", `target_lang`: str = "", `format`: str = "png" |
| `ocr_export_batch` | Пакетный экспорт результатов OCR | `file_ids`: list, `format`: str = "", `output_dir`: str = "", `overlay_mode`: str = "translated", `target_lang`: str = "" |
| `ocr_pdf` | OCR для PDF-документа | `file_id`: int, `task`: str = "ocr_document", `language`: str = "auto", `server_id`: str = "", `page_range`: str = "" |
| `ocr_engines` | Список доступных OCR-движков и их возможностей | -- |
| `ocr_profiles` | Список всех профилей возможностей моделей | -- |
| `ocr_profiles_fetch` | Получить профили моделей сообщества по URL и смёржить | `url`: str |
| `ocr_profile_update` | Ручное обновление оценок модели | `model_prefix`: str, `scores`: dict |
| `ocr_benchmark` | Измерение точности OCR через бенчмарк | `task`: str = "ocr", `server_id`: str = "", `benchmark_dir`: str = "" |
| `ocr_benchmark_cases` | Список доступных тест-кейсов бенчмарка | `benchmark_dir`: str = "" |
| `ocr_npu_status` | Доступность NPU и рекомендации по оптимизации | `task`: str = "ocr" |

## SD WebUI Bridge (14)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `sd_test_connection` | Тест соединения | — |
| `sd_generate` | Генерация изображения (txt2img) | `prompt`: str, `negative_prompt`: str = '', `steps`: int = 28, `sampler`: str = 'Euler a', `cfg_scale`: float = 7.0, `width`: int = 512, `height`: int = 768, `seed`: int = -1, `expand_wildcards`: bool = False |
| `sd_get_progress` | Прогресс генерации | — |
| `sd_cancel` | Отмена генерации | — |
| `sd_list_models` | Список моделей-чекпоинтов | — |
| `sd_list_samplers` | Список семплеров | — |
| `sd_list_loras` | Список LoRA | `q`: str = '' |
| `sd_list_embeddings` | Список Embedding | `q`: str = '' |
| `sd_list_scripts` | Список скриптов | — |
| `sd_get_script_info` | Детали скрипта | — |
| `sd_list_extensions` | Список расширений | — |
| `sd_list_upscalers` | Список апскейлеров | — |
| `sd_get_config` | Получить настройки | — |
| `sd_save_config` | Сохранить настройки | `api_url`: str = '', `save_folder`: str = '', `auto_save`, `auto_import`, `default_sampler`: str = '' |

## ComfyUI Bridge (13)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `comfyui_test_connection` | Тест соединения | — |
| `comfyui_generate` | Генерация изображения (txt2img) | `prompt`: str, `negative_prompt`: str = '', `steps`: int = 20, `sampler_name`: str = 'euler', `scheduler`: str = 'normal', `cfg`: float = 7.0, `width`: int = 512, `height`: int = 768, `seed`: int = -1, `ckpt_name`: str = '', `expand_wildcards`: bool = False, `image_format`: str = 'png' |
| `comfyui_generate_json` | Генерация по JSON-воркфлоу | `workflow`: str |
| `comfyui_get_progress` | Прогресс генерации | — |
| `comfyui_cancel` | Отмена генерации | — |
| `comfyui_list_models` | Список моделей-чекпоинтов | — |
| `comfyui_list_samplers` | Список семплеров | — |
| `comfyui_list_schedulers` | Список планировщиков | — |
| `comfyui_list_loras` | Список LoRA | `q`: str = '' |
| `comfyui_list_embeddings` | Список Embedding | `q`: str = '' |
| `comfyui_list_custom_nodes` | Список кастомных нод | `q`: str = '' |
| `comfyui_get_config` | Получить настройки | — |
| `comfyui_save_config` | Сохранить настройки | `api_url`: str = '', `save_folder`: str = '', `auto_save`, `auto_import`, `default_sampler`: str = '', `default_scheduler`: str = '' |

## NovelAI Bridge (8)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `nai_test_connection` | Тест соединения | — |
| `nai_get_anlas` | Получить баланс Anlas | — |
| `nai_generate` | Генерация изображения | `prompt`: str, `negative_prompt`: str = '', `width`: int = 832, `height`: int = 1216, `steps`: int = 28, `sampler`: str = '', `noise_schedule`: str = '', `seed`: int = -1, `model`: str = '', `cfg_scale`: float = 5.0 |
| `nai_list_models` | Список моделей | — |
| `nai_list_samplers` | Список семплеров | — |
| `nai_list_noise_schedules` | Список расписаний шума | — |
| `nai_get_config` | Получить настройки | — |
| `nai_save_config` | Сохранить настройки | `api_key`: str = '', `save_folder`: str = '', `auto_save`: bool = True, `auto_import`: bool = True, `default_model`: str = '' |

## Hailo GenAI (10)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `hailo_genai_status` | Статус расширения | — |
| `hailo_genai_model_status` | Статус загрузки модели | — |
| `hailo_genai_model_download` | Загрузка модели | `model_name`: str = '' |
| `hailo_genai_model_unload` | Выгрузка модели | — |
| `hailo_llm_generate` | Генерация текста LLM | `prompt`: str, `max_tokens`: int = 256, `temperature`: float = 0.7, `system_prompt`: str = '' |
| `hailo_llm_clear_context` | Очистка контекста LLM | — |
| `hailo_vlm_generate` | Генерация текста по изображению (VLM) | `file_id`: int, `prompt`: str = 'Describe this image.', `max_tokens`: int = 256 |
| `hailo_benchmark` | Бенчмарк производительности Hailo LLM | `prompt`: str, `runs`: int = 3, `max_tokens`: int = 256, `temperature`: float = 0.7, `model`: str = "qwen2.5-1.5b-chat" |
| `hailo_benchmark_compare` | Сравнение производительности Hailo vs Ollama LLM | `prompt`: str, `runs`: int = 3, `max_tokens`: int = 256, `hailo_model`: str, `ollama_model`: str |
| `hailo_genai_openai_info` | Сведения об OpenAI-совместимом API Hailo GenAI | -- |

## Hailo Chat (7)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `hailo_chat_new` | Создать новый диалог Hailo Chat | `model`: str = "qwen2.5-1.5b-chat" |
| `hailo_chat_list` | Список диалогов Hailo Chat | `limit`: int = 50, `offset`: int = 0 |
| `hailo_chat_get` | Получить диалог со всеми сообщениями | `conversation_id`: int |
| `hailo_chat_active` | Получить ID текущего активного диалога | -- |
| `hailo_chat_search` | Веб-поиск через DuckDuckGo (для инъекции контекста) | `query`: str, `max_results`: int = 5 |
| `hailo_chat_rename` | Переименовать диалог | `conversation_id`: int, `title`: str |
| `hailo_chat_delete` | Удалить диалог | `conversation_id`: int |

## Hailo Remote Tagger (7)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `hailo_tagger_tag_file` | Тегирование одного файла через Hailo-таггер | `file_id`: int |
| `hailo_tagger_batch` | Пакетное тегирование нескольких файлов (до 500) | `file_ids`: list, `expected_count`: int = 0 |
| `hailo_tagger_status` | Состояние соединения с Hailo-таггером | — |
| `hailo_tagger_get_config` | Получить настройки Hailo-таггера | — |
| `hailo_tagger_save_config` | Сохранить настройки Hailo-таггера | `config`: dict |
| `hailo_tagger_get_tags` | Получить Hailo-теги файла | `file_id`: int |
| `hailo_tagger_delete_tags` | Удалить Hailo-теги файла | `file_id`: int |

## Tagger Server Registry (13)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `tagger_servers_list` | Список зарегистрированных таггер-серверов и режим распределения | -- |
| `tagger_servers_add` | Добавить таггер-сервер | `name`: str, `type`: str, `config`: dict, `priority`: int = 50, `enabled`: bool = True |
| `tagger_servers_update` | Обновить настройки таггер-сервера | `server_id`: str, `updates`: dict |
| `tagger_servers_remove` | Удалить таггер-сервер | `server_id`: str |
| `tagger_servers_test` | Тест соединения с таггер-сервером | `server_id`: str |
| `tagger_servers_health` | Проверка здоровья всех активных серверов | -- |
| `tagger_servers_set_mode` | Установить режим распределения (single/parallel/idle_first) | `mode`: str |
| `tagger_servers_batch` | Распределённое пакетное тегирование (work-stealing) | `file_ids`: list = None, `limit`: int = 500, `force`: bool = False, `threshold`: float = None |
| `tagger_servers_batch_cancel` | Отменить выполняющуюся пакетную задачу кластера таггеров | -- |
| `tagger_servers_tags` | Получить теги файла (через таггер) | `file_id`: int |
| `tagger_servers_delete_tags` | Удалить теги файла (через таггер) | `file_id`: int |
| `tagger_servers_stats` | Статистика таггера (число нетегированных файлов) | -- |
| `tagger_servers_migrate_legacy` | Миграция устаревшей конфигурации hailo_tagger в формат реестра | -- |

## Prompt Library (21)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `search_prompts` | Поиск промптов | `query`: str = '', `folder_id`: int = 0, `tag_id`: int = 0, `sort`: str = 'updated_at', `order`: str = 'desc', `limit`: int = 50, `offset`: int = 0 |
| `get_prompt` | Получить детали промпта | `prompt_id`: int |
| `create_prompt` | Создать промпт | `title`: str, `positive`: str = '', `negative`: str = '', `memo`: str = '', ... |
| `create_prompt_from_file` | Создать промпт из метаданных изображения | `file_id`: int |
| `update_prompt` | Обновить промпт (частично) | `prompt_id`: int, ... |
| `delete_prompt` | Удалить промпт | `prompt_id`: int |
| `list_prompt_folders` | Список папок | — |
| `create_prompt_folder` | Создать папку | `name`: str |
| `update_prompt_folder` | Переименовать папку | `folder_id`: int, `name`: str |
| `delete_prompt_folder` | Удалить папку | `folder_id`: int |
| `move_prompt_to_folder` | Переместить промпт в папку | `prompt_id`: int, `folder_id`: int |
| `remove_prompt_from_folder` | Вынести промпт из папки (в корень) | `prompt_id`: int |
| `list_prompt_tags` | Список тегов | — |
| `create_prompt_tag` | Создать тег | `name`: str |
| `delete_prompt_tag` | Удалить тег | `tag_id`: int |
| `set_prompt_tags` | Установить теги промпта | `prompt_id`: int, `tag_ids`: list |
| `bulk_delete_prompts` | Массовое удаление | `prompt_ids`: list |
| `bulk_move_prompts` | Массовое перемещение | `prompt_ids`: list, `folder_id`: int |
| `bulk_tag_prompts` | Массовое тегирование | `prompt_ids`: list, `tag_ids`: list |
| `export_prompts` | Экспорт всех промптов в JSON | — |
| `import_prompts` | Импорт промптов из JSON | `data`: dict |

## Prompt Simulator (6)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `prompt_dp_analyze` | Разбор синтаксиса Dynamic Prompts | `text`: str |
| `prompt_emphasis` | Преобразование синтаксиса эмфазы | `text`: str, `format`: str = 'a1111' |
| `prompt_convert` | Преобразование форматов A1111 ↔ NAI | `text`: str, `from_format`: str = 'a1111', `to_format`: str = 'nai' |
| `prompt_list_wildcards` | Список wildcards | — |
| `prompt_set_wildcard_dirs` | Установка каталогов wildcards | `dirs`: list |
| `prompt_danbooru_autocomplete` | Автодополнение тегов Danbooru | `q`: str |

## Prompt Syntax (1)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `analyze_prompt_syntax` | Разбор синтаксиса промпта (токены) | `text`: str, `engine`: str = 'a1111' |

## SD/NAI Conversion (3)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `convert_sd_to_nai` | Преобразование промпта SD → NAI | `text`: str |
| `convert_nai_to_sd` | Преобразование промпта NAI → SD | `text`: str |
| `convert_prompt_batch` | Пакетное преобразование промптов | `items`: list, `direction`: str = 'sd-to-nai' |

## Chat Logs (16)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `search_chat_logs` | Полнотекстовый поиск FTS5 | `query`: str = '', `source`: str = '', `model`: str = '', `limit`: int = 50, ... |
| `search_chat_logs_grouped` | Поиск с группировкой по диалогам | `query`: str, `source`: str = '', `limit`: int = 20 |
| `get_conversation` | Детали диалога (все сообщения) | `conversation_id`: int |
| `get_chat_full` | Алиас для get_conversation | `conversation_id`: int |
| `get_chat_summary` | Сводка, сгенерированная AI | `conversation_id`: int |
| `get_chat_decisions` | Решения, извлечённые AI | `conversation_id`: int |
| `get_related_conversations` | Связанные диалоги | `conversation_id`: int, `limit`: int = 10 |
| `find_chat_by_entity` | Поиск диалогов по сущности | `entity_type`: str, `entity_value`: str, `limit`: int = 50 |
| `search_chat_by_topic` | Поиск по теме | `topic`: str, `limit`: int = 50 |
| `search_decisions` | Сквозной поиск по решениям | `query`: str, `limit`: int = 50 |
| `import_chat_log` | Импорт из локального файла | `source`: str, `json_path`: str |
| `get_chatlog_import_status` | Прогресс импорта | — |
| `get_chatlog_stats` | Статистика журнала чатов | — |
| `delete_conversation` | Удалить диалог | `conversation_id`: int |
| `reprocess_chat_logs` | Повторная обработка AI | `target`: str = 'unprocessed' |
| `text_search` | Сквозной поиск по MD/чатам/промптам | `query`: str, `target`: str = 'md,chat,prompt', `limit`: int = 20 |

## Markdown Viewer (8)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `search_md_files` | Поиск по Markdown-файлам | `query`: str = '', `path_filter`: str = '', `limit`: int = 50, `offset`: int = 0 |
| `get_md_content` | Получить содержимое файла | `file_id`: int |
| `get_md_scan_roots` | Список корней сканирования | — |
| `set_md_scan_roots` | Установка корней сканирования | `roots`: list |
| `remove_md_scan_root` | Удаление корня сканирования | `index`: int |
| `trigger_md_scan` | Запуск сканирования | — |
| `get_md_scan_status` | Прогресс сканирования | — |
| `get_md_stats` | Статистика | — |

## Freeze & Pull-back (6)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `generate_freeze_pullback` | Генерация видео Ken Burns | `file_id`: int, `hold_seconds`: float = 2.0, `pull_seconds`: float = 5.0, `fps`: int = 30, ... |
| `get_fpb_status` | Статус задачи рендеринга | — |
| `fpb_check` | Проверка предусловий (ffmpeg и т. п.) | — |
| `fpb_cancel` | Отмена генерации | — |
| `fpb_list_outputs` | Список выходных файлов | — |
| `fpb_delete_output` | Удалить выходной файл | `filename`: str |

## Speech-to-Text (8)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `s2t_status` | Статус бэкенда | — |
| `s2t_transcribe_video` | Транскрибация видео/аудио | `file_id`: int, `language`: str = '' |
| `s2t_batch_transcribe` | Пакетная транскрибация | `file_ids`: list, `language`: str = '', `expected_count`: int = 0 |
| `s2t_get_transcript` | Получить сохранённую транскрипцию | `file_id`: int |
| `s2t_stream_start` | Запуск потоковой транскрибации | `source_url`: str, `language`: str = 'ja', `mode`: str = 'chunk' |
| `s2t_stream_stop` | Остановка потоковой транскрибации | — |
| `s2t_stream_status` | Статус потока | — |
| `s2t_stream_transcript` | Получить результат потоковой транскрибации | — |

## Statistics (6)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `get_stats_timeline` | Статистика по временной шкале | `period`: str = 'daily' |
| `get_stats_hourly` | Статистика по часам | — |
| `get_stats_models` | Статистика использования моделей | — |
| `get_stats_resolutions` | Статистика распределения разрешений | — |
| `get_stats_story` | Повествовательный рассказ о библиотеке | — |
| `get_monthly_report` | Месячный отчёт | `month`: str = '' |

## Profiles (11)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `list_profiles` | Список профилей | — |
| `get_profile` | Получить профиль | `name`: str |
| `create_profile` | Создать профиль | `name`: str, `description`: str = '' |
| `update_profile` | Обновить профиль | `name`: str, `settings`: dict |
| `delete_profile` | Удалить профиль | `name`: str |
| `duplicate_profile` | Дублировать профиль | `name`: str, `new_name`: str |
| `rename_profile` | Переименовать профиль | `name`: str, `new_name`: str |
| `toggle_profile_favorite` | Переключить избранное | `name`: str |
| `export_profile` | Экспорт профиля | `name`: str |
| `import_profile` | Импорт профиля из экспортированных данных | `qr_data`: str, `mode`: str = "full" |
| `import_profile_preview` | Предпросмотр импорта профиля | `qr_data`: str |

## File Operations (4)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `convert_image` | Преобразование формата изображения | `file_id`: int, `format`: str = 'webp' |
| `extract_from_zip` | Извлечение файла из ZIP | `file_id`: int, `members`: list |
| `inspect_metadata` | Инспекция сырых метаданных | `file_id`: int |
| `get_share_link` | Генерация ссылки для общего доступа | `file_id`: int |

## SVG Rasterization (2)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `svg_info` | Информация о доступности и бэкенде растеризации SVG | — |
| `svg_rasterize` | Растеризация SVG в PNG/WebP. Возвращаемый base64 можно использовать напрямую как вход img2img | `file_id`: int = 0, `svg_path`: str = '', `svg_data`: str = '', `width`: int = 1024, `height`: int = 1024, `format`: str = 'png', `background`: str = '' |

## Download (1)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `batch_download_zip` | Скачать несколько изображений в виде ZIP | `file_ids`: list, `expected_count`: int = 0 |

## Video Analysis (3)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `get_video_analysis_config` | Получить настройки анализа видео | — |
| `save_video_analysis_config` | Сохранить настройки анализа видео | `config`: dict |
| `get_video_analysis_status` | Статус анализа видео | — |

## Backup (5)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `list_backups` | Список резервных копий | — |
| `create_backup` | Создать резервную копию | — |
| `restore_backup` | Восстановить резервную копию | `filename`: str |
| `delete_backup` | Удалить резервную копию | `filename`: str |
| `get_backup_status` | Статус резервного копирования | — |

## Archive Cleanup (7)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `archive_cleanup_scan` | Сканирование пар архивов | `path`: str = '' |
| `archive_cleanup_execute` | Выполнить очистку | `actions`: list, `expected_count`: int = 0 |
| `archive_cleanup_llm_verify` | Валидация действия через LLM (одиночная) | `file_path`: str, `action`: str |
| `archive_cleanup_llm_verify_batch` | Валидация действий через LLM (пакетная) | `items`: list |
| `archive_cleanup_get_llm_config` | Получить настройки LLM | — |
| `archive_cleanup_save_llm_config` | Сохранить настройки LLM | `config`: dict |
| `archive_cleanup_list_models` | Список доступных LLM-моделей | — |

## Auto Scan Watcher (3)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `auto_scan_info` | Статус мониторинга | — |
| `auto_scan_start` | Запуск наблюдения за файлами | — |
| `auto_scan_stop` | Остановка наблюдения за файлами | — |

## Scheduler (6)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `get_scheduler_status` | Статус планировщика задач и зарегистрированные задания | -- |
| `list_scheduled_jobs` | Список всех плановых задач с триггерами и временем следующего запуска | -- |
| `trigger_scheduled_job` | Немедленный запуск плановой задачи | `job_id`: str |
| `pause_scheduled_job` | Приостановить плановую задачу | `job_id`: str |
| `resume_scheduled_job` | Возобновить приостановленную задачу | `job_id`: str |
| `get_scheduler_history` | История недавних запусков плановых задач | -- |

## Webhooks (9)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `list_webhooks` | Список Webhook | — |
| `create_webhook` | Создать Webhook | `url`: str, `events`: list, `name`: str = '' |
| `update_webhook` | Обновить Webhook | `webhook_id`: str, `url`: str = '', `events`: list = None, `name`: str = '', `enabled`: bool = True |
| `delete_webhook` | Удалить Webhook | `webhook_id`: str |
| `test_webhook` | Отправить тестовое событие | `webhook_id`: str |
| `get_webhook_deliveries` | История доставок | `webhook_id`: str = '', `limit`: int = 50 |
| `create_inbound_webhook` | Создать inbound webhook для внешних триггеров (возвращает URL с токеном). | `label`: str, `allowed_events`: list |
| `list_inbound_webhooks` | Список зарегистрированных inbound webhook. | — |
| `delete_inbound_webhook` | Удалить inbound webhook. | `webhook_id`: str |

## Extensions (25)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `list_extensions` | Список расширений | — |
| `get_extension_detail` | Детали расширения | `name`: str |
| `toggle_extension` | Включить/выключить расширение | `name`: str, `enabled`: bool |
| `install_extension` | Установка из Git-репозитория | `url`: str |
| `update_extension` | Обновить расширение | `name`: str |
| `update_all_extensions` | Массовое обновление всех расширений | — |
| `uninstall_extension` | Удалить расширение | `name`: str |
| `search_marketplace` | Поиск в маркетплейсе | `query`: str = '' |
| `refresh_marketplace` | Обновить каталог маркетплейса | — |
| `get_extension_config` | Получить настройки | `name`: str |
| `set_extension_config` | Обновить настройки | `name`: str, `values`: dict |
| `get_extension_permissions` | Получить права | `name`: str |
| `approve_extension_permissions` | Одобрение/отклонение прав | `name`: str, `granted`: list = None, `denied`: list = None, `action`: str = 'approve' |
| `scan_extension_code` | Статический анализ кода | `name`: str |
| `rescan_extension` | Повторный анализ кода | `name`: str |
| `get_extension_tokens` | Состояние Capability Token | `name`: str |
| `get_extension_integrity` | Целостность файлов и состояние наблюдения | `name`: str |
| `get_extension_hooks` | Список зарегистрированных хуков | — |
| `get_extension_isolation_status` | Статус изоляции процессов | — |
| `get_extension_os_isolation_status` | Статус изоляции на уровне ОС | — |
| `create_extension` | Создать пользовательское расширение из шаблона | `name`: str, `description`: str = "" |
| `validate_extension` | Валидация манифеста и кода расширения | `extension_name`: str |
| `list_extension_files` | Список файлов пользовательского расширения | `extension_name`: str |
| `read_extension_file` | Чтение файла пользовательского расширения | `extension_name`: str, `file_type`: str, `filename`: str |
| `write_extension_file` | Запись файла в пользовательское расширение | `extension_name`: str, `file_type`: str, `filename`: str, `content`: str |

## UI Management (4)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `list_uis` | Список UI | — |
| `switch_ui` | Переключить активный UI | `name`: str |
| `install_ui` | Установка UI | `url`: str |
| `uninstall_ui` | Удаление UI | `name`: str |

## Settings (18)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `settings_get_schema` | Получить схему настроек | — |
| `settings_get_all` | Получить все настройки | — |
| `settings_get` | Получить отдельную настройку | `key`: str |
| `settings_set` | Обновить настройку | `key`: str, `value`: str, `op_uri`: str = '' |
| `get_legacy_config` | Получить устаревший config.json | — |
| `save_legacy_config` | Сохранить устаревший config.json | `config`: dict |
| `secrets_status` | Состояние ключа шифрования | — |
| `secrets_export` | Экспорт ключа шифрования | `password`: str |
| `secrets_import` | Импорт ключа шифрования | `export_json`: str, `password`: str |
| `get_op_status` | Состояние 1Password CLI | — |
| `delete_op_mapping` | Удалить сопоставление 1Password | `key`: str |
| `migrate_secrets_to_keychain` | Миграция секретов в keychain ОС | — |
| `get_bw_status` | Статус интеграции с Bitwarden CLI | -- |
| `list_bw_folders` | Список папок Bitwarden | -- |
| `delete_bw_mapping` | Удалить сопоставление поля Bitwarden | `key`: str |
| `list_op_vaults` | Список Vault 1Password | -- |
| `push_secrets_to_1password` | Запушить все секреты в 1Password и автоматически связать op_secrets | `vault`: str, `item_title`: str = "YU AI Manager" |
| `push_secrets_to_bitwarden` | Запушить все секреты в Bitwarden и автоматически связать маппинги | `item_name`: str = "YU AI Manager", `folder_id`: str = "" |

## SNS Sharing (15)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `share_to_bluesky` | Публикация в Bluesky | `file_id`: int, `text`: str = '', `attach_image`: bool = True |
| `test_bluesky_connection` | Тест соединения с Bluesky | — |
| `get_x_share_url` | Получить URL шаринга для X (Twitter) | `file_id`: int |
| `get_sns_preview` | Предпросмотр шеринга в SNS | `file_id`: int |
| `get_sns_config` | Получить настройки SNS | — |
| `save_sns_config` | Сохранить настройки SNS | `config`: dict |
| `bsky_get_pending_notifications` | Получить непрочитанные уведомления Bluesky из очереди | -- |
| `bsky_get_notification_queue` | Получить элементы очереди уведомлений с фильтрами | `status`: str = "", `notification_type`: str = "" |
| `bsky_poll_notifications` | Немедленная выборка уведомлений Bluesky | -- |
| `bsky_triage_notification` | Установить результат триажа для уведомления | `queue_id`: int, `result`: str |
| `bsky_send_auto_response` | Отправить автоответ на mention/reply/quote | `queue_id`: int, `text`: str |
| `bsky_get_monitor_config` | Получить настройки монитора Bluesky | -- |
| `bsky_save_monitor_config` | Сохранить настройки монитора Bluesky | `poll_interval_minutes`: int = 0, `auto_dismiss_follow`: bool = True, `auto_dismiss_like`: bool = True, `auto_dismiss_repost`: bool = True, `auto_respond_enabled`: bool = False |
| `bsky_get_triage_prompts` | Получить промпты и шаблоны триажа Bluesky | -- |
| `bsky_save_triage_prompts` | Сохранить промпты триажа Bluesky | `triage_mention`: str = "", `triage_reply`: str = "", `triage_quote`: str = "", `response_mention`: str = "", `response_reply`: str = "" |

## LAN Share (2)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `create_lan_share` | Создать токен LAN-шеринга | `collection_id`: int, `expires_hours`: int = 24 |
| `revoke_lan_share` | Отозвать токен шеринга | `token`: str |

## MCP Client (8)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `list_mcp_connections` | Список MCP-подключений | — |
| `create_mcp_connection` | Создать MCP-подключение | `name`: str, `command`: str, `args`: list = None, `env`: dict = None |
| `update_mcp_connection` | Обновить MCP-подключение | `connection_id`: str, `name`: str = '', `command`: str = '', `args`: list = None, `env`: dict = None |
| `delete_mcp_connection` | Удалить MCP-подключение | `connection_id`: str |
| `connect_mcp_server` | Подключиться к MCP-серверу | `connection_id`: str |
| `disconnect_mcp_server` | Отключиться от MCP-сервера | `connection_id`: str |
| `get_mcp_connection_tools` | Список инструментов подключения | `connection_id`: str |
| `call_mcp_tool` | Вызов инструмента на подключении | `connection_id`: str, `tool_name`: str, `arguments`: dict = None |

## Cross Search (9)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `cross_search_get_scan_roots` | Получить каталоги корней сканирования Cross Search | -- |
| `cross_search_set_scan_roots` | Установить каталоги корней сканирования Cross Search | `roots`: list |
| `cross_search_delete_scan_root` | Удалить корень Cross Search по индексу | `index`: int |
| `cross_search_scan` | Запуск сканирования текстовых файлов Cross Search | -- |
| `cross_search_scan_stop` | Остановить выполняющееся сканирование Cross Search | -- |
| `cross_search_scan_status` | Прогресс сканирования Cross Search | -- |
| `cross_search_get_txt` | Получить текстовое содержимое проиндексированного файла | `file_id`: int |
| `cross_search_open_file` | Открыть файл в системном файловом менеджере | `path`: str |
| `cross_search_stats` | Статистика Cross Search | -- |

## Tag Dictionary (6)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `search_tag_dictionary` | Поиск по словарю тегов | `query`: str, `limit`: int = 20, `fuzzy`: bool = False |
| `get_tag_dict_stats` | Статистика словаря тегов | — |
| `split_tags` | Разделение слитных тегов | `text`: str |
| `import_tag_dictionary` | Импорт словаря тегов | `data`: dict |
| `clear_tag_dictionary` | Очистка словаря тегов | — |
| `get_tag_dict_info` | Подробная информация об отдельном теге | `tag`: str |

## Trophies (1)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `list_trophies` | Список трофеев | — |

## Source Code Browsing (3)

Инструменты только для безопасного чтения исходного кода проекта.
Защищены трёхслойной безопасностью (нормализация пути + белый список расширений + чёрный список чувствительных файлов).
Подробности: [`docs/api/source.md`](source.md)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `source_tree` | Отображение дерева каталогов | `path`: str = '', `depth`: int = 3 |
| `source_read` | Чтение содержимого файла (с номерами строк) | `path`: str, `offset`: int = 0, `limit`: int = 2000 |
| `source_search` | Поиск текста в исходниках | `query`: str, `glob`: str = '', `limit`: int = 30 |

## Help (3)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `help_toc` | Оглавление справки | — |
| `help_get_section` | Получить содержимое раздела | `section`: str |
| `help_search` | Поиск по справке | `query`: str, `limit`: int = 5 |

## System Info (3)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `get_server_info` | Информация о сервере | — |
| `get_inference_info` | Информация о движке инференса | — |
| `get_market_quotes` | Рыночные данные | — |

## System Update (5)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `check_for_update` | Проверить, доступна ли новая версия на GitHub | — |
| `get_update_status` | Получить текущий способ установки и версию | — |
| `apply_system_update` | Применить доступное обновление (только git/portable) | `confirm`: str |
| `check_unified_updates` | Проверить обновления системы + всех расширений одним запросом | `force`: bool (optional) |
| `apply_unified_updates` | Массово обновить систему + расширения (с автобэкапом настроек) | `update_system`: bool, `update_extensions`: bool, `extension_names`: list (optional) |

## Suggestions (4)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `get_suggestions` | Автодополнение тегов/промптов | `q`: str, `limit`: int = 10 |
| `suggest_tags` | Автодополнение тегов | `q`: str, `limit`: int = 10 |
| `suggest_lora` | Автодополнение имён LoRA | `q`: str = '' |
| `suggest_embedding` | Автодополнение имён Embedding | `q`: str = '' |

## Logs & Debug (9)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `get_recent_logs` | Получить недавние логи | `limit`: int = 100 |
| `get_debug_log` | Вывод отладочного лога | `lines`: int = 200 |
| `clear_debug_log` | Очистка отладочного лога | — |
| `get_cache_info` | Статистика кэша | — |
| `clear_cache` | Очистка кэша | — |
| `rebuild_groups` | Перестроение групп каталогов | — |
| `list_dirs` | Список каталогов | `path`: str = '' |
| `debug_file_meta` | Отладочные метаданные файла | `file_id`: int |
| `debug_model_check` | Проверка доступности моделей | — |

## Agent Safety Gateway (25)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `agent_status` | Сводное состояние средств безопасности | — |
| `agent_kill` | Активация Kill Switch (мгновенная блокировка всех инструментов) | `reason`: str = 'Manual kill via MCP' |
| `agent_resume` | Снятие Kill Switch | — |
| `agent_circuit_breaker_status` | Состояние Circuit Breaker | — |
| `agent_circuit_breaker_reset` | Сброс Circuit Breaker | — |
| `agent_budget_status` | Состояние Budget Tracker | — |
| `agent_budget_reset` | Сброс Budget Tracker | — |
| `agent_approval_status` | Список ожидающих запросов на одобрение | — |
| `agent_approval_respond` | Ответ на запрос одобрения | `request_id`: str, `action`: str |
| `agent_approval_history` | История одобрений | `limit`: int = 50 |
| `agent_scope_status` | Состояние Scope Fence | — |
| `agent_scope_get` | Получить scope сессии | `session_id`: str |
| `agent_scope_set` | Установить scope сессии | `preset`: str = 'organizer', `duration_hours`: float = 0 |
| `agent_scope_delete` | Удалить scope сессии | `session_id`: str |
| `agent_tool_level` | Проверка уровня безопасности инструмента | `tool_name`: str = '' |
| `agent_auto_approve_list` | Список правил автодопуска | — |
| `agent_auto_approve_add` | Добавить правило автодопуска | `tool_name`: str |
| `agent_auto_approve_remove` | Удалить правило автодопуска | `index`: int |
| `agent_undo` | Откат действия | `journal_id`: int |
| `agent_undoable` | Список действий, которые можно откатить | `session_id`: str = '', `limit`: int = 50 |
| `agent_journal` | Поиск в журнале действий | `tool_name`: str = '', `status`: str = '', `session_id`: str = '', `limit`: int = 50, `offset`: int = 0 |
| `agent_journal_stats` | Статистика журнала | — |
| `agent_anomaly_status` | Состояние детекции аномалий | — |
| `agent_anomaly_alerts` | История аномальных алертов | `limit`: int = 50 |
| `agent_anomaly_reset` | Сброс детекции аномалий | — |

---

## GitHub Integration (12)

Мониторинг, триаж и отчёты по issue-аккаунтам GitHub.

| Tool | Описание | Параметры |
|------|----------|-----------|
| `github_list_accounts` | Список зарегистрированных аккаунтов GitHub (токены замаскированы) | — |
| `github_fetch_issues` | Получение issue из репозиториев аккаунта | `account_label`: str, `state`: str = 'open', `since`: str = '' |
| `github_triage_issues` | Получение и классификация issue (valid_bug / skip / needs_info). Возвращает приоритизированный отчёт | `account_label`: str, `state`: str = 'open', `since`: str = '' |
| `github_get_issue_detail` | Детали issue в структурированном виде для Claude Code (с комментариями) | `account_label`: str, `repo`: str, `issue_number`: int |
| `github_rate_limit` | Проверка остатка лимита GitHub API | `account_label`: str |
| `github_get_pending_issues` | Получить необработанные Issue из локальной очереди | -- |
| `github_get_issue_queue` | Получить элементы очереди Issue с фильтрами по статусу | `status`: str = "" |
| `github_poll_issues` | Немедленная выборка GitHub Issue | -- |
| `github_triage_queue_item` | Установить результат триажа для Issue в очереди | `queue_id`: int, `result`: str |
| `github_dismiss_queue_item` | Отклонить Issue в очереди (опционально с auto close) | `queue_id`: int, `auto_close`: bool = False, `account_label`: str = "" |
| `github_get_triage_prompts` | Получить промпты триажа Issue/PR/Discussion | `repo`: str = "" |
| `github_save_triage_prompts` | Сохранить промпты триажа | `issue`: str = "", `pr`: str = "", `discussion`: str = "", `repo`: str = "" |

## Debug Tools (9)

Инструменты валидации и отладки системы. Активируются при `YU_DEBUG_MODE=1`.

| Tool | Описание | Параметры |
|------|----------|-----------|
| `debug_health_check` | Проверка здоровья системы: Flask, таблицы БД, версия схемы | -- |
| `debug_validate_counts` | Кросс-проверка статистики API и счётчиков БД | -- |
| `debug_validate_search` | Проверка поискового API по тестовым шаблонам | `patterns`: str = "all" |
| `debug_validate_collection` | Проверка кэшированных счётчиков коллекций и БД | -- |
| `debug_validate_annotations` | Проверка целостности данных аннотаций | -- |
| `debug_sample_files` | Случайная выборка файлов и отчёт о полноте полей | `n`: int = 50, `fields`: str = "meta_source,width,height" |
| `debug_roundtrip_test` | Roundtrip-тест запись-чтение-обновление-удаление | -- |
| `debug_readonly_query` | Выполнение только-читающего SQL-запроса | `sql`: str, `limit`: int = 100 |
| `debug_full_report` | Выполнить все отладочные проверки сразу | -- |

---

## LoRA Dataset Manager (15)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `list_lora_projects` | Список проектов | — |
| `get_lora_project` | Детали проекта | `project_id`: int |
| `create_lora_project` | Создать проект | `name`: str, `concept`: str, `base_model`: str = 'sdxl', `repeat`: int = 10, `model_scope`: str = 'active' |
| `update_lora_project` | Обновить проект | `project_id`: int, `file_ids`: list = None, `tag_exclude`: list = None, `model_scope`: str = 'active' / 'all' / '<model_id>' |
| `delete_lora_project` | Удалить проект | `project_id`: int |
| `get_lora_project_tags` | Получить агрегаты тегов | `project_id`: int, `limit`: int = 200 |
| `preview_lora_caption` | Предпросмотр подписи | `project_id`: int, `file_id`: int = None |
| `export_lora_dataset` | Экспорт датасета | `project_id`: int, `output_dir`: str = '' |
| `get_lora_export_status` | Прогресс экспорта | `project_id`: int |
| `list_lora_checkpoints` | Список чекпоинтов | — |
| `preview_lora_train_command` | Предпросмотр команды обучения (dry run) | `project_id`: int, `checkpoint`: str |
| `start_lora_training` | Запуск обучения LoRA | `project_id`: int, `checkpoint`: str |
| `get_lora_train_status` | Статус обучения и логи | `project_id`: int, `tail`: int = 50 |
| `list_lora_tag_presets` | Список пресетов исключений тегов | — |
| `create_lora_tag_preset` | Создать пресет исключений тегов | `name`: str, `tags`: list |

## LLM Endpoints (5)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `llm-endpoints-list` | Список настроенных LLM-эндпоинтов | — |
| `llm-endpoints-set` | Добавление/обновление LLM-эндпоинта | `category`: str, `base_url`: str, `model`: str, `api_key`: str = '', `timeout`: int = 60 |
| `llm-endpoints-remove` | Удаление LLM-эндпоинта | `category`: str |
| `llm-endpoints-test` | Тест соединения с LLM-эндпоинтом | `category`: str |
| `llm-chat` | Делегирование чата настроенному LLM | `category`: str, `message`: str, `system_prompt`: str = '', `max_tokens`: int = 1024, `temperature`: float = 0.7 |

## Server Mode (2)

| Tool | Описание | Параметры |
|------|----------|-----------|
| `server-mode-get` | Получить текущий серверный режим | — |
| `server-subsystems-status` | Список статусов подсистем | — |

## Возможности, не поддерживаемые через MCP

Следующее не реализовано в виде инструментов из-за ограничений MCP:

- **Бинарный ответ**: миниатюры (`/api/thumbnail/`), оригиналы (`/api/original/`), скачивание ZIP, видеофайлы
- **Диалоги ОС**: диалог выбора папки (`/api/tools/select-folder`), запуск файлового менеджера (`/api/open-folder/`)
- **SSE-стримы**: стриминг логов (`/api/logs/stream`)
- **Страницы аутентификации**: экран ввода PIN, страница гостя LAN Share
