# Extensions API

API для управления расширениями, установки, безопасности и авторства.

---

## GET /api/extensions

Список всех установленных расширений.

### Параметры

Нет

### Ответ

```json
{
  "extensions": [
    {
      "name": "builtin-sd-webui-bridge",
      "version": "1.0.0",
      "description": "SD WebUI Bridge",
      "enabled": true,
      "trust_level": "trusted",
      "category": "integration",
      "directory": "extensions/builtin_sd_webui_bridge"
    }
  ],
  "total": 5,
  "category_order": ["core", "integration", "tools", "ui", "other"]
}
```

| Поле | Тип | Описание |
|-------|------|-------------|
| `extensions` | array | Массив информации о расширениях |
| `total` | int | Общее количество расширений |
| `category_order` | string[] | Порядок отображения категорий |

## GET /api/extensions/\<name\>

Получить подробную информацию о конкретном расширении.

### Параметры

| Параметр | Тип | Описание |
|-----------|------|-------------|
| `name` | string | Имя расширения (параметр пути) |

### Ответ

```json
{
  "name": "builtin-sd-webui-bridge",
  "version": "1.0.0",
  "description": "SD WebUI Bridge",
  "enabled": true,
  "trust_level": "trusted",
  "category": "integration",
  "directory": "extensions/builtin_sd_webui_bridge"
}
```

### Ошибки

- `404` — Расширение не найдено

## POST /api/extensions/\<name\>/toggle

Переключить состояние включённости/отключённости расширения.

### Rate Limit

WRITE

### Параметры

| Параметр | Тип | Описание |
|-----------|------|-------------|
| `name` | string | Имя расширения (параметр пути) |

### Запрос

```json
{
  "enabled": true
}
```

| Параметр | Тип | Обязательный | Описание |
|-----------|------|----------|-------------|
| `enabled` | boolean | Нет | `true` для включения, `false` для отключения. Опустить для переключения (инвертировать текущее состояние) |

### Ответ

```json
{
  "name": "builtin-sd-webui-bridge",
  "enabled": true,
  "message": "Extension 'builtin-sd-webui-bridge' enabled"
}
```

### Ошибки

- `404` — Расширение не найдено

## GET /api/extensions/\<name\>/config

Получить схему конфигурации и текущие значения для расширения.

### Параметры

| Параметр | Тип | Описание |
|-----------|------|-------------|
| `name` | string | Имя расширения (параметр пути) |

### Ответ

```json
{
  "name": "builtin-sd-webui-bridge",
  "config_schema": {
    "fields": [
      {
        "key": "api_url",
        "label": "API URL",
        "type": "text",
        "default": "http://127.0.0.1:7860",
        "value": "http://127.0.0.1:7860"
      }
    ]
  }
}
```

### Ошибки

- `404` — Расширение не найдено

## POST /api/extensions/\<name\>/config

Сохранить значения конфигурации расширения. Включает валидацию.

### Rate Limit

WRITE

### Параметры

| Параметр | Тип | Описание |
|-----------|------|-------------|
| `name` | string | Имя расширения (параметр пути) |

### Запрос

```json
{
  "values": {
    "api_url": "http://127.0.0.1:7860",
    "timeout": 30
  }
}
```

| Параметр | Тип | Обязательный | Описание |
|-----------|------|----------|-------------|
| `values` | object | Да | Карта ключей полей к значениям |

### Ответ

```json
{
  "ok": true,
  "saved": {
    "api_url": "http://127.0.0.1:7860",
    "timeout": 30
  }
}
```

### Ошибки

- `404` — Расширение не найдено
- `400` — Ошибка валидации

---

## Установка / Обновление / Удаление расширения

Следующие конечные точки ограничены **только доступом с localhost**. Удалённые запросы возвращают `403`.

## POST /api/extensions/install

Установить расширение из Git-репозитория.

### Rate Limit

WRITE

### Ограничение доступа

Только localhost

### Запрос

```json
{
  "url": "https://github.com/user/my-extension.git"
}
```

| Параметр | Тип | Обязательный | Описание |
|-----------|------|----------|-------------|
| `url` | string | Да | URL Git-репозитория. `git` и `repo` принимаются как псевдонимы |

