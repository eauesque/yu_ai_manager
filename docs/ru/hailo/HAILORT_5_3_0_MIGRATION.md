# Заметки по миграции HailoRT 5.2.0 → 5.3.0

Опыт обновления с HailoRT 5.2.0 до 5.3.0 на Raspberry Pi 5 + AI HAT 2 (Hailo-10H).
Основано на сквозных имплементационных тестах и прямом анализе git diff тегов `v5.2.0` / `v5.3.0`.

**Целевая аудитория**: Разработчики, выполняющие инференс на Hailo-10H NPU с использованием Python (`pyhailort`).

---

## TL;DR

- **Фактически никаких критических изменений в типичных Python-приложениях для инференса**.
  Заголовочные цифры (688 изменённых файлов, +12,035 / −8,987 строк) велики, но
  поверхность `VDevice`, `InferModel`, GenAI (`LLM` / `VLM` / `Speech2Text`) полностью
  обратно совместима.
- Большая часть изменений — **удаление API управления камерой/ISP/прошивкой Hailo-8**
  и внутренний рефакторинг. На чистый NPU-инференс не влияет.
- **Файлы `.hef` эпохи v5.2.0 загружаются без изменений в среде выполнения 5.3.0.**
  Проверено на 5 моделях (YOLOv8n, CLIP ViT-B/16, Qwen2.5-1.5B, Qwen2-VL-2B, Whisper-Base).
- Драйвер Linux изменился с `hailo_pci` на `hailo1x_pci`, узел устройства — с
  `/dev/hailort0` на **`/dev/h1x-0`**. `pyhailort` разрешает новый узел внутренне,
  поэтому Python-код с `VDevice()` работает без изменений.
  **Обновление нужно только для проброса устройств Docker.**
- `Speech2Text.SegmentInfo` предоставляет атрибуты `text` / `start_sec` / `end_sec`
  (так же, как в v5.2.0). `start` или `start_time` не публичны.

---

## 1. Область изменений

Прямой diff тегов `v5.2.0` и `v5.3.0` в официальном репозитории HailoRT на GitHub:

| Область | Файлов | Добавлено | Удалено |
|---------|-------:|----------:|--------:|
| Всего | 688 | +12,035 | −8,987 |
| Публичные заголовки C++ (`include/hailo/`) | 27 | +205 | **−383** |
| Python-биндинги (`bindings/python/`) | 35 | +306 | **−413** |
| Только `pyhailort.py` | 1 | +98 | **−158** |

**Удалений больше, чем добавлений** — это релиз «упрощения».
Большинство удалённого не связано с пайплайном NPU-инференса.

---

## 2. Удалённые API — только для камеры/ISP/прошивки Hailo-8

`hailort/libhailort/include/hailo/device.hpp` потерял 169 строк, `platform.h` — 75.
Всё удалённое — низкоуровневое управление устройством:

- `firmware_update()` / `second_stage_update()` (перепрошивка)
- `store_sensor_config()` / `store_isp_config()`
- `sensor_dump_config()` / `sensor_reset()`
- `sensor_load_and_start_config()`
- `sensor_set_i2c_bus_index()` / `sensor_set_generic_i2c_slave()`
- `sensor_get_sections_info()`
- `examine_user_config()` / `read_user_config()` / `write_user_config()` / `erase_user_config()`

Всё это — API для **Hailo-8 AI Vision Camera Module** (SoC-платы, где чип Hailo
управляет ISP и датчиком изображения напрямую).
В типичном потоке `VDevice` → `InferModel` → `generate` на чистом Hailo-10H NPU
не вызываются.

**Влияние**: Нулевое для приложений чистого NPU-инференса.

---

## 3. Изменения сигнатур Python

| API | v5.2.0 | v5.3.0 | Совместимость |
|-----|--------|--------|--------------|
| `Speech2Text.generate_all_segments(timeout_ms=)` | По умолч. `10000` | По умолч. `600000` | ✅ Только значение по умолчанию, существующие вызовы не изменились |
| `Speech2Text.generate_all_text(timeout_ms=)` | То же | То же | ✅ То же |
| `LLM.read_all(timeout_ms=10000)` | Есть по умолч. | По умолч. **удалено** (обязателен) | ⚠️ `read_all()` без аргументов → `TypeError` |
| `DeviceArchitecture.__init__` | 9 позиционных аргументов | +`chip_serial_number` (10) | ⚠️ Прямое создание нарушает |

