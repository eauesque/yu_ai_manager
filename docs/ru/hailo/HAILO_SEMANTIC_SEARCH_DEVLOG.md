# Hailo-10H Semantic Search — журнал разработки

**Проект**: YU AI Manager — CLIP семантический поиск изображений на Hailo-10H
**Цель**: реализовать семантический поиск изображений на естественном языке на базе CLIP на Raspberry Pi 5 + AI HAT 2 (Hailo-10H)
**Начало**: 2026-03-01
**Статус**: Phase 1-8 завершены; Phase 9-12 (связка VLM-подписи, S2T для видео, многоходовой LLM, OpenAI-совместимый API) завершены

---

## Почему этот проект важен

Hailo-10H (AI HAT 2) — относительно новый edge-AI ускоритель, выпущенный в конце 2025 года;
устанавливается в M.2-слот Raspberry Pi 5. Он обеспечивает 40 TOPS инференса, но
**примеров его применения в реальных приложениях пока практически нет в открытом доступе**.

Этот проект, использующий Hailo-10H для семантического поиска (поиска изображений на естественном языке)
по библиотеке объёмом около 200 тысяч изображений, станет, возможно, первым практическим
ПО подобного рода.

---

## Phase 1: Проверка реализуемости (2026-03-01)

### Параметры среды

| Параметр | Значение |
|------|-----|
| Оборудование | Raspberry Pi 5 (8GB) + AI HAT 2 (Hailo-10H) |
| ОС | Raspberry Pi OS Trixie (Linux 6.12.62+rpt-rpi-2712) |
| Python | 3.13.5 |
| Драйвер HailoRT | 5.2.0 (hailort-pcie-driver) |
| Библиотека HailoRT | 5.2.0 (hailort deb) |
| Python HailoRT | 5.2.0 (**сборка из исходников**) |

### Step 1-1: Распознавание устройства — OK

```bash
$ hailortcli fw-control identify
Firmware Version: 5.2.0 (release,app)
Device Architecture: HAILO10H
```

Устройство без проблем определилось. PCIe-подключение и загрузка драйвера прошли нормально.

### Step 1-2: Загрузка HEF — OK

Удалось напрямую загрузить из S3-бакета Hailo Model Zoo v5.2.0 (без аутентификации).

```
~/hailo_models/clip_vit_b_16_image_encoder.hef  (76 MB)
~/hailo_models/clip_vit_b_16_text_encoder.hef   (77 MB)
```

Шаблон URL:
```
https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/<model>.hef
```

### Step 1-3: Python-байндинги — требуется сборка из исходников

#### Проблема: несовпадение версий пакетов

В репозиториях Raspberry Pi OS существуют 2 разные линейки пакетов:

| Линейка пакетов | Версия | Примечание |
|---------------|-----------|------|
| `hailort` + `hailort-pcie-driver` | 5.2.0 | Официальные deb от Hailo. Нет Python-байндингов |
| `h10-hailort` + `python3-h10-hailort` | 5.1.1 | От команды Raspberry Pi. Python есть |

**Проблема**: две линейки имеют `Conflicts` и не сосуществуют. Установка `h10-hailort` (5.1.1)
заменяет и драйвер на 5.1.1, но для hailo-ollama требуется 5.2.0.

#### Решение: собрать Python wheel hailort 5.2.0 из исходников

**Wheel нет в PyPI**. На странице загрузок Hailo Developer Zone
**также нет wheel для aarch64** (только x86_64).

Решил сборку из исходников GitHub-репозитория:

```bash
git clone --depth 1 --branch v5.2.0 https://github.com/hailo-ai/hailort.git ~/hailort

# Сборочные зависимости
sudo apt install -y swig build-essential
pip install pybind11 setuptools wheel

# Сборка (около 2 минут)
cd ~/hailort/hailort/libhailort/bindings/python/platform
HAILORT_INCLUDE_DIR=/usr/include/hailo \
LIBHAILORT_PATH=/usr/lib/libhailort.so.5.2.0 \
PYBIND11_PYTHON_VERSION=3.13 \
python3 setup.py bdist_wheel --plat-name linux_aarch64

# Установка
pip install dist/hailort-5.2.0-cp313-cp313-linux_aarch64.whl
```

**Важные замечания**:
- `--plat-name linux_aarch64` обязателен. Без него парсинг имени каталога `LIBHAILORT_PATH`
  приводит к `ValueError: not enough values to unpack` (баг в строке 163 setup.py)
- Сначала необходимо установить deb-пакет `hailort` (C-библиотека)
- `h10-hailort` и `hailort` несовместимы (`Conflicts`), поэтому нужно
  сначала удалить `h10-hailort`, а затем поставить `hailort` 5.2.0

### Step 1-4: Тест инференса — успешно (с изменениями API)

#### Важное открытие: Hailo-10H не поддерживает устаревший VStreams API

Код из спецификации с `InferVStreams` + `ConfigureParams.create_from_hef()`
**не работает на Hailo-10H**. `VDevice.configure()` возвращает `HAILO_NOT_IMPLEMENTED (error 7)`.

Это **фундаментальное различие API между Hailo-8/8L и Hailo-10H**,
о котором недостаточно чётко сказано даже в официальной документации.

