# Спецификация управления текстом и журналом чатов YU AI Manager

Создано: 2026-03-01
Целевая версия: TBD (время реализации под рассмотрением)

## Обзор

Три функции добавляются в YU AI Manager:

- **MD Viewer** — локальный просмотр файлов Markdown
- **Chatlog Management** — импорт, просмотр и поиск журналов из Claude/ChatGPT/Open WebUI
- **Full-Text Search** — поиск по всему содержимому powered by FTS5

Философия проектирования такая же, как у существующих функций: "полностью локальное, независимое от облака".

---

## 1. MD Viewer

### Назначение

Встроенные в ОС средства просмотра файлов обеспечивают плохую отрисовку Markdown. Эта функция полностью расположена в YU AI Manager, служа в качестве ежедневного справочного инструмента для заметок разработки, документов проектирования и списков TODO.

### Целевые сканирования

- Расширения: `.md`, `.markdown`
- Существующие корни сканирования переиспользуются
- Исключено: файлы под `.git/` и `node_modules/`

### Схема БД

```sql
CREATE TABLE md_files (
    id          INTEGER PRIMARY KEY,
    path        TEXT NOT NULL UNIQUE,
    mtime       INTEGER NOT NULL,
    size        INTEGER NOT NULL,
    title       TEXT,        -- Извлечено из первого заголовка #
    content     TEXT,        -- Сырой текст Markdown
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    indexed_at  INTEGER
);

CREATE VIRTUAL TABLE md_files_fts USING fts5(
    title,
    content,
    content='md_files',
    content_rowid='id'
);
```

### UI просмотра

- Интегрировано в существующее модальное окно или боковую панель
- Отрисовка: marked.js (bundled локально, нет CDN)
- Блоки кода: подсветка синтаксиса (highlight.js)
- Кнопка переключения сырого текстового представления предусмотрена

### Поддержка MCP

- `search_md_files(query, path_filter)` -> список файлов
- `get_md_content(file_id)` -> сырой текст

---

## 2. Управление журналом чатов

### Назначение

Эта функция служит в качестве поисковой системы для истории разработки, делая возможным поиск прошлых обсуждений, используя туманные ключевые слова. Примеры: "Где было обсуждение этого bug?" или "Какова была причина этого решения дизайна?"

### Поддерживаемые форматы

| Сервис | Формат экспорта | Как получить |
|---|---|---|
| Claude | conversations.json | Settings -> Export Data |
| ChatGPT | conversations.json | Settings -> Export Data |
| Open WebUI | JSON экспорт | Chat History -> Export |

### Схема БД

```sql
-- Per conversation
CREATE TABLE chat_conversations (
    id            INTEGER PRIMARY KEY,
    source        TEXT NOT NULL,  -- 'claude' / 'chatgpt' / 'openwebui'
    external_id   TEXT,           -- Conversation ID из оригинального сервиса
    title         TEXT,
    model         TEXT,           -- Используемое имя модели
    created_at    INTEGER,
    updated_at    INTEGER,
    message_count INTEGER,
    imported_at   INTEGER NOT NULL
);

-- Per message
CREATE TABLE chat_messages (
    id              INTEGER PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES chat_conversations(id),
    role            TEXT NOT NULL,  -- 'user' / 'assistant' / 'system'
    content         TEXT NOT NULL,
    created_at      INTEGER,
    seq             INTEGER         -- Порядок в conversation
);

-- FTS5 полнотекстовый поиск
CREATE VIRTUAL TABLE chat_messages_fts USING fts5(
    content,
    content='chat_messages',
    content_rowid='id',
    tokenize='unicode61'
);
```

### Импортер

Каждый JSON сервиса конвертируется в общий промежуточный формат и вставляется в БД.

**Структура Claude JSON (ключевые поля):**

```json
{
  "uuid": "...",
  "name": "Conversation title",
  "created_at": "2026-01-01T00:00:00Z",
  "chat_messages": [
    {"role": "human", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}
```

**Структура ChatGPT JSON (ключевые поля):**

```json
{
  "id": "...",
  "title": "Conversation title",
  "create_time": 1234567890,
  "mapping": {
    "node_id": {
      "message": {
        "author": {"role": "user"},
        "content": {"parts": ["..."]}
      }
    }
  }
}
```

**Структура Open WebUI JSON:**

- Следует формату OpenAI-compatible API
- messages массив с role/content

### UI импорта

- Раздел импорта добавляется на страницу параметров
- JSON файлы могут быть отпущены через drag-and-drop или выбраны с помощью file picker
- Ранее импортированные conversation дедублицированы по `external_id` (идемпотентно)
- Отображается итоговая сводка импорта (добавленное количество и пропущенное количество)

### UI просмотра

- Страница списка conversation (название, дата, модель, источник)
- Страница деталей conversation (отображение на основе ходов с цветовой кодировкой на основе ролей)
- Фильтры по имени модели, источнику и диапазону дат
- Прикреплённые изображения сохраняют только ссылки на пути (нет копий файлов)

### Поддержка MCP

- `search_chat_logs(query, source, model, date_from, date_to)` -> список conversation
- `get_conversation(conversation_id)` -> список сообщений
- `import_chat_log(source, json_path)` -> выполнить импорт

---

## 3. Полнотекстовый поиск

### Целевые направления

- MD файлы (`md_files_fts`)
- Chat журналы (`chat_messages_fts`)
- Существующая библиотека приглашений (`prompt_library_fts`, уже реализовано)

### UI поиска

- Либо расширьте существующую строку поиска, либо предоставьте выделенную страницу поиска текста
- Переключение целевых направлений поиска (MD / chatlog / prompt library)
- Результаты ранжируются по BM25 оценке
- Отображение snippet попадания (~50 символов окружающего контекста)

### API поиска

```
GET /api/text-search?q=keyword&target=md,chat,prompt&limit=20
```

Ответ:

```json
{
  "results": [
    {
      "type": "chat",
      "conversation_id": 123,
      "title": "Conversation title",
      "snippet": "...text around the hit...",
      "score": 0.95,
      "date": "2026-01-01"
    }
  ]
}
```

---

## Приоритет реализации

1. MD Viewer (низкая стоимость реализации, высокая немедленная ценность)
2. Chatlog импортер (поддержка Claude/ChatGPT в первую очередь)
3. Chatlog просмотр
4. Поддержка Open WebUI
5. UI кросс-контентного текстового поиска

---

## Будущие расширения

- Автоматический периодический импорт chatlog (поместите файлы экспорта в контролируемую папку для автоматического приёма)
- Связь приглашений генерирования изображения с обсуждениями chatlog, которые их произвели
- Автоматическое суммирование и теггирование chatlog через Ollama

---

## Примечания

- Паттерны FTS5 могут быть переиспользованы из существующей реализации `prompt_library_fts`
- marked.js bundled локально, а не загружается из CDN (следует философии только-локального проектирования)
- Прикреплённые изображения в chatlog (DALL-E генерируемые изображения и т.д.) не сохраняются локально, потому что их URL истекают
