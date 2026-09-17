# API обновления системы

API для проверки новых версий на GitHub и применения обновлений приложений.
Автоматически обнаруживает тип установки (git / tauri / docker / portable) и предоставляет соответствующий метод обновления.

## GET /api/system/update/check

Проверить доступна ли новая версия на репозитории GitHub.

- **Ограничение частоты запросов**: Нет (GET)
- **Аутентификация**: Сессия PIN или ключ API

### Ответ

```json
{
  "current": "4.21.0",
  "latest": "4.22.0",
  "update_available": true,
  "release_url": "https://github.com/...",
  "release_notes": "## What's New\n...",
  "published_at": "2026-03-20T12:00:00Z",
  "install_type": "git",
  "docker_command": null,
  "portable_download_url": null
}
```

| Поле | Тип | Описание |
|-------|------|-------------|
| `current` | string | Текущая версия |
| `latest` | string | Последняя версия на GitHub |
| `update_available` | bool | Доступна ли новая версия |
| `release_url` | string | URL страницы релиза GitHub |
| `release_notes` | string | Примечания к релизу (Markdown) |
| `published_at` | string | Дата публикации релиза (ISO 8601) |
| `install_type` | string | Тип установки (`"git"`, `"tauri"`, `"docker"`, `"portable"`) |
| `docker_command` | string \| null | Только Docker: команда для обновления |
| `portable_download_url` | string \| null | Только portable: URL для загрузки |

---

## GET /api/system/update/status

Получить текущий тип установки и информацию о версии.

- **Ограничение частоты запросов**: Нет (GET)
- **Аутентификация**: Сессия PIN или ключ API

### Ответ

```json
{
  "version": "4.21.0",
  "install_type": "git",
  "update_in_progress": false
}
```

| Поле | Тип | Описание |
|-------|------|-------------|
| `version` | string | Текущая версия |
| `install_type` | string | Тип установки (`"git"` \| `"tauri"` \| `"docker"` \| `"portable"`) |
| `update_in_progress` | bool | Выполняется ли обновление |

---

## POST /api/system/update/apply

Применить доступное обновление. Поддерживается только для git клонов и portable установок.

- **Ограничение частоты запросов**: DESTRUCTIVE
- **Аутентификация**: Сессия PIN (localhost) или маркер перезагрузки
- **CSRF**: Требуется `X-Requested-With: XMLHttpRequest`

### Тело запроса

| Параметр | Тип | Требуется | Описание |
|-----------|------|----------|-------------|
| `confirm` | string | Да | Строка подтверждения. Должна быть `"update"` |

### Пример запроса

```json
{
  "confirm": "update"
}
```

### Ответ

```json
{
  "ok": true,
  "message": "Update started"
}
```

### SSE события

Во время обновления события `update.progress` доставляются через SSE.

```
event: update.progress
data: {"step": "backup", "status": "running", "detail": "Creating backup..."}
```

| Поле | Тип | Описание |
|-------|------|-------------|
| `step` | string | Этап прогресса (см. ниже) |
| `status` | string | `"running"` \| `"done"` \| `"error"` |
| `detail` | string | Детали этапа |

#### Справочник этапов

| Этап | Описание |
|------|-------------|
| `backup` | Создание резервной копии |
| `fetch` | Выполнение git fetch |
| `pull` | Выполнение git pull |
| `download` | Загрузка файлов (portable) |
| `extract` | Извлечение архива (portable) |
| `replace` | Замена файлов (portable) |
| `pip_install` | Установка зависимостей Python |
| `ts_build` | Построение TypeScript |
| `complete` | Обновление завершено |

### Ответы об ошибках

**Docker установки** (400):
```json
{
  "ok": false,
  "error": "Docker installs cannot be updated from the web UI. Pull the latest image instead.",
  "code": "DOCKER_UPDATE_NOT_SUPPORTED"
}
```

**Tauri установки** (400):
```json
{
  "ok": false,
  "error": "Tauri updates are handled by the desktop app's built-in updater.",
  "code": "TAURI_UPDATE_NOT_SUPPORTED"
}
```

---

## Примечания

- Установки Docker не могут использовать `/api/system/update/apply`. Используйте `docker pull` для получения последней версии
- Обновления приложения Tauri обрабатываются встроенным обновлением приложения
- Только git и portable установки поддерживают обновление через веб-интерфейс
- Во время процесса обновления может произойти перезагрузка сервера