**Исправление `read_all()` — одна строка**:

```python
# До (стиль v5.2.0, таймаут 10 секунд по умолчанию)
text = generator.read_all()

# После (v5.3.0 требует явный таймаут)
text = generator.read_all(timeout_ms=600000)  # 10 минут
```

`DeviceArchitecture` редко создаётся напрямую в пользовательском коде, поэтому
изменение сигнатуры почти ни на что не влияет.

---

## 4. Изменения имён в заголовках C++ (прозрачные для Python)

Критичны для приложений, использующих HailoRT напрямую через C++:

- **`Speech2Text::DEFAULT_OPERATION_TIMEOUT`** (10 сек) →
  **`DEFAULT_GENERATE_ALL_TIMEOUT`** (10 мин), переименование и увеличение
- Добавлен **`LLM::DEFAULT_READ_ALL_TIMEOUT`**, тоже 10 минут
- В `vlm.hpp` добавлены 4 перегрузки `generate_from_embeddings()`

Эти переименования не распространяются через Python-биндинги.

---

## 5. Исправление координат ограничивающих рамок NMS (изменение поведения)

Исправление логики постобработки NMS в `pyhailort.py`:

```python
# v5.2.0
y_min = numpy.ceil(bbox[0] * image_height)
x_min = numpy.ceil(bbox[1] * image_width)
bbox_width = numpy.ceil((bbox[3] - bbox[1]) * image_width)

# v5.3.0
y_min = int(max(numpy.floor(bbox[0] * image_height), 0))
x_min = int(max(numpy.floor(bbox[1] * image_width), 0))
x_max = int(min(numpy.ceil(bbox[3] * image_width), image_width))
bbox_width = x_max - x_min
```

Улучшения:
- Добавлено ограничение по границам изображения `max(0, …)` / `min(image_width, …)`
- `ceil` → `floor` (предотвращение перелёта)
- `bbox_width` пересчитывается из ограниченного `x_max - x_min`

**Разница в поведении**: На тех же модели и изображении выходные данные NMS могут
смещаться на ±1 пиксель в районе границ. Приложения, использующие хелперы
`_output_raw_buffer_to_nms_with_byte_mask_*` из pyhailort, могут получить изменение
формы ограничивающих рамок у краёв изображения.

---

## 6. Новые API (аддитивные)

- **`VDevice::create_session(uint16_t port)`** — новый API сессии инференса по сети
- **`VLM::generate_from_embeddings()`** — 4 перегрузки, принимающие предвычисленные
  эмбеддинги изображений/видео. Позволяет вычислить эмбеддинги один раз и
  использовать повторно в нескольких вызовах VLM
- **`InferModel::set_nms_classes_filter_mask(vector<bool>)`** — фильтрация по классам
  для вывода NMS (на чипе)
- **`Device::query_performance_stats(sampling_period_ms)`** — настраиваемый период выборки
- **`Device::get_current_limit()`** — запрос ограничения тока
- **`DeviceArchitecture.chip_serial_number`** — чтение серийного номера чипа

Все аддитивные — существующий код не нарушают.

---

## 7. Изменения окружения

### 7.1 Новый драйвер Linux PCI

| Параметр | Старый | Новый |
|----------|--------|-------|
| Модуль ядра | `hailo_pci` | `hailo1x_pci` |
| Узел устройства | `/dev/hailort0` (или `/dev/hailo0`) | `/dev/h1x-0` |

```bash
lsmod | grep hailo        # → hailo1x_pci
ls /dev/h1x-*             # → /dev/h1x-0
```

**`pyhailort` разрешает новый узел устройства внутренне**, поэтому Python-код
с `VDevice()` продолжает работать без изменений.
Обновление нужно только коду, который напрямую открывает `/dev/hailo*` или `/dev/hailort0`.

#### Проброс устройств Docker / Podman

Обновите объявления проброса устройств:

```yaml
# docker-compose.yml
services:
  my-app:
    devices:
      - /dev/h1x-0:/dev/h1x-0   # было: /dev/hailort0:/dev/hailort0
```

Также обновите строки `DeviceAllow=` в systemd-юнитах и правила udev.

### 7.2 Смягчение ограничений numpy

- v5.2.0 `setup.py`: `numpy<2` (фиксированно)
- v5.3.0 `setup.py`: `numpy` (без верхней границы)