#### Правильный API: InferModel

На Hailo-10H используется `VDevice.create_infer_model()`:

```python
from hailo_platform import VDevice
import numpy as np

hef_path = "~/.hailo_models/clip_vit_b_16_image_encoder.hef"

with VDevice() as vdevice:
    infer_model = vdevice.create_infer_model(hef_path)

    # inputs/outputs — это свойства, а не вызываемые методы
    inp_info = infer_model.inputs[0]   # NOT inputs()
    out_info = infer_model.outputs[0]

    configured = infer_model.configure()
    bindings = configured.create_bindings()

    # Вход: изображение в uint8
    dummy = np.random.randint(0, 255, inp_info.shape, dtype=np.uint8)
    bindings.input().set_buffer(dummy)

    # Выход: нужно явно выделить uint8-буфер
    output_buf = np.empty(out_info.shape, dtype=np.uint8)
    bindings.output().set_buffer(output_buf)

    configured.run([bindings], timeout=10000)

    vec = output_buf.flatten()  # (512,) uint8
```

#### Где мы застряли и как решили

| Проблема | Ошибка | Решение |
|------|--------|------|
| `infer_model.inputs()` — TypeError | `'list' object is not callable` | Это свойство, использовать `inputs[0]` (без скобок) |
| Не установлен выходной буфер | `not configured as view` | Явно выделить через `bindings.output().set_buffer(buf)` |
| Выходной буфер как float32 | `buffer size 2048 != expected 512` | Выделить **uint8** (512 байт). float32 занял бы 2048 байт |
| Ошибка при завершении VDevice | `Lost communication with server` | Проблема порядка очистки VDevice. **На результаты инференса не влияет** |

### Производительность инференса

| Параметр | Значение |
|------|-----|
| Модель | CLIP ViT-B/16 Image Encoder |
| Вход | (224, 224, 3) uint8 |
| Выход | (1, 1, 512) uint8 (квантованный) |
| Время инференса | **~20 ms** |
| Теоретическая пропускная способность | **~50 изобр./с** |

Построение индекса для 200 тыс. изображений: только инференс — около 67 минут. С учётом
препроцессинга ожидаемое время — в пределах нескольких часов.

### Вердикт по Phase 1

| Критерий | Результат |
|------|------|
| Выходной вектор размерности 512 | **OK** (uint8 квантовано, требуется деквантование) |
| Скорость инференса | **Отлично** (20 ms/изображение) |
| Совместимость API | Используется InferModel API (VStreams API из спецификации недоступен) |
| Вердикт | **Переходим к Phase 2** |

### Что передаётся в следующую фазу

1. **Деквантование**: uint8-выход необходимо преобразовать в float32.
   В HEF должны быть зашиты параметры квантования (scale/zero_point).
   Вероятно, можно задействовать `hailo_platform.pyhailort._pyhailort.dequantize_output_buffer`.
2. **Текстовый энкодер**: HEF есть, но не тестировался. Нужно проверить, работает ли он с тем же InferModel API.
   Возможно, безопаснее реализовать на CPU (sentence-transformers), как и задумывалось в спецификации.
3. **Сосуществование с hailo-ollama**: VDevice используется эксклюзивно.
   Во время построения индекса hailo-ollama нужно останавливать.
4. **Очистка VDevice**: сообщение об ошибке при завершении безобидно, но
   в долго живущих серверных процессах нужно следить за утечками ресурсов.

---

## Phase 2: Расширение схемы БД (2026-03-01)

### Реализация

Добавлена таблица `file_vectors` как Migration 25.

```sql
CREATE TABLE file_vectors (
    file_id     INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
    model       TEXT NOT NULL DEFAULT 'clip_vit_b_16',
    vector      BLOB NOT NULL,        -- float32 numpy array tobytes() (512*4=2048 bytes)
    created_at  INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);
CREATE INDEX idx_file_vectors_model ON file_vectors(model);
```

**Проектные решения**:
- В `vector` сохраняется float32 BLOB после деквантования. Сохранение в uint8 даёт потерю точности
- `file_id` — PRIMARY KEY (1 файл = 1 вектор). Для поддержки нескольких моделей в будущем потребуется перейти на UNIQUE(file_id, model)
- `ON DELETE CASCADE` для автоматического удаления при удалении файла

**Тест**: применение миграции на in-memory БД → проверка наличия таблицы/индекса → OK

### Файлы

- `core/schema_core/schema_migrate_steps_25.py` (новый)
- `core/schema_core/schema_migrate.py` (импорт + добавлено `if current_version < 25`)
- `core/schema_core/schema_constants.py` (`CURRENT_SCHEMA_VERSION = 25`)
- `core/hailo_clip_core/vector_store.py` (новый — CRUD векторов в БД)  *(сейчас перенесён в `extensions/builtin_hailo_semantic_search/core_impl/`)*

---

## Phase 3: Ядро инференса Hailo (2026-03-01)

### Реализация

Новый пакет `core/hailo_clip_core/` *(сейчас — `extensions/builtin_hailo_semantic_search/core_impl/`)*:

