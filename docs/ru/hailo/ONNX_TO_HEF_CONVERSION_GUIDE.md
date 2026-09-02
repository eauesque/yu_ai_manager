# Инструкция по конвертации ONNX → HEF

**Цель**: Конвертация ONNX-моделей (WD-Tagger и др.) в формат Hailo HEF для инференса на Hailo-10H NPU
**Среда выполнения**: x86_64 Linux (AI-сервер) — Hailo Dataflow Compiler работает только на x86
**Среда инференса**: Raspberry Pi 5 + AI HAT 2 (Hailo-10H)

---

## Предварительные знания

### Зачем нужна конвертация

| Параметр | ONNX Runtime (текущий) | Hailo HEF (цель) |
|---------|----------------------|-----------------|
| Выполнение | CPU | Hailo-10H NPU (40 TOPS) |
| Квантование | float32 | INT8 (uint8) |
| Скорость инференса | ~500ms/image (Pi5 CPU) | ~20ms/image (оценка, по данным CLIP) |
| Память | ~200MB (загрузка модели) | ~десятки МБ (HEF) |

### Обзор пайплайна конвертации

```
model.onnx (float32)
  |
  | [1] Парсер Hailo Model Zoo (ONNX → HAR)
  v
model.har (Hailo Archive, float32)
  |
  | [2] Оптимизация (слияние слоёв, расстановка памяти)
  v
model_optimized.har
  |
  | [3] Квантование (float32 → INT8, с калибровочными изображениями)
  v
model_quantized.har
  |
  | [4] Компиляция (преобразование в HW-инструкции)
  v
model.hef (Hailo Executable Format)
```

---

## 1. Настройка окружения на AI-сервере

### 1-1. Установка Hailo Dataflow Compiler

