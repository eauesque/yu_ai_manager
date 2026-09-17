# API поиска

API для поиска файлов, предложений и группировки.

## GET /api/search

Основная конечная точка поиска файлов.

### Параметры

| Параметр | Тип | По умолчанию | Описание |
|-----------|------|---------|-------------|
| `q` | string | `""` | Поисковый запрос (текст в приглашениях, имена тегов) |
| `sort` | string | `"date"` | Порядок сортировки: `date`, `name`, `size`, `rating`, `random` |
| `order` | string | `"desc"` | `asc` / `desc` |
| `offset` | int | `0` | Начальная позиция пагинации |
| `limit` | int | `50` | Количество результатов (макс 200) |
| `cursor` | string | - | Токен для пагинации на основе курсора |
| `meta` | string | `"all"` | Тип метаданных: `all`, `a1111`, `nai`, `comfy`, `unknown` |
| `tags` | string | - | Фильтр тегов (разделены запятой) |
| `rating_min` | int | - | Минимальная оценка (0-5) |
| `rating_max` | int | - | Максимальная оценка (0-5) |
| `path` | string | - | Фильтр префикса пути |
| `ext` | string | - | Фильтр расширения (разделены запятой, например `png,webp`) |
| `has_prompt` | bool | - | Фильтр по наличию приглашения |
| `collection_id` | int | - | Поиск в коллекции |
| `favorites_only` | bool | `false` | Только избранное |
| `group_by` | string | - | Группировка: `folder`, `conversation` |

### Ответ

```json
{
  "results": [
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
      "positive": "1girl, landscape, sunset",
      "negative": "low quality",
      "rating": 4,
      "is_favorite": true,
      "tags": ["landscape", "sunset"]
    }
  ],
  "total": 1500,
  "offset": 0,
  "limit": 50,
  "next_cursor": "eyJtdGltZSI6MTcwOTUwMDAwMCwiaWQiOjQyfQ=="
}
```

## GET /api/search-grouped

Результаты поиска, сгруппированные по папке/ZIP.

### Параметры

Те же параметры запроса, что и `/api/search`, плюс:

| Параметр | Тип | Описание |
|-----------|------|-------------|
| `group_limit` | int | Максимальное количество элементов, показываемых на группу |

## GET /api/groups-index

Индекс групп папок и контейнеров ZIP. Используется для группировки результатов поиска.

### Параметры

| Параметр | Тип | Описание |
|-----------|------|-------------|
| `sort` | string | Порядок сортировки: `name`, `count`, `date` |
| `order` | string | `asc` / `desc` |
| `offset` | int | Начальная позиция пагинации |
| `limit` | int | Количество результатов |

## GET /api/group-members

Список ID файлов в указанном контейнере.

### Параметры

| Параметр | Тип | Описание |
|-----------|------|-------------|
| `key` | string | Ключ контейнера (путь папки или путь ZIP) |

## GET /api/suggest

Автозаполнение для тегов и приглашений.

### Параметры

| Параметр | Тип | Описание |
|-----------|------|-------------|
| `q` | string | Входной текст |
| `limit` | int | Количество предложений (по умолчанию 10) |

### Ответ

```json
{
  "suggestions": [
    { "value": "1girl", "count": 5432 },
    { "value": "1boy", "count": 1234 }
  ]
}
```

## GET /api/suggest/lora

Предложения имен моделей LoRA.

### Параметры

| Параметр | Тип | Описание |
|-----------|------|-------------|
| `q` | string | Входной текст |
| `limit` | int | Количество предложений |

## GET /api/server-info

Основная информация о сервере.

### Ответ

```json
{
  "version": "4.12.1",
  "db_path": "/path/to/tags.db",
  "file_count": 150000,
  "tag_count": 8500,
  "auth_required": false,
  "lan_ip": "192.168.1.100",
  "active_ui": "default"
}
```
