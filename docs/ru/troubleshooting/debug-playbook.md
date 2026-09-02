# 🔬 Справочник по отладке yu_ai_manager

## Быстрый старт

```bash
# Запустить всю диагностику
python debug_check.py

# Указать БД
python debug_check.py --db /path/to/tags.db

# Быстрая проверка (пропустить синтаксис/Extension)
python debug_check.py --quick
```

---

## Частые проблемы и решения

### 1. config.json повреждена (проблема обратной косой черты)

**Симптомы:** JSONDecodeError при запуске сервера
**Причина:** Ручной ввод пути Windows с `\U`, `\w` и т.д. становится неправильным экранированием
**Решение:** Автоматическое исправление при запуске сервера. Для ручного исправления:
```bash
python -c "
from core.config import safe_load_json
data = safe_load_json('config.json')
print('OK' if data else 'FAILED')
"
```

### 2. scan-all пропускает определенную папку

**Симптомы:** "全フォルダスキャン" не обрабатывает некоторые папки
**Шаги проверки:**
```bash
# Проверить содержимое scan_roots
python -c "
import json
c = json.load(open('config.json'))
for i, r in enumerate(c.get('scan_roots', [])):
    print(f'  [{i}] repr={repr(r)} len={len(r)}')
"
```
**Пункты проверки:**
- Путь слишком короткий? (`\\wsl.localhost\` только?)
- Нет ли конечной `\`?
- Возвращает ли `os.path.exists(path)` True?

### 3. QR-обмен показывает "нет содержимого"

**Симптомы:** QR-кнопка обмена → Положительное/Отрицательное пусто
**Возможные причины:**
1. Нет записей в таблице `templates` (meta_source=unknown)
2. Несоответствие ключей ответа API (исправлено в v2.7.0)

**Проверка:**
```bash
# Проверить наличие шаблона для ID файла
python -c "
import sqlite3
con = sqlite3.connect('tags.db')
file_id = 276323  # Проблемный ID
row = con.execute('SELECT * FROM templates WHERE file_id=?', (file_id,)).fetchone()
print('templates:', 'EXISTS' if row else 'MISSING')
meta = con.execute('SELECT meta_source FROM files WHERE id=?', (file_id,)).fetchone()
print('meta_source:', meta[0] if meta else 'NOT FOUND')
"
```

### 4. Сбой сканирования по пути WSL/UNC

**Симптомы:** Ошибка зонда по пути `\\wsl.localhost\...`
**Проверка:**
```bash
python -c "
import os
path = r'\\\\wsl.localhost\\Ubuntu\\home\\user\\...'
print(f'exists: {os.path.exists(path)}')
print(f'isdir: {os.path.isdir(path)}')
print(f'repr: {repr(path)}')
print(f'len: {len(path)}')
"
```
**Примечание:** `pathlib.Path.exists()` имеет ошибку с путями WSL UNC. Используйте `os.path.exists()`.

### 5. Расширение не загружается

**Симптомы:** Не отображается в списке расширений
**Проверка:**
```bash
python debug_check.py  # Смотрите раздел проверки Extension
```
**Пункты проверки:**
- Существует ли `extension.json` или `extension.yml`?
- Действителен ли JSON/YAML? (проверить с `safe_load_config`)
- Существует ли поле `name`?

### 6. Блокировка по PIN-аутентификации

**Симптомы:** 5 неудачных попыток → блокировка на 60 секунд
**Решение:** Подождите 60 секунд. Или перезагрузите сервер для сброса.
**Проверка:** Открыть инструменты разработчика браузера → Сеть → ответ `/_pin_check` для сообщения об ошибке

---

## Чтение журналов отладки

### Вывод консоли сервера

```
[WARN] config.json had invalid escapes — auto-repaired and saved
  → config.json автоматическое исправление обратной косой черты был выполнен

[DEBUG] scan/start: raw=..., sanitized=...
  → Путь при запуске сканирования (необработанное значение → после санитизации)

[DEBUG] scan-all root 0: repr=..., len=...
  → Детали каждого пути корня при сканировании всех папок

[Scan] Auto-registered scan root: /path/to/dir
  → Успешное сканирование при автоматической регистрации

[DEBUG share] file_id=123, file_row=yes, tmpl=no
  → QR API обмена: файл существует, но шаблон отсутствует

[ERROR] file.json: JSON parse failed: ...
  → Ошибка анализа в safe_load_json (приложение не падает)
```

---

## Структура файла и цели отладки

```
web_ui.py          ← Точка входа (запуск сервера)
core/
  config.py        ← Управление конфигурацией, safe_load_*
  server.py        ← PIN-аутентификация, QuickLock
  scanner.py       ← Двигатель сканирования
  extensions.py    ← Загрузка расширений
  db.py            ← Управление подключением БД
  schema.py        ← Определение таблиц
routes/
  scan.py          ← API сканирования
  search.py        ← API поиска
  share.py         ← QR API обмена
  tools.py         ← API инструментов + API инспекции
  debug.py         ← API отладки
  pages.py         ← Маршрутизация страниц
static/js/
  main.js          ← Основной пользовательский интерфейс (поиск, модальное окно, QR, клавиатура)
  scan-banner.js   ← Прогресс сканирования + прокрутка вверх (все страницы)
```
