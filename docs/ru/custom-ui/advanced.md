# Advanced Guide — SSE, пакетные операции, безопасность

Продвинутые возможности и шаблоны реализации пользовательских интерфейсов.

## Обновления в реальном времени (SSE)

При помощи Server-Sent Events можно получать в реальном времени ход сканирования, изменения избранного, прогресс AI-анализа и другие события.

### Способ подключения

```javascript
// Используем EventSource напрямую (в кастомных UI так безопасно)
const sse = new EventSource('/api/events/stream');

// Подписка на события
sse.addEventListener('scan.progress', (e) => {
  const data = JSON.parse(e.data);
  console.log(`Scan: ${data.scanned}/${data.total}`);
});

sse.addEventListener('scan.complete', (e) => {
  const data = JSON.parse(e.data);
  console.log(`Scan done: ${data.added_count} added`);
  // Перезагрузить сетку
  reloadResults();
});
```

**Примечание**: в референсном UI (`ui/default/`) `window.EventSource` переопределён через Proxy, поэтому `new EventSource()` там использовать нельзя. В кастомных UI это ограничение не применяется, и его можно использовать напрямую.

### Список основных событий

| Событие | Данные | Применение в UI |
|---------|--------|------------------|
| `scan.progress` | `{ scanned, total, current_file }` | Отображение прогресс-бара |
| `scan.complete` | `{ added_count, updated_count }` | Перезагрузка результатов поиска |
| `favorite.add` | `{ file_id, collection_id }` | Обновление иконки избранного |
| `favorite.remove` | `{ file_id, collection_id }` | Обновление иконки избранного |
| `collection.create` | `{ id, name }` | Обновление списка коллекций |

Полный список типов событий см. в [events.md](../api/events.md).

### Управление соединением

```javascript
class SSEConnection {
  constructor() {
    this.handlers = new Map();
    this.connect();
  }

  connect() {
    this.sse = new EventSource('/api/events/stream');
    this.sse.onerror = () => {
      this.sse.close();
      // Переподключение (экспоненциальная задержка)
      setTimeout(() => this.connect(), 3000);
    };
    // Восстановить зарегистрированные обработчики
    for (const [type, handler] of this.handlers) {
      this.sse.addEventListener(type, handler);
    }
  }

  on(eventType, callback) {
    const handler = (e) => callback(JSON.parse(e.data));
    this.handlers.set(eventType, handler);
    this.sse.addEventListener(eventType, handler);
  }

  close() {
    this.sse.close();
  }
}

// Пример использования
const sse = new SSEConnection();
sse.on('scan.progress', (data) => updateProgressBar(data));
sse.on('scan.complete', () => reloadResults());
```

### Подключение с учётом видимости вкладки

Отключать соединение, когда вкладка скрыта, чтобы экономить ресурсы:

```javascript
document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    sse.close();
  } else {
    sse.connect();
  }
});
```

## Пакетные операции

Шаблон API для массового выполнения операций над несколькими файлами.

### Пакетная установка рейтинга

```javascript
async function batchRate(items) {
  // items: [{file_id: 1, rating: 5}, {file_id: 2, rating: 3}]
  // Максимум 500 элементов
  const res = await api('/api/ratings/batch-set', {
    method: 'POST',
    body: JSON.stringify({ items }),
  });
  return res;
}
```

### Пакетные операции с тегами

```javascript
async function batchSetTags(items) {
  // items: [{file_id: 1, add: ["good"], remove: ["bad"]}, ...]
  const res = await api('/api/tags/batch-set', {
    method: 'POST',
    body: JSON.stringify({ items }),
  });
  return res;
}
```

### Пакетные операции с коллекциями

```javascript
// Добавить в коллекцию
async function addToCollection(collectionId, fileIds) {
  return api(`/api/collections/${collectionId}/batch-add`, {
    method: 'POST',
    body: JSON.stringify({ file_ids: fileIds }),
  });
}

// Удалить из коллекции
async function removeFromCollection(collectionId, fileIds) {
  return api(`/api/collections/${collectionId}/batch-remove`, {
    method: 'POST',
    body: JSON.stringify({ file_ids: fileIds }),
  });
}
```

### Обработка частичного успеха

Пакетные операции могут завершаться частично успешно:

```javascript
const result = await batchRate(items);
if (result.failed && result.failed.length > 0) {
  console.warn(`${result.failed.length} items failed:`, result.failed);
  showToast(`${result.succeeded} succeeded, ${result.failed.length} failed`);
}
```

## Обработка ошибок

### HTTP-коды статусов

| Код | Значение | Что делать |
|-----|----------|-----------|
| 200 | Успех | - |
| 304 | Not Modified | Использовать кэш (миниатюры) |
| 400 | Некорректный запрос | Проверить входные данные |
| 403 | Ошибка авторизации / CSRF | Проверить заголовок `X-Requested-With` |
| 404 | Ресурс не найден | Проверить ID файла |
| 429 | Rate limit | Подождать секунды из заголовка `Retry-After` |
| 500 | Ошибка сервера | Повторить попытку или проверить журнал |

### Обработка rate limit