| Файл | Назначение |
|---------|------|
| `hailo_inference.py` | Синглтон HailoClipEncoder. Обёртка над InferModel API |
| `image_preprocess.py` | Ресайз 224x224 + BGR→RGB через cv2 |
| `dequantize.py` | Деквантование uint8→float32 + L2-нормализация + извлечение quant_params |
| `text_encoder.py` | CPU CLIP-энкодер текста (`openai/clip-vit-base-patch16`) |

**Проектные решения**:
- Изображение передаётся в Hailo в uint8 без предварительной нормализации (она выполняется внутри HEF)
- Для текстового энкодера используется CLIPModel из `transformers` (а не `sentence-transformers`).
  Причина: `openai/clip-vit-base-patch16` — та же модель, что CLIP ViT-B/16 в Hailo HEF,
  и векторные пространства совпадают
- Параметры деквантования сперва пытаемся взять из `infer_model.outputs[0].quant_infos[0]`,
  при неудаче откат на scale=1.0, zero_point=0.0

**Зависимости**: `opencv-python-headless`, `numpy` (обязательные), `transformers`, `torch` (для поиска по тексту)

---

## Phase 4: Индексатор + Extension (2026-03-01)

### Реализация

| Файл | Назначение |
|---------|------|
| `core/hailo_clip_core/indexer.py` *(сейчас — `extensions/builtin_clip_search/core_impl/`)* | Пакетное построение индекса в фоновом потоке |
| `core/hailo_clip_core/event_handler.py` *(сейчас — `extensions/builtin_clip_search/core_impl/`)* | Автоиндексация по событию scan.complete |
| `extensions/builtin_hailo_semantic_search/extension.json` | Манифест расширения |
| `extensions/builtin_hailo_semantic_search/hailo_semantic_search.py` | Blueprint из 5 API |

**API-эндпоинты**:
- `GET /ext/hailo-semantic/api/status` — состояние устройства и индекса
- `POST /ext/hailo-semantic/api/index/start` — запуск построения индекса
- `GET /ext/hailo-semantic/api/index/status` — прогресс
- `POST /ext/hailo-semantic/api/index/stop` — прерывание
- `GET /ext/hailo-semantic/api/search` — семантический поиск
- `POST /ext/hailo-semantic/api/index/clear` — очистка индекса

**События**: добавлены `semantic_index.start/progress/complete` в event_bus

---

## Phase 5: Движок семантического поиска (2026-03-01)

### Реализация

`core/hailo_clip_core/search.py` *(сейчас — `extensions/builtin_clip_search/core_impl/search.py`)* — поиск по косинусной близости с кэшем в памяти

**Алгоритм**:
1. Единоразовая загрузка всех векторов из БД → кэш в памяти
2. Предварительная L2-нормализация векторов
3. Текст запроса → CLIP-энкодер текста → 512-мерный вектор
4. Пакетное вычисление косинусной близости матричным умножением (dot product)
5. Сортировка всех, что выше threshold → возврат результатов

**Оценка памяти**: 200K x 512 x 4 байт = ~400 MB (в пределах 8 GB RAM Pi5)

**Формат ответа**:
```json
{
    "status": "ok",
    "total": 25,
    "results": [{"file_id": 123, "score": 0.82, "path": "..."}],
    "query": "blue sky",
    "indexed_count": 200000,
    "threshold": 0.2,
    "timing": {"encode_ms": 150.3, "search_ms": 12.5}
}
```

---

## Phase 6: Интеграция UI (2026-03-01)

### Страница поиска

- Рядом со строкой поиска добавлен тумблер семантического поиска (иконка мозга в стиле `regex-pill`)
- Отображается только если Hailo доступен и индекс построен
- При включении: перехват submit формы поиска → вызов API семантического поиска → отображение результатов в существующей сетке
- Placeholder заменён на пример английского текста

### Страница Tools

- В вкладку Search & Analysis добавлена секция семантического поиска
- Отображение состояния устройства и индекса
- Слайдер размера пакета + чекбокс автоиндексации
- Кнопки Build Index / Stop / Clear + прогресс-бар (опрос каждые 2 секунды)

---

## Технические заметки

### Основные отличия Hailo-10H vs Hailo-8/8L (с точки зрения разработчика)

| Параметр | Hailo-8/8L | Hailo-10H |
|------|-----------|-----------|
| VStreams API | Поддерживается | **Не поддерживается** (NOT_IMPLEMENTED) |
| InferModel API | Поддерживается | Поддерживается |
| ConfigureParams | create_from_hef(hef, interface) | Не нужно (заменяет create_infer_model) |
| Формат выхода | float32 или uint8 на выбор | Только uint8 (нужно деквантование) |
| Python-пакет | Wheel в PyPI есть | **Отсутствует** (требуется сборка из исходников) |
| APT-пакет | Интегрировано в `hailort` | Отдельная линейка `h10-hailort` (только 5.1.1) |

### Хранение собранного wheel

```
~/hailort/hailort/libhailort/bindings/python/platform/dist/
  hailort-5.2.0-cp313-cp313-linux_aarch64.whl
```

При переносе на другие Pi5 этот wheel можно просто скопировать и установить
(при наличии libhailort.so.5.2.0 и hailort-pcie-driver 5.2.0).

---

## Журнал исправлений после реализации Phase 2-6 (2026-03-01)

