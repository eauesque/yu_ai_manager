# SNS Share API

API для обмена в социальных сетях, публикации на Bluesky и управления очередью уведомлений.

Предоставляется с помощью `routes/sns_share.py`. Все конечные точки требуют аутентификацию (сессия PIN или ключ API).

## Предпросмотр и X Intent

### GET /api/sns/preview

Развернуть шаблон поста с метаданными изображения и вернуть предпросмотр. Полезно для предпросмотра того, что будет опубликовано перед общей ссылкой.

### Параметры

| Параметр | Тип | Требуется | Описание |
|-----------|------|----------|-------------|
| `file_id` | int | Да | ID файла целевого изображения |
| `template` | string | Нет | Строка пользовательского шаблона (использует значение по умолчанию, если опущена) |

### Ответ

```json
{
  "text": "New artwork: sunset landscape #aiart #stablediffusion",
  "graphemes": 52,
  "meta": {
    "title": "sunset landscape",
    "model": "sd_xl_base_1.0",
    "generator": "a1111"
  }
}
```

### Пример curl

```bash
curl -H "Authorization: Bearer sk_xxxxx" \
  "http://localhost:5000/api/sns/preview?file_id=42"
```

### GET /api/sns/x/intent

Создать URL X (Twitter) Web Intent для обмена. Откроет диалог составления X с предварительно заполненным текстом.

### Параметры

| Параметр | Тип | Требуется | Описание |
|-----------|------|----------|-------------|
| `file_id` | int | Да | ID файла целевого изображения |

### Ответ

```json
{
  "url": "https://twitter.com/intent/tweet?text=New+artwork%3A+sunset+landscape+%23aiart"
}
```

---

## Публикация на Bluesky

### POST /api/sns/bluesky/post

Опубликовать текст (и опционально изображение) на Bluesky.

### Запрос

```json
{
  "file_id": 42,
  "text": "Check out my new artwork! #aiart",
  "attach_image": true
}
```

| Поле | Тип | Требуется | Описание |
|-------|------|----------|-------------|
| `file_id` | int | Да | ID файла целевого изображения |
| `text` | string | Нет | Текст поста (использует расширение шаблона, если опущено) |
| `attach_image` | boolean | Нет | Приложить изображение к посту (по умолчанию: false) |

### Ответ

```json
{
  "ok": true,
  "uri": "at://did:plc:xxxxx/app.bsky.feed.post/yyyyy"
}
```

### Ответ об ошибке

```json
{
  "ok": false,
  "error": "Authentication failed: invalid app password"
}
```

### POST /api/sns/bluesky/test

Проверить соединение Bluesky с настроенными учетными данными.

### Ответ

```json
{
  "ok": true,
  "handle": "user.bsky.social",
  "display_name": "My Display Name"
}
```

### Ответ об ошибке

```json
{
  "ok": false,
  "error": "Invalid identifier or password"
}
```

---

## Конфигурация SNS

### GET /api/sns/config

Получить конфигурацию SNS. Пароли замаскированы в ответе.

### Ответ

```json
{
  "bluesky": {
    "handle": "user.bsky.social",
    "app_password": "****...xxxx"
  },
  "post_template": "{title} #aiart #{generator}"
}
```

### POST /api/sns/config

Сохранить конфигурацию SNS.

### Запрос

```json
{
  "bluesky_handle": "user.bsky.social",
  "bluesky_app_password": "xxxx-xxxx-xxxx-xxxx",
  "post_template": "{title} #aiart #{generator}"
}
```

| Поле | Тип | Требуется | Описание |
|-------|------|----------|-------------|
| `bluesky_handle` | string | Нет | Дескриптор Bluesky (например `user.bsky.social`) |
| `bluesky_app_password` | string | Нет | Пароль приложения Bluesky |
| `post_template` | string | Нет | Шаблон поста по умолчанию с переменными `{placeholder}` |

### Пример curl

```bash
curl -X POST -H "Authorization: Bearer sk_xxxxx" \
  -H "Content-Type: application/json" \
  -H "X-Requested-With: XMLHttpRequest" \
  -d '{"bluesky_handle": "user.bsky.social", "bluesky_app_password": "xxxx-xxxx-xxxx-xxxx"}' \
  "http://localhost:5000/api/sns/config"
```

---

## Очередь уведомлений Bluesky

### GET /api/sns/bsky/queue

Список элементов очереди уведомлений с опциональными фильтрами.

### Параметры

| Параметр | Тип | Описание |
|-----------|------|-------------|
| `status` | string | Фильтр: `pending`, `notified`, `dismissed` или пусто для всех |
| `type` | string | Фильтр типа уведомления (например `mention`, `reply`, `quote`, `like`, `repost`, `follow`) |
| `limit` | int | Максимальное количество результатов (по умолчанию 50) |

### Ответ

```json
{
  "data": {
    "items": [
      {
        "id": 1,
        "type": "mention",
        "author_handle": "someone.bsky.social",
        "author_display_name": "Someone",
        "text": "@user.bsky.social great artwork!",
        "uri": "at://did:plc:xxxxx/app.bsky.feed.post/yyyyy",
        "created_at": "2026-03-15T10:00:00Z",
        "fetched_at": "2026-03-15T12:00:00Z",
        "status": "pending",
        "triage_result": null
      }
    ],
    "stats": { "pending": 3, "notified": 1, "dismissed": 5, "total": 9 }
  }
}
```

