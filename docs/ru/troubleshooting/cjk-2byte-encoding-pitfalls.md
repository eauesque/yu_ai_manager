# Ловушки кодирования CJK / двухбайтовых символов

Этот документ суммирует ошибки, специфичные для двухбайтовых зон (прежде всего японский CP932/Shift-JIS),
и решения, принятые в данном проекте.

---

## 1. Крэш cp932 в консоли Windows

### Симптомы

`cmd.exe` / PowerShell / Git Bash на Windows по умолчанию используют **cp932 (Shift-JIS)** для вывода.
`print()` с символами Unicode, отсутствующими в cp932, вызывает мгновенный крэш `UnicodeEncodeError`:

```
UnicodeEncodeError: 'charmap' codec can't encode character '\u2014' in position 12
```

### Решение

- **Использовать в `print()` только ASCII-безопасные символы**: `[OK]`, `[NG]`, `[!]`, `--`, `#` и т.д.
- Установить `PYTHONIOENCODING=utf-8`, но безопаснее перейти на ASCII

---

## 2. Кракозябры в именах файлов ZIP (CP437 mojibake)

### Симптомы

Старые ZIP-файлы (Windows 95/98/XP) хранят имена файлов в **Shift-JIS (CP932)**,
но Python декодирует без UTF-8 флага как **CP437** — японские имена отображаются как `âwâCâèâb`.

### Решение: 10-уровневый цепочечный фолбэк

В `core/infra_core/encoding.py` определён приоритетный список кодировок CJK:

```
UTF-8 → CP932 → EUC-JP → ISO-2022-JP → EUC-KR → CP949 → GB2312 → GBK → Big5 → CP950
```

### Python 3.11+ `metadata_encoding`

```python
# Python 3.11+: прямое указание кодировки
zf = zipfile.ZipFile(path, metadata_encoding='cp932')
```

---

## 3. Зависание сканирования при двухбайтовых символах в ZIP/7z

### Симптомы

`zipfile.ZipFile()` при чтении старых ZIP с Shift-JIS зависает на определённых байтовых последовательностях.

### Решение

1. **Защита таймаутом**: Вспомогательный метод `run_with_timeout()` с таймаутом 30 с для листинга и 60 с для I/O сканирования
2. **Таблица scan_errors**: Постоянная запись в DB ошибок таймаута и кодирования

---

## 4. Проблемы с кавычками в FTS5 tokenchars SQLite

### Симптомы

```sql
-- Неверно: внешние одинарные кавычки + внутренние двойные → parse error
tokenize='unicode61 tokenchars "_:."'

-- Верно: внешние двойные + внутренние одинарные
tokenize="unicode61 tokenchars '_:.'"
```

### Решение

```python
# Верно: использовать ''' в Python, содержащие как " так и '
con.execute('''
    CREATE VIRTUAL TABLE fts USING fts5(
        col1,
        tokenize="unicode61 tokenchars '_:.'"
    )
''')
```

---

## 5. WebP EXIF с кодировкой UTF-16

Некоторые инструменты (особенно NAI) сохраняют метаданные EXIF в WebP с **UTF-16 (с BOM)**.
Нужно определять BOM и применять соответствующую кодировку.

---

## 6. Кодирование tEXt-чанков PNG

Спецификация PNG определяет tEXt как **Latin-1 (ISO-8859-1)**, но большинство AI-инструментов
записывают UTF-8. Декодировать с предпочтением UTF-8:

```python
try:
    text = raw_bytes.decode('utf-8')
except UnicodeDecodeError:
    text = raw_bytes.decode('latin-1')
```

---

## 7. Обратные слэши Windows в config.json

```json
{"scan_roots": ["C:\Users\test"]}  // \U и \t — escape-последовательности!
```

**Решение**: `_repair_json_backslashes()` автоматически исправляет при запуске сервера.

---

## 8. pathlib и UNC-пути WSL

`pathlib.Path.exists()` может давать неверные результаты для UNC-путей (`\\server\share\...`).
**Решение**: Использовать `os.path.exists()` для UNC-путей.

---

## 9. UTF-8 BOM в CSV-экспорте

Excel без BOM интерпретирует UTF-8 CSV как ANSI (CP932 в японском окружении).

```python
buf.write("\ufeff")  # UTF-8 BOM для совместимости с Excel
```

---

## 10. `json.dumps()` с `ensure_ascii=False`

```python
json.dumps(data, ensure_ascii=False, indent=2)
```

---

## Примечания для AI-агентов

Многие из вышеуказанных проблем легко упустить при генерации кода:

1. **Не использовать эмодзи или декоративные символы в `print()`**
2. **Не предполагать кодировку имён файлов** — UTF-8 предположение ломается в CP932
3. **Кавычки SQLite требуют проверки в реальной среде**
4. **Всегда `ensure_ascii=False` в `json.dumps()`** при работе с японскими данными
5. **Вывод subprocess декодировать в кодировке окружения** — на Windows обычно CP932
6. **CSV с BOM** — для совместимости с Excel
