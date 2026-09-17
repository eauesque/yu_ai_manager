# Руководство по отладке

Исчерпывающее руководство по отладке YU AI Manager.
Справочник для разработчиков и AI-агентов по эффективному исследованию и исправлению ошибок.

---

## Содержание

1. [Запуск сервера](#запуск-сервера)
2. [Логи отладки](#логи-отладки)
3. [Запуск тестов](#запуск-тестов)
4. [Отладка DB](#отладка-db)
5. [Обход аутентификации и тестирование](#обход-аутентификации-и-тестирование)
6. [Отладка MCP](#отладка-mcp)
7. [Отладка фронтенда](#отладка-фронтенда)
8. [Список переменных окружения](#список-переменных-окружения)
9. [Распространённые ошибки и способы их устранения](#распространённые-ошибки-и-способы-их-устранения)
10. [Отладка производительности](#отладка-производительности)

---

## Запуск сервера

### Для верификации (рекомендуется)

Запуск без PIN, с локальным байндингом. Базовая форма для тестирования и отладки.

```bash
source venv/Scripts/activate  # Windows Git Bash
python web_ui.py --db ./tags.db --config config_test.json --port 5100
```

Если `config_test.json` не существует, создайте его:

```json
{
  "scan_roots": [],
  "server": {
    "host": "127.0.0.1",
    "port": 5100,
    "lan": false
  },
  "extract_a1111": true,
  "extract_comfyui": true,
  "lowercase_tags": true,
  "compute_hash": false,
  "enable_fts": true,
  "extensions": {}
}
```

### Производственный аналог (публичный LAN)

```bash
python web_ui.py --db ./tags.db --host 0.0.0.0 --port 5000 --pin 1234
```

> **Примечание**: При байндинге на `0.0.0.0` PIN обязателен. С v4.8.1 при публикации в LAN флаг `--debug` игнорируется (защита от утечки стека).

### Правила выбора порта

5100 → 5200 → 5300 → далее с шагом 100. Проверка перед запуском:

```bash
# Windows
netstat -ano | grep :5100

# Linux/macOS
ss -tlnp | grep :5100
```

---

## Логи отладки

### Включение

```bash
# Включить через CLI
python web_ui.py --db ./tags.db --debug-log on

# Включить через переменную окружения
export TAGDB_DEBUG=1
python web_ui.py --db ./tags.db
```

### Формат логов

Структурированные логи отладки (функция `dlog()` из `core/infra_core/debug_log.py`):

```
[DEBUG] 2026-03-15 12:34:56 | scan:prepare | counting_start | root=/path/to/dir, recursive=True
```

Формат: `[DEBUG] timestamp | source | event_name | key=value, ...`

### Мониторинг в реальном времени

```bash
# Tail файла
tail -f logs/debug.log

# Получение через API
curl http://127.0.0.1:5100/api/debug/logs

# SSE-стриминг
curl -N "http://127.0.0.1:5100/api/debug/logs?stream=1"
```

---

## Запуск тестов

### Модульные тесты

```bash
source venv/Scripts/activate

# Запустить все тесты
python -m pytest tests/test_basic.py -v

# Только конкретный тест
python -m pytest tests/test_basic.py::TestImports -v

# Остановиться при первом сбое
python -m pytest tests/test_basic.py -x
```

### API-интеграционные тесты

```bash
python -m pytest tests/api/ -v
```

### Playwright-тесты браузера

```bash
# 1. Запустить тестовый сервер
python web_ui.py --db ./tags.db --config config_test.json --port 5100 &

# 2. Запустить тесты
TARGET_URL=http://localhost:5100 python -m pytest tests/test_webui_browser.py -v
```

---

## Отладка DB

### Проверка версии схемы

```bash
python -c "
import sqlite3
con = sqlite3.connect('data/tags.db')
v = con.execute('SELECT MAX(version) FROM schema_version').fetchone()[0]
print(f'Schema version: {v}')
"
```

### Проверка целостности DB

```bash
python db_health.py --db ./tags.db
```

### Отладочное выполнение SQL-запросов

Доступно только при запуске с `YU_DEBUG_MODE=1`.

```bash
# Через API
curl -X POST http://127.0.0.1:5100/api/debug/query \
  -H "Content-Type: application/json" \
  -H "X-Requested-With: XMLHttpRequest" \
  -d '{"sql":"SELECT COUNT(*) as cnt FROM files WHERE is_deleted=0"}'
```

> **Примечание**: С v4.8.1 разрешены только SELECT-запросы. ATTACH, PRAGMA, INSERT и т.д. отклоняются.

### Полезные диагностические запросы

```sql
-- Количество файлов (по источнику)
SELECT meta_source, COUNT(*) as cnt FROM files WHERE is_deleted=0 GROUP BY meta_source;

-- Рейтинг использования моделей
SELECT model_name, COUNT(*) as cnt FROM templates GROUP BY model_name ORDER BY cnt DESC LIMIT 20;

-- Осиротевшие теги
SELECT t.id, t.name FROM tags t LEFT JOIN file_tags ft ON t.id=ft.tag_id WHERE ft.tag_id IS NULL;

-- Обнаружение дублирующихся путей
SELECT path, COUNT(*) as cnt FROM files GROUP BY path HAVING cnt > 1;
```

### Разделение соединений с DB

| Функция | Назначение | Когда использовать |
|---------|-----------|-------------------|
| `get_readonly_db()` | Только для чтения | GET API, поиск, thumbnails, статистика |
| `get_db()` | Чтение/запись (с Row factory) | POST/PUT/DELETE API |
| `get_raw_db()` | Чтение/запись (без Row factory) | Пакетная обработка, сканирование, миграции |

> **Важно**: Использование `get_db()` в read-only API во время сканирования вызывает конфликт блокировки записи и блокирует вьювер на несколько секунд.

---

## Обход аутентификации и тестирование

### Пропустить PIN-аутентификацию

Запуск с `config_test.json` (без PIN) пропускает всю аутентификацию.

### Тест API Key

```bash
# Bearer-токен (заголовок CSRF не нужен)
curl -H "Authorization: Bearer sk_xxxxxxxxxxxxxx" \
  http://127.0.0.1:5000/api/stats/all
```

### Области видимости API Key

С v4.8.1 ключи без области видимости допускают **только чтение**. Для операций записи нужен ключ с явной областью.

| Область | Разрешённые операции |
|---------|---------------------|
| `read` | Поиск, детали файла, thumbnails, статистика |
| `rate` | Установка/получение/массовые рейтинги |
| `tag.write` | Добавление/удаление тегов |
| `collection.write` | CRUD коллекций, избранное |
| `annotate` | Чтение/запись аннотаций |
| `scan` | Старт/остановка/возобновление сканирования |
| `admin` | Управление API Key, изменение настроек, резервное копирование/восстановление |

---

## Отладка MCP

### Запуск MCP-сервера

```bash
source venv/Scripts/activate
python -m mcp_server
```

### Включение инструментов отладки

```bash
export YU_DEBUG_MODE=1
export YU_BASE_URL=http://127.0.0.1:5100
export YU_API_KEY=sk_...
python -m mcp_server
```

### Настройка Claude Desktop

`claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "yu-ai-manager": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "<project root>",
      "env": {
        "YU_API_KEY": "sk_...",
        "YU_BASE_URL": "http://127.0.0.1:5000",
        "YU_DEBUG_MODE": "1"
      }
    }
  }
}
```

---

## Отладка фронтенда

### Сборка TypeScript

```bash
pnpm run build        # Бандл через esbuild
pnpm run typecheck    # tsc --noEmit (только проверка типов)
```

### SSE общий движок

`window.EventSource` перезаписан Proxy — напрямую `new EventSource()` вызовет ошибку.

```javascript
// Правильно
window.sseSubscribe('scan.progress', (d) => console.log(d.data));
```

### Отладка i18n

```javascript
// Переключить язык
window.setLang('en');

// Проверить ключ перевода
console.log(window.tr('search.count.normal', { count: 5 }));
```

---

## Список переменных окружения

### Отладка и логи

| Переменная | Значения | По умолч. | Описание |
|-----------|---------|----------|----------|
| `TAGDB_DEBUG` | `1`/`0` | `0` | Включить/отключить структурированные логи отладки |
| `TAGDB_DEBUG_LOG` | путь | `logs/debug.log` | Путь к файлу логов |

### Сервер

| Переменная | Значения | Описание |
|-----------|---------|----------|
| `TAGDB_DB` | путь | Путь к файлу DB |
| `TAGDB_CONFIG` | путь | Путь к config.json |

### MCP

| Переменная | Значения | Описание |
|-----------|---------|----------|
| `YU_DEBUG_MODE` | `1` | Зарегистрировать 9 дополнительных инструментов отладки |
| `YU_BASE_URL` | URL | BASE URL для MCP-клиента |
| `YU_API_KEY` | `sk_...` | API Key для MCP-клиента |

---

## Распространённые ошибки и способы их устранения

### Запуск сервера

| Ошибка | Причина | Решение |
|--------|---------|---------|
| `Address already in use` | Порт занят | Указать другой порт `--port 5200` |
| `database is locked` | Конфликт блокировки DB | Убедиться, что DB не на сетевом пути |
| `--pin is required` | LAN-байндинг без PIN | Установить `--pin <число>` |
| `ModuleNotFoundError` | venv не активирован или пакеты отсутствуют | `source venv/Scripts/activate && uv pip install -r requirements.txt` |

### Windows-специфичные

| Ошибка | Причина | Решение |
|--------|---------|---------|
| `UnicodeEncodeError` (при выводе) | Em dash и т.д. недоступны в cp932 | Использовать только ASCII-безопасные символы |
| `pkill` не работает | Ограничение Git Bash | `tasklist \| grep python` → `taskkill //F //PID <pid>` |
| Сбой `os.replace()` | Файл открыт | Завершить процесс и повторить |

---

## Отладка производительности

### Конкуренция при сканировании

**Симптом**: Отображение изображений останавливается на 5-10 секунд во время сканирования

**Причина**: Read API использовал `get_db()` (подключение с записью) вместо `get_readonly_db()`

**Решение**: Всегда использовать `get_readonly_db()` в read-only API

### Проверка ограничений скорости

| Уровень | Область | Лимит |
|---------|---------|-------|
| **HEAVY** | Семантический поиск, хэш, AI-анализ, сканирование | ~20 req/min (burst 5) |
| **DESTRUCTIVE** | purge, hard-delete, сброс кэша, запись конфигурации | ~12 req/min (burst 3) |
| **WRITE** | Остальные POST/PUT/DELETE | ~120 req/min (burst 30) |
| GET | Чтение | Без ограничений |

При HTTP 429 смотрите заголовок `Retry-After`.
