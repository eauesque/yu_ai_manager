# API параметров

API для управления параметрами приложения, шифрованием секретов и интеграцией с менеджерами паролей (1Password / Bitwarden).

Значения секретов всегда маскируются (`****`) в GET ответах. Поле `source` указывает, от какого бэкенда было разрешено значение.

## Аутентификация

Все конечные точки требуют аутентификацию PIN или API Key.

---

## GET /api/settings/schema

Получение полного определения схемы параметров. Возвращает имена ключей, типы, значения по умолчанию, категории и другие метаданные для всех параметров.

### Параметры

Нет

### Ответ

```json
{
  "schema": [
    {
      "key": "pin",
      "type": "str",
      "default": "",
      "category": "security",
      "secret": true,
      "label": "PIN Code"
    }
  ]
}
```

| Поле | Тип | Описание |
|-------|------|-------------|
| `key` | string | Ключ параметра (разделенный точками, например `github.token`) |
| `type` | string | Тип значения (`str`, `int`, `float`, `bool`) |
| `default` | any | Значение по умолчанию |
| `category` | string | Имя категории |
| `secret` | bool | Является ли это значением секрета |
| `label` | string | Отображаемое имя |

---

## GET /api/settings/all

Получение всех значений параметров. Значения секретов возвращаются в замаскированном виде.

### Параметры

Нет

### Ответ

```json
{
  "settings": [
    {
      "key": "pin",
      "value": "****",
      "source": "encrypted",
      "secret": true,
      "category": "security"
    },
    {
      "key": "theme",
      "value": "dark",
      "source": "config",
      "secret": false,
      "category": "appearance"
    }
  ]
}
```

| Поле | Тип | Описание |
|-------|------|-------------|
| `key` | string | Ключ параметра |
| `value` | any | Текущее значение (замаскировано, если секрет) |
| `source` | string | Источник значения: `default` / `config` / `encrypted` / `1password` / `bitwarden` |
| `secret` | bool | Является ли это значением секрета |
| `category` | string | Имя категории |

---

## GET /api/settings/\<key\>

Получение значения одного параметра. Ключ использует формат пути, разделенный точками (например `github.token`).

### Параметры

| Параметр | Тип | Описание |
|-----------|------|-------------|
| `key` | string | Ключ параметра (параметр пути) |

### Ответ

```json
{
  "key": "github.token",
  "value": "****",
  "source": "1password",
  "secret": true,
  "category": "integrations"
}
```

### Ошибки

| Статус | Код | Описание |
|--------|------|-------------|
| 404 | `not_found` | Неизвестный ключ параметра |

---

## PUT /api/settings/\<key\>

Обновление значения параметра. Значения секретов автоматически шифруются. Опционально указывать 1Password URI для управления секретом извне.

### Ограничение скорости

DESTRUCTIVE

### Параметры

| Параметр | Тип | Описание |
|-----------|------|-------------|
| `key` | string | Ключ параметра (параметр пути) |

### Запрос

```json
{
  "value": "new-value",
  "op_uri": "op://vault/item/field"
}
```

| Параметр | Тип | Обязательный | Описание |
|-----------|------|----------|-------------|
| `value` | any | Да | Значение для установки. Автоматически преобразуется в тип, определенный схемой |
| `op_uri` | string | Нет | 1Password URI. Когда указано, сохраняет отображение `op_secrets` вместо значения |

### Ответ

```json
{
  "key": "github.token",
  "value": "****",
  "source": "encrypted"
}
```

### Ошибки

| Статус | Код | Описание |
|--------|------|-------------|
| 400 | `bad_request` | В теле запроса отсутствует `value` |
| 404 | `not_found` | Неизвестный ключ параметра |

---

## GET /api/settings/secrets/status

Получение статуса бэкенда ключа шифрования. Показывает, какой метод управления ключами используется в данный момент.

### Параметры

Нет

### Ответ

```json
{
  "backend": "keychain",
  "available": true,
  "keychain_supported": true
}
```

