# API просмотра исходного кода

API только для чтения для просмотра исходного кода проекта.
Разработан таким образом, чтобы инструменты MCP и внешние AI агенты могли безопасно просматривать и искать в кодовой базе.

## Модель безопасности

Три слоя защиты обеспечивают безопасность:

### 1. Нормализация пути (предотвращение обхода)

- Все пути нормализуются с помощью `os.path.realpath()` и проверяются против корня проекта через совпадение префиксов.
- Атаки обхода, такие как `../../etc/passwd` или `../../../Windows/System32`, заблокированы.
- Внедрение нулевого байта (`\x00`) также обнаруживается и отклоняется.

### 2. Whitelist расширений

Допустимые расширения файлов для чтения:

| Категория | Расширения |
|----------|-----------|
| Python | `.py` |
| TypeScript / JavaScript | `.ts`, `.js`, `.mjs`, `.tsx`, `.jsx` |
| Web | `.html`, `.css`, `.scss` |
| Конфигурация | `.json`, `.yaml`, `.yml`, `.toml`, `.cfg`, `.ini` |
| Документация | `.md`, `.txt`, `.rst` |
| Скрипты | `.sh`, `.bat`, `.cmd`, `.ps1` |
| Другое | `.sql`, `.gitignore`, `.gitattributes`, `.editorconfig` |

Следующие файлы без расширения специально разрешены: `Dockerfile`, `Makefile`, `Procfile`, `VERSION`, `LICENSE`, `CHANGELOG`, `TODO`

### 3. Blacklist конфиденциальных файлов

Файлы, соответствующие следующим шаблонам, отклоняются:

| Шаблон | Причина |
|---------|--------|
| `config.json`, `config_*.json` | Данные аутентификации, такие как PIN и API Key |
| `*.env`, `.env.*` | Переменные среды (секреты) |
| `secret.salt`, `*.key`, `*.pem`, `*.cert` | Ключи шифрования и сертификаты |
| `credentials*`, `*token*`, `*secret*` | Данные аутентификации |
| `*.db`, `*.sqlite*` | Файлы базы данных |
| `pnpm-lock.yaml`, `package-lock.json` и т.д. | Файлы блокировки (большие) |
| Изображения, видео, шрифты и файлы моделей | Двоичные файлы |

### Заблокированные каталоги

`.git`, `__pycache__`, `node_modules`, `venv`, `dist`, `data`, `backups`, `screenshots`, `reports`, `src-tauri`

### Лимиты чтения

| Элемент | Лимит |
|------|-------|
| Размер файла | 1 МБ |
| Строк на чтение | 2,000 |
| Глубина обхода дерева | 6 |
| Результаты поиска | 50 |

---

## Конечные точки

### GET /api/source/tree

Получение дерева каталогов.

#### Параметры

| Параметр | Тип | По умолчанию | Описание |
|-----------|------|---------|-------------|
| `path` | string | `""` (корень) | Относительный путь |
| `depth` | int | `3` | Глубина обхода (1-6) |

#### Ответ

```json
{
  "ok": true,
  "root": ".",
  "depth": 3,
  "entries": [
    {
      "name": "core",
      "type": "dir",
      "path": "core",
      "children": [
        {
          "name": "source_core",
          "type": "dir",
          "path": "core/source_core",
          "children": [
            {
              "name": "source_browser.py",
              "type": "file",
              "path": "core/source_core/source_browser.py",
              "size": 8234
            }
          ]
        }
      ]
    },
    {
      "name": "web_ui.py",
      "type": "file",
      "path": "web_ui.py",
      "size": 3456
    }
  ]
}
```

- Каталоги появляются в первую очередь, затем файлы (отсортированы по имени).
- `size` в байтах (только файлы).
- `children` опускается, когда обход достигает указанной `depth`.

---

### GET /api/source/read

Чтение содержимого файла с номерами строк.

#### Параметры

| Параметр | Тип | По умолчанию | Описание |
|-----------|------|---------|-------------|
| `path` | string | — (обязательно) | Относительный путь к файлу |
| `offset` | int | `0` | Начальная строка (основание 0) |
| `limit` | int | `2000` | Максимальное количество строк |

#### Ответ

```json
{
  "ok": true,
  "path": "core/source_core/source_browser.py",
  "total_lines": 250,
  "offset": 0,
  "limit": 2000,
  "content": "    1\t\"\"\"Source code browser...\n    2\t\n    3\timport os\n..."
}
```

- `content` использует формат `{line_number}\t{line_content}`.
- Используйте `offset` + `limit` для разбиения на страницы длинных файлов.

#### Примеры ошибок

```json
{
  "ok": false,
  "error": "This file is not eligible for reading"
}
```

```json
{
  "ok": false,
  "error": "Access outside the project root is prohibited"
}
```

---

### GET /api/source/search

Поиск в исходном коде по тексту.

#### Параметры

| Параметр | Тип | По умолчанию | Описание |
|-----------|------|---------|-------------|
| `q` | string | — (обязательно) | Поисковый текст (минимум 2 символа) |
| `glob` | string | `""` (все файлы) | Фильтр имени файла (например `*.py`) |
| `limit` | int | `30` | Максимальное количество результатов (1-50) |

#### Ответ

```json
{
  "ok": true,
  "query": "def source_tree",
  "glob": "*.py",
  "total": 2,
  "results": [
    {
      "file": "core/source_core/source_browser.py",
      "line": 120,
      "text": "def source_tree("
    },
    {
      "file": "routes/source_api.py",
      "line": 15,
      "text": "    result = source_tree(rel_path, depth_int)"
    }
  ]
}
```

- Поиск без учета регистра.
- `text` усечено до максимум 200 символов.

---

## MCP инструменты

| Инструмент | Описание | Ключевые параметры |
|------|-------------|----------------|
| `source_tree` | Отображение дерева каталогов | `path`: str = '', `depth`: int = 3 |
| `source_read` | Чтение содержимого файла | `path`: str (обязательно), `offset`: int = 0, `limit`: int = 2000 |
| `source_search` | Поиск исходного кода по тексту | `query`: str (обязательно), `glob`: str = '', `limit`: int = 30 |

### Примеры использования с MCP

```
# Просмотр структуры проекта
source_tree(path="", depth=2)

# Чтение конкретного файла
source_read(path="core/source_core/source_browser.py")

# Поиск в кодовой базе
source_search(query="def register_blueprints", glob="*.py")
```

### Область и ограничение скорости

- **Scope Fence**: Доступно в области `read_only` (разрешено во всех предустановках)
- **Budget Tracker**: категория `read` (без ограничения скорости)
- **HITL Gate**: Уровень 0 (утверждение не требуется)

---

## Файлы реализации

| Файл | Роль |
|------|------|
| `core/source_core/source_browser.py` | Слой безопасности + бизнес-логика |
| `routes/source_api.py` | Flask API конечные точки (Blueprint) |
| `mcp_server/source_tools.py` | Регистрация MCP инструментов |