### 1. Проблема совместимости `get_text_features` у текстового энкодера

**Проблема**: `CLIPModel.get_text_features(**inputs)` в новых версиях transformers стал возвращать
не `torch.Tensor`, а объект `BaseModelOutputWithPooling`.
Из-за этого вызов `.squeeze()` падал с `AttributeError`, и семантический поиск возвращал `Search failed`.

**Симптом**: `curl /ext/hailo-semantic/api/search?q=girl` → `{"message":"Search failed","status":"error"}`

**Причина**: возвращаемое `_model.get_text_features()` зависит от версии transformers.
В новых версиях возвращается целый объект вывода модели, и необходимо самостоятельно извлекать `.pooler_output`.

**Исправление**: в `text_encoder.py` явно разнесён процесс на 2 этапа — `text_model()` → `text_projection()`:

```python
# До (сломано)
text_features = _model.get_text_features(**inputs)
vec = text_features.squeeze().numpy()

# После (исправлено)
text_out = _model.text_model(**inputs)
text_features = _model.text_projection(text_out.pooler_output)
vec = text_features.squeeze().numpy()
```

**Производительность**:
- Первый запрос (включая загрузку модели): ~6 секунд
- Второй и далее: ~100-170 ms (только CPU-инференс)
- Поиск по векторам: <1 ms (51 элемент, кэш в памяти)

### 2. Бесконечный цикл ретраев при построении индекса

**Проблема**: файлы с ошибкой декодирования (не-изображения, повреждённые файлы и т. д.) не отслеживались
как `failed_ids`, поэтому `get_unindexed_file_ids()` каждый раз возвращал одни и те же провальные файлы,
и счётчик ошибок перевалил 3 миллиона.

**Исправление**: в `indexer.py` добавлен `failed_ids: set`. Провалившиеся file_id запоминаются и исключаются из следующего пакета.

### 3. Ошибка чтения изображений из архивных файлов

**Проблема**: `cv2.imread('test.7z!image.png')` не понимает путь к элементу внутри архива.

**Исправление**: в `image_preprocess.py` добавлен `is_archive_member()` для распознавания архивного пути;
используется паттерн `read_bytes_from_zip` / `read_bytes_from_7z` + `cv2.imdecode()`.

### 4. Обновление прогресса в реальном времени через SSE

**Проблема**: опрос каждые 2 секунды даёт рваный прогресс — неудобно.

**Исправление**: переход на SSE через `EventSource`. Прогресс в реальном времени через событие `semantic_index.progress`.
При `visibilitychange` (вкладка скрыта) SSE отключается и переподключается при возврате.

---

## Phase 7: Детекция объектов YOLO (2026-03-02)

### Обзор

После CLIP-поиска на том же Hailo-10H реализована детекция объектов YOLO.
Выполняется детекция 80 классов COCO по изображениям и видео, результат сохраняется в таблицу `file_annotations`.

### Проектирование архитектуры

#### Проблема общего VDevice

На Hailo-10H в одном процессе доступен только один VDevice, и InferModel также эксклюзивен.
CLIP и YOLO одновременно не запустить.

**Решение**: новый модуль `core/hailo_device_core/device_manager.py`.
- `acquire_device(owner, hef_path)` — если другой owner удерживает — автоматически освобождает и переключает
- Один и тот же owner с одним и тем же HEF — переиспользуем (избегаем повторной инициализации)
- Потокобезопасно через `threading.Lock`
- CLIP-овский `hailo_inference.py` рефакторим и делегируем в device_manager

#### Обработка выходных тензоров YOLO

У CLIP один выходной тензор, у YOLO — несколько (по одному на головку для каждого stride).
`device_manager` собирает и возвращает quantization parameters для всех выходов.

#### Пайплайн постобработки

Постобработка YOLO включает шаги:
1. uint8 → float32 деквантование (scale/zero_point на каждый выход)
2. Декодирование grid cell → пиксельных координат (sigmoid + grid offset + stride)
3. Фильтрация по confidence
4. NMS покласоно (на чистом numpy)
5. Преобразование letterbox-координат → нормализованные координаты исходного изображения (0-1)

#### Поддержка видео

Извлечение кадров ffmpeg → детекция каждого кадра независимо → агрегация по классам.
Для каждого класса сохраняем максимальное confidence + количество кадров, в которых он встречался.

### Состав новых модулей

| Модуль | Роль |
|---|---|
| `core/hailo_device_core/device_manager.py` | Управление жизненным циклом общего VDevice |
| `core/hailo_yolo_core/hailo_yolo_inference.py` | Синглтон YOLODetector |
| `core/hailo_yolo_core/yolo_postprocess.py` | NMS, декодирование box, деквантование |
| `core/hailo_yolo_core/yolo_labels.py` | 80 меток COCO |
| `core/hailo_yolo_core/yolo_preprocess.py` | Letterbox-ресайз 640x640 |
| `core/hailo_yolo_core/yolo_video.py` | Извлечение кадров из видео + агрегация |
| `core/hailo_yolo_core/yolo_indexer.py` | Фоновая пакетная детекция |
| `core/hailo_yolo_core/model_download.py` | Загрузка HEF |
| `core/hailo_yolo_core/event_handler.py` | Обработчик scan.complete |
| `extensions/builtin_hailo_yolo_detect/` | Extension + Blueprint API + UI |