### GET /api/sns/bsky/queue/pending

Получить ожидающие (необработанные) уведомления для MCP уведомления.

### Ответ

```json
{
  "data": {
    "items": [...],
    "count": 3,
    "stats": { "pending": 3, "notified": 1, "dismissed": 5, "total": 9 }
  }
}
```

### POST /api/sns/bsky/queue/<queue_id>/triage

Установить результат сортировки для элемента очереди.

### Запрос

```json
{ "result": "valid" }
```

| Поле | Тип | Требуется | Описание |
|-------|------|----------|-------------|
| `result` | string | Да | `valid` или `invalid` |

### PUT /api/sns/bsky/queue/<queue_id>/status

Обновить статус элемента очереди.

### Запрос

```json
{ "status": "notified" }
```

| Поле | Тип | Требуется | Описание |
|-------|------|----------|-------------|
| `status` | string | Да | `pending`, `notified` или `dismissed` |

### POST /api/sns/bsky/queue/<queue_id>/respond

Отправить автоматический ответ на уведомление.

### Запрос

```json
{ "text": "Thank you for your kind words!" }
```

| Поле | Тип | Требуется | Описание |
|-------|------|----------|-------------|
| `text` | string | Да | Текст ответа для публикации в виде ответа |

### POST /api/sns/bsky/queue/poll

Запустить немедленный опрос новых уведомлений Bluesky.

### Пример curl

```bash
curl -X POST -H "Authorization: Bearer sk_xxxxx" \
  -H "X-Requested-With: XMLHttpRequest" \
  "http://localhost:5000/api/sns/bsky/queue/poll"
```

---

## Конфигурация монитора Bluesky

### GET /api/sns/bsky/monitor/config

Получить параметры монитора уведомлений Bluesky.

### Ответ

```json
{
  "data": {
    "poll_interval_minutes": 15,
    "auto_dismiss_follow": false,
    "auto_dismiss_like": true,
    "auto_dismiss_repost": true,
    "auto_respond_enabled": false,
    "notify_on_connect": true
  }
}
```

### PUT /api/sns/bsky/monitor/config

Обновить параметры монитора уведомлений Bluesky. Обновляются только предоставленные поля.

### Запрос

```json
{
  "poll_interval_minutes": 30,
  "auto_dismiss_follow": false,
  "auto_dismiss_like": true,
  "auto_dismiss_repost": true,
  "auto_respond_enabled": false,
  "notify_on_connect": true
}
```

| Поле | Тип | Требуется | Описание |
|-------|------|----------|-------------|
| `poll_interval_minutes` | int | Нет | Интервал опроса в минутах |
| `auto_dismiss_follow` | boolean | Нет | Автоматически отклонять уведомления о подписке |
| `auto_dismiss_like` | boolean | Нет | Автоматически отклонять уведомления о понравившихся |
| `auto_dismiss_repost` | boolean | Нет | Автоматически отклонять уведомления о репостах |
| `auto_respond_enabled` | boolean | Нет | Включить автоматические ответы |
| `notify_on_connect` | boolean | Нет | Отправить уведомление при подключении клиента MCP |

---

## Подсказки для сортировки и шаблоны автоматических ответов

### GET /api/sns/bsky/monitor/triage-prompts

Получить редактируемые подсказки для сортировки, шаблоны автоматических ответов и их значения по умолчанию.

### Ответ

```json
{
  "data": {
    "triage_prompts": {
      "mention": "Evaluate this mention for relevance...",
      "reply": "Evaluate this reply...",
      "quote": "Evaluate this quote post..."
    },
    "auto_responses": {
      "mention": "Thanks for the mention!",
      "reply": "Thank you for your reply!",
      "quote": "Thanks for sharing!"
    },
    "defaults": {
      "triage_prompts": {
        "mention": "Evaluate this mention for relevance...",
        "reply": "Evaluate this reply...",
        "quote": "Evaluate this quote post..."
      },
      "auto_responses": {
        "mention": "Thanks for the mention!",
        "reply": "Thank you for your reply!",
        "quote": "Thanks for sharing!"
      }
    }
  }
}
```

### PUT /api/sns/bsky/monitor/triage-prompts

Обновить подсказки для сортировки и/или шаблоны автоматических ответов. Обновляются только предоставленные поля.

### Запрос

```json
{
  "triage_prompts": {
    "mention": "Custom mention triage prompt...",
    "reply": "Custom reply triage prompt...",
    "quote": "Custom quote triage prompt..."
  },
  "auto_responses": {
    "mention": "Custom mention auto-response...",
    "reply": "Custom reply auto-response...",
    "quote": "Custom quote auto-response..."
  }
}
```

| Поле | Тип | Требуется | Описание |
|-------|------|----------|-------------|
| `triage_prompts` | object | Нет | Подсказки для сортировки, ключированные по типу уведомления (`mention`, `reply`, `quote`) |
| `auto_responses` | object | Нет | Шаблоны автоматических ответов, ключированные по типу уведомления |
