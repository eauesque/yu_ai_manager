# Tag Database — Чеклист отладки

**Список отладки в порядке приоритета**
**Статус**: устаревший (записи эпохи v2.5.x, все пункты уже закрыты)
**Последнее обновление**: 2026-02-13

---

## P0 (Critical): немедленное исправление (влияет на удобство использования)

### ✅ 1. Исправление смещения разметки UI

**Проблема:**
```
Поля поиска не помещаются в одну строку,
и кнопки сдвинуты.
```

**Как проверить:**
1. Запустите WebUI
2. Измените размер окна браузера до 1366x768
3. Проверьте расположение полей поиска

**Место правки:** `templates/index.html`
```html
<!-- Before -->
<div class="search-row">
  <div class="form-group">...</div>
  <div class="form-group">...</div>
  <div class="form-group">...</div>
  <div class="form-group">...</div>
  <div class="form-group">...</div>
  <div class="form-group">...</div>
</div>

<!-- After -->
<div class="search-row">
  <!-- Добавлено flex-wrap: wrap -->
  <div class="form-group" style="flex: 1 1 200px;">...</div>
  ...
</div>
```

**Проверка:**
- [ ] Корректное отображение при 1920x1080
- [ ] Корректное отображение при 1366x768
- [ ] Корректное отображение при 768x1024 (планшет)

---

### ✅ 2. Удаление дубликатов в автодополнении тегов

**Проблема:**
```
В кандидатах автодополнения появляются дубликаты.

Пример:
  sample_creator_a,sample_creator_b,sample_creator_c
  sample_creator_a, sample_creator_b, sample_creator_c
  ↑ Различаются только наличием пробелов
```

**Как проверить:**
1. В поле ввода тега наберите "sample_creator"
2. Посмотрите на автодополнение
3. Проверьте наличие дубликатов

**Место правки:** `static/js/main/main.js`
```javascript
// Внутри initTagAutocomplete()
async function fetchSuggestions(q) {
  const response = await fetch(`/api/suggest?q=${encodeURIComponent(q)}`);
  const data = await response.json();

  // Нормализация и удаление дубликатов
  const normalized = new Map();

  for (const item of data) {
    const clean = item.tag
      .replace(/,(?!\s)/g, ', ')  // Пробел после запятой
      .replace(/\s+/g, ' ')        // Несколько пробелов → один
      .trim();

    if (!normalized.has(clean)) {
      normalized.set(clean, item.count);
    } else {
      // Суммирование счётчика
      normalized.set(clean, normalized.get(clean) + item.count);
    }
  }

  return Array.from(normalized.entries()).map(([tag, count]) => ({
    tag,
    count
  }));
}
```

**Проверка:**
- [ ] Дубликатов больше нет
- [ ] Счётчики суммируются
- [ ] Нет проблем с производительностью

---

## P1 (High): улучшение (влияет на функциональность)

### ✅ 3. Тест нормализации скобок при поиске

**Проблема:**
```
Проверить, что \(tag\) и (tag) эквивалентны
```

**Как проверить:**
1. Подготовьте изображение с тегом `\(emphasis\)`
2. Выполните поиск по `(emphasis)`
3. Проверьте попадание в результат

**Пункты проверки:**
- [ ] Поиск по `(tag)` → находит и `\(tag\)`
- [ ] Поиск по `\(tag\)` → находит и `(tag)`
- [ ] В режиме регулярных выражений преобразование не выполняется

**Связанный код:** `web_ui.py` — `normalize_tag_for_search()`

---

### ✅ 4. Тест чтения файлов внутри ZIP

**Проблема:**
```
Корректно ли отображаются изображения внутри ZIP,
корректно ли извлекаются метаданные.
```

**Тест-кейсы:**

#### Test 1: Базовое поведение
```bash
# 1. Создать тестовый ZIP
zip test.zip image1.png image2.png

# 2. Сканировать
python tagdb_tool.py scan --db test.db --root . --scan-zips

# 3. Проверить
python tagdb_tool.py search --db test.db --q "*"
```

**Проверка:**
- [ ] Файлы внутри ZIP регистрируются в формате `test.zip!image1.png`
- [ ] Извлекаются метаданные
- [ ] Отображаются миниатюры

#### Test 2: Распаковка
```
1. В WebUI открыть файл внутри ZIP
2. Нажать кнопку "Распаковать и редактировать"
3. Убедиться, что открывается проводник
4. Проверить наличие распакованного файла
```

**Проверка:**
- [ ] Кнопка распаковки отображается
- [ ] По клику открывается проводник
- [ ] Файл распаковывается в каталог extracted/
- [ ] Распакованный файл регистрируется в БД

#### Test 3: Большой ZIP
```bash
# 1) Создать ZIP размером 1,1 ГБ (Zip64)
mkdir -p /tmp/tagdb_largezip_test/input
python - <<'PY'
from pathlib import Path
import base64
Path('/tmp/tagdb_largezip_test/input/sample.png').write_bytes(
    base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+X2foAAAAASUVORK5CYII=')
)
PY
truncate -s 1100M /tmp/tagdb_largezip_test/input/payload.bin
python - <<'PY'
import zipfile
from pathlib import Path
root = Path('/tmp/tagdb_largezip_test')
with zipfile.ZipFile(root / 'large_1_1gb.zip', 'w', compression=zipfile.ZIP_STORED, allowZip64=True) as z:
    z.write(root / 'input' / 'sample.png', arcname='images/sample.png')
    z.write(root / 'input' / 'payload.bin', arcname='payload/payload.bin')
print((root / 'large_1_1gb.zip').stat().st_size)
PY

# 2) Сканирование содержимого ZIP
/usr/bin/time -f 'elapsed=%E maxrss_kb=%M' \
  python tagdb_tool.py scan --db /tmp/tagdb_largezip_test/largezip.db \
  --root /tmp/tagdb_largezip_test --recursive --scan-zips
```