### Ответ

```json
{
  "ok": true,
  "name": "my-extension",
  "message": "Extension installed successfully"
}
```

### Ошибки

- `400` — URL не предоставлен или неверный формат URL
- `403` — Доступ с non-localhost

## POST /api/extensions/\<name\>/update

Обновить конкретное расширение до последней версии (git pull).

### Rate Limit

WRITE

### Ограничение доступа

Только localhost

### Параметры

| Параметр | Тип | Описание |
|-----------|------|-------------|
| `name` | string | Имя расширения (параметр пути) |

### Ответ

```json
{
  "ok": true,
  "name": "my-extension",
  "message": "Extension updated successfully"
}
```

### Ошибки

- `403` — Доступ с non-localhost
- `404` — Расширение не найдено

## POST /api/extensions/update-all

Пакетное обновление всех расширений, установленных из Git.

### Rate Limit

WRITE

### Ограничение доступа

Только localhost

### Ответ

```json
{
  "results": [
    {"name": "my-extension", "ok": true, "message": "Updated"},
    {"name": "other-ext", "ok": false, "error": "Git pull failed"}
  ]
}
```

### Ошибки

- `403` — Доступ с non-localhost

## DELETE /api/extensions/\<name\>/uninstall

Удалить расширение (удалить папку).

### Rate Limit

DESTRUCTIVE

### Ограничение доступа

Только localhost

### Параметры

| Параметр | Тип | Описание |
|-----------|------|-------------|
| `name` | string | Имя расширения (параметр пути) |

### Ответ

```json
{
  "ok": true,
  "name": "my-extension",
  "message": "Extension uninstalled"
}
```

### Ошибки

- `403` — Доступ с non-localhost
- `404` — Расширение не найдено

---

## Безопасность и разрешения

## GET /api/extensions/\<name\>/permissions

Получить информацию о разрешениях и статус одобрения для расширения.

### Параметры

| Параметр | Тип | Описание |
|-----------|------|-------------|
| `name` | string | Имя расширения (параметр пути) |

### Ответ

```json
{
  "name": "my-extension",
  "trust_level": "L2",
  "approved": true,
  "permissions": {
    "required": [
      {"name": "network", "reason": "API calls to external service"}
    ],
    "optional": [
      {"name": "filesystem_read", "reason": "Read user images"}
    ]
  },
  "granted": {
    "granted": ["network", "filesystem_read"],
    "denied": [],
    "granted_at": "2025-01-15T10:30:00",
    "auto_approved": false
  }
}
```

| Поле | Тип | Описание |
|-------|------|-------------|
| `trust_level` | string | Уровень доверия (`trusted`, `L1`, `L2`) |
| `approved` | boolean | Одобрено ли пользователем расширение |
| `permissions.required` | array | Список обязательных разрешений |
| `permissions.optional` | array | Список опциональных разрешений |
| `granted` | object/null | Детали предоставленных разрешений. `null` если не одобрено |

### Ошибки

- `404` — Расширение не найдено

## POST /api/extensions/\<name\>/permissions

Одобрить или отозвать разрешения расширения.

### Rate Limit

WRITE

### Параметры

| Параметр | Тип | Описание |
|-----------|------|-------------|
| `name` | string | Имя расширения (параметр пути) |

### Запрос (Одобрить)

```json
{
  "action": "approve",
  "granted": ["network", "filesystem_read"],
  "denied": ["filesystem_write"]
}
```

### Запрос (Отозвать)

```json
{
  "action": "revoke"
}
```

| Параметр | Тип | Обязательный | Описание |
|-----------|------|----------|-------------|
| `action` | string | Нет | `"approve"` (по умолчанию) или `"revoke"` |
| `granted` | string[] | Нет | Список имён разрешений для предоставления (для одобрения) |
| `denied` | string[] | Нет | Список имён разрешений для отрицания (для одобрения) |

### Ответ (Одобрить)

```json
{
  "name": "my-extension",
  "action": "approved",
  "granted": ["network", "filesystem_read"],
  "denied": ["filesystem_write"]
}
```

### Ответ (Отозвать)

```json
{
  "name": "my-extension",
  "action": "revoked"
}
```

