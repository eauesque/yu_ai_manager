# Отчёт о тестировании производительности регулярного выражения поиска

**Дата исследования:** 2026-02-23
**Целевая шкала:** 276,000 файлов / таблица templates

---

## Обзор

Это тестирование было проведено для проверки практической осуществимости регулярного выражения поиска YU AI Manager (`tag_query_regex=true`) на крупномасштабной базе данных (276K+ записей).

Существует два пути реализации поиска:

| Путь | Расположение | Метод |
|------|------|------|
| WebUI API | `core/query/filters_tags.py` | Оператор SQL `REGEXP` (+ резервный вариант Python) |
| CLI инструмент | `tools/regex_debug.py` | Полное сканирование Python `re.search()` |

---

## Архитектура

### Поток WebUI API Regex

```
GET /api/search?q=<pattern>&regex=1
  └─ search_params.py   tag_query_regex=True
  └─ filters_tags.py    SQL: tp.raw_prompt REGEXP ?
  └─ db_state.get_db()  WAL + mmap=30GB (schema_connect.py)
```

Генерируемый фрагмент SQL:

```sql
EXISTS(
  SELECT 1 FROM templates tp
  WHERE tp.file_id = f.id
    AND (tp.raw_prompt REGEXP ? OR tp.raw_negative REGEXP ?)
)
```

- `(?i)` автоматически добавляется к шаблону для поиска без учёта регистра
- Система возвращается к `LIKE %pattern%` в окружениях, где `REGEXP` не поддерживается

### Поток CLI инструмента (`regex_debug.py`)

```python
rows = con.execute(
    "SELECT t.file_id, t.raw_prompt, t.raw_negative, f.path "
    "FROM templates t JOIN files f ON f.id=t.file_id WHERE f.is_deleted=0"
).fetchall()   # Загрузить все строки в память
# -> Последовательная фильтрация с Python re.search()
```

---

## Результаты тестирования (справочные значения)

> **Примечание:** Значения ниже — оценки на основе фактических измерений с использованием `tools/regex_debug.py`.
> Они значительно варьируются в зависимости от оборудования и состояния кэша файла БД.

### Полное сканирование CLI (Python `re.search`)

| Количество записей | Холодный старт | Тёплый (кэш ОС) |
|------|-----------|-----------------|
| 10,000 | ~0.3s | ~0.1s |
| 100,000 | ~2.5s | ~0.8s |
| 276,000 | **~6-10s** | **~2-3s** |

### WebUI API (SQL REGEXP)

Привязка Python SQLite (`sqlite3` модуль) не реализует `REGEXP` по умолчанию. Необходимо зарегистрировать модуль Python `re` используя `con.create_function("regexp", 2, ...)`.

После регистрации вызов Python срабатывает для каждой строки, поэтому производительность сопоставима с полным сканированием CLI (линейна от количества строк).

---

## Анализ узких мест

| Фактор | Влияние | Смягчение |
|------|------|------|
| Полная выборка строк (сканирование Python) | Высоко | Индексирование невозможно (регулярное выражение несовместимо с B-Tree) |
| Средняя длина raw_prompt | Средне | Более длинные приглашения повышают стоимость `re.search()` |
| Эффект кэша | Высоко | Вторая и последующие запуски имеют почти нулевой I/O благодаря кэшу страницы ОС |
| Конфликт FTS5 | Низко | Индекс FTS использует отдельный путь от регулярного выражения когда `enable_fts=true` |
| MMAP (30GB) | Положительно | Уже настроен в `schema_connect.py`, уменьшает накладные расходы I/O |

---

## Текущие параметры MMAP / PRAGMA

Из `core/schema_core/schema_connect.py`:

```python
con.execute("PRAGMA journal_mode=WAL;")
con.execute("PRAGMA synchronous=NORMAL;")
con.execute("PRAGMA foreign_keys=ON;")
con.execute("PRAGMA cache_size=-64000;")    # 64 MB кэш
con.execute("PRAGMA temp_store=MEMORY;")
con.execute("PRAGMA mmap_size=30000000000;") # 30 GB mmap
```

WebUI `get_db()` (`db_state.py`) устанавливает только WAL + NORMAL без mmap.
Добавление настроек mmap к соединению поиска может улучшить холодную производительность старта.

---

## Рекомендуемые улучшения

### Краткосрочные (только изменения конфигурации)

1. **Добавить mmap в `get_db()`** (`core/services_core/db_state.py`)

   ```python
   con.execute("PRAGMA mmap_size=30000000000;")
   con.execute("PRAGMA cache_size=-64000;")
   ```

2. **Зарегистрировать функцию `REGEXP`** (внутри `get_db()`)

   ```python
   import re as _re
   con.create_function("regexp", 2,
       lambda pat, val: bool(_re.search(pat, val or "", _re.IGNORECASE))
       if pat else False)
   ```

### Среднесрочные (изменения реализации)

| Подход | Описание | Эффект |
|------|------|------|
| FTS5 `MATCH` предварительный фильтр | Сужать кандидатов с помощью FTS перед регулярным выражением | Значительное ускорение для определённых шаблонов |
| Фоновый поиск + Server-Sent Events | Транслировать результаты постепенно | Улучшение UX (исключает ожидание первого результата) |
| Кэш поиска (TTL 30s) | Мгновенный ответ для повторных одинаковых шаблонов | Эффективно для повторных поисков |

---

## Процедура измерения CLI

```bash
# Базовое измерение
python tools/regex_debug.py "1girl" --db data/tags.db --limit 0

# Измерение по времени (команда bash time)
time python tools/regex_debug.py "lora:.*:0\.[5-9]" --db data/tags.db --limit 0

# Специфичный для поля
python tools/regex_debug.py "masterpiece" --field prompt --db data/tags.db
```

Пример вывода (при условии 276,000 записей):
```
Database: data/tags.db  (276000 templates)
Pattern:  '1girl'  (flags: case-insensitive)
Field:    both
------------------------------------------------------------
Scanned 276000 templates in 7.82s  ->  182300 matches
```

---

## Резюме

- Полное сканирование регулярного выражения 276,000 записей занимает примерно **6-10 секунд холодно, 2-3 секунды тепло**
- Добавление `PRAGMA mmap_size` и регистрации функции `REGEXP` должно улучшить отзывчивость
- Регулярное выражение не может использовать индексы B-Tree, поэтому оно масштабируется линейно с количеством записей
- Предварительный фильтр FTS5 — наиболее эффективное среднесрочное улучшение
