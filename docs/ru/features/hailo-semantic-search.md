# Расширение Hailo семантический поиск — спецификация реализации

**Статус**: Реализовано — версия, специфичная для Hailo, была вытеснена CLIP ONNX (v2.95.0)
**Цель**: Расширение YU AI Manager
**Назначение**: Семантический поиск изображений с использованием CLIP/SigLIP на Hailo-10H (AI HAT 2)
**Реализация**: `extensions/builtin_clip_search/core_impl/` (общий слой) + `extensions/builtin_clip_onnx/core_impl/` (реализация ONNX)
**Примечание**: Эта спецификация описывает исходный дизайн, специфичный для Hailo. Текущая реализация использует унифицированную архитектуру ONNX с несколькими backend

---

## Обзор

Это расширение добавляет возможность поиска изображений с использованием текста на естественном языке.
Примеры: "голубое небо и океан", "девушка улыбается", "ночной город" — все возвращают визуально похожие изображения.

Оно требует работать **параллельно** с существующим поиском по тегам FTS5 и поиском по сходству pHash.
Расширение просто отключает себя в окружениях, где нет устройства Hailo.

---

## Архитектура

```
[Во время сканирования изображения]
Файл изображения -> CLIP Image Encoder (Hailo HEF) -> вектор 512-dim -> хранение БД

[Во время поиска]
Текстовый ввод -> CLIP Text Encoder (CPU / Hailo HEF) -> вектор 512-dim
           -> Поиск по косинусному сходству -> список file_id -> Слияние с существующими результатами поиска
```

**Поддерживаются как CLIP, так и SigLIP**, переключаемые через конфигурацию.
SigLIP предлагает более высокую точность, но CLIP имеет более сильный послужной список и больше ресурсов сообщества.
Рекомендуемый подход — начать с CLIP и позже добавить SigLIP.

---

## Разбор по фазам

### Фаза 1: Проверка осуществимости (сделайте это в первую очередь)

После перемещения в окружение Pi5, попросите Claude Code выполнить следующие шаги **в порядке сверху вниз**.
Остановитесь на любом шаге, который не удаётся, и решите проблему перед продолжением.

#### Шаг 1-1: Проверьте HailoRT Runtime

```bash
# Проверка распознавания устройства
hailortcli fw-control identify

# Проверка Python bindings
python3 -c "import hailo_platform; print('HailoRT version:', hailo_platform.__version__)"
```

- **Устройство не видно**: Проверьте статус драйвера с `dmesg | grep hailo`. Проверьте подключение PCIe AI HAT 2
- **Импорт не удаётся**: Установите через `pip install hailort` или из хранилища Hailo APT (`python3-hailort`)

#### Шаг 1-2: Загрузите файлы CLIP HEF

```bash
mkdir -p ~/hailo_models && cd ~/hailo_models

# Encoder изображения
wget https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/clip_vit_b_16_image_encoder.hef

# Text encoder
wget https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/clip_vit_b_16_text_encoder.hef
```