| Поле | Тип | Описание |
|-------|------|-------------|
| `backend` | string | Текущий бэкенд ключа (`keychain` / `passphrase` / `file`) |
| `available` | bool | Доступно ли шифрование |
| `keychain_supported` | bool | Поддерживается ли системное хранилище ключей ОС |

---

## POST /api/settings/secrets/export

Экспорт ключа шифрования в виде JSON, защищённого паролем. Используется для резервного копирования или переноса в другую среду.

### Ограничение скорости

DESTRUCTIVE

### Запрос

```json
{
  "password": "my-export-password"
}
```

| Параметр | Тип | Обязательный | Описание |
|-----------|------|----------|-------------|
| `password` | string | Да | Пароль для защиты экспортируемых данных |

### Ответ

```json
{
  "success": true,
  "export_data": "base64-encoded-encrypted-key-data"
}
```

### Ошибки

| Статус | Код | Описание |
|--------|------|-------------|
| 400 | `bad_request` | В запросе отсутствует `password` |
| 400 | `export_failed` | Операция экспорта завершилась ошибкой |

---

## POST /api/settings/secrets/import

Импорт ключа шифрования из ранее экспортированных данных.

### Ограничение скорости

DESTRUCTIVE

### Запрос

```json
{
  "export_data": "base64-encoded-encrypted-key-data",
  "password": "my-export-password"
}
```

| Параметр | Тип | Обязательный | Описание |
|-----------|------|----------|-------------|
| `export_data` | string | Да | Данные, полученные при экспорте |
| `password` | string | Да | Пароль, заданный при экспорте |

### Ответ

```json
{
  "success": true,
  "message": "Key imported successfully"
}
```

### Ошибки

| Статус | Код | Описание |
|--------|------|-------------|
| 400 | `bad_request` | Отсутствует `export_data` или `password` |
| 400 | `import_failed` | Неверный пароль или повреждённые данные |

---

## POST /api/settings/secrets/migrate-keychain

Перенос ключа шифрования из файлового бэкенда в хранилище ключей ОС. Поддерживает macOS Keychain, Windows Credential Manager и Linux Secret Service.

### Ограничение скорости

DESTRUCTIVE

### Запрос

Нет (тело не требуется)

### Ответ

```json
{
  "success": true,
  "message": "Key migrated to OS keychain"
}
```

### Ошибки

| Статус | Код | Описание |
|--------|------|-------------|
| 400 | `migration_failed` | Хранилище ключей недоступно или перенос завершился ошибкой |

---

## GET /api/settings/op-status

Получение статуса подключения 1Password CLI (`op`).

### Параметры

Нет

### Ответ

```json
{
  "available": true,
  "signed_in": true,
  "version": "2.24.0"
}
```

| Поле | Тип | Описание |
|-------|------|-------------|
| `available` | bool | Наличие команды `op` в PATH |
| `signed_in` | bool | Выполнен ли вход в 1Password |
| `version` | string | Версия `op` CLI |

---

## GET /api/settings/secrets/op-vaults

Получение списка доступных хранилищ 1Password.

### Параметры

Нет

### Ответ

```json
{
  "vaults": [
    {
      "id": "abc123",
      "name": "Personal"
    }
  ]
}
```

### Ошибки

| Статус | Код | Описание |
|--------|------|-------------|
| 503 | `op_unavailable` | CLI 1Password недоступен |

---

## POST /api/settings/secrets/push-to-op

Пакетная запись всех секретных параметров в 1Password и сохранение отображений `op_secrets` в config.json.

### Ограничение скорости

DESTRUCTIVE

### Запрос

```json
{
  "vault": "Personal",
  "item_title": "YU AI Manager",
  "remove_local": false
}
```

| Параметр | Тип | Обязательный | Описание |
|-----------|------|----------|-------------|
| `vault` | string | Да | Целевое хранилище 1Password |
| `item_title` | string | Нет | Название элемента в 1Password. По умолчанию: `YU AI Manager` |
| `remove_local` | bool | Нет | Если `true`, удаляет локально зашифрованные значения из config.json после отправки. По умолчанию: `false` |