### Ошибки

- `400` — `granted` не является списком
- `404` — Расширение не найдено

## GET /api/extensions/\<name\>/scan-results

Получить результаты статического анализа кода расширения. Возвращает результаты ManifestAuthority и CodeVerifier.

### Параметры

| Параметр | Тип | Описание |
|-----------|------|-------------|
| `name` | string | Имя расширения (параметр пути) |

### Ответ

```json
{
  "name": "my-extension",
  "trust_level": "L2",
  "manifest_review": {
    "approved": true,
    "issues": []
  },
  "code_scan": {
    "approved": true,
    "findings": [
      {
        "file": "my_ext.py",
        "line": 15,
        "severity": "warning",
        "message": "Uses subprocess module"
      }
    ]
  }
}
```

| Поле | Тип | Описание |
|-------|------|-------------|
| `manifest_review.approved` | boolean | Прошла ли манифест проверку |
| `manifest_review.issues` | array | Список проблем (`severity`, `message`) |
| `code_scan` | object/null | Результаты сканирования кода. `null` если нет папки |
| `code_scan.findings` | array | Список находок |

### Ошибки

- `404` — Расширение не найдено

## POST /api/extensions/\<name\>/rescan

Повторное сканирование кода расширения. Возвращает тот же формат результата, что и `scan-results`.

### Rate Limit

WRITE

### Параметры

| Параметр | Тип | Описание |
|-----------|------|-------------|
| `name` | string | Имя расширения (параметр пути) |

### Ответ

Тот же формат, что и `GET /api/extensions/<name>/scan-results`.

## GET /api/extensions/\<name\>/tokens

Получить статус выдачи маркеров возможностей для расширения.

### Параметры

| Параметр | Тип | Описание |
|-----------|------|-------------|
| `name` | string | Имя расширения (параметр пути) |

### Ответ

```json
{
  "name": "my-extension",
  "token_count": 2,
  "tokens": [
    {
      "capability": "network",
      "issued_at": "2025-01-15T10:30:00",
      "expires_at": "2025-01-16T10:30:00"
    }
  ]
}
```

### Ошибки

- `404` — Расширение не найдено

## GET /api/extensions/\<name\>/integrity

Получить статус целостности файлов расширения. Также включает информацию об отслеживании отзыва и защите импорта.

### Параметры

| Параметр | Тип | Описание |
|-----------|------|-------------|
| `name` | string | Имя расширения (параметр пути) |

### Ответ

```json
{
  "name": "my-extension",
  "integrity": {
    "verified": true,
    "last_check": "2025-01-15T10:30:00",
    "files_changed": 0
  },
  "revocation": {
    "denial_count": 0,
    "last_access": null
  },
  "import_guard": {
    "import_denial_count": 0
  }
}
```

| Поле | Тип | Описание |
|-------|------|-------------|
| `integrity` | object | Результаты проверки целостности файлов |
| `revocation` | object | Информация об отслеживании отзыва маркеров |
| `import_guard` | object | Счётчик отрицания импорта |

### Ошибки

- `404` — Расширение не найдено

---

## Hooks и Marketplace

## GET /api/extensions/hooks

Список зарегистрированных хуков расширений и определений хуков.

### Параметры

Нет

### Ответ

```json
{
  "hooks": {
    "after_scan": [
      {"extension": "builtin-tagger", "priority": 100}
    ]
  },
  "definitions": {
    "after_scan": {"mode": "sequential"},
    "before_import": {"mode": "sequential"}
  }
}
```

| Поле | Тип | Описание |
|-------|------|-------------|
| `hooks` | object | Карта имён хуков к зарегистрированным спискам расширений |
| `definitions` | object | Доступные определения хуков. `mode` — режим выполнения |

## GET /api/extensions/marketplace

Поиск расширений на marketplace.

### Параметры

| Параметр | Тип | Обязательный | Описание |
|-----------|------|----------|-------------|
| `q` | string | Нет | Поисковый запрос (параметр query). Пустая строка возвращает все |

### Ответ

```json
{
  "extensions": [
    {
      "name": "awesome-extension",
      "description": "An awesome extension",
      "author": "developer",
      "version": "1.0.0",
      "installed": false
    }
  ],
  "total": 10
}
```