---

## GET /api/system/update/unified-check

Проверить статус обновления для системы и всех расширений одновременно.

- **Ограничение частоты запросов**: Нет (GET)
- **Аутентификация**: Сессия PIN или ключ API

### Параметры запроса

| Параметр | Тип | Описание |
|-----------|------|-------------|
| `force` | string | `"1"` для обхода кеша и повторной проверки |

### Ответ

```json
{
  "system": {
    "current": "4.22.0",
    "latest": "4.23.0",
    "update_available": true,
    "install_type": "git"
  },
  "extensions": [
    {
      "name": "builtin-backup",
      "version": "1.0.0",
      "source": "builtin",
      "status": "builtin",
      "enabled": true,
      "description": "..."
    },
    {
      "name": "my-custom-ext",
      "version": "0.3.0",
      "source": "git",
      "status": "update_available",
      "enabled": true,
      "description": "...",
      "local_head": "abc12345",
      "remote_head": "def67890",
      "commits_behind": 3
    }
  ],
  "summary": {
    "total": 45,
    "up_to_date": 1,
    "update_available": 1,
    "unknown": 0,
    "builtin": 43
  }
}
```

| Поле | Тип | Описание |
|-------|------|-------------|
| `system` | object | Информация об обновлении системы (тот же формат, что и `check_for_update`) |
| `extensions` | array | Статус обновления для каждого расширения |
| `extensions[].status` | string | `"up_to_date"` \| `"update_available"` \| `"unknown"` \| `"builtin"` |
| `extensions[].source` | string | `"builtin"` \| `"git"` \| `"local"` |
| `extensions[].commits_behind` | int | Количество коммитов отставания от удаленной (если обновление доступно) |
| `summary` | object | Разбор по категориям |

---

## POST /api/system/update/unified-apply

Применить обновления для системы и/или расширений в одной операции. Конфигурации расширений автоматически резервируются перед обновлением.

- **Ограничение частоты запросов**: DESTRUCTIVE
- **Аутентификация**: Сессия PIN (localhost) или маркер перезагрузки
- **CSRF**: Требуется `X-Requested-With: XMLHttpRequest`

### Тело запроса

| Параметр | Тип | Требуется | Описание |
|-----------|------|----------|-------------|
| `update_system` | bool | Нет | Обновить систему (по умолчанию: true) |
| `update_extensions` | bool | Нет | Обновить расширения (по умолчанию: true) |
| `extension_names` | array | Нет | Список имен расширений для обновления (опустить для всех git расширений) |

### Пример запроса

```json
{
  "update_system": true,
  "update_extensions": true,
  "extension_names": ["my-custom-ext"]
}
```

### Ответ

```json
{
  "ok": true,
  "accepted": true,
  "message": "Unified update started. Progress via SSE (update.progress).",
  "update_system": true,
  "update_extensions": true
}
```

### SSE события

Во время объединенного обновления события `update.progress` включают флаг `"unified": true`.

```
event: update.progress
data: {"step": "ext_config_backup", "status": "done", "detail": "...", "unified": true}
event: update.progress
data: {"step": "ext_update_my-custom-ext", "status": "running", "detail": "(1/1)", "unified": true}
```

#### Дополнительные этапы

| Этап | Описание |
|------|-------------|
| `ext_config_backup` | Резервная копия конфигурации расширения |
| `ext_update_<name>` | Обновление отдельного расширения |

---

## Интеграция MCP

Управляйте обновлениями системы из Claude Desktop.

```
# Шаг 1: Проверить новую версию
check_for_update()

# Шаг 2: Проверить статус обновления
get_update_status()

# Шаг 3: Применить обновление (только git/portable)
apply_system_update(confirm="update")

# Объединенная проверка: система + все расширения
check_unified_updates()

# Объединенное применение: обновить систему + расширения одновременно
apply_unified_updates(update_system=True, update_extensions=True)
```

### MCP инструменты

| Инструмент | Описание |
|------|-------------|
| `check_for_update` | Проверить доступна ли новая версия на GitHub |
| `get_update_status` | Получить текущий тип установки и версию |
| `apply_system_update` | Применить доступное обновление (git/portable только) |
| `check_unified_updates` | Проверить статус обновления для системы + всех расширений |
| `apply_unified_updates` | Обновить систему + расширения одновременно (автоматическая резервная копия конфигураций) |
