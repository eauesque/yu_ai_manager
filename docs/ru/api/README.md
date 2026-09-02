# Справка по API YU AI Manager

Полная документация REST API для всех функций YU AI Manager, доступная для пользовательских интерфейсов и скриптов.

## Общие соглашения

### Базовый URL

```
http://<host>:<port>
```

По умолчанию: `http://127.0.0.1:5000`
Тестовая среда: `http://127.0.0.1:5100` (при использовании `config_test.json`)

### Аутентификация

Поддерживаются четыре метода аутентификации:

| Метод | Случай использования | Пример заголовка |
|--------|----------|----------------|
| PIN Auth | Сеансы браузера | Cookie: `session=...` |
| API Key | Взаимодействие машин | `Authorization: Bearer sk_...` |
| Trusted Proxy | За обратным прокси | `X-Remote-User: username` |
| LAN Share Token | Гостевой доступ | URL-путь `/s/<token>/...` |

Возможно полностью пропустить аутентификацию, запустив с помощью `config_test.json` (без PIN).

### Защита от CSRF

Все запросы `POST` / `PUT` / `DELETE` к конечным точкам `/api/` требуют заголовка `X-Requested-With`:

```
X-Requested-With: XMLHttpRequest
```

**Исключение**: Запросы с API Key, содержащие заголовок `Authorization: Bearer`, не требуют CSRF.

### Ограничение скорости

| Уровень | Область | Скорость | Всплеск |
|------|-------|------|-------|
| READ | Все GET | Неограниченно | - |
| WRITE | POST/PUT/DELETE (стандартно) | ~120 запросов/мин | 30 |
| HEAVY | Похожий поиск, хеширование, анализ AI, сканирование | ~20 запросов/мин | 5 |
| DESTRUCTIVE | Очистка, жесткое удаление, очистка кэша, запись конфигурации | ~12 запросов/мин | 3 |

Ответы 429 сопровождаются заголовком `Retry-After`.

### Формат ответа

**Успех** (новые API):
```json
{
  "ok": true,
  "error": null,
  "data": { ... }
}
```

**Ошибка**:
```json
{
  "ok": false,
  "error": "Сообщение об ошибке",
  "code": "ERROR_CODE",
  "detail": "Дополнительные детали (необязательно)"
}
```

Некоторые устаревшие API возвращают формат `{ "success": true, "message": "..." }`.

### Пагинация

**На основе смещения** (по умолчанию):
```
GET /api/search?offset=0&limit=50
```

**На основе курсора** (для больших наборов данных):
```
GET /api/search?cursor=<opaque_token>&limit=50
```

Ответ включает поле `next_cursor`.

### Массовые операции

API массовых операций поддерживают до 500 операций на запрос. Возможен частичный успех:

```json
POST /api/ratings/batch-set
{
  "items": [
    { "file_id": 1, "rating": 5 },
    { "file_id": 999, "rating": 3 }
  ]
}
```

## Категории API

| Документ | Содержимое |
|----------|---------|
| [search.md](search.md) | Поиск, предложения, группы |
| [files.md](files.md) | Детали файлов, миниатюры, получение медиа |
| [scan.md](scan.md) | Управление сканированием, управление корневыми папками сканирования |
| [events.md](events.md) | Поток событий SSE |
| [theming.md](theming.md) | CSS переменные, настройка темы |
| [source.md](source.md) | Просмотр исходного кода (только чтение для MCP) |
| [github.md](github.md) | GitHub интеграция (аккаунты, проблемы, PR, уведомления, обсуждения, релизы) |
| [scheduler.md](scheduler.md) | Планировщик задач (управление работами, история выполнения) |
| [ratings.md](ratings.md) | Оценки (установка, массовая установка, получение, статистика) |
| [favorites.md](favorites.md) | Избранное (переключение, проверка, список) |
| [collections.md](collections.md) | Коллекции (CRUD, переупорядочивание, массовое добавление/удаление, экспорт CSV) |
| [tags.md](tags.md) | Теги (массовая установка, предложение) |
| [sns.md](sns.md) | SNS Share & Bluesky Monitor (публикация, уведомления, сортировка, автоответ) |
| [hailo-remote-tagger.md](hailo-remote-tagger.md) | Hailo Remote Tagger (конфигурация, разметка одного/группы, CRUD тегов) |
| [tagger-servers.md](tagger-servers.md) | Реестр серверов разметчиков (распределенный кластер вывода тегов, управление серверами, массовое выполнение) |
| [svg.md](svg.md) | Растеризация SVG (преобразование SVG в PNG/WebP, поддержка конвейера img2img) |
| [settings.md](settings.md) | Управление параметрами (схема, получение/обновление значений, шифрование секретов, интеграция 1Password/Bitwarden) |
| [extensions.md](extensions.md) | Расширения (список, переключение, конфигурация, установка, безопасность, рынок, разработка) |
| [analysis.md](analysis.md) | AI анализ (конфигурация, анализ одного/группы, анализ тренда, статистика, реестр серверов) |
| [system-update.md](system-update.md) | Обновление системы (проверка версии, применение обновления, единый менеджер обновлений) |
| [tools.md](tools.md) | Инструменты (обнаружение дубликатов, вычисление хеша, похожий поиск, управление кэшем, резервное копирование, очистка архива, логирование отладки) |
| [agent.md](agent.md) | Шлюз безопасности агентов (Kill Switch, Circuit Breaker, Budget, Approval, Scope Fence, Undo, Anomaly Detection) |
| [profiles.md](profiles.md) | Управление профилями (CRUD, дублирование, экспорт/импорт QR) |
| [wd-tagger.md](wd-tagger.md) | WD-Tagger (авторазметка Danbooru, управление моделями, VLM, XMP) |
| [ocr.md](ocr.md) | OCR (распознавание текста, перевод, поддержка видео/PDF, тесты производительности, профили) |
| [apikeys.md](apikeys.md) | Управление ключами API (создание, список, области, отзыв) |
| [debug.md](debug.md) | Отладка (проверка метаданных, SQL запрос, проверка модели) |
| [ui.md](ui.md) | Управление UI (список, переключение, установка, удаление) |
| [video-analysis.md](video-analysis.md) | Видео анализ (конфигурация, состояние, извлечение ключевых кадров) |

## Быстрый старт (curl)

```bash
# Поиск (среда без PIN)
curl "http://localhost:5100/api/search?q=landscape&limit=10"

# Получение миниатюры
curl "http://localhost:5100/api/thumbnail/42" -o thumb.webp

# Поиск с API Key
curl -H "Authorization: Bearer sk_your_key_here" \
     "http://localhost:5100/api/search?q=portrait"

# Установка оценки
curl -X POST "http://localhost:5100/api/ratings/set" \
     -H "X-Requested-With: XMLHttpRequest" \
     -H "Content-Type: application/json" \
     -d '{"file_id": 42, "rating": 5}'
```