Приложения, ранее зафиксированные на numpy 1.x из-за ограничения `numpy<2` в HailoRT,
теперь могут обновиться до numpy 2.x вместе с апгрейдом HailoRT.

### 7.3 Бинарная совместимость HEF

**Файлы `.hef`, загруженные из бакета v5.2.0, загружаются и выполняются без изменений
в среде выполнения 5.3.0.** Проверено на 5 моделях (Raspberry Pi 5 + AI HAT 2):

| Модель | Файл | Результат |
|--------|------|-----------|
| YOLOv8n | `yolov8n.hef` | ✅ `create_infer_model()` + `.run()` |
| CLIP ViT-B/16 энкодер изображений | `clip_vit_b_16_image_encoder.hef` | ✅ Вывод 512 измерений |
| Qwen2.5-1.5B Instruct | `Qwen2.5-1.5B-Instruct.hef` | ✅ `LLM.generate_all()` возвращает корректный текст |
| Qwen2-VL-2B Instruct | `Qwen2-VL-2B-Instruct.hef` | ✅ `VLM.generate_all(frames=[…])` работает |
| Whisper-Base | `Whisper-Base.hef` | ✅ `Speech2Text.generate_all_segments()` возвращает `SegmentInfo` |

### 7.4 URL бакета для загрузки HEF

Hailo Developer Zone (`dev-public.hailo.ai`) хостит бакеты v5.2.0 и v5.3.0 параллельно:

```
https://dev-public.hailo.ai/v5.2.0/blob/<model>.hef
https://dev-public.hailo.ai/v5.3.0/blob/<model>.hef
```

Состояние бакета v5.3.0 по состоянию на 2026-04-06:

| Модель | Бакет v5.3.0 |
|--------|-------------|
| Qwen2.5-1.5B-Instruct | ✅ 200 |
| DeepSeek-R1-Distill-Qwen-1.5B | ✅ 200 |
| Qwen2.5-Coder-1.5B-Instruct | ✅ 200 |
| Qwen2-VL-2B-Instruct | ✅ 200 |
| Whisper-Base / Whisper-Small | ✅ 200 |
| **Llama-3.2-1B-Instruct** | ❌ **404** |

→ Приложения, которым нужна Llama-3.2-1B, пока должны брать её из бакета v5.2.0.
HEF из v5.2.0 корректно загружается в среде выполнения 5.3.0.

---

## 8. Имена атрибутов `Speech2Text.SegmentInfo`

В v5.2.0 и v5.3.0 `Speech2Text.generate_all_segments()` возвращает объекты `SegmentInfo`
со следующими публичными атрибутами:

```python
seg.text        # str
seg.start_sec   # float (секунды)
seg.end_sec     # float (секунды)
```

**`seg.start` и `seg.start_time` не существуют.** Проверить реальные имена атрибутов:

```python
from hailo_platform import VDevice
from hailo_platform.genai import Speech2Text, Speech2TextTask
import numpy as np

vd = VDevice()
s2t = Speech2Text(vd, "/path/to/Whisper-Base.hef")
audio = (np.random.default_rng(0).standard_normal(32000) * 0.01).astype("<f4")
segments = s2t.generate_all_segments(
    audio_data=audio, task=Speech2TextTask.TRANSCRIBE,
    language="en", timeout_ms=30000,
)
if segments:
    print([a for a in dir(segments[0]) if not a.startswith("_")])
    # => ['end_sec', 'start_sec', 'text']
```

---

## 9. Скрипт smoke-теста

Минимальный скрипт для проверки работоспособности окружения после обновления до 5.3.0:

