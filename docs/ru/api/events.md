# API событий (SSE)

Доставка событий в реальном времени через Server-Sent Events.

## GET /api/events/stream

Основной поток событий. Все страницы используют одно соединение.

### Подключение

```javascript
// Из TypeScript модуля
import { sseSubscribe } from '../sse';
sseSubscribe('scan.complete', (data) => { ... });

// Из встроенного скрипта шаблона
window.sseSubscribe('scan.complete', (data) => { ... });
```

**Важно**: Не используйте `new EventSource()` напрямую. `window.EventSource` перезаписан Proxy, поэтому прямое использование вызывает ошибки.

### Параметры

| Параметр | Тип | Описание |
|-----------|------|-------------|
| `types` | string | Типы событий для подписки (разделены запятой; опустить для всех событий) |

### Лимиты подключения

- До 10 одновременных соединений на IP
- С учетом видимости: соединение переходит в сокращенное состояние, когда вкладка скрыта
- Автоматическое переподключение с экспоненциальной задержкой

## Типы событий

### Сканирование

| Событие | Данные | Описание |
|-------|------|-------------|
| `scan.progress` | `{ scanned, total, current_file }` | Прогресс сканирования |
| `scan.complete` | `{ added_count, updated_count, added_ids?, updated_ids? }` | Сканирование завершено |
| `config.scan_roots_changed` | `{}` | Уведомление об изменении корня сканирования |

### Избранное и коллекции

| Событие | Данные | Описание |
|-------|------|-------------|
| `favorite.add` | `{ file_id, collection_id }` | Избранное добавлено |
| `favorite.remove` | `{ file_id, collection_id }` | Избранное удалено |
| `collection.create` | `{ id, name }` | Коллекция создана |
| `collection.delete` | `{ id }` | Коллекция удалена |

### AI анализ и разметка

| Событие | Данные | Описание |
|-------|------|-------------|
| `semantic_index.start` | `{ total }` | Запущено индексирование CLIP |
| `semantic_index.progress` | `{ done, total }` | Прогресс индексирования CLIP |
| `semantic_index.complete` | `{ indexed }` | Индексирование CLIP завершено |
| `vlm_caption.start` | `{ total }` | Запущено субтитрирование VLM |
| `vlm_caption.progress` | `{ done, total }` | Прогресс субтитрирования VLM |
| `vlm_caption.complete` | `{ processed }` | Субтитрирование VLM завершено |
| `yolo_detect.start` | `{ total }` | Запущено обнаружение YOLO |
| `yolo_detect.progress` | `{ done, total }` | Прогресс обнаружения YOLO |
| `yolo_detect.complete` | `{ detected }` | Обнаружение YOLO завершено |

### Freeze и Pull-back

| Событие | Данные | Описание |
|-------|------|-------------|
| `fpb.start` | `{ job_id }` | Работа начата |
| `fpb.progress` | `{ job_id, frame, total }` | Прогресс кадра |
| `fpb.complete` | `{ job_id, output_path }` | Работа завершена |
| `fpb.error` | `{ job_id, error }` | Ошибка работы |

### Журналы чата

| Событие | Данные | Описание |
|-------|------|-------------|
| `chatlog_reprocess.start` | `{ total }` | Запущена переработка AI |
| `chatlog_reprocess.progress` | `{ done, total }` | Прогресс переработки AI |
| `chatlog_reprocess.complete` | `{ processed }` | Переработка AI завершена |
| `chatlog_reprocess.error` | `{ error }` | Ошибка переработки AI |

### Планировщик

| Событие | Данные | Описание |
|-------|------|-------------|
| `scheduler.job_executed` | `{ job_id, result }` | Запланированная работа успешно завершена |
| `scheduler.job_error` | `{ job_id, error }` | Запланированная работа не удалась |

## GET /api/logs/stream

Выделенный поток SSE для журналов сервера. Работает независимо от основного потока.

### Параметры

| Параметр | Тип | Описание |
|-----------|------|-------------|
| `level` | string | Минимальный уровень журнала (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

### События

| Событие | Данные | Описание |
|-------|------|-------------|
| `log.entry` | `{ seq, ts, level, name, message }` | Запись в журнал |

### Лимиты подключения

- До 3 одновременных соединений на IP (отдельно от основного потока)
- Интервал сердцебиения 15 секунд (`: heartbeat\n\n`)
