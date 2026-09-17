# Расширение речь в текст

**Статус**: Реализовано (v3.28.0)
**Цель**: `extensions/builtin_speech_to_text/`
**Назначение**: Транскрибировать видео и аудиофайлы с автоматическим обнаружением backend

---

## Обзор

Это расширение извлекает аудио из видео и аудиофайлов и транскрибирует его с использованием моделей Whisper.
Оно автоматически выбирает оптимальный backend на основе доступного оборудования и работает на GPU или CPU даже без Hailo NPU.

---

## Приоритет Backend

| Приоритет | Backend | Библиотека | Целевое оборудование |
|--------|-------------|-----------|-----------------|
| P100 | `hailo` | `hailo_platform.genai` | Hailo-10H NPU |
| P70 | `torch-whisper-rocm` | `torch` (ROCm) + `transformers` | AMD GPU (ROCm/HIP) |
| P50 | `faster-whisper-cuda` | `faster-whisper` (CTranslate2) | NVIDIA GPU (CUDA) |
| P40 | `torch-whisper-cuda` | `torch` (CUDA) + `transformers` | NVIDIA GPU (CUDA) |
| P20 | `torch-whisper-cpu` | `torch` + `transformers` | CPU |
| P50 | `faster-whisper-cpu` | `faster-whisper` (CTranslate2) | CPU |
| P10 | `whisper-cpp` | `pywhispercpp` | CPU (наилегче) |

В режиме `auto` выбирается backend с самым высоким приоритетом среди возвращающих `is_available() == True`.

---

## Настройка окружения

### Общие требования

- Python 3.11+
- ffmpeg (требуется для извлечения аудио из видео)

### Hailo-10H NPU (Raspberry Pi AI HAT 2)

Дополнительные пакеты не требуются (`hailo_platform` должен быть уже установлен).
Модель (`whisper-base` и т.д.) должна быть загружена через расширение GenAI.

```bash
# Загрузить модель из UI расширения GenAI если её ещё нет
```

### NVIDIA GPU (CUDA)

```bash
# Рекомендуется: faster-whisper (легковесный, PyTorch не требуется)
pip install faster-whisper

# GPU используется автоматически когда обнаружена CUDA (float16)
# Автоматически возвращается к CPU когда CUDA отсутствует (int8)
```

### AMD GPU (ROCm)

```bash
# 1. Установить PyTorch ROCm edition
#    Официально: https://pytorch.org/get-started/locally/
#    Пример (ROCm 6.x):
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/rocm6.2

# 2. Установить HuggingFace transformers
pip install transformers

# 3. Установить backend в конфигурацию (автоматически обнаружен в режиме "auto")
#    В параметрах расширения: backend: "rocm" или "auto"
```

**Механизм обнаружения ROCm**: PyTorch раскрывает ROCm как CUDA через HIP.
Система идентифицирует ROCm когда `torch.version.hip` не равен `None`.

**Требования к памяти** (ROCm):

| Модель | Оценка VRAM |
|--------|----------|
| tiny | ~150 MB |
| base | ~300 MB |
| small | ~500 MB |
| medium | ~1.5 GB |

### Только CPU

```bash
# Опция 1: faster-whisper (рекомендуется, быстро с int8 квантованием)
pip install faster-whisper

# Опция 2: whisper.cpp (наилегче, PyTorch не требуется)
pip install pywhispercpp

# Опция 3: torch + transformers (общего назначения, но тяжело)
pip install torch transformers
```

**Оценки производительности CPU** (модель base, 1 минута аудио):

| Backend | RPi 5 | x86 (4 ядра) |
|---|---|---|
| faster-whisper (int8) | ~30 сек | ~5 сек |
| whisper.cpp | ~40 сек | ~8 сек |
| torch (float32) | ~90 сек | ~15 сек |

---

## Конфигурация

Настроить через страницу параметров расширения (`/ext/speech-to-text/`) или config.json:

| Элемент | Варианты | По умолчанию | Описание |
|------|--------|-----------|------|
| `backend` | auto / hailo / cuda / rocm / cpu | auto | Backend умозаключения |
| `model_size` | tiny / base / small / medium | base | Размер модели Whisper |
| `default_language` | Код BCP-47 (ja, en и т.д.) | ja | Язык по умолчанию |

---

## API конечные точки

Все конечные точки находятся под префиксом `/ext/speech-to-text`.

### POST `/api/s2t/transcribe`

Транскрибирует загруженное WAV аудио.

- **Content-Type**: `multipart/form-data`
- **Параметры**: `audio` (файл), `language` (опционально)
- **Ответ**: `{ status, text, segments, language, sample_rate, backend }`

### POST `/api/s2t/transcribe-video`

Транскрибирует видео/аудиофайл зарегистрированный в БД. Результаты сохраняются как аннотации.

