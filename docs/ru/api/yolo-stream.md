# API потока YOLO

API для обработки потока YOLO в реальном времени. Предоставляет управление источниками потока, доставку MJPEG, правила обнаружения и функциональность записи/снимков.

Все конечные точки POST/PUT/DELETE требуют заголовок `X-Requested-With` (кроме использования ключа API Bearer).

---

## Управление источником

### GET /ext/hailo-yolo/api/stream/sources

Список всех зарегистрированных источников потока.

#### Ответ

```json
{
  "status": "ok",
  "sources": [
    {
      "id": "cam1",
      "name": "Front Camera",
      "url": "rtsp://192.168.1.100:554/stream",
      "type": "rtsp",
      "state": "running",
      "resolution": { "width": 1920, "height": 1080 },
      "fps": 25.0,
      "frame_count": 15420,
      "error": null,
      "viewers": 1
    }
  ]
}
```

### POST /ext/hailo-yolo/api/stream/sources

Добавить новый источник потока.

#### Запрос

```json
{
  "id": "cam2",
  "url": "rtsp://192.168.1.101:554/stream",
  "name": "Back Camera"
}
```

| Параметр | Тип | Требуется | Описание |
|-----------|------|----------|-------------|
| `id` | string | Да | Уникальный идентификатор источника |
| `url` | string | Да | RTSP URL или индекс устройства |
| `name` | string | Нет | Отображаемое имя |

#### Ответ (201)

```json
{ "status": "ok", "source": { "id": "cam2", "..." : "..." } }
```

### DELETE /ext/hailo-yolo/api/stream/sources/\<id\>

Удалить указанный источник.

#### Ответ

```json
{ "status": "ok" }
```

### POST /ext/hailo-yolo/api/stream/sources/\<id\>/start

Начать захват для указанного источника.

#### Ответ

```json
{ "status": "ok", "source": { "id": "cam1", "state": "running", "..." : "..." } }
```

### POST /ext/hailo-yolo/api/stream/sources/\<id\>/stop

Остановить захват для указанного источника.

#### Ответ

```json
{ "status": "ok", "source": { "id": "cam1", "state": "stopped", "..." : "..." } }
```

### POST /ext/hailo-yolo/api/stream/sources/\<id\>/test

Проверить соединение с источником. Если в теле запроса предоставлен URL, проверяется этот URL; в противном случае используется существующий URL источника.

#### Запрос

```json
{ "url": "rtsp://192.168.1.100:554/stream" }
```

#### Ответ

```json
{ "ok": true, "resolution": { "width": 1920, "height": 1080 } }
```

### GET /ext/hailo-yolo/api/stream/devices

Обнаружить подключенные USB камеры.

#### Ответ

```json
{
  "status": "ok",
  "devices": [
    { "index": 0, "name": "USB Camera", "resolution": null }
  ]
}
```

> **Примечание:** Нативный ответ Rust перечисляет USB-камеры только в Linux и никогда не открывает их; `resolution` всегда равно `null`. Windows и macOS возвращают `devices: []` и не поддерживают регистрацию по числовому индексу камеры.
>
> Fan-out событий также сокращён: нет неявной wildcard-доставки настроенным webhook-расширениям, LAN relay при совпадении пользовательского имени события с `RELAY_TYPES` и отдельного приёмника MCP-событий. `mcp_event` доставляется через общий SSE hub.

---

## Видеопоток

### GET /ext/hailo-yolo/api/stream/\<id\>/mjpeg

Возвращает поток MJPEG с наложением обнаружения YOLO. Максимум 4 одновременных зрителя на источник.

- **Content-Type**: `multipart/x-mixed-replace; boundary=frame`

---

## Управление правилами

### GET /ext/hailo-yolo/api/stream/rules

Список всех правил.

#### Ответ

```json
{
  "status": "ok",
  "rules": [
    {
      "id": "rule1",
      "name": "Person detection",
      "enabled": true,
      "conditions": {
        "classes": ["person"],
        "min_confidence": 0.7,
        "sources": ["cam1"],
        "schedule": { "start": "22:00", "end": "06:00", "days": ["mon","tue","wed","thu","fri","sat","sun"] }
      },
      "cooldown_sec": 60,
      "actions": [
        { "type": "snapshot", "save_dir": "./detections/snapshots" },
        { "type": "record", "save_dir": "./detections/videos", "duration_sec": 30, "extend_mode": "fixed" },
        { "type": "webhook", "url": "https://example.com/hook", "secret": "hmac-key" },
        { "type": "sse", "channel": "yolo_stream" },
        { "type": "mcp_event", "event": "yolo_stream.detection" }
      ]
    }
  ]
}
```

### POST /ext/hailo-yolo/api/stream/rules

Добавить новое правило. Передайте полный JSON правила в теле запроса.

#### Ответ (201)

```json
{ "status": "ok", "rule": { "..." : "..." } }
```

### PUT /ext/hailo-yolo/api/stream/rules/\<id\>

Обновить существующее правило.

#### Ответ

```json
{ "status": "ok", "rule": { "..." : "..." } }
```

### DELETE /ext/hailo-yolo/api/stream/rules/\<id\>

Удалить правило.

#### Ответ

```json
{ "status": "ok" }
```

---

## Записи и снимки

### GET /ext/hailo-yolo/api/stream/recordings

Список файлов записей.

#### Ответ

```json
{
  "status": "ok",
  "recordings": [
    { "filename": "cam1_20260328_220500.mp4", "path": "./detections/videos/cam1_20260328_220500.mp4", "size_bytes": 5242880, "created_at": "2026-03-28T22:05:00" }
  ]
}
```

### GET /ext/hailo-yolo/api/stream/snapshot/\<filename\>

Выдать файл снимка изображения.

---

## Статус

### GET /ext/hailo-yolo/api/stream/status

Получить общий статус конвейера и источника.

#### Ответ

```json
{
  "status": "ok",
  "pipeline": { "running": true, "queue_size": 2, "fps": 24.8 },
  "sources": [ { "id": "cam1", "state": "running" } ],
  "rules_count": 3,
  "recorder": { "active_recordings": 1 }
}
```

---

## Структура JSON правила

| Поле | Тип | Описание |
|-------|------|-------------|
| `id` | string | Уникальный идентификатор правила |
| `name` | string | Имя правила |
| `enabled` | boolean | Активно ли правило |
| `conditions.classes` | string[] | Целевые классы обнаружения (например `["person"]`) |
| `conditions.min_confidence` | number | Минимальный порог уверенности (0.0-1.0) |
| `conditions.sources` | string[] | ID целевых источников. Все источники, если опущено |
| `conditions.schedule` | object | Расписание (`start`, `end`, `days`) |
| `cooldown_sec` | number | Время охлаждения в секундах |
| `actions` | object[] | Массив действий |

### Типы действий

| type | Описание |
|------|-------------|
| `snapshot` | Сохранить снимок при обнаружении |
| `record` | Начать запись при обнаружении |
| `webhook` | Отправить уведомление на URL webhook (с подписью HMAC) |
| `sse` | Отправить событие в канал SSE |
| `mcp_event` | Запустить событие MCP |