### Ответ

```json
{
  "message": "2 secrets pushed to 1Password",
  "pushed_keys": ["github.token", "pin"],
  "uris": {
    "github.token": "op://Personal/YU AI Manager/github.token",
    "pin": "op://Personal/YU AI Manager/pin"
  },
  "remove_local": false
}
```

### Ошибки

| Статус | Код | Описание |
|--------|------|-------------|
| 400 | `bad_request` | Отсутствует `vault` |
| 400 | `no_secrets` | Нет секретов для отправки |
| 500 | `op_push_failed` | Не удалось выполнить запись в 1Password |
| 503 | `op_unavailable` | CLI 1Password недоступен |

---

## DELETE /api/settings/op-mapping/\<key\>

Удаление отображения URI 1Password с возвратом к локальному шифрованию.

### Ограничение скорости

WRITE

### Параметры

| Параметр | Тип | Описание |
|-----------|------|-------------|
| `key` | string | Ключ параметра (параметр пути) |

### Ответ

```json
{
  "key": "github.token",
  "unlinked": true
}
```

### Ошибки

| Статус | Код | Описание |
|--------|------|-------------|
| 404 | `not_found` | Ключ не найден в отображении `op_secrets` |

---

## GET /api/settings/bw-status

Получение статуса подключения Bitwarden CLI (`bw`).

### Параметры

Нет

### Ответ

```json
{
  "available": true,
  "status": "unlocked"
}
```

| Поле | Тип | Описание |
|-------|------|-------------|
| `available` | bool | Наличие команды `bw` в PATH |
| `status` | string | Статус сессии Bitwarden |

---

## GET /api/settings/secrets/bw-folders

Получение списка доступных папок Bitwarden.

### Параметры

Нет

### Ответ

```json
{
  "folders": [
    {
      "id": "folder-uuid",
      "name": "Development"
    }
  ]
}
```

### Ошибки

| Статус | Код | Описание |
|--------|------|-------------|
| 503 | `bw_unavailable` | Bitwarden CLI недоступен |

---

## POST /api/settings/secrets/push-to-bw

Пакетная запись всех секретных параметров в Bitwarden и сохранение отображений `bw_secrets` в config.json.

### Ограничение скорости

WRITE

### Запрос

```json
{
  "folder_id": "folder-uuid",
  "item_name": "YU AI Manager"
}
```

| Параметр | Тип | Обязательный | Описание |
|-----------|------|----------|-------------|
| `folder_id` | string/null | Нет | Идентификатор папки Bitwarden. Не указывайте, чтобы не использовать папку |
| `item_name` | string | Нет | Название элемента в Bitwarden. По умолчанию: `YU AI Manager` |

### Ответ

```json
{
  "message": "2 secrets pushed to Bitwarden",
  "pushed_keys": ["github.token", "pin"],
  "mappings": {
    "github.token": {"item_id": "item-uuid", "field": "github.token"},
    "pin": {"item_id": "item-uuid", "field": "pin"}
  }
}
```

### Ошибки

| Статус | Код | Описание |
|--------|------|-------------|
| 400 | `no_secrets` | Нет секретов для отправки |
| 500 | `bw_push_failed` | Не удалось выполнить запись в Bitwarden |
| 503 | `bw_unavailable` | Bitwarden CLI недоступен |

---

## DELETE /api/settings/bw-mapping/\<key\>

Удаление отображения Bitwarden с возвратом к локальному шифрованию.

### Ограничение скорости

WRITE

### Параметры

| Параметр | Тип | Описание |
|-----------|------|-------------|
| `key` | string | Ключ параметра (параметр пути) |

### Ответ

```json
{
  "key": "github.token",
  "unlinked": true
}
```

### Ошибки

| Статус | Код | Описание |
|--------|------|-------------|
| 404 | `not_found` | Ключ не найден в отображении `bw_secrets` |