- **Body**: `{ file_id: int, language?: string }`
- **Ответ**: `{ status, text, segments, language, backend }`
- **Аннотация**: `source="s2t"`, ключи: `transcript`, `transcript_segments`, `transcript_backend`

### POST `/api/s2t/batch-transcribe`

Пакетное транскрибирование нескольких файлов (работает в фоне).

Выберите **один** из трёх методов ввода (взаимоисключающие):

#### Метод 1: Список ID файлов (наследие)

```json
{
  "file_ids": [123, 456, 789],
  "language": "ja"
}
```

#### Метод 2: Директория

Автоматически обнаруживает видео/аудиофайлы в указанной директории и обрабатывает только зарегистрированные в БД.

```json
{
  "directory": "/path/to/videos/",
  "recursive": true,
  "language": "en"
}
```

- `recursive` (по умолчанию: `true`): Рекурсивно ищите поддиректории
- Целевые расширения: `.webm`, `.mp4`, `.avi`, `.mov`, `.mkv`, `.m4v`, `.ogv`, `.mp3`, `.wav`, `.ogg`, `.opus`, `.m4a`, `.aac`, `.flac`

#### Метод 3: Список текста/CSV

Укажите текстовый файл или CSV со списком путей файлов.

```json
{
  "list_file": "/path/to/targets.txt",
  "language": "ja"
}
```

**Формат текстового файла** (`.txt` и т.д.):
```
# Строки комментариев (строки начинающиеся с # игнорируются)
/mnt/videos/interview_01.mp4
/mnt/videos/interview_02.webm
/mnt/audio/podcast_03.mp3
```

**Формат CSV** (`.csv`):
```csv
/mnt/videos/interview_01.mp4
/mnt/videos/interview_02.webm
/mnt/audio/podcast_03.mp3
```
Первый столбец используется как путь файла. Строки начинающиеся с `#` пропускаются.

#### Общие опции

| Параметр | Тип | По умолчанию | Описание |
|-----------|---|-----------|------|
| `language` | string | Значение конфигурации (типично `ja`) | Код языка (см. ниже) |
| `recursive` | bool | `true` | Только метод директории: рекурсивный поиск поддиректорий |

#### Ограничения и ограничения

- Максимум целевых файлов: **500**
- Только файлы зарегистрированные в БД (таблица `files`) обрабатываются
- Удалённые файлы (`is_deleted=1`) исключены

#### Пример ответа

```json
{
  "status": "started",
  "total": 15,
  "mode": "directory",
  "directory": "/mnt/videos/",
  "recursive": true,
  "files_found": 23,
  "matched_in_db": 15
}
```

- **SSE события**: `s2t.batch_start`, `s2t.batch_progress`, `s2t.batch_complete`

### GET `/api/s2t/transcript/<file_id>`

Получает сохранённые результаты транскрибирования. Оба `source="s2t"` и `source="hailo:s2t"` проверяются для обратной совместимости.

### GET `/api/s2t/status`

Возвращает статус backend и список доступных backend.

---

## MCP инструменты

| Имя инструмента | Описание |
|---------|------|
| `s2t_status` | Получить статус backend |
| `s2t_transcribe_video` | Транскрибировать один видеофайл |
| `s2t_batch_transcribe` | Запустить пакетное транскрибирование (file_ids / directory / list_file) |
| `s2t_get_transcript` | Получить сохранённое транскрибирование |

### Параметры `s2t_batch_transcribe`

| Параметр | Тип | Требуется | Описание |
|-----------|---|------|------|
| `file_ids` | list[int] | *1 | Список ID файлов (макс 500) |
| `directory` | string | *1 | Путь директории (автоматически обнаруживает видео/аудио) |
| `list_file` | string | *1 | Путь текстового/CSV файла |
| `recursive` | bool | | Только метод директории. Рекурсивный поиск поддиректорий (по умолчанию true) |
| `language` | string | | Код языка. Пусто = конфигурация по умолчанию |
| `expected_count` | int | | Для обнаружения усечения file_ids |

*1: Укажите ровно один из `file_ids`, `directory` или `list_file` (взаимоисключающие)

---

## Структура файла

```
extensions/builtin_speech_to_text/
  extension.json                      # Манифест
  speech_to_text_ext.py               # Точка входа (Blueprint)
  s2t_routes.py                       # Маршруты API одного файла
  s2t_batch_routes.py                 # Маршруты API пакета
  core_impl/
    base.py                           # Абстрактный базовый класс S2TBackend
    backend_hailo.py                  # Hailo-10H NPU
    backend_faster_whisper.py         # faster-whisper (CUDA/CPU)
    backend_torch_whisper.py          # PyTorch transformers (ROCm/CUDA/CPU)
    backend_whisper_cpp.py            # whisper.cpp (CPU)
    backend_registry.py               # Автоматическое обнаружение + управление синглтоном
  templates/speech_to_text/
    s2t.html                          # Страница UI
mcp_server/
  s2t_tools.py                        # Определения инструментов MCP
```

