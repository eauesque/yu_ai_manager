# Справочник API — ссылки для разработчиков пользовательского UI

Список ссылок на API-документацию для разработки пользовательского UI и краткий справочник наиболее используемых API.

## Список документов

### Общие соглашения

- [Общие соглашения API](../api/README.md) — базовый URL, аутентификация (4 способа), защита CSRF, ограничение скорости, формат ответов, пагинация

### По эндпоинтам

- [API поиска](../api/search.md) — GET /api/search, подсказки, группировка, server-info
- [API файлов](../api/files.md) — детали файла, миниатюры, оригинал, конвертация промпта
- [API сканирования](../api/scan.md) — управление сканированием, корневые директории, заполнение хэшей
- [API событий](../api/events.md) — SSE события в реальном времени, поток логов

### Темы оформления

- [Список CSS-переменных](../api/theming.md) — CSS-свойства тем (Light/Dark)

## Краткий справочник часто используемых API

### Чтение (GET, аутентификация не обязательна*)

| Эндпоинт | Назначение | Основные параметры |
|----------|-----------|-------------------|
| `/api/search` | Поиск файлов | `q`, `sort`, `limit`, `cursor`, `rating_min`, `collection_id` |
| `/api/thumbnail/<id>` | Миниатюра (WebP) | `size` (по умолчанию 300) |
| `/api/original/<id>` | Оригинальный файл | поддержка Range |
| `/api/file/<id>` | Детали файла | — |
| `/api/suggest` | Подсказки тегов | `q`, `limit` |
| `/api/stats/all` | Статистика | — |
| `/api/collections` | Список коллекций | — |
| `/api/server-info` | Информация о сервере | — |
| `/api/events/stream` | SSE-поток | `types` |

*При отсутствии PIN или при наличии аутентифицированной сессии

### Запись (POST, обязателен заголовок `X-Requested-With`)

| Эндпоинт | Назначение | Пример тела |
|----------|-----------|-------------|
| `/api/ratings/set` | Установка рейтинга | `{file_id: 42, rating: 5}` |
| `/api/ratings/batch-set` | Массовый рейтинг | `{items: [{file_id, rating}, ...]}` |
| `/api/favorites/add` | Добавить в избранное | `{file_id: 42}` |
| `/api/favorites/remove` | Удалить из избранного | `{file_id: 42}` |
| `/api/tags/batch-set` | Массовые операции с тегами | `{items: [{file_id, add: [], remove: []}]}` |
| `/api/collections` | Создать коллекцию | `{name: "My Collection"}` |
| `/api/collections/<id>/batch-add` | Добавить в коллекцию | `{file_ids: [1, 2, 3]}` |
| `/api/scan-all` | Начать сканирование | `{}` |
| `/api/convert` | Конвертация промпта | `{prompt, direction}` |

### Управление UI

| Эндпоинт | Метод | Назначение |
|----------|-------|-----------|
| `/api/ui/list` | GET | Список UI |
| `/api/ui/switch` | POST | Переключить UI |
| `/api/ui/install` | POST | Установить UI (только localhost) |
| `/api/ui/<name>/uninstall` | DELETE | Удалить UI (только localhost) |

## Формат ответов

### Результаты поиска

```javascript
{
  results: [
    {
      id: 42,
      path: "/images/00042.png",
      filename: "00042.png",
      width: 1024,
      height: 1536,
      meta_type: "a1111_png",   // a1111_png, novelai_v4_png, comfy_png, unknown
      model_name: "animagine-xl-3.1",
      positive: "1girl, landscape",
      rating: 4,                 // 0-5 (0 = без рейтинга)
      is_favorite: true,
      tags: ["landscape", "sunset"]
    }
  ],
  total: 1500,
  next_cursor: "base64token..."  // null = последняя страница
}
```

### Миниатюры

```
GET /api/thumbnail/42
→ Content-Type: image/webp
→ ETag: "abc123"
→ Cache-Control: max-age=86400
```

Браузер кэширует автоматически. Можно использовать напрямую в теге `<img>`:

```html
<img src="/api/thumbnail/42" loading="lazy" alt="thumbnail">
```

### Ответ при ошибке

```javascript
{
  ok: false,
  error: "Rate limit exceeded",
  code: "RATE_LIMIT",      // опционально
  detail: "Retry after 5s"  // опционально
}
```

## Примечания по CSRF-заголовку

```javascript
// Вспомогательный объект с общими заголовками
const API_HEADERS = {
  'Content-Type': 'application/json',
  'X-Requested-With': 'XMLHttpRequest',
};

// GET: заголовок не нужен
fetch('/api/search?q=test');

// POST: X-Requested-With обязателен
fetch('/api/ratings/set', {
  method: 'POST',
  headers: API_HEADERS,
  body: JSON.stringify({ file_id: 42, rating: 5 }),
});
```
