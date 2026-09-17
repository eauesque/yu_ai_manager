# OCR API

API для извлечения текста (OCR) из изображений, видео и PDF-файлов, а также для перевода, создания наложенных изображений, экспорта, бенчмаркинга и управления движками.

## POST /api/ocr/<file_id>

Выполнить OCR на одном файле и сохранить результат в базу данных.

### Rate Limit

WRITE

### Request

```json
{
  "task": "ocr",
  "language": "auto",
  "server_id": ""
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | ID файла (параметр пути) |
| `task` | string | No | Тип задачи OCR. Одно из `ocr` / `ocr_document` / `ocr_manga`. По умолчанию: `ocr` |
| `language` | string | No | Подсказка о языке. По умолчанию: `auto` |
| `server_id` | string | No | ID сервера анализа для использования. Автоматически выбирается, если опущено |

### Response (200)

```json
{
  "file_id": 42,
  "engine": "gemini-2.0-flash",
  "task": "ocr",
  "full_text": "Extracted text...",
  "language": "ja",
  "regions_count": 3,
  "row_id": 1
}
```

### Errors

- `400` — Неверное значение task
- `404` — Файл не найден
- `500` — Ошибка разрешения OCR движка / ошибка выполнения OCR

---

## GET /api/ocr/result/<file_id>

Получить сохраненный результат OCR.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | ID файла (параметр пути) |
| `task` | string | No | Фильтр по типу задачи |
| `engine` | string | No | Фильтр по названию движка |
| `all` | string | No | Если установлено на любое значение, возвращает все результаты |

### Response (result found)

```json
{
  "file_id": 42,
  "task": "ocr",
  "engine": "gemini-2.0-flash",
  "full_text": "Extracted text...",
  "language": "ja",
  "regions": [...]
}
```

### Response (with `?all=1`)

```json
{
  "file_id": 42,
  "results": [
    { "task": "ocr", "engine": "gemini-2.0-flash", "full_text": "..." },
    { "task": "ocr_manga", "engine": "manga-ocr", "full_text": "..." }
  ]
}
```

### Response (no result)

```json
{
  "status": "not_found"
}
```

---

## DELETE /api/ocr/result/<file_id>

Удалить сохраненные результаты OCR.

### Rate Limit

WRITE

### Request

```json
{
  "task": "",
  "engine": ""
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | ID файла (параметр пути) |
| `task` | string | No | Фильтр по типу задачи. Пустая строка охватывает все задачи |
| `engine` | string | No | Фильтр по названию движка. Пустая строка охватывает все движки |

### Response

```json
{
  "deleted": 2
}
```

---

## POST /api/ocr/batch

Выполнить OCR на нескольких файлах в пакетном режиме.

### Rate Limit

WRITE

### Request

```json
{
  "file_ids": [1, 2, 3],
  "task": "ocr",
  "language": "auto",
  "server_id": ""
}
```

| Parameter | Type | Required | Limit | Description |
|-----------|------|----------|-------|-------------|
| `file_ids` | int[] | Yes | Max 500 | Массив целевых ID файлов |
| `task` | string | No | — | Тип задачи OCR. `ocr` / `ocr_document` / `ocr_manga`. По умолчанию: `ocr` |
| `language` | string | No | — | Подсказка о языке. По умолчанию: `auto` |
| `server_id` | string | No | — | ID сервера анализа для использования |

### Response (200)

```json
{
  "processed": 2,
  "errors": 1,
  "results": [
    { "file_id": 1, "full_text_length": 128, "regions_count": 3 },
    { "file_id": 2, "full_text_length": 256, "regions_count": 5 }
  ],
  "error_details": [
    { "file_id": 3, "error": "File not found" }
  ]
}
```

### Errors

- `400` — `file_ids` пуст / превышает 500 / неверное значение task
- `500` — Ошибка разрешения OCR движка

---

## POST /api/ocr/video/<file_id>

Извлечь ключевые кадры из видеофайла и выполнить OCR на каждом кадре.

### Rate Limit

WRITE

### Request

```json
{
  "task": "ocr",
  "language": "auto",
  "server_id": "",
  "keyframe_count": 4,
  "strategy": "uniform"
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | ID файла (параметр пути) |
| `task` | string | No | Тип задачи OCR. По умолчанию: `ocr` |
| `language` | string | No | Подсказка о языке. По умолчанию: `auto` |
| `server_id` | string | No | ID сервера анализа для использования |
| `keyframe_count` | int | No | Количество ключевых кадров для извлечения. Диапазон: 1-16. По умолчанию: `4` |
| `strategy` | string | No | Стратегия извлечения ключевых кадров. По умолчанию: `uniform` |

### Response (200)

```json
{
  "file_id": 42,
  "engine": "gemini-2.0-flash",
  "task": "ocr",
  "full_text": "Text extracted from frames...",
  "frame_count": 4,
  "row_id": 5
}
```

### Errors

- `400` — Файл не является видео
- `404` — Файл не найден
- `500` — Ошибка разрешения OCR движка / ошибка выполнения OCR видео

---

## POST /api/ocr/pdf/<file_id>

Преобразовать страницы PDF в изображения и выполнить OCR. Полезно для отсканированных PDF-файлов без текстового слоя.

### Rate Limit

WRITE

### Request

```json
{
  "task": "ocr_document",
  "language": "auto",
  "server_id": "",
  "page_range": "",
  "dpi": 200
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | ID файла (параметр пути) |
| `task` | string | No | Тип задачи OCR. По умолчанию: `ocr_document` |
| `language` | string | No | Подсказка о языке. По умолчанию: `auto` |
| `server_id` | string | No | ID сервера анализа для использования |
| `page_range` | string | No | Диапазон страниц (например, `"1-5"`, `"1,3,5"`). Пустая строка означает все страницы |
| `dpi` | int | No | Разрешение рендеринга. Диапазон: 72-400. По умолчанию: `200` |

### Response (200)

```json
{
  "file_id": 42,
  "engine": "gemini-2.0-flash",
  "task": "ocr_document",
  "full_text": "Text extracted from PDF...",
  "page_count": 10,
  "row_id": 6
}
```

### Errors

- `400` — Файл не является PDF
- `404` — Файл не найден
- `500` — Ошибка разрешения OCR движка / ошибка выполнения OCR PDF

---

## POST /api/ocr/bbox/<file_id>

Обнаружить ограничивающие прямоугольники текста для существующих результатов OCR. Используется в качестве второго прохода для добавления информации о положении к ранее извлеченным текстовым областям.

### Rate Limit

WRITE

### Request

```json
{
  "task": "",
  "server_id": ""
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | ID файла (параметр пути) |
| `task` | string | No | Целевой тип задачи OCR |
| `server_id` | string | No | ID сервера анализа для использования |

### Response (200)

```json
{
  "file_id": 42,
  "total_regions": 5,
  "detected_bboxes": 4,
  "regions": [
    {
      "id": 0,
      "text": "Text region",
      "bbox": { "x": 10, "y": 20, "width": 200, "height": 30 }
    }
  ]
}
```

### Errors

- `400` — Не найдены текстовые области / требуется VLM движок
- `404` — Результат OCR не найден (сначала выполните OCR) / Файл не найден
- `500` — Ошибка разрешения OCR движка / ошибка обнаружения bbox

---

## GET /api/ocr/engines

Список доступных OCR движков (серверы анализа) с оценками для каждой задачи.

### Parameters

None

### Response

```json
{
  "engines": [
    {
      "server_id": "server-1",
      "server_name": "Gemini Flash",
      "model": "gemini-2.0-flash",
      "type": "google",
      "scores": {
        "ocr": 85,
        "ocr_document": 90,
        "ocr_manga": 60
      }
    }
  ],
  "manga_ocr_available": false
}
```

---

## GET /api/ocr/npu

Получить статус устройства NPU (Neural Processing Unit) и рекомендуемые параметры оптимизации.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `task` | string | No | Тип задачи для рекомендаций оптимизации. По умолчанию: `ocr` |

### Response

```json
{
  "npu": {
    "available": true,
    "device": "Hailo-10H",
    "driver_version": "4.20.0"
  },
  "optimization": {
    "recommended_batch_size": 4,
    "use_npu": true
  }
}
```

---

## POST /api/ocr/translate/<file_id>

Перевести существующий результат OCR на указанный язык. Перевод сохраняется в базу данных.

### Rate Limit

WRITE

### Request

```json
{
  "target_lang": "en",
  "server_id": "",
  "task": ""
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | ID файла (параметр пути) |
| `target_lang` | string | Yes | Код целевого языка (например, `en`, `ja`, `zh`, `ko`) |
| `server_id` | string | No | ID сервера анализа для использования |
| `task` | string | No | Целевой тип задачи OCR |

### Response (200)

```json
{
  "file_id": 42,
  "target_lang": "en",
  "translated_text": "Translated full text...",
  "engine": "gemini-2.0-flash",
  "region_translations": [
    { "region_id": 0, "original": "Original text", "translated": "Translated text" }
  ]
}
```

### Errors

- `400` — `target_lang` не указан
- `404` — Результат OCR не найден
- `500` — Ошибка выполнения перевода

---

## GET /api/ocr/translations/<file_id>

Получить список результатов перевода для файла.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | ID файла (параметр пути) |
| `target_lang` | string | No | Фильтр по коду языка |

### Response

```json
{
  "file_id": 42,
  "translations": [
    {
      "target_lang": "en",
      "translated_text": "Translated text...",
      "engine": "gemini-2.0-flash",
      "region_translations": [...]
    }
  ]
}
```

---

## GET /api/ocr/overlay/<file_id>

Создать наложенное изображение с результатами OCR (или переводами), отображаемыми поверх исходного изображения.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | ID файла (параметр пути) |
| `mode` | string | No | Режим отображения. `translated` / `original` / `both`. По умолчанию: `translated` |
| `target_lang` | string | No | Фильтр по языку перевода |
| `format` | string | No | Формат выходного изображения. `png` / `jpeg`. По умолчанию: `png` |
| `task` | string | No | Целевой тип задачи OCR |

### Response

- Content-Type: `image/png` или `image/jpeg`
- Filename: `ocr_overlay_{file_id}.{ext}`

### Errors

- `400` — Неверное значение mode / format
- `404` — Результат OCR не найден / Файл не найден
- `500` — Ошибка создания наложенного изображения

---

## GET /api/ocr/export/<file_id>

Экспортировать результат OCR в указанном формате как загружаемый файл.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | ID файла (параметр пути) |
| `format` | string | No | Формат экспорта. `txt` / `md` / `json` / `pdf`. По умолчанию: `md` |
| `task` | string | No | Целевой тип задачи OCR |
| `include_translation` | string | No | Если установлено на любое значение, включает переводы |
| `target_lang` | string | No | Код языка для включения перевода |

### Response

- Content-Type: MIME-тип, соответствующий формату
- Content-Disposition: `attachment; filename=...`

### Errors

- `400` — Неверное значение format
- `404` — Результат OCR не найден

---

## POST /api/ocr/export/batch

Пакетный экспорт результатов OCR для нескольких файлов. Поддерживает загрузку ZIP или прямое сохранение на сервере.

### Rate Limit

WRITE

### Request

```json
{
  "file_ids": [1, 2, 3],
  "format": "md",
  "output_dir": "",
  "overlay_mode": "translated",
  "target_lang": "",
  "include_translation": false
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_ids` | int[] | Yes | Массив целевых ID файлов |
| `format` | string | No | Формат экспорта. `txt` / `md` / `json` / `pdf` / `overlay`. Значение по умолчанию из config расширения |
| `output_dir` | string | No | Абсолютный путь для сохранения на сервере. Если опущено, возвращает загрузку ZIP |
| `overlay_mode` | string | No | Режим наложения (при `format=overlay`). `translated` / `original` / `both`. По умолчанию: `translated` |
| `target_lang` | string | No | Код языка перевода |
| `include_translation` | bool | No | Включать ли переводы. По умолчанию: `false` |

### Response (ZIP download)

- Content-Type: `application/zip`
- Filename: `ocr_export_batch.zip` (текстовые форматы) или `ocr_overlay_batch.zip` (формат наложения)

### Response (server-side save)

```json
{
  "saved": 3,
  "errors": 0,
  "output_dir": "/path/to/output",
  "results": [
    { "file_id": 1, "path": "/path/to/output/ocr_1.md" }
  ],
  "error_details": []
}
```

### Errors

- `400` — `file_ids` пуст / неверное значение format / `output_dir` не является абсолютным путем
- `403` — `output_dir` является запрещенной директорией
- `404` — Результаты OCR не найдены

---

## POST /api/ocr/benchmark

Выполнить бенчмарк OCR для измерения точности и производительности. Требует тестовые случаи (пары изображение + текст с истинным значением).

### Rate Limit

WRITE

### Request

```json
{
  "task": "ocr",
  "server_id": "",
  "benchmark_dir": ""
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `task` | string | No | Тип задачи для бенчмарка. По умолчанию: `ocr` |
| `server_id` | string | No | ID сервера анализа для использования |
| `benchmark_dir` | string | No | Путь директории для тестовых случаев. По умолчанию: `extensions/builtin_ocr/benchmarks/` |

### Response (200)

```json
{
  "total_cases": 10,
  "avg_accuracy": 0.92,
  "avg_time_ms": 1500,
  "results": [
    {
      "image": "test1.png",
      "accuracy": 0.95,
      "time_ms": 1200
    }
  ]
}
```

### Errors

- `404` — Не найдены тестовые случаи
- `500` — Ошибка разрешения OCR движка / Ошибка выполнения бенчмарка

---

## GET /api/ocr/benchmark/cases

Список доступных тестовых случаев бенчмарка.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `dir` | string | No | Путь директории для тестовых случаев |

### Response

```json
{
  "cases": [
    {
      "image": "test1.png",
      "task": "ocr",
      "language": "ja",
      "expected_length": 256,
      "tags": ["manga", "vertical"]
    }
  ],
  "total": 10
}
```

---

## GET /api/ocr/profiles

Список профилей OCR моделей с конфигурациями оценок для каждой задачи.

### Parameters

None

### Response

```json
{
  "profiles": [
    {
      "model_prefix": "gemini-2.0-flash",
      "scores": {
        "ocr": 85,
        "ocr_document": 90,
        "ocr_manga": 60
      }
    }
  ]
}
```

---

## POST /api/ocr/profiles/fetch

Получить и объединить опубликованные сообществом профили моделей с URL.

### Rate Limit

WRITE

### Request

```json
{
  "url": "https://example.com/ocr-profiles.json"
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `url` | string | Yes | URL JSON с профилями |

### Response (200)

```json
{
  "added": 3,
  "updated": 1,
  "total": 15
}
```

### Errors

- `400` — `url` не указан
- `500` — Ошибка получения или объединения

---

## PUT /api/ocr/profiles/<model_prefix>

Вручную обновить оценки для профиля модели.

### Rate Limit

WRITE

### Request

```json
{
  "scores": {
    "ocr": 90,
    "ocr_document": 85,
    "ocr_manga": 70
  }
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `model_prefix` | string | Yes | Префикс названия модели (параметр пути) |
| `scores` | object | Yes | Объект с типами задач в качестве ключей и оценками (целые числа) в качестве значений |

### Response

```json
{
  "model": "gemini-2.0-flash",
  "scores": {
    "ocr": 90,
    "ocr_document": 85,
    "ocr_manga": 70
  }
}
```

### Errors

- `400` — `scores` не указан