Скачать из Hailo Developer Zone (https://hailo.ai/developer-zone/).
Требуется регистрация.

```bash
# Рекомендуется Python 3.10 или 3.11 (3.12+ может не поддерживаться)
python3 --version

# Создать venv
python3 -m venv ~/hailo_env
source ~/hailo_env/bin/activate

# Установить Hailo Dataflow Compiler (DFC)
# Указать .whl, скачанный из Developer Zone
uv pip install hailo_dataflow_compiler-3.29.0-py3-none-linux_x86_64.whl

# Зависимости
uv pip install numpy pillow onnx onnxruntime
```

**Проверка**:
```bash
python -c "from hailo_sdk_client import ClientRunner; print('DFC OK')"
```

### 1-2. Hailo Model Zoo (опционально, рекомендуется)

```bash
git clone https://github.com/hailo-ai/hailo_model_zoo.git ~/hailo_model_zoo
uv pip install -e ~/hailo_model_zoo
```

Model Zoo содержит конфигурации конвертации (YAML) для многих моделей — полезно для справки.

---

## 2. Подготовка целевой модели

### 2-1. WD-Tagger

Текущие используемые модели:
- **Репозиторий**: HuggingFace `SmilingWolf/wd-swinv2-tagger-v3` и др.
- **Файл**: `model.onnx` (~110MB, float32)
- **Вход**: `(1, 448, 448, 3)` float32, BGR, без нормализации [0, 255]
- **Выход**: `(1, num_tags)` float32, вероятности после сигмоиды

```bash
# Скачать с HuggingFace
mkdir -p ~/hailo_convert/wd_tagger
cd ~/hailo_convert/wd_tagger

# Получить model.onnx и selected_tags.csv
wget https://huggingface.co/SmilingWolf/wd-swinv2-tagger-v3/resolve/main/model.onnx
wget https://huggingface.co/SmilingWolf/wd-swinv2-tagger-v3/resolve/main/selected_tags.csv
```

### 2-2. Проверка входов/выходов ONNX-модели

```python
import onnx

model = onnx.load("model.onnx")

print("=== Входы ===")
for inp in model.graph.input:
    shape = [d.dim_value for d in inp.type.tensor_type.shape.dim]
    print(f"  {inp.name}: {shape}")

print("=== Выходы ===")
for out in model.graph.output:
    shape = [d.dim_value for d in out.type.tensor_type.shape.dim]
    print(f"  {out.name}: {shape}")
```

Записать shape и имена входов/выходов — понадобятся при конвертации.

---

## 3. Подготовка калибровочных изображений

Для квантования INT8 нужен репрезентативный набор изображений (калибровочные данные).
Используются для определения параметров квантования (scale/zero_point).

```bash
mkdir -p ~/hailo_convert/calibration_images
```

### Требования

- **Количество**: ~100-1000 изображений (больше = стабильнее, но дольше)
- **Содержание**: Репрезентативные примеры реальных изображений для инференса (вариации AI-генерированных)
- **Формат**: JPEG/PNG
- **Размер**: Произвольный (скрипт предобработки изменит размер)

### Скрипт предобработки калибровочных данных

Применить ту же предобработку, что и для WD-Tagger:

```python
# calibration_preprocess.py
"""Предобработка калибровочных изображений в формат WD-Tagger."""
import numpy as np
from PIL import Image
from pathlib import Path

INPUT_SIZE = 448

def preprocess(image_path: str) -> np.ndarray:
    """Та же предобработка, что в engine_onnx.py yu_ai_manager."""
    with Image.open(image_path) as raw:
        img = raw.convert("RGBA")

    # Наложить на белый фон (поддержка прозрачности)
    canvas = Image.new("RGBA", img.size, (255, 255, 255, 255))
    canvas.alpha_composite(img)
    img = canvas.convert("RGB")

    # Масштабировать с сохранением пропорций
    old_w, old_h = img.size
    scale = INPUT_SIZE / max(old_w, old_h)
    new_w = int(old_w * scale)
    new_h = int(old_h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)

    # Дополнить белым до квадрата
    padded = Image.new("RGB", (INPUT_SIZE, INPUT_SIZE), (255, 255, 255))
    padded.paste(img, ((INPUT_SIZE - new_w) // 2, (INPUT_SIZE - new_h) // 2))

    # HWC, float32, RGB -> BGR
    arr = np.array(padded, dtype=np.float32)
    arr = arr[:, :, ::-1]  # RGB -> BGR

    return arr  # (448, 448, 3)


def load_calibration_set(image_dir: str, max_images: int = 500) -> np.ndarray:
    """Вернуть калибровочные изображения как батч-тензор."""
    images = []
    for p in sorted(Path(image_dir).glob("*")):
        if p.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
            continue
        try:
            images.append(preprocess(str(p)))
        except Exception as e:
            print(f"  skip {p.name}: {e}")
        if len(images) >= max_images:
            break

    print(f"Loaded {len(images)} calibration images")
    return np.stack(images, axis=0)  # (N, 448, 448, 3)


if __name__ == "__main__":
    dataset = load_calibration_set("calibration_images")
    np.save("calibration_data.npy", dataset)
    print(f"Saved: calibration_data.npy {dataset.shape}")
```

---

## 4. Выполнение конвертации в HEF

### 4-1. Скрипт конвертации

```python
# convert_wd_tagger.py
"""Скрипт конвертации WD-Tagger ONNX → Hailo HEF."""
from hailo_sdk_client import ClientRunner
import numpy as np

# ========== Конфигурация ==========
ONNX_PATH = "model.onnx"
MODEL_NAME = "wd_swinv2_tagger_v3"
CALIBRATION_NPY = "calibration_data.npy"
HW_ARCH = "hailo10h"  # Для Hailo-10H
# ===================================

# --- Шаг 1: Парсинг ONNX → HAR ---
print("[1/4] Parsing ONNX model...")
runner = ClientRunner(hw_arch=HW_ARCH)

hn, npz = runner.translate_onnx_model(
    ONNX_PATH,
    MODEL_NAME,
    # net_input_shapes={"input": [1, 448, 448, 3]},  # При необходимости
)
print(f"  Parsed: {len(npz)} layers")

# --- Шаг 2: Оптимизация модели ---
print("[2/4] Optimizing model...")
runner.optimize(npz)

# --- Шаг 3: Квантование INT8 ---
print("[3/4] Quantizing (INT8)...")
calib_data = np.load(CALIBRATION_NPY)
print(f"  Calibration set: {calib_data.shape}")

runner.quantize(calib_data)

# --- Шаг 4: Компиляция → HEF ---
print("[4/4] Compiling to HEF...")
hef = runner.compile()

hef_path = f"{MODEL_NAME}.hef"
with open(hef_path, "wb") as f:
    f.write(hef)
print(f"Done: {hef_path} ({len(hef) / 1024 / 1024:.1f} MB)")

# Сохранить HAR (промежуточный файл) для отладки
har_path = f"{MODEL_NAME}.har"
runner.save_har(har_path)
print(f"HAR saved: {har_path}")
```

### 4-2. Запуск

```bash
source ~/hailo_env/bin/activate
cd ~/hailo_convert/wd_tagger

# Предобработка калибровочных изображений
python calibration_preprocess.py

# Конвертация в HEF
python convert_wd_tagger.py
```

**Ориентировочное время**: Зависит от размера модели и количества калибровочных изображений — от десятков минут до нескольких часов.

### 4-3. Распространённые ошибки и способы их устранения

| Ошибка | Причина | Решение |
|--------|---------|---------|
| `UnsupportedOp: <op_name>` | Оператор ONNX не поддерживается DFC | Проверить список поддерживаемых операторов Hailo. Неподдерживаемые op — изменить модель или удалить через `onnx-simplifier` |
| `Shape mismatch` | Динамический входной shape | Явно указать фиксированный shape через `net_input_shapes` |
| `Quantization error` / деградация точности | Неподходящие калибровочные данные | Увеличить количество изображений, использовать реальные эксплуатационные |
| `Memory allocation failed` | Модель слишком большая для памяти NPU | Зафиксировать batch_size=1 или рассмотреть более лёгкую модель |
| `hailo_sdk_client not found` | DFC не установлен | Проверить шаг 1-1 |

### 4-4. (Рекомендуется) Предварительная обработка через onnx-simplifier

Упрощение ONNX-модели перед конвертацией повышает вероятность успеха:

```bash
uv pip install onnx-simplifier
python -m onnxsim model.onnx model_simplified.onnx
```

---

## 5. Верификация после конвертации (на AI-сервере)

### 5-1. Проверка точности через эмулятор Hailo

Можно проверить точность сконвертированной модели без реального устройства:

```python
# verify_hef.py
"""Сравнить выходные данные HEF с ONNX для проверки деградации точности."""
import numpy as np
import onnxruntime as ort

# Инференс ONNX (float32, эталон)
sess = ort.InferenceSession("model.onnx")
test_image = np.load("calibration_data.npy")[0:1]
input_name = sess.get_inputs()[0].name
onnx_output = sess.run(None, {input_name: test_image})[0][0]

# Инференс через эмулятор HEF
from hailo_sdk_client import ClientRunner

runner = ClientRunner(har="wd_swinv2_tagger_v3.har")
hef_output = runner.infer(test_image)[0]

# Сравнение
diff = np.abs(onnx_output - hef_output)
print(f"Max diff:  {diff.max():.6f}")
print(f"Mean diff: {diff.mean():.6f}")
print(f"Cosine similarity: {np.dot(onnx_output, hef_output) / (np.linalg.norm(onnx_output) * np.linalg.norm(hef_output)):.6f}")

# Процент совпадения тегов (при пороге 0.35)
threshold = 0.35
onnx_tags = set(np.where(onnx_output > threshold)[0])
hef_tags = set(np.where(hef_output > threshold)[0])
overlap = len(onnx_tags & hef_tags)
print(f"Tag match: {overlap}/{len(onnx_tags)} ({overlap/max(len(onnx_tags),1)*100:.1f}%)")
```

**Критерии приёмки**:
- Косинусное сходство > 0.95: хорошо
- Совпадение тегов > 90%: производственный уровень
- Совпадение тегов < 80%: требуется пересмотр калибровочных данных

---

## 6. Перенос на Pi и тестирование на реальном устройстве

### 6-1. Перенос HEF-файла

```bash
scp ~/hailo_convert/wd_tagger/wd_swinv2_tagger_v3.hef pi@raspberrypi:~/hailo_models/
```

---

## 7. Известные проблемы

### Возможность конвертации архитектуры SwinV2

WD-Tagger v3 основан на **Swin Transformer V2**. Следующие операции могут не поддерживаться DFC:
- Window Attention (shifted window)
- Операция Roll
- Относительное позиционное смещение

Альтернативы при невозможности конвертации SwinV2:
1. **wd-vit-tagger-v3** (Vision Transformer) — ViT той же серии, что CLIP, есть прецеденты конвертации Hailo
2. **wd-convnext-tagger-v3** (ConvNeXt) — CNN-подобный, легче конвертируется
3. **wd-eva02-large-tagger-v3** (EVA-02) — большая модель (300MB+), осторожно с памятью NPU

---

## Справочные ссылки

- [Документация Hailo Dataflow Compiler](https://hailo.ai/developer-zone/documentation/dataflow-compiler/)
- [Hailo Model Zoo](https://github.com/hailo-ai/hailo_model_zoo)
- [WD-Tagger модели (HuggingFace)](https://huggingface.co/SmilingWolf)
- [ONNX Simplifier](https://github.com/daquexian/onnx-simplifier)
