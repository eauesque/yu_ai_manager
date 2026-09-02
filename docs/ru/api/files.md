# API файлов

API для получения детали файлов, миниатюр и исходных медиа.

## GET /api/file/<id>

Получение подробных метаданных для файла.

### Параметры

| Параметр | Тип | Описание |
|-----------|------|-------------|
| `id` | int | ID файла (параметр пути) |

### Ответ

```json
{
  "id": 42,
  "path": "/images/output/00042.png",
  "filename": "00042.png",
  "size": 1234567,
  "mtime": 1709500000,
  "width": 1024,
  "height": 1536,
  "meta_type": "a1111_png",
  "model_name": "animagine-xl-3.1",
  "positive": "1girl, landscape",
  "negative": "low quality",
  "steps": 28,
  "sampler": "Euler a",
  "cfg_scale": 7.0,
  "seed": 1234567890,
  "rating": 4,
  "is_favorite": true,
  "tags": ["landscape"],
  "collections": [1, 3],
  "hash_md5": "abc123...",
  "hash_phash": "def456...",
  "analysis": { "description": "A scenic landscape..." }
}
```

## GET /api/thumbnail/<id>

Изображение миниатюры (WebP). Поддерживает кэширование ETag.

### Параметры

| Параметр | Тип | Описание |
|-----------|------|-------------|
| `id` | int | ID файла |
| `size` | int | Размер миниатюры (по умолчанию 300) |

### Ответ

- Content-Type: `image/webp`
- Поддержка ETag / If-None-Match (304 Not Modified)
- Кэш: 24 часа

## GET /api/original/<id>

Потоковая передача исходного файла. Также поддерживает файлы внутри ZIP архивов.

### Параметры

| Параметр | Тип | Описание |
|-----------|------|-------------|
| `id` | int | ID файла |

### Ответ

- Content-Type: MIME тип файла
- Content-Disposition: `inline`
- Поддержка Range запросов (для поиска видео)

## POST /api/convert

Преобразование формата приглашения (A1111 <-> NAI).

### Запрос

```json
{
  "prompt": "1girl, (masterpiece:1.2)",
  "direction": "a1111_to_nai"
}
```

### Ответ

```json
{
  "converted": "1girl, {{masterpiece}}",
  "direction": "a1111_to_nai"
}
```

## GET /api/container-thumb-ids

Список ID миниатюр для контейнера (папка/ZIP), исключая уже кэшированные записи.

### Параметры

| Параметр | Тип | Описание |
|-----------|------|-------------|
| `keys` | string | Ключи контейнера (разделены запятой) |