### Технические заметки

- **Несколько выходных тензоров**: YOLO HEF имеет несколько выходных тензоров (по одному на головку каждого stride).
  Необходимо пройтись по `infer_model.outputs` и собрать shape/quant_params у всех
- **Выходные буферы**: для каждого выходного тензора выделяем отдельный uint8-буфер
  и привязываем по имени через `bindings.output(out.name).set_buffer(buf)`
- **Разметка тензоров**: обычно форма `(1, H, W, C)`. В C хранятся bbox (4) + class scores (80)
- **Загрузка HEF**: напрямую с Hailo Model Zoo v5.2.0. Без установки User-Agent
  Cloudflare блокирует, поэтому задаём `_USER_AGENT`
- **Сохранение результатов детекции**: в таблицу `file_annotations` с `source='hailo:<model>'`, `key='detections'`
  сохраняется JSON-массив. Используются существующие API CRUD для аннотаций

---

## Phase 8: Интеграция GenAI (LLM / VLM / Speech2Text) (2026-03-02)

### Цель

Интегрировать модуль `hailo_platform.genai` (LLM, VLM, Speech2Text) Hailo-10H
в device_manager, сделать генерацию текста, понимание изображений и транскрибацию речи доступными из WebUI.

### Расширение device_manager

- **Проблема**: существующий device_manager поддерживал только InferModel API (CLIP/YOLO).
  Классы GenAI принимают не InferModel, а VDevice напрямую — это другой режим
- **Решение**: переменная `_mode` (`"infer"` | `"genai"`) различает режимы.
  Добавлен `acquire_genai(owner, model_path, genai_factory)`,
  через factory-паттерн создающий экземпляры LLM/VLM/S2T
- **Отличия при освобождении**:
  - InferModel: `del configured` → `del infer_model` → `del vdevice`
  - GenAI: `instance.release()` → `vdevice.release()` (явный метод release)

### Обнаружения в API GenAI

- **Формат сообщений**: OpenAI-совместимая структура role/content. content — массив формата `{"type": "text", "text": "..."}`
- **Ввод для VLM**: numpy массив RGB uint8 336x336. Передаётся списком `frames=[image]`.
  В промпт вставляется плейсхолдер `{"type": "image"}`
- **Ввод для S2T**: little-endian float32 (`<f4`), моно, 16 кГц. Нормализация int16→float32 обязательна
- **Сегменты S2T**: `generate_all_segments()` возвращает список объектов `SegmentInfo`
  с атрибутами `.text`, `.start`, `.end`
- **Управление контекстом**: у LLM/VLM есть `get_context_usage_size()`, `max_context_capacity()`,
  `clear_context()` для управления окном контекста
- **Стриминг**: `generate()` возвращает итератор, токены yield по одному

### URL загрузки HEF моделей

- Шаблон: `https://dev-public.hailo.ai/v{hailort_version}/blob/{ModelName}.hef`
- HailoRT 5.2.0 → `v5.2.0`
- Имя модели в CamelCase (например: `Qwen2.5-1.5B-Instruct.hef`, `Whisper-Base.hef`)
- Подтверждено в `download_resources.py` репозитория `hailo-apps-infra`, тип источника `gen-ai-mz`

### Новые файлы

| Файл | Описание |
|----------|------|
| `core/hailo_genai_core/__init__.py` | init пакета |
| `core/hailo_genai_core/genai_types.py` | enum GenAIModelType + dataclass GenAIModelInfo |
| `core/hailo_genai_core/model_download.py` | Управление загрузкой HEF для 7 моделей |
| `core/hailo_genai_core/llm_inference.py` | Обёртка HailoLLM (singleton, streaming) |
| `core/hailo_genai_core/vlm_inference.py` | Обёртка HailoVLM (singleton, препроцессинг изображений) |
| `core/hailo_genai_core/s2t_inference.py` | Обёртка HailoS2T (singleton, поддержка сегментов) |
| `extensions/builtin_hailo_genai/extension.json` | Манифест расширения |
| `extensions/builtin_hailo_genai/hailo_genai_ext.py` | Blueprint из 8 API (SSE streaming) |
| `extensions/.../templates/hailo_genai/_genai_ui.html` | UI страницы Tools (4 панели) |

### Технические заметки

- **VDevice.create_params()**: в режиме GenAI параметры создаются через `VDevice.create_params()`,
  а VDevice инстанцируется как `VDevice(params)`. Это отличается от режима InferModel, где `VDevice()` без аргументов
- **SSE-стриминг**: через `Response(generator(), mimetype='text/event-stream')` во Flask
  отправляются токены как `data: {"token": "..."}\n\n`. По завершении `data: {"done": true}\n\n`
- **VLM через FormData**: поскольку нужно одновременно отправлять файл изображения и текстовый промпт,
  VLM API принимает не JSON, а `multipart/form-data`
- **Чтение WAV для S2T**: на сервере считывается непосредственно из загруженного байтового потока WAV
  через `wave` + `io.BytesIO`

---

## Phase 9: Связка семантический поиск + VLM-подписи (2026-03-03)

### Цель