```python
"""HailoRT 5.3.0 smoke test — VDevice / InferModel / LLM / Speech2Text."""
import numpy as np
from hailo_platform import VDevice

# 1. Создать VDevice
params = VDevice.create_params()
params.group_id = "SMOKE_TEST"
vd = VDevice(params)
print("1. VDevice OK")

# 2. Путь InferModel (YOLOv8n или любой существующий HEF)
im = vd.create_infer_model("/path/to/yolov8n.hef")
conf = im.configure()
inp = im.inputs[0]
bindings = conf.create_bindings()
bindings.input().set_buffer(np.zeros(tuple(inp.shape), dtype=np.uint8))
for o in im.outputs:
    fmt = str(getattr(o.format, "type", "")).lower()
    dtype = np.float32 if "float" in fmt else np.uint8
    bindings.output(o.name).set_buffer(np.zeros(tuple(o.shape), dtype=dtype))
conf.run([bindings], timeout=10000)
print("2. InferModel (YOLO) OK")
del conf, im

vd.release()
del vd

# 3. Путь GenAI LLM
from hailo_platform.genai import LLM
params = VDevice.create_params(); params.group_id = "SMOKE_TEST"
vd = VDevice(params)
llm = LLM(vd, "/path/to/Qwen2.5-1.5B-Instruct.hef")
text = llm.generate_all(
    prompt=[{"role": "user", "content": "Say hi in one word."}],
    temperature=0.1, max_generated_tokens=16,
)
print(f"3. LLM OK: {text!r}")
llm.release(); vd.release()

# 4. Путь Speech2Text
from hailo_platform.genai import Speech2Text, Speech2TextTask
params = VDevice.create_params(); params.group_id = "SMOKE_TEST"
vd = VDevice(params)
s2t = Speech2Text(vd, "/path/to/Whisper-Base.hef")
audio = (np.random.default_rng(0).standard_normal(32000) * 0.01).astype("<f4")
segments = s2t.generate_all_segments(
    audio_data=audio, task=Speech2TextTask.TRANSCRIBE,
    language="en", timeout_ms=30000,
)
print(f"4. Speech2Text OK: {len(segments)} segments")
if segments:
    seg = segments[0]
    print(f"   attrs: text={seg.text!r} start_sec={seg.start_sec} end_sec={seg.end_sec}")
s2t.release(); vd.release()

print("\nAll smoke tests passed.")
```

---

## 10. Чеклист обновления

Что проверить в коде перед или во время обновления с 5.2.0 на 5.3.0:

- [ ] `VDevice()` / `create_infer_model()` / `InferModel.configure()` — **без изменений**
- [ ] Конструкторы `LLM(vd, path)` / `VLM(vd, path)` / `Speech2Text(vd, path)` — **без изменений**
- [ ] Ключевые аргументы `LLM.generate()` / `.generate_all()` / `VLM.generate(frames=…)` — **без изменений**
- [ ] `Speech2Text.generate_all_segments(audio_data=, task=, language=, timeout_ms=)` — **без изменений** (при явной передаче `timeout_ms`)
- [ ] Проверить вызовы `LLM.read_all()` без `timeout_ms` → добавить явный таймаут
- [ ] Проверить прямое создание `DeviceArchitecture` → добавить `chip_serial_number`
- [ ] Поиском найти прямое открытие `/dev/hailo*` или `/dev/hailort0` → заменить на `/dev/h1x-0`
- [ ] Обновить секцию `devices:` в Docker / Podman на `/dev/h1x-0`
- [ ] Обновить строки `DeviceAllow=` в systemd-юнитах и правила udev
- [ ] Поиском найти обращение к атрибутам `SegmentInfo` через `.start` или `.start_time` → заменить на `.start_sec` / `.end_sec`
- [ ] Если numpy зафиксирован на 1.x (из-за `numpy<2` в v5.2.0) — теперь можно снять ограничение
- [ ] Повторно скачивать существующие файлы `.hef` **не нужно**
- [ ] Если URL загрузки HEF содержит хардкод бакета `v5.2.0` — обновить до `v5.3.0` (сохранить `v5.2.0` для Llama-3.2-1B)
- [ ] При зависимости от встроенной постобработки NMS в pyhailort — учесть возможный сдвиг координат ограничивающих рамок на ±1 пиксель у границ изображения

---

## 11. Заключение

«688 изменённых файлов» — сильно преувеличено относительно реального влияния.
Для типичного NPU-инференс приложения на Hailo-10H:

- **Ядро NPU-инференса API (`VDevice` / `InferModel` / GenAI) полностью обратно совместимо**
- Все удалённые API — это поверхность управления камерами/датчиками/ISP/прошивкой Hailo-8
- **Все существующие файлы `.hef` загружаются без повторной загрузки**
- Единственное обязательное изменение на уровне окружения — обновить проброс устройств Docker на `/dev/h1x-0`

Основные улучшения качества жизни после обновления:
- Таймауты по умолчанию значительно увеличены (10 сек → 10 мин)
- Доступен `FormatType.FLOAT32` (в v5.2.0 требовалось ручное квантование/деквантование)
- Исправлен баг обрезки координат NMS
- Открыт путь обновления до numpy 2.x
- `VLM.generate_from_embeddings()` позволяет повторно использовать предвычисленные эмбеддинги