```javascript
async function apiWithRetry(path, options = {}, maxRetries = 3) {
  for (let i = 0; i < maxRetries; i++) {
    const res = await fetch(path, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
        ...options.headers,
      },
    });

    if (res.status === 429) {
      const retryAfter = parseInt(res.headers.get('Retry-After') || '5', 10);
      console.warn(`Rate limited, retry after ${retryAfter}s`);
      await new Promise(r => setTimeout(r, retryAfter * 1000));
      continue;
    }

    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: res.statusText }));
      throw new Error(err.error || `HTTP ${res.status}`);
    }

    return res.json();
  }
  throw new Error('Max retries exceeded');
}
```

### Определение формата ответа

Существует два формата ответов — новый и устаревший:

```javascript
function parseApiResponse(json) {
  // Новый формат: { ok, error, data }
  if ('ok' in json) {
    if (!json.ok) throw new Error(json.error || 'Unknown error');
    return json.data ?? json;
  }
  // Старый формат: { success, message }
  if ('success' in json) {
    if (!json.success) throw new Error(json.message || 'Unknown error');
    return json;
  }
  // Формат с данными напрямую (results и т. п.)
  return json;
}
```

## Безопасность

### Защита от CSRF

Все записывающие операции (POST / PUT / DELETE) обязаны содержать заголовок `X-Requested-With`:

```javascript
// Корректно: заголовок присутствует
fetch('/api/ratings/set', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-Requested-With': 'XMLHttpRequest',
  },
  body: JSON.stringify({ file_id: 42, rating: 5 }),
});
```

**Исключение**: запросам с заголовком `Authorization: Bearer sk_...` (использующим API Key) CSRF-заголовок не требуется.

### Защита от XSS

При вставке пользовательского ввода или имён файлов в DOM необходимо выполнять санитизацию:

```javascript
function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// Плохой пример: имя файла вставляется как есть
card.innerHTML = `<p>${file.filename}</p>`;  // риск XSS

// Хороший пример: с экранированием
card.innerHTML = `<p>${escapeHtml(file.filename)}</p>`;

// Ещё лучше: использовать DOM API
const p = document.createElement('p');
p.textContent = file.filename;  // автоматическое экранирование
card.appendChild(p);
```

### Обращение с API Key

При использовании API Key из кастомного UI не встраивайте ключ на клиентской стороне.
В UI на основе браузера обычно применяется авторизация по PIN / сессии с защитой через CSRF-заголовок.

## Реализация поиска

### Базовый поиск

```javascript
async function search(query, options = {}) {
  const params = new URLSearchParams({
    q: query,
    limit: String(options.limit || 50),
    sort: options.sort || 'date',
  });

  if (options.cursor) params.set('cursor', options.cursor);
  if (options.minRating) params.set('rating_min', String(options.minRating));
  if (options.collection) params.set('collection_id', String(options.collection));
  if (options.favOnly) params.set('favorites_only', 'true');

  const res = await fetch(`/api/search?${params}`);
  return res.json();
}
```

### Автодополнение

```javascript
let debounceTimer;

function onSearchInput(e) {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(async () => {
    const q = e.target.value;
    if (q.length < 2) return;

    const res = await fetch(`/api/suggest?q=${encodeURIComponent(q)}&limit=10`);
    const { suggestions } = await res.json();
    showSuggestions(suggestions);  // [{value: "1girl", count: 5432}, ...]
  }, 200);
}
```

### Переключение сортировки

```javascript
const SORT_OPTIONS = [
  { value: 'date', label: 'Date (New)' },
  { value: 'name', label: 'Name' },
  { value: 'size', label: 'Size' },
  { value: 'rating', label: 'Rating' },
  { value: 'random', label: 'Random' },
];
```

## Управление коллекциями

```javascript
// Получить список коллекций
async function getCollections() {
  const res = await fetch('/api/collections');
  return res.json();
}

// Создать коллекцию
async function createCollection(name) {
  return api('/api/collections', {
    method: 'POST',
    body: JSON.stringify({ name }),
  });
}

// Поиск внутри коллекции
async function searchInCollection(collectionId, query = '') {
  return search(query, { collection: collectionId });
}
```

## Преобразование промптов

Преобразование между форматами A1111 и NAI:

```javascript
async function convertPrompt(prompt, direction) {
  // direction: "a1111_to_nai" or "nai_to_a1111"
  const res = await api('/api/convert', {
    method: 'POST',
    body: JSON.stringify({ prompt, direction }),
  });
  return res.converted;
}
```

## Развёртывание

### Распространение кастомного UI

Если вы хотите поделиться кастомным UI с другими пользователями:

1. **Git-репозиторий**: запушить в GitHub и т. п. → установить через Settings UI
2. **ZIP-архив**: упаковать файлы в ZIP и поделиться ссылкой на загрузку
3. **Ручное размещение**: скопировать напрямую в каталог `ui/<name>/`

### Установка

Устанавливать можно через вкладку «UI» на странице Settings или через API:

```bash
# Установка через curl
curl -X POST http://localhost:5000/api/ui/install \
  -H "X-Requested-With: XMLHttpRequest" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://github.com/user/my-custom-ui.git"}'
```

### Требования к manifest.json

Файл `manifest.json` распространяемого UI должен содержать следующее:

```json
{
  "name": "my-custom-ui",
  "version": "1.0.0",
  "description": "A beautiful custom UI for YU AI Manager",
  "author": "Your Name",
  "api_version": "1"
}
```

- Поля `name` и `version` обязательны
- Значение `name` также используется как имя каталога установки
- Имя `"default"` зарезервировано и не может использоваться
