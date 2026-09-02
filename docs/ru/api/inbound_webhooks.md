# API входящих вебхуков

Конечная точка получения для отправки событий из внешних сервисов на шину событий yu_ai_manager.

## Конечная точка получения (не требуется аутентификация — на основе токена)

`POST /api/webhooks/receive/{token}`

### Тело запроса

| Поле | Тип | Описание |
|-------|------|-------------|
| event | string | event_type для запуска (по умолчанию: `webhook.received`) |
| data | object | Данные события |

### Ответ

```json
{"ok": true, "event": "scan.start"}
```

### Ошибки

| Код | Описание |
|------|-------------|
| 403 | Неверный токен / несовпадение HMAC / событие отсутствует в allowed_events |

## API управления (требуется PIN сеанс)

### Создание

`POST /api/webhooks/inbound`

```json
{"label": "n8n trigger", "allowed_events": ["scan.start"]}
```

Ответ:

```json
{
  "id": "iwh_a1b2c3...",
  "token": "64char_hex...",
  "label": "n8n trigger",
  "allowed_events": ["scan.start"],
  "active": true,
  "created_at": 1712188800
}
```

### Список

`GET /api/webhooks/inbound`

### Обновление

`PUT /api/webhooks/inbound/{id}`

```json
{"label": "updated", "allowed_events": ["scan.start", "tag.add"], "active": true}
```

### Удаление

`DELETE /api/webhooks/inbound/{id}`

## Аутентификация

- Принято, если токен в URL совпадает
- Если присутствует заголовок `X-Webhook-Signature`, выполняется дополнительная проверка HMAC-SHA256 (необязательно)

## Безопасность

- Токен имеет формат 64-символьного шестнадцатеричного числа (256 бит)
- `allowed_events` ограничивает, какие события могут быть запущены
- Пустой массив `allowed_events` = все события разрешены