---

## Поддерживаемые коды языка

Основные коды языков (BCP-47) поддерживаемые Whisper:

| Код | Язык | Код | Язык |
|--------|------|--------|------|
| `ja` | Японский | `en` | Английский |
| `zh` | Китайский | `ko` | Корейский |
| `de` | Немецкий | `fr` | Французский |
| `es` | Испанский | `it` | Итальянский |
| `pt` | Португальский | `ru` | Русский |
| `ar` | Арабский | `hi` | Хинди |
| `th` | Тайский | `vi` | Вьетнамский |
| `nl` | Голландский | `tr` | Турецкий |
| `pl` | Польский | `uk` | Украинский |
| `id` | Индонезийский | `sv` | Шведский |

Другие поддерживаемые Whisper языки также могут быть указаны. Пустая строка запускает автоматическое обнаружение.
Язык по умолчанию может быть изменён через параметр расширения `default_language` (начальное значение: `ja`).

---

## Известные ограничения

- **Задержка первой загрузки**: transformers / faster-whisper загружают модели из HuggingFace Hub (base: ~150MB). Первый запуск может занять несколько минут
- **Модели Hailo HEF**: Должны быть загружены через расширение GenAI. Расширение S2T не имеет функции загрузки
- **Память**: Модель medium может вызвать ошибки нехватки памяти на RPi 5 (8GB). Рекомендуется модель base
- **Параллелизм**: Backend управляются как синглтоны. Запросы поступающие во время пакетной обработки совместно используют тот же экземпляр
- **Формат ввода**: WAV (PCM s16le, mono, 16kHz) предполагается. Видеофайлы автоматически конвертируются через ffmpeg
- **Ввод пакета**: Методы directory / list_file обрабатывают только файлы зарегистрированные в БД. Несканированные файлы должны сначала быть зарегистрированы через `start_scan`

---

## Потоковое транскрибирование в реальном времени

Транскрибируйте аудио из интернет-радио, потоков RTSP и видеофайлов в реальном времени и отображайте субтитры в WebUI.

### Два режима

- **Режим chunks** (по умолчанию): Разделяет аудио на фрагменты, используя обнаружение тишины на основе RMS. Совместимо со всеми backend (Hailo/CUDA/CPU). Результаты отображаются после завершения каждого высказывания.
- **Live режим**: Выполняет постепенное транскрибирование с использованием Silero VAD от faster-whisper. Отображает промежуточные результаты пока речь ещё идёт. Требуется backend ONNX/faster-whisper.

### Поддерживаемые источники ввода

- HTTP/HTTPS потоки (интернет-радио и т.д.)
- RTSP камеры
- RTMP потоки

### API конечные точки

| Конечная точка | Метод | Функция |
|---|---|---|
| `/api/s2t/stream/start` | POST | Запустить потоковую передачу (`source_url`, `language`, `mode`) |
| `/api/s2t/stream/stop` | POST | Остановить потоковую передачу |
| `/api/s2t/stream/status` | GET | Получить статус |
| `/api/s2t/stream/transcript` | GET | Получить полное транскрибирование |
| `/api/s2t/stream/export/txt` | GET | Экспортировать как текст |
| `/api/s2t/stream/export/srt` | GET | Экспортировать как субтитры SRT |

### SSE события

| Событие | Описание |
|---|---|
| `s2t.stream_chunk` | Завершённый текст |
| `s2t.stream_interim` | Промежуточный текст (только Live режим) |
| `s2t.stream_complete` | Потоковая передача завершена |

### MCP инструменты

| Инструмент | Описание |
|---|---|
| `s2t_stream_start(source_url, language)` | Запустить потоковую передачу |
| `s2t_stream_stop()` | Остановить потоковую передачу |
| `s2t_stream_status()` | Получить статус |
| `s2t_stream_transcript()` | Получить полное транскрибирование |

### Конфигурация потоковой передачи

Настраиваемые элементы в `extension.json`:

| Элемент | Описание | По умолчанию |
|---|---|---|
| `stream_chunk_min_sec` | Минимальная длина фрагмента в режиме Chunk (секунды) | — |
| `stream_chunk_max_sec` | Максимальная длина фрагмента в режиме Chunk (секунды) | — |
| `stream_silence_threshold` | Пороговое значение RMS для обнаружения тишины | — |
| `stream_silence_ms` | Продолжительность тишины для обнаружения (миллисекунды) | — |
| `live_interval_sec` | Интервал транскрибирования в Live режиме (секунды) | — |