Пакетно генерировать подписи к изображениям из результатов CLIP-поиска через VLM (Qwen2-VL)
и сохранять их в `file_annotations`.

### Реализация

- **`core/hailo_clip_core/caption_runner.py`** *(сейчас — `extensions/builtin_hailo_semantic_search/core_impl/caption_runner.py`)* (~150 строк): фоновый поток пакетно запускает VLM-генерацию подписей. Паттерн `_state_lock` + `_stop_requested` + `_progress` из `indexer.py`. SSE-события `vlm_caption.start/progress/complete`
- **Расширение Blueprint**: в `hailo_semantic_search.py` добавлены 3 эндпоинта `/api/caption/start`, `/api/caption/status`, `/api/caption/stop`
- **UI**: в секции Semantic Search на странице Tools добавлена панель «VLM Caption Generation». Ввод промпта, SSE прогресс-бар, автосвязывание file_ids из результатов поиска

### Эксклюзивное управление VDevice

- `acquire_genai("vlm", ...)` — получение VLM. Если работает CLIP-индексер, device_manager автоматически освободит его
- После завершения генерации подписей VLM удерживает устройство; для возобновления CLIP-индекса требуется выгрузить модель

### Соглашение по сохранению аннотаций

- `source="hailo:vlm"`, `key="caption"`, `value=<текст подписи>`

---

## Phase 10: Транскрибация аудио из видео — S2T пайплайн (2026-03-03)

### Цель

Из видеофайла извлечь аудио через ffmpeg → транскрибировать Whisper (S2T) → сохранить в `file_annotations`.

### Реализация

- **`core/files_core/video_audio.py`** (~80 строк): функция `extract_audio_wav()` извлекает моно PCM s16le 16 кГц через ffmpeg. Таймаут вычисляется динамически из длительности видео (максимум 120 секунд). `check_ffmpeg()` переиспользован из `media_video.py`
- **Расширение Blueprint**: в `hailo_genai_ext.py` добавлены 3 эндпоинта:
  - `POST /api/s2t/transcribe-video`: транскрибация одного видео (file_id, language)
  - `POST /api/s2t/batch-transcribe`: пакетная транскрибация нескольких видео (file_ids, language), фоновый поток + SSE-прогресс (`video_s2t.*`)
  - `GET /api/s2t/transcript/<file_id>`: получение сохранённой транскрипции
- **UI**: в панели S2T добавлен подраздел «Video Transcription». Ввод file_id, выбор языка (ja/en), кнопка получения сохранённой записи

### Соглашение по сохранению аннотаций

- `source="hailo:s2t"`, `key="transcript"`, `value=<полный текст>`
- `source="hailo:s2t"`, `key="transcript_segments"`, `value=<JSON [{text, start, end}, ...]>`

### Важные замечания

- Временный WAV создаётся через `tempfile.NamedTemporaryFile`, обязательно удаляется в finally
- S2T и LLM/VLM эксклюзивны на уровне устройства (одновременно не используются)

---

## Phase 11: Улучшение UI многоходовых диалогов LLM (2026-03-03)

### Цель

Расширить одиночный промпт до поддержки истории диалога. Продолжение контекста, сброс, bubble-стиль UI.

### Реализация

- **Изменения API**: `api_llm_generate()` теперь принимает массив `messages`. Обратная совместимость: если только `prompt`, он преобразуется в system + user сообщения как раньше. `generate_stream()` уже поддерживает многоходовые диалоги через `_normalise_prompt()`
- **UI чата в стиле bubble**: `hg-chat-container` + `hg-bubble` (user — справа фиолетовые, AI — слева серые). CSS-классы: `hg-bubble-user`, `hg-bubble-ai`, `hg-bubble-label`
- **Управление историей диалога**: на стороне JS массив `_chatHistory = []` накапливает `{role, content}`. При отправке в API передаётся `messages: [systemMsg, ..._chatHistory]`. `hgLlmClear()` сбрасывает массив + очищает контекст HailoRT
- **Стриминг**: AI-пузырь заранее вставляется в DOM, SSE-токены добавляются постепенно

### Баг-фикс: ошибка system role в многоходовом диалоге (2026-03-03)

Обнаружено через MCP debug-запросы + логи hailort. При втором и последующих вызовах `generate()` возникала ошибка:

```
[HailoRT] [error] CHECK failed - System role messages can only be provided on the first prompt
[HailoRT] [error] CHECK_SUCCESS failed with status=HAILO_INVALID_OPERATION(6)
```

**Причина**: UI-шаблон каждый раз отправлял `[systemMsg].concat(_chatHistory)`, вставляя system role в начало.
LLM API HailoRT не принимает system role при наличии контекста (со 2-го хода и далее).

**Исправление**:
1. В `llm_inference.py` добавлен метод `_prepare_prompt()`: при `get_context_usage_size() > 0` system-сообщение автоматически удаляется
2. UI-шаблон (`_genai_ui.html`): system добавляется только если `_chatHistory.length <= 1` (только первое сообщение пользователя)

**Техническая заметка**: HailoRT допускает обработку system role у `LLM.generate()` только при первом вызове.
Это отличается от поведения OpenAI API, что важно учитывать при реализации многоходовых диалогов.

---