**Проверка:**
- [x] Потребление памяти не растёт аномально
- [x] Время сканирования в допустимых пределах (до 5 минут)
- [x] Отсутствуют ошибки

**Фактические измерения (2026-02-17):**
- Размер ZIP: `1,153,433,914 bytes` (около 1,1 ГБ)
- Время выполнения: `elapsed=0:00.14`
- Пиковый RSS: `maxrss_kb=23864`
- Запись в БД: `zip_members=1` (`large_1_1gb.zip!images/sample.png`)

---

### ✅ 5. Тест поиска по чекпоинтам

**Проблема:**
```
Корректно ли извлекаются и ищутся имена моделей.
```

**Тест-кейсы:**

#### Test 1: Извлечение имени модели
```python
# Проверить извлечение имени модели для каждого формата

# NovelAI
metadata = {"model": "nai-diffusion-3"}
→ model_name: "nai-diffusion-3"

# SD
metadata = {"Model": "animagine-xl-3.1", "Model hash": "abc123"}
→ model_name: "animagine-xl-3.1", model_hash: "abc123"

# ComfyUI
metadata = {"checkpoint": "ponyDiffusionV6XL.safetensors"}
→ model_name: "ponyDiffusionV6XL"
```

**Проверка:**
- [ ] Извлекается формат NovelAI
- [ ] Извлекается формат SD
- [ ] Извлекается формат ComfyUI

#### Test 2: Функция поиска
```
1. В WebUI кликнуть по полю ввода чекпоинта
2. Проверить появление автодополнения
3. Искать "animagine"
4. Убедиться, что отображаются только изображения этой модели
```

**Проверка:**
- [ ] Автодополнение работает
- [ ] Работает поиск по частичному совпадению
- [ ] Сортировка по частоте использования

---

## P2 (Medium): отложенные задачи (улучшение производительности)

### ✅ 6. Реализация кэша миниатюр

**Проблема:**
```
Миниатюры файлов внутри ZIP создаются каждый раз
→ медленно
```

**Предложение реализации:**
```python
# web_ui.py
import hashlib

CACHE_DIR = Path("cache/thumbnails")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

@app.route("/api/thumbnail/<int:file_id>")
def api_thumbnail(file_id):
    # Формирование пути к кэшу
    cache_key = hashlib.md5(f"{file_id}".encode()).hexdigest()
    cache_path = CACHE_DIR / f"{cache_key}.jpg"

    # Если кэш есть — вернуть его
    if cache_path.exists():
        return send_file(cache_path, mimetype='image/jpeg')

    # Если нет — сгенерировать
    thumbnail = generate_thumbnail(...)

    # Сохранить в кэш
    thumbnail.save(cache_path, 'JPEG', quality=85)

    return send_file(cache_path, mimetype='image/jpeg')
```

**Проверка:**
- [ ] Повторный доступ ускоряется
- [ ] Потребление диска в допустимых пределах
- [ ] Функция очистки кэша

---

### ✅ 7. Замер производительности на большом объёме данных

**Тест-кейсы:**

#### Test 1: 100 000 файлов
```bash
# Замер времени сканирования
time python tagdb_tool.py scan --db large.db --root /path/to/100k --recursive

# Замер времени поиска
time python tagdb_tool.py search --db large.db --q "1girl"
```

**Цели:**
- [ ] Сканирование: не менее 50 000 файлов/час
- [ ] Поиск: в пределах 1 секунды (на 100 000 записей)

#### Test 2: Отзывчивость WebUI
```
1. Запустить WebUI с БД на 100 000 записей
2. Выполнить поиск
3. Пролистать результаты
```

**Проверка:**
- [ ] Результаты поиска отображаются в течение 3 секунд
- [ ] Прокрутка плавная
- [ ] Браузер не зависает

---

## Чеклист выполнения тестов

### Подготовка окружения
- [ ] Проверена установка Python 3.8+
- [ ] Установлены зависимые пакеты
- [ ] Подготовлены тестовые данные (изображения разных форматов)

### Функциональные тесты
- [ ] Чтение ZIP
- [ ] Сканирование нескольких каталогов
- [ ] Нормализация тегов
- [ ] Поиск по чекпоинтам
- [ ] Фильтр по модели

### UI/UX тесты
- [ ] Разметка (несколько разрешений)
- [ ] Тёмная тема
- [ ] Горячие клавиши
- [ ] Автодополнение

### Тесты производительности
- [ ] 10 000 записей
- [ ] 50 000 записей
- [ ] 100 000 записей
- [ ] Большой ZIP (500 МБ и более)

### Совместимость с браузерами
- [ ] Chrome/Edge
- [ ] Firefox
- [ ] Safari

### Совместимость с ОС
- [ ] Windows 10/11
- [ ] macOS
- [ ] Linux (Ubuntu)

---

## Инструменты отладки

### Включение логирования
```bash
# Добавить в начало tagdb_tool.py
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Замер производительности
```python
import time

start = time.time()
# ... обработка ...
print(f"Time: {time.time() - start:.2f}s")
```

### Контроль использования памяти
```python
import tracemalloc

tracemalloc.start()
# ... обработка ...
current, peak = tracemalloc.get_traced_memory()
print(f"Memory: {peak / 1024 / 1024:.2f} MB")
tracemalloc.stop()
```

---

**Дата создания:** 2026-02-13
**Приоритет:** выполнять в порядке P0 → P1 → P2
**Примечание:** данный чеклист был создан в эпоху v2.5.x, все перечисленные пункты уже закрыты
