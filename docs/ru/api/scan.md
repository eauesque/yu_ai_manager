# API сканирования

API для управления сканированием файлов и управлением корневыми папками сканирования.

## Управление сканированием

### POST /api/scan/start

Запуск сканирования.

### Запрос

```json
{
  "root_indices": [0, 1],
  "force": false
}
```

| Поле | Тип | Описание |
|-------|------|-------------|
| `root_indices` | int[] | Индексы корней для сканирования (опустить для всех корней) |
| `force` | bool | Повторное сканирование существующих файлов |

### Ответ

```json
{
  "ok": true,
  "message": "Scan started"
}
```

### GET /api/scan/status

Получение прогресса сканирования.

### Ответ

```json
{
  "scanning": true,
  "progress": 45,
  "total": 1500,
  "current_file": "/images/output/00042.png",
  "errors": 0,
  "started_at": 1709500000
}
```

### POST /api/scan/cancel

Отмена выполняющегося сканирования.

### GET /api/scan/interrupted

Получение информации о прерванном сканировании.

### POST /api/scan/resume

Возобновление прерванного сканирования.

### POST /api/scan/dismiss

Отмена состояния прерванного сканирования.

## CLI сканера

Начиная с v3.27.0, сканирования выполняются в отдельном процессе (воркер).
Воркер может управляться непосредственно из CLI в дополнение к API WebUI.

```bash
# Запуск сканирования
python -m core.scan.scan_worker start --db ./tags.db --root /path/to/images [--scan-zips] [--force] [--resume]

# Остановка сканирования (SIGTERM -> плавное завершение)
python -m core.scan.scan_worker stop

# Проверка статуса
python -m core.scan.scan_worker status
```

### IPC файлы

| Файл | Содержимое |
|------|---------|
| `/tmp/yu-scan/worker.pid` | PID воркера |
| `/tmp/yu-scan/progress.json` | Прогресс (JSON: running, phase, current, total, percent, message, detail, error) |

WebUI опрашивает этот файл прогресса и передает данные через `GET /api/scan/status` и SSE события (`scan.progress`, `scan.complete`).

## Ошибки сканирования

### GET /api/scan-errors

Список ошибок, произошедших во время сканирования.

| Параметр | Тип | Описание |
|-----------|------|-------------|
| `type` | string | Фильтр типа ошибки |
| `resolved` | bool | Только разрешенные ошибки |
| `limit` | int | Количество результатов |

### POST /api/scan-errors/<id>/resolve

Отметить ошибку как разрешенную.

### POST /api/scan-errors/clear

Удалить все разрешенные ошибки одновременно.

## Управление корневыми папками сканирования

### GET /api/scan-roots

Список зарегистрированных корневых папок сканирования.

### Ответ

```json
{
  "roots": [
    {
      "path": "O:\\webui\\outputs",
      "enabled": true,
      "file_count": 15000
    }
  ]
}
```

### POST /api/scan-roots

Добавление корневой папки сканирования.

```json
{
  "path": "O:\\webui\\outputs"
}
```

### PUT /api/scan-roots/<index>

Обновление корневой папки сканирования (изменение пути, переключение включено/отключено).

### DELETE /api/scan-roots/<index>

Удаление корневой папки сканирования.

## Заполнение хешей

### POST /api/hash-backfill/start

Запуск фонового вычисления хешей для существующих файлов.

### GET /api/hash-backfill/status

Получение прогресса.

### POST /api/hash-backfill/cancel

Отмена вычисления.

## Фоновые работы

### GET /api/jobs/status

Статус всех фоновых работ. Используется для отображения баннера UI.

```json
{
  "jobs": [
    {
      "type": "scan",
      "status": "running",
      "progress": 45,
      "total": 1500
    }
  ]
}
```