## Тестирование WD-Tagger VLM × Hailo-10H на реальном устройстве (2026-03-03)

### Среда тестирования
- Raspberry Pi 5 + Hailo AI HAT 2 (Hailo-10H)
- HailoRT FW 5.2.0, hailo_platform Python 5.2.0
- hailo-ollama v0.5.1 (собрано из исходников)
- Qwen2-VL-2B-Instruct.hef (3.0 GB)

### Важное открытие: hailo-ollama не поддерживает VLM

В официальной документации hailo-ollama (USAGE.rst) явно указано:
> "The Hailo-Ollama API is currently limited to language models (LLMs) and cannot be used for VLMs."

В таблице MODELS в столбце Inference API для `Qwen2-VL-2B-Instruct` указаны только "C++, Python", без "Hailo-Ollama".

Список моделей, возвращаемый `/hailo/v1/list`:
```
deepseek_r1:1.5b, llama3.2:1b, qwen2.5-coder:1.5b, qwen2.5:1.5b, qwen2:1.5b
```
`qwen2-vl` отсутствует.

### Результаты тестирования hailo-ollama

**Нюанс config**: собранный бинарь использует макрос `NLOHMANN_DEFINE_TYPE_NON_INTRUSIVE`, поэтому в JSON-конфиге обязательно нужен ключ `limits`. В официальном шаблоне его нет, необходимо добавить:
```json
"limits": {"max_in_flight": 4, "max_queue": 10, "retry_after_sec": 1}
```

- **Генерация текста LLM (qwen2.5:1.5b)**: OpenAI + Ollama native — оба OK, 6.5 TPS
- **OpenAI API vision-запрос**: ошибка 500 (`Node is NOT a STRING`)
- **Ollama native API + images**: принимается, но LLM не умеет обрабатывать изображения
- **VlmWdTaggerEngine, fallback**: OpenAI 500 → автопереключение на Ollama native — OK
- **response_format: json_object**: принимается, но JSON-вывод не гарантируется

### Результаты прямого тестирования Hailo Python SDK с VLM

В VLM-сообщениях обязательно должен быть `{"type": "image"}`:
```python
messages = [
    {"role": "user", "content": [
        {"type": "image"},
        {"type": "text", "text": "Tag this image."}
    ]}
]
vlm.generate_all(messages, frames=[frame_336x336_rgb_uint8])
```

- **Загрузка модели**: 33 секунды (первый холодный старт. Разница с заявленными 6,2 секунды вызвана I/O по диску)
- **Скорость инференса**: ~5,1 TPS (128 токенов / 20 секунд). Разница с заявленными 6,73 TPS — из-за учёта TTFT
- **Качество распознавания изображения**: корректно понимает содержимое (точно описывает «две женщины держатся за руки в снежном пейзаже»)
- **Качество JSON-вывода**: низкое. У 2B-модели нестабильная точность генерации структурированного JSON (отсутствуют запятые, просачиваются code fence от markdown)

### Обнаруженные баги

1. **Формат промпта в `engines_hailo_vlm.py`**: VLM передавались только текстовые сообщения → исправлено на список с `{"type": "image"}`
2. **Аргумент frames в `vlm_inference.py`**: у VLM `generate_all()` frames обязателен, а был объявлен Optional → исправлено на обязательный

### Технические заметки

- **Эксклюзивность VDevice**: пока работает hailo-ollama, получить `hailo_platform.VDevice()` невозможно. Для прямого инференса VLM нужно останавливать hailo-ollama
- **VLM.generate_all() требует frames**: инференс только текста вызывает ошибку `HAILO_INVALID_OPERATION`. У LLM и VLM разные предусловия API
- **Prompt template для Qwen2-VL**: в Jinja2-шаблоне вставляются `<|vision_start|><|image_pad|><|vision_end|>`. Если в сообщениях указан `{"type": "image"}`, SDK обрабатывает это автоматически

---

## Phase 12: OpenAI-совместимый API + баг-фикс переключения устройства (2026-03-14)

### Цели

1. Реализовать OpenAI-совместимый API, чтобы внешние инструменты (OpenAI SDK / LiteLLM / Continue.dev / Open WebUI и др.) могли напрямую работать с Hailo GenAI
2. Исправить огрехи async-поддержки в Quart
3. Поддержка SSE-эндпоинтов в MCP-инструментах

### Реализация: OpenAI-совместимый API (`hailo_openai_routes.py`)

Создан новый файл `extensions/builtin_hailo_genai/hailo_openai_routes.py`. Реализованы 4 эндпоинта:

| Эндпоинт | Функция | Поддерживаемые модели |
|---|---|---|
| `GET /v1/models` | Список доступных моделей | Все модели + CLIP |
| `POST /v1/chat/completions` | Текст/изображение чат (поддержка stream) | LLM + VLM |
| `POST /v1/audio/transcriptions` | Транскрибация аудио | Whisper |
| `POST /v1/embeddings` | Текст → вектор CLIP | CLIP ViT-B/16 |

#### Проектные решения

