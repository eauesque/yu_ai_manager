# API растеризации SVG

API для преобразования векторных изображений SVG в растровые PNG/WebP.
Разработан для интеграции конвейера img2img — возвращаемые данные изображения base64 могут быть переданы непосредственно на NovelAI Bridge или SD WebUI Bridge.

## GET /api/svg/info

Проверка доступности растеризации SVG.

- **Ограничение скорости**: Нет (GET)

### Ответ

```json
{
  "available": true,
  "backend": "resvg"
}
```

| Поле | Тип | Описание |
|-------|------|-------------|
| `available` | bool | Доступна ли растеризация |
| `backend` | string \| null | Активный бэкенд (`"resvg"` или `null`) |

---

## POST /api/svg/rasterize

Растеризация SVG в растровое изображение PNG/WebP.

- **Ограничение скорости**: HEAVY

### Тело запроса

| Параметр | Тип | Обязательный | Описание |
|-----------|------|----------|-------------|
| `file_id` | int | *1 | ID файла SVG из базы данных |
| `svg_path` | string | *1 | Абсолютный путь к файлу SVG |
| `svg_data` | string | *1 | Встроенная строка SVG XML |
| `width` | int | Нет | Ширина выхода (по умолчанию: 1024) |
| `height` | int | Нет | Высота выхода (по умолчанию: 1024) |
| `format` | string | Нет | `"png"` или `"webp"` (по умолчанию: `"png"`) |
| `background` | string | Нет | Цвет фона (например `"#ffffff"`). Прозрачный, если опущен |

> *1: Укажите ровно один из `file_id`, `svg_path` или `svg_data`.

### Пример запроса

```json
{
  "file_id": 123,
  "width": 832,
  "height": 1216,
  "format": "png",
  "background": "#ffffff"
}
```

### Ответ

```json
{
  "ok": true,
  "base64": "iVBORw0KGgo...",
  "width": 832,
  "height": 1216,
  "format": "png",
  "size_bytes": 45678
}
```

| Поле | Тип | Описание |
|-------|------|-------------|
| `ok` | bool | Флаг успеха |
| `base64` | string | Кодированные в base64 данные PNG/WebP |
| `width` | int | Фактическая ширина выхода |
| `height` | int | Фактическая высота выхода |
| `format` | string | Формат выхода |
| `size_bytes` | int | Бинарный размер в байтах |

### Ответ об ошибке

```json
{
  "ok": false,
  "error": "resvg is not installed (pip install resvg)"
}
```

---

## Интеграция MCP

Используйте Claude Desktop для создания конвейера SVG → img2img:

```
# Шаг 1: растеризация SVG
svg_rasterize(file_id=123, width=832, height=1216, background="#ffffff")

# Шаг 2: передача возвращаемого base64 на img2img
nai_generate(prompt="icon, detailed illustration, ...", image=<base64>, strength=0.7)
```

### MCP инструменты

| Инструмент | Описание |
|------|-------------|
| `svg_info` | Проверка доступности растеризации |
| `svg_rasterize` | Растеризация SVG в PNG/WebP |

---

## Зависимости

| Пакет | Лицензия | Назначение |
|---------|---------|---------|
| `resvg` | MIT | Растеризатор SVG на основе Rust (кроссплатформенный) |

Если `resvg` не установлен, миниатюры показывают заполнитель, а API возвращает HTTP 501.

```bash
pip install resvg
```
