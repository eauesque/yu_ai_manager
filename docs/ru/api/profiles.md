# API Профилей

API для управления профилями конфигурации. Профили — это именованные снимки параметров приложения, хранящиеся как `profiles/<name>.json`.

Все конечные точки требуют аутентификации PIN. Возвращает 403, если аутентификация PIN отключена, или 401, если сессия не аутентифицирована.

## Правила именования профилей

- От 1 до 64 символов
- Допустимые символы: `a-zA-Z0-9_-`

---

## GET /api/profiles

Список метаданных всех профилей. Отсортировано по избранным в первую очередь, затем по алфавиту по метке.

### Parameters

None

### Response

```json
{
  "profiles": [
    {
      "name": "default",
      "label": "Default",
      "description": "Standard configuration",
      "favorite": true,
      "last_used_at": "2026-03-20T12:00:00Z",
      "created_at": "2026-01-01T00:00:00Z",
      "db": null,
      "is_active": true
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Имя профиля (используется как имя файла) |
| `label` | string | Метка дисплея |
| `description` | string | Текст описания |
| `favorite` | boolean | Флаг избранного |
| `last_used_at` | string/null | Последний используемый временной штамп (ISO 8601) |
| `created_at` | string/null | Временной штамп создания (ISO 8601) |
| `db` | string/null | Связанный путь базы данных |
| `is_active` | boolean | Активен ли это текущий профиль |

## GET /api/profiles/\<name\>

Получить полные данные конкретного профиля.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | string | Имя профиля (параметр пути) |

### Response

```json
{
  "profile": {
    "name": "default",
    "label": "Default",
    "description": "Standard configuration",
    "favorite": false,
    "created_at": "2026-01-01T00:00:00Z",
    "last_used_at": "2026-03-20T12:00:00Z",
    "is_active": true
  }
}
```

### Errors

| Code | Status | Description |
|------|--------|-------------|
| `invalid_profile_name` | 400 | Неверное имя профиля |
| `profile_not_found` | 404 | Профиль не существует |

## POST /api/profiles

Создать новый профиль.

### Rate Limit

WRITE

### Request

```json
{
  "name": "my_profile",
  "label": "My Profile",
  "description": "Custom settings",
  "base_config": {}
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | string | Yes | Имя профиля (`a-zA-Z0-9_-`, 1-64 символа) |
| `label` | string | No | Метка дисплея. По умолчанию используется `name`, если не указано |
| `description` | string | No | Текст описания |
| `base_config` | object | No | Начальные значения конфигурации. Ключи, отличные от ключей метаданных (`name`, `label`, `description`, `favorite`, `last_used_at`, `created_at`, `db`), копируются в профиль |

### Response (201)

```json
{
  "profile": {
    "name": "my_profile",
    "label": "My Profile",
    "description": "Custom settings",
    "favorite": false,
    "created_at": "2026-03-22T00:00:00Z",
    "last_used_at": null
  }
}
```

### Errors

| Code | Status | Description |
|------|--------|-------------|
| `invalid_profile_name` | 400 | Неверное имя профиля |
| `invalid_label` | 400 | Метка пуста |
| `profile_exists` | 409 | Профиль с таким же именем уже существует |

## PUT /api/profiles/\<name\>

Обновить метаданные профиля. Можно изменить только `label`, `description` и `favorite`.

### Rate Limit

WRITE

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | string | Имя профиля (параметр пути) |

### Request

```json
{
  "label": "Updated Label",
  "description": "Updated description",
  "favorite": true
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `label` | string | No | Метка дисплея |
| `description` | string | No | Текст описания |
| `favorite` | boolean | No | Флаг избранного |

Должно быть предоставлено как минимум одно поле.

### Response

```json
{
  "profile": {
    "name": "my_profile",
    "label": "Updated Label",
    "description": "Updated description",
    "favorite": true,
    "created_at": "2026-03-22T00:00:00Z",
    "last_used_at": null
  }
}
```

### Errors

| Code | Status | Description |
|------|--------|-------------|
| `empty_update` | 400 | Не указаны поля для обновления |
| `update_failed` | 400 | Профиль не найден и т. д. |

## DELETE /api/profiles/\<name\>

Удалить профиль. Текущий активный профиль не может быть удалён.

### Rate Limit

WRITE

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | string | Имя профиля (параметр пути) |

### Response

```json
{
  "deleted": "my_profile"
}
```

### Errors

| Code | Status | Description |
|------|--------|-------------|
| `delete_active` | 400 | Не удаётся удалить активный профиль |
| `delete_failed` | 400 | Профиль не найден и т. д. |

## POST /api/profiles/\<name\>/duplicate

Дублировать профиль с новым именем.

### Rate Limit

WRITE

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | string | Имя исходного профиля (параметр пути) |

### Request

```json
{
  "new_name": "copied_profile",
  "new_label": "Copied Profile"
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `new_name` | string | Yes | Новое имя профиля |
| `new_label` | string | No | Новая метка дисплея. По умолчанию используется `new_name`, если не указано |

### Response (201)

```json
{
  "profile": {
    "name": "copied_profile",
    "label": "Copied Profile",
    "description": "Custom settings",
    "favorite": false,
    "created_at": "2026-03-22T00:00:00Z",
    "last_used_at": null
  }
}
```

### Errors

| Code | Status | Description |
|------|--------|-------------|
| `duplicate_failed` | 400 | Исходный профиль не найден, неверное новое имя или имя уже существует |

## POST /api/profiles/\<name\>/rename

Переименовать профиль. Если переименуется активный профиль, `active_profile` в `config.json` автоматически обновляется.

### Rate Limit

WRITE

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | string | Текущее имя профиля (параметр пути) |

### Request

```json
{
  "new_name": "renamed_profile"
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `new_name` | string | Yes | Новое имя профиля |

### Response

```json
{
  "profile": {
    "name": "renamed_profile",
    "label": "My Profile",
    "description": "Custom settings",
    "favorite": false,
    "created_at": "2026-03-22T00:00:00Z",
    "last_used_at": null
  }
}
```

### Errors

| Code | Status | Description |
|------|--------|-------------|
| `invalid_profile_name` | 400 | Неверное новое имя профиля |
| `rename_failed` | 400 | Исходный профиль не найден или новое имя уже существует |

## POST /api/profiles/\<name\>/favorite

Переключить статус избранного профиля. Инвертирует текущее значение `favorite`.

### Rate Limit

WRITE

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | string | Имя профиля (параметр пути) |

### Request

No body required.

### Response

```json
{
  "profile": {
    "name": "my_profile",
    "label": "My Profile",
    "favorite": true
  }
}
```

### Errors

| Code | Status | Description |
|------|--------|-------------|
| `profile_not_found` | 404 | Профиль не существует |
| `favorite_failed` | 400 | Ошибка обновления |

---

## QR Экспорт / Импорт

Экспортировать и импортировать профили как JSON строки для QR кодов. Чувствительные поля (содержащие `pin`, `token`, `secret` или `key`) автоматически удаляются при экспорте.

## GET /api/profiles/\<name\>/export

Экспортировать профиль как QR-готовую JSON строку. Чувствительные поля исключены.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | string | Имя профиля (параметр пути) |

### Response

```json
{
  "qr_data": "{\"schema\":\"yu://profile/1\",\"profile\":{\"name\":\"my_profile\",\"label\":\"My Profile\",\"description\":\"...\"}}"
}
```

`qr_data` — это JSON строка для встраивания в QR код. Поле `schema` идентифицирует версию формата.

### Errors

| Code | Status | Description |
|------|--------|-------------|
| `profile_not_found` | 404 | Профиль не существует |

## POST /api/profiles/import-preview

Предварительный просмотр импорта из QR данных. Используется для проверки различий с существующими профилями. Реальный импорт не выполняется.

### Rate Limit

WRITE

### Request

```json
{
  "qr_data": "{\"schema\":\"yu://profile/1\",\"profile\":{\"name\":\"my_profile\",\"label\":\"My Profile\"}}"
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `qr_data` | string/object | Yes | JSON строка или разобранный объект из QR кода |

### Response (new profile)

```json
{
  "mode": "new",
  "name": "my_profile",
  "label": "My Profile",
  "preview": {
    "name": "my_profile",
    "label": "My Profile",
    "description": "..."
  }
}
```

### Response (existing profile)

```json
{
  "mode": "existing",
  "name": "my_profile",
  "label": "My Profile",
  "diff": {
    "description": {
      "old": "Old description",
      "new": "New description"
    }
  }
}
```

### Errors

| Code | Status | Description |
|------|--------|-------------|
| `invalid_qr` | 400 | Неверные QR данные или отсутствует ключ `profile` |
| `invalid_profile_name` | 400 | Неверное имя профиля |

## POST /api/profiles/import

Импортировать профиль из QR данных. Поддерживает три режима: создание нового, слияние различий и полная перезапись.

### Rate Limit

WRITE

### Request

```json
{
  "qr_data": "{\"schema\":\"yu://profile/1\",\"profile\":{\"name\":\"my_profile\",\"label\":\"My Profile\"}}",
  "mode": "full"
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `qr_data` | string/object | Yes | JSON строка или разобранный объект из QR кода |
| `mode` | string | No | Режим импорта: `full` (полная перезапись, по умолчанию), `diff` (слияние только изменённых ключей), `new` (создание нового только) |

### Response

```json
{
  "imported": "my_profile",
  "mode": "full"
}
```

Возвращает статус 201 при создании нового профиля.

### Errors

| Code | Status | Description |
|------|--------|-------------|
| `invalid_qr` | 400 | Неверные QR данные |
| `invalid_profile_name` | 400 | Неверное имя профиля |
| `profile_exists` | 409 | Профиль уже существует, когда `mode=new` |
| `import_failed` | 400 | Импорт не выполнен |