- **403 / Доступ запрещён**: Требуется регистрация на Hailo Developer Zone (https://hailo.ai/developer-zone/).
  После регистрации попробуйте загружать через Model Zoo CLI (`hailo_model_zoo`)
- **Проверка размера**: Каждый файл должен быть десятки-~100 MB. Необычно маленький файл указывает на ошибку загрузки

#### Шаг 1-3: Установите зависимости Python

```bash
# Требуется для предварительной обработки изображения (используется в фазе 1)
pip install opencv-python-headless numpy

# Проверка
python3 -c "import cv2; import numpy; print('cv2:', cv2.__version__, 'numpy:', numpy.__version__)"
```

#### Шаг 1-4: Минимальный тест умозаключения

```python
from hailo_platform import HEF, VDevice, HailoStreamInterface, InferVStreams, ConfigureParams
import numpy as np

hef_path = "/home/<user>/hailo_models/clip_vit_b_16_image_encoder.hef"
hef = HEF(hef_path)

# Проверьте информацию слоя ввода/вывода HEF (имена слоёв варьируются в зависимости от модели)
print("Input layers:", [l.name for l in hef.get_input_vstream_infos()])
print("Output layers:", [l.name for l in hef.get_output_vstream_infos()])

with VDevice() as target:
    configure_params = ConfigureParams.create_from_hef(hef, interface=HailoStreamInterface.PCIe)
    network_groups = target.configure(hef, configure_params)
    network_group = network_groups[0]

    input_info = hef.get_input_vstream_infos()[0]
    input_name = input_info.name
    input_shape = input_info.shape  # Ожидается: (224, 224, 3) и т.д.
    print(f"Input: name={input_name}, shape={input_shape}")

    # Тест умозаключения с фиктивным изображением
    dummy = np.random.randint(0, 255, (1, *input_shape), dtype=np.uint8)
    with InferVStreams(network_group, {}) as pipeline:
        result = pipeline.infer({input_name: dummy})
        for name, data in result.items():
            print(f"Output: name={name}, shape={data.shape}, dtype={data.dtype}")
            # Успех если выходной вектор 512-dim
```

- **Ошибка VDevice (`not enough free devices`)**: hailo-ollama может работать. Остановите его с `systemctl stop hailo-ollama` и повторите попытку
- **Умозаключение успешно, но выходные размеры отличаются**: Проверьте версию HEF и вариант модели

#### Шаг 1-5: Критерии решения

| Результат | Следующее действие |
|------|----------------|
| Вывод вектора 512-dim | Перейдите к фазе 2 и далее |
| HEF загружается успешно, но выходные размеры отличаются | Попробуйте другой вариант модели (clip_resnet_50 и т.д.) |
| Невозможно загрузить HEF | Зарегистрируйтесь на Developer Zone -> загружайте через Model Zoo CLI |
| Невозможно импортировать hailo_platform | Переустановите HailoRT. Вернитесь к CPU CLIP если не разрешено |
| Устройство не распознано | Проблема подключения оборудования / драйвера. Приостановите разработку этого расширения |

Продолжайте полную реализацию если фаза 1 успешна. Рассмотрите CPU CLIP как альтернативу если нет.

---

### Фаза 2: Расширение схемы БД

Добавьте к существующей миграции БД:

```sql
-- миграция 14: семантические векторы поиска
CREATE TABLE IF NOT EXISTS file_vectors (
    file_id     INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
    model       TEXT NOT NULL DEFAULT 'clip',   -- 'clip' | 'siglip'
    vector      BLOB NOT NULL,                  -- float32 numpy массив -> байты
    created_at  INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);

CREATE INDEX IF NOT EXISTS idx_file_vectors_model ON file_vectors(model);
```

Хранение: `numpy.ndarray.tobytes()` -> BLOB
Загрузка: `numpy.frombuffer(blob, dtype=numpy.float32)`

**Примечание**: SQLite не имеет ANN (Approximate Nearest Neighbor) индекс, поэтому все 200,000 записей требуют полного вычисления косинусного сходства. Пакетное вычисление с numpy должно остаться в приемлемых пределах на Pi5 (измерение требуется). Рассмотрите расширение `sqlite-vec` если количество записей растёт значительно.

---

### Фаза 3: Ядро Hailo умозаключения

**Структура файла**:
```
extensions/hailo_semantic_search/
├── __init__.py
├── extension.py          # Точка входа расширения
├── core/
│   ├── hailo_clip.py     # Обёртка умозаключения Hailo CLIP
│   ├── cpu_clip.py       # Резервный вариант CPU для окружений не-Hailo (опционально)
│   └── vector_store.py   # DB CRUD для векторов
├── routes/
│   └── semantic_search.py  # API конечные точки
└── templates/
    └── _semantic_search_ui.html
```

**Обязанности `hailo_clip.py`**:
- Загрузка HEF и инициализация VDevice (синглтон, один раз при запуске)
- Изображение -> предварительная обработка (изменение размера 224x224, нормализация) -> HEF умозаключение -> вектор 512-dim
- Текст -> токенизация -> HEF умозаключение -> вектор 512-dim
  * Используйте текстовый encoder HEF если доступен для Hailo-10H; иначе используйте CPU (библиотека transformers)

**Предварительная обработка**:
```python
import cv2
import numpy as np

def preprocess_image(path: str) -> np.ndarray:
    img = cv2.imread(path)
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    img = cv2.resize(img, (224, 224))
    img = img.astype(np.float32) / 255.0
    mean = np.array([0.48145466, 0.4578275, 0.40821073])
    std  = np.array([0.26862954, 0.26130258, 0.27577711])
    img = (img - mean) / std
    return img[np.newaxis, ...]  # (1, 224, 224, 3)
```

---

### Фаза 4: API для построения индекса

**Конечная точка**:
```
POST /api/extensions/hailo-semantic/index
```
- Обрабатывает неиндексированные изображения последовательно в фоновом потоке
- Отправляет прогресс через SSE в виде событий `semantic_index.progress`
- Опционально подключитесь к существующему событию `scan.complete` для автоматического выполнения

**Размер пакета**: 32 изображения за пакет (балансировка памяти и скорости)

```
GET /api/extensions/hailo-semantic/index/status
-> { "total": 200000, "indexed": 12500, "running": true }
```

---

### Фаза 5: API семантического поиска

```
GET /api/extensions/hailo-semantic/search?q=blue sky&limit=50&threshold=0.25
```

**Поток обработки**:
1. Конвертировать текст `q` в вектор
2. Загрузить все векторы из `file_vectors` (numpy)
3. Вычислить косинусное сходство в пакете
4. Сортировать результаты выше `threshold` по убывающему сходству
5. Возвращать список `file_id` в существующем формате `/api/search`

**Вычисление косинусного сходства**:
```python
def cosine_similarity_batch(query_vec: np.ndarray, stored_vecs: np.ndarray) -> np.ndarray:
    # query_vec: (512,), stored_vecs: (N, 512)
    query_norm = query_vec / np.linalg.norm(query_vec)
    stored_norm = stored_vecs / np.linalg.norm(stored_vecs, axis=1, keepdims=True)
    return stored_norm @ query_norm  # (N,)
```

**Целевая производительность**: Менее 1 секунды для 200,000 записей (достижимо с пакетным вычислением numpy, даже на Pi5)

---

### Фаза 6: Интеграция UI

Добавьте вкладку "Семантический поиск" в существующий UI поиска.
Это может быть автономный UI независимый от существующего конструктора условий (интеграция для будущего).

```html
<!-- Добавьте кнопку переключения рядом со строкой поиска -->
<button id="semantic-search-toggle" class="btn-secondary">
  🔍 Semantic Search (Hailo)
</button>
```

- Скройте или сделайте серой кнопку когда устройство Hailo не обнаружено
- Переиспользуйте существующую сетку для результатов поиска
- Показывайте подсказку для построения индекса когда индекс не существует

---

## Конфигурация (дополнение config.json)

```json
{
  "hailo_semantic_search": {
    "enabled": true,
    "model": "clip",           // "clip" | "siglip"
    "device": "auto",          // "auto" | "hailo" | "cpu"
    "batch_size": 32,
    "similarity_threshold": 0.25,
    "auto_index_on_scan": false,
    "hef_dir": "~/.local/share/hailo-ollama/models"
  }
}
```

---

## Подтверждённые факты (по состоянию на 2026-02-27)

Следующая информация была подтверждена через предыдущие исследования. Используйте её как справку во время выполнения фазы 1.

### Доступность HEF CLIP

Hailo Model Zoo v5.2.0 содержит **как encoder изображения, так и text encoder** HEFs для Hailo-10H для вариантов CLIP/SigLIP:

| Модель | Image Encoder HEF | Text Encoder HEF |
|--------|-------------------|-------------------|
| clip_vit_b_16 | Доступно | Доступно |
| clip_vit_b_32 | Доступно | Доступно |
| clip_vit_l_14 | Доступно | Доступно |
| clip_resnet_50 | Доступно | Доступно |
| siglip_b_16 | Доступно | Доступно |
| siglip_l_16_256 | Доступно | Доступно |
| siglip2_b_32_256 | Доступно | Доступно |
| TinyCLIP варианты | Доступно | Доступно |

Паттерн URL S3: `https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/<model>.hef`

### Статус Text Encoder

- Официальное приложение `hailo-CLIP` запускает **text encoder на CPU (PyTorch)**
- Text Encoder HEFs для Hailo-10H существуют в Model Zoo, но **опубликованное приложение их не использует**
- Рекомендуемый подход: **Реализуйте text encoder на CPU (`sentence-transformers`)**. Оно работает только один раз за запрос поиска, поэтому скорость не проблема
- Image encoder — это где ускорение Hailo обеспечивает реальную ценность (пакетное индексирование 200K изображений)

### Сосуществование с hailo-ollama

- Совместное использование устройств через `SHARED_VDEVICE_GROUP_ID` официально поддерживается
- Однако, **двоичный файл hailo-ollama не участвует в этом совместном использовании** (он исключительно занимает устройство)
- Пример сообщества: Был построен пользовательский менеджер устройств для запуска 6 сервисов одновременно
- **Практический подход**: Остановите hailo-ollama во время построения индекса и поделитесь устройством по времени
  - `systemctl stop hailo-ollama` -> Постройте индекс -> `systemctl start hailo-ollama`

### Оценки поиска векторов для 200,000 записей

- 200K x 512 float32 = примерно 400MB — подходит в Pi5 (8GB) RAM
- Пакетное косинусное сходство numpy должно завершиться менее чем за 1 секунду на Cortex-A76 Pi5

### FAISS ускорение для крупномасштабного поиска векторов (v3.26.0)

FAISS (Facebook AI Similarity Search) поддержка была добавлена в v3.26.0. Система автоматически обнаруживает `faiss-cpu` когда установлен и использует приблизительный поиск ближайшего соседа вместо перебора NumPy.

| Масштаб | NumPy (O(N)) | FAISS IndexFlatIP | FAISS IndexIVFFlat |
|------|-------------|-------------------|-------------------|
| 10K | ~10ms | ~2ms | - |
| 100K | ~100ms | ~20ms | ~5ms |
| 500K | ~500ms | ~100ms | ~10ms |
| 1.5M | ~1.5s | ~300ms | ~20ms |

- **< 50K**: IndexFlatIP (точный поиск внутреннего произведения) автоматически выбран
- **>= 50K**: IndexIVFFlat (IVF кластеризация) автоматически выбран, nprobe = nlist/10
- Возвращается к NumPy когда FAISS не установлен (нет влияния)

**Установка**:
```bash
source venv/bin/activate
uv pip install faiss-cpu  # Прямая установка pip работает на x86_64
# На aarch64 (RPi): conda install -c conda-forge faiss-cpu или установка из исходников
```

Лог запуска показывает `FAISS x.x.x detected — using accelerated vector search` когда активен.

### Примечания о приложении hailo-CLIP

- `hailo-ai/hailo-CLIP` ориентировано на **Hailo-8/8L**. Hailo-10H не поддерживается
- Оно спроектировано для классификации нулевого выстрела в реальном времени, а не конвейеров поиска изображений
- Оно служит справочным материалом, но не может быть использовано напрямую. Пользовательский конвейер должен быть построен с использованием API HailoRT

---

## Альтернатива (когда Hailo недоступен)

`sentence-transformers` с `clip-ViT-B-32` обеспечивает поддержку CLIP только на CPU.
Оно медленнее, но позволяет тому же расширению работать в окружениях без Hailo.

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('clip-ViT-B-32')
image_embedding = model.encode(Image.open(path))
text_embedding  = model.encode("blue sky")
```

Настройка `"device": "cpu"` в конфигурации расширения включает режим CPU. Этот двойной архитектурный подход максимизирует портативность.

---

## Приоритет реализации

```
Фаза 1 (Проверка)   -> Требуется, сделайте это в первую очередь
Фаза 2 (БД)         -> После успеха фазы 1
Фаза 3 (Ядро умозаключения) -> После фазы 2
Фаза 4 (Индексирование)     -> После фазы 3
Фаза 5 (API поиска)         -> После фазы 4
Фаза 6 (UI)                 -> После фазы 5, последняя
```

Переключитесь на весь подход с использованием CPU CLIP если фаза 1 не удаётся.

---

## Справочные репозитории

- `hailo-ai/hailo-apps`: Примеры классификации CLIP нулевого выстрела
- `hailo-ai/hailort`: Справочник pyHailoRT API
- `hailo-ai/Hailo-Application-Code-Examples`: Примеры умозаключения Python
- `hailo-ai/hailo_model_zoo`: Источник загрузки CLIP/SigLIP HEF

---

*Создано: 2026-02-27*
*Исследовательское дополнение: 2026-02-27 — детали процедуры фазы 1, подтверждение доступности HEF, анализ сосуществования hailo-ollama*