| Поле | Тип | Описание |
|-------|------|-------------|
| `extensions` | array | Информация о расширениях marketplace |
| `extensions[].installed` | boolean | Установлено ли расширение локально |
| `total` | int | Общее количество результатов поиска |

## POST /api/extensions/marketplace/refresh

Принудительно обновить кэш marketplace.

### Rate Limit

WRITE

### Ответ

```json
{
  "refreshed": true,
  "total": 25
}
```

---

## Изоляция

## GET /api/extensions/isolation

Получить статус изоляции процессов.

### Параметры

Нет

### Ответ

```json
{
  "available": true,
  "processes": {
    "my-extension": {
      "pid": 12345,
      "status": "running"
    }
  }
}
```

| Поле | Тип | Описание |
|-------|------|-------------|
| `available` | boolean | Доступна ли изоляция процессов |
| `processes` | object | Карта имён расширений к статусу процессов |

## GET /api/extensions/os-isolation

Получить статус изоляции на уровне OS (Phase D). Также включает информацию об изоляции процессов.

### Параметры

Нет

### Ответ

```json
{
  "os_isolation": {
    "platform": "linux",
    "available_backends": ["apparmor"]
  },
  "config": {
    "enabled": true,
    "apparmor": true,
    "macos_sandbox_exec": false,
    "macos_user_isolation": false,
    "windows_restricted_token": false,
    "windows_job_object": false
  },
  "processes": {}
}
```

| Поле | Тип | Описание |
|-------|------|-------------|
| `os_isolation` | object | Информация об изоляции на уровне OS |
| `config.enabled` | boolean | Включена ли изоляция на уровне OS |
| `config.apparmor` | boolean | Статус использования AppArmor (Linux) |
| `config.macos_sandbox_exec` | boolean | Статус использования macOS sandbox-exec |
| `config.macos_user_isolation` | boolean | Статус использования macOS user isolation |
| `config.windows_restricted_token` | boolean | Статус использования Windows restricted token |
| `config.windows_job_object` | boolean | Статус использования Windows Job Object |
| `processes` | object | Статус изоляции процессов |

---

## Авторство расширений

API для создания и редактирования пользовательских расширений. На основе модели концессии, только папка `extensions/custom-{name}/` доступна для записи.

Все конечные точки ограничены **только доступом с localhost**.

### Ограничения безопасности

- Имя расширения: строчные буквы, цифры и дефисы только (`[a-z0-9-]`), максимум 50 символов, префикс `builtin-` запрещён
- Типы файлов: только whitelist (`entrypoint`, `template`, `static_css`, `static_js`, `config`, `readme`)
- Бинарные файлы: полностью запрещены
- Ограничения размера файла: 10KB до 50KB в зависимости от типа

## POST /api/extensions/author/create

Создать новое пользовательское расширение с файлами-шаблонами.

### Rate Limit

WRITE

### Ограничение доступа

Только localhost

### Запрос

```json
{
  "name": "my-tool",
  "description": "A useful tool extension"
}
```

| Параметр | Тип | Обязательный | Описание |
|-----------|------|----------|-------------|
| `name` | string | Да | Имя расширения (`[a-z0-9-]`, максимум 50 символов) |
| `description` | string | Нет | Описание расширения |

### Ответ

```json
{
  "ok": true,
  "name": "custom-my-tool",
  "path": "extensions/custom-my-tool",
  "files": [
    "extension.json",
    "my_tool_ext.py"
  ]
}
```

### Ошибки

- `400` — Неверное имя или расширение уже существует
- `403` — Доступ с non-localhost

## POST /api/extensions/author/\<name\>/write

Записать файл в пользовательское расширение.

### Rate Limit

WRITE

### Ограничение доступа

Только localhost

### Параметры

| Параметр | Тип | Описание |
|-----------|------|-------------|
| `name` | string | Имя расширения (параметр пути, без префикса `custom-`) |

### Запрос

```json
{
  "file_type": "entrypoint",
  "filename": "my_tool_ext",
  "content": "\"\"\"My tool extension.\"\"\"\n\nfrom quart import Blueprint\n..."
}
```