- **Поддержка Vision**: принимаются данные в формате OpenAI Vision API (`image_url` с `data:` base64) как есть. Дополнительно в `image_url` можно указать формат `file_id:123` и напрямую ссылаться на изображение из библиотеки YU
- **Запрет HTTP URL**: для защиты от SSRF `image_url` не принимает `http://` / `https://`
- **Алиасы моделей**: определены OpenAI-совместимые алиасы: `whisper-1` → `whisper-base`, `clip` → `clip-vit-b-16` и т. д.
- **Аудио не в WAV**: автоматическое преобразование через ffmpeg (16 кГц моно PCM16)
- **Поле Usage**: Hailo SDK не возвращает число токенов, поэтому возвращается `0` константой. Есть место для улучшения в будущем

#### MCP-инструмент

- `hailo_genai_openai_info`: вспомогательный инструмент, возвращающий список эндпоинтов и инструкции использования (без вызова API, генерация локально)

### Исправление: async SSE-генераторы Quart

Во всех файлах маршрутов SSE-генераторы имели огрехи async-поддержки:

| Файл | Проблема | Исправление |
|---|---|---|
| `hailo_llm_routes.py` | `def generate_sse()` был синхронным | Сделан `async def`, `get_llm()` и `next(it)` обёрнуты в `asyncio.to_thread` |
| `hailo_vlm_routes.py` | То же + обращения к БД синхронные | То же + обёртка в `run_db_sync` |
| `hailo_s2t_routes.py` | Синхронная транскрибация + синхронные обращения к БД | `asyncio.to_thread` + обёртка `run_db_sync` |
| `hailo_chat_routes.py` | То же (и LLM, и VLM) | Все блокирующие вызовы async-изированы |

В Quart (ASGI) если генератор не `async def`, он блокирует event loop, и во время отдачи SSE другие запросы не обрабатываются.

### Обнаруженный баг: несоответствие синглтонов при переключении устройств

#### Симптом

После использования VLM вызов LLM приводит к ошибке `'NoneType' object has no attribute 'get_context_usage_size'`. Обратная последовательность (LLM→VLM→LLM) также всегда даёт ошибку.

#### Анализ причин

Hailo-10H удерживает только один VDevice, поэтому `device_manager.py` управляет эксклюзивно. Поток переключения моделей:

1. VLM `get_vlm()` → `acquire_genai("vlm", ...)` → внутри `_release_internal()` освобождает VDevice у LLM
2. Работа с VLM завершена
3. LLM `get_llm()` → `_instance` остался + `model_name` совпадает → **переиспользуется существующий экземпляр**
4. VDevice за `_instance._llm` уже освобождён → `get_context_usage_size()` вызывается на `None` и падает

Корень проблемы: даже если синглтон `_instance` остался, его внутренний объект Hailo SDK (`self._llm`) указывает на VDevice, уже освобождённый через `_release_internal()` из `device_manager`. В Python reference count `_instance._llm` ещё жив, но нативные ресурсы Hailo SDK освобождены.

#### Исправление

В проверках переиспользования синглтона `get_llm()` / `get_vlm()` / `get_s2t()` добавлена проверка `device_manager.get_current_owner()`:

```python
def get_llm(model_name="qwen2.5-1.5b-chat"):
    global _instance
    with _lock:
        if _instance is not None and _instance.model_name == model_name:
            from core.hailo_device_core.device_manager import get_current_owner
            if get_current_owner() == "llm":
                return _instance  # Удерживает устройство → переиспользование OK
            # Устройство уже перехвачено другой моделью → пересоздать
            _instance = None
        ...
```

Одинаковая правка применена ко всем трём синглтонам: LLM / VLM / S2T.

#### Проверка

Четырёхкратное последовательное переключение LLM → VLM → LLM → VLM — всё работает корректно.

### Прочие исправления

- **Метод MCP `post_sse`**: в `mcp_server/client.py` добавлен метод `post_sse()`, который потребляет SSE-стрим и возвращает итоговый текст в JSON. Используется инструментами `hailo_llm_generate` и `hailo_vlm_generate`
- **Параметр MCP `yolo_search`**: `labels` → переименован в `class_name` (для совпадения с именем на стороне API)
- **Circuit Breaker**: добавлены `_READ_SUFFIXES` (`_status`, `_info`, `_list`, `_stats`). Теперь в состоянии half_open разрешаются инструменты статусного типа вроде `hailo_genai_status`
- **Async для Semantic Search**: `get_encoder_info()` и `semantic_search()` обёрнуты в `run_db_sync` (чтобы не блокировать event loop Quart)

### Технические заметки

- **Эксклюзивность VDevice — на уровне SDK**: даже если на стороне Python есть ссылка на объект, при освобождении нативных ресурсов на стороне Hailo SDK объект становится непригодным. При использовании паттерна синглтон необходимо отдельно проверять валидность нативных ресурсов
- **Quart + синхронный генератор**: если в SSE-ответ Quart передать синхронный генератор, он будет работать, но обработка между `yield` блокирует event loop. Тяжёлые вычисления вроде Hailo-инференса необходимо обязательно выносить в отдельный поток через `asyncio.to_thread`
- **Связь OpenAI Vision API и VLM**: OpenAI Vision API принимает изображения в поле `image_url`, а Hailo VLM принимает `frames` (numpy array). В слое преобразования выполняется base64-декодирование → декодирование OpenCV → ресайз в 336x336 RGB