| Параметр | Тип | Обязательный | Описание |
|-----------|------|----------|-------------|
| `file_type` | string | Да | Тип файла. Один из: `entrypoint`, `template`, `static_css`, `static_js`, `config`, `readme` |
| `filename` | string | Да | Имя файла без расширения. Буквы, цифры, дефисы и подчёркивания только |
| `content` | string | Да | Содержимое файла (только текст) |

### Ограничения по типу файла

| file_type | Расширение | Макс размер | Примечания |
|-----------|-----------|----------|-------|
| `entrypoint` | `.py` | 50KB | Точка входа расширения |
| `template` | `.html` | 50KB | Размещён в `templates/{name}/` |
| `static_css` | `.css` | 50KB | Размещён в `static/` |
| `static_js` | `.js` | 50KB | Размещён в `static/` |
| `config` | `.json` | 10KB | Имя файла должно быть `extension` |
| `readme` | `.md` | 20KB | Имя файла должно быть `README` |

### Ответ

```json
{
  "ok": true,
  "file": "my_tool_ext.py",
  "size": 256
}
```

### Ошибки

- `400` — Ошибка валидации (неверное имя, тип файла, размер превышен, обнаружен бинарный файл)
- `403` — Доступ с non-localhost

## GET /api/extensions/author/\<name\>/read

Прочитать файл из пользовательского расширения.

### Ограничение доступа

Только localhost

### Параметры

| Параметр | Тип | Описание |
|-----------|------|-------------|
| `name` | string | Имя расширения (параметр пути) |

### Query параметры

| Параметр | Тип | Обязательный | Описание |
|-----------|------|----------|-------------|
| `file_type` | string | Да | Тип файла |
| `filename` | string | Да | Имя файла без расширения |

### Ответ

```json
{
  "ok": true,
  "file": "my_tool_ext.py",
  "content": "\"\"\"My tool extension.\"\"\"\n...",
  "size": 256
}
```

### Ошибки

- `400` — Ошибка валидации
- `403` — Доступ с non-localhost

## GET /api/extensions/author/\<name\>/files

Список всех файлов в пользовательском расширении.

### Ограничение доступа

Только localhost

### Параметры

| Параметр | Тип | Описание |
|-----------|------|-------------|
| `name` | string | Имя расширения (параметр пути) |

### Ответ

```json
{
  "ok": true,
  "name": "custom-my-tool",
  "files": [
    {"path": "extension.json", "size": 320},
    {"path": "my_tool_ext.py", "size": 256},
    {"path": "templates/my_tool/index.html", "size": 1024}
  ],
  "total_size": 1600
}
```

### Ошибки

- `400` — Неверное имя расширения
- `403` — Доступ с non-localhost

## POST /api/extensions/author/\<name\>/validate

Валидировать extension.json и код пользовательского расширения. Запускает CodeVerifier без регистрации расширения.

### Rate Limit

WRITE

### Ограничение доступа

Только localhost

### Параметры

| Параметр | Тип | Описание |
|-----------|------|-------------|
| `name` | string | Имя расширения (параметр пути) |

### Ответ (Успех)

```json
{
  "ok": true,
  "name": "custom-my-tool",
  "issues": [],
  "code_findings": [],
  "manifest": {
    "name": "custom-my-tool",
    "version": "0.1.0",
    "entrypoint": "my_tool_ext.py"
  }
}
```

### Ответ (Обнаружены проблемы)

```json
{
  "ok": false,
  "name": "custom-my-tool",
  "issues": [
    "Missing required field: version",
    "CodeVerifier rejected: dangerous patterns detected"
  ],
  "code_findings": [
    {
      "severity": "critical",
      "message": "Uses eval()",
      "file": "my_tool_ext.py",
      "line": 42
    }
  ],
  "manifest": {}
}
```

| Поле | Тип | Описание |
|-------|------|-------------|
| `ok` | boolean | Прошли ли все проверки |
| `issues` | string[] | Проблемы валидации манифеста и кода |
| `code_findings` | array | Находки CodeVerifier |
| `manifest` | object | Разобранное содержимое extension.json |

### Ошибки

- `400` — Неверное имя расширения или расширение не существует
- `403` — Доступ с non-localhost
