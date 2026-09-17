# Дневник разработки CLIP ONNX Embedding

## Обзор

Расширение семантического поиска изображений CLIP, ранее работавшего только на Hailo-10H,
до универсального энкодера на базе ONNX Runtime.
Работает на CPU / NVIDIA CUDA / AMD ROCm / DirectML (Ryzen AI NPU) / OpenVINO (Intel NPU) / CoreML.

## Дата: 2026-03-04

### Phase 1: Извлечение общего ядра (`core/clip_core/`, сейчас `extensions/builtin_clip_search/core_impl/`)

**Созданные файлы:**
- `encoder_abc.py` — абстрактный класс `ClipImageEncoder` (encode, encode_batch, close, output_dim, backend_name)
- `image_io.py` — ввод/вывод изображений (обычные файлы + ZIP/7z-архивы)
- `vector_store.py` — перенесён из `hailo_clip_core`
- `text_encoder.py` — перенесён из `hailo_clip_core`
- `search.py` — перенесён с изменением импортов на относительные
- `indexer.py` — обобщён: `encoder_factory` и `preprocess_fn` вынесены в параметры инъекции
- `event_handler.py` — перенесён с изменением импорта `indexer`
- `encoder_factory.py` — `get_best_encoder()` (приоритет Hailo > ONNX), `get_preprocessor()`, `get_encoder_info()`

**Проектные решения:**
- `cv2` — отложенный импорт: загрузка модуля успешна даже без opencv-python
- Если `encoder_factory`/`preprocess_fn` в `indexer.py` равны None, автоматически разрешаются через `encoder_factory.py`
- `event_handler.py` использует ключ конфигурации extension `"builtin-hailo-semantic-search"` как есть (для обратной совместимости)

### Phase 2: ONNX-энкодер (`core/clip_onnx_core/`, сейчас `extensions/builtin_clip_onnx/core_impl/`)

**Созданные файлы:**
- `onnx_encoder.py` — синглтон `OnnxClipEncoder(ClipImageEncoder)`
- `preprocess.py` — нормализация float32 NCHW (официальные значения mean/std CLIP)
- `model_download.py` — загрузка `onnx/vision_model.onnx` из `Xenova/clip-vit-base-patch16` на HuggingFace

**Технические заметки:**
- Модель: `Xenova/clip-vit-base-patch16` (конвертированный ONNX через HuggingFace Optimum)
- Вход: `pixel_values` (batch, 3, 224, 224) float32
- Выход: `image_embeds` (batch, 512) float32 — сохраняется с L2-нормализацией
- Соответствует паттерну WD-Tagger `engine_onnx.py` (SessionOptions, пакетный инференс)
- Автоматический выбор ExecutionProvider через `ort_provider.select_providers()`

### Phase 3: Рефакторинг Hailo

- Добавлено наследование ABC `ClipImageEncoder` в `HailoClipEncoder` + свойство `backend_name`
- `vector_store.py`, `text_encoder.py`, `search.py`, `event_handler.py` → реэкспорт из `clip_core`
- `indexer.py` → тонкая обёртка с инъекцией encoder/preprocess от Hailo
- `image_preprocess.py` → использует `clip_core.image_io.read_and_decode()`

### Phase 4: Расширение inference_core

- Добавлен `OpenVINOExecutionProvider` в `_PROVIDER_PRIORITY` файла `ort_provider.py`
- Добавлено поле `openvino_available` + `_detect_openvino()` в `gpu_detect.py`
- Добавлена информация о пакете OpenVINO в `ort_install_helper.py`

### Phase 5: Расширение Extension

- Добавлена настройка `preferred_backend` в `extension.json`
- Все импорты изменены на `core.clip_core`
- Новые API: `GET /api/backends`, `GET /api/model/status`, `POST /api/model/download`

### Phase 6: MCP-инструменты

- `mcp_server/semantic_tools.py` — 5 инструментов
- `semantic_search`, `semantic_index_start/status/stop`, `semantic_backend_info`

### Phase 7: runtime_runner.py

- Импорт event handler изменён на `core.clip_core.event_handler`

## Совместимость векторов

Hailo HEF (uint8-квантование → деквантование) и ONNX (прямой вывод float32)
основаны на одной модели `openai/clip-vit-base-patch16`, поэтому выводы находятся
в одном 512-мерном пространстве эмбеддингов.
Индексы, построенные на Hailo, и векторы, добавленные через ONNX, могут сосуществовать.

## Матрица поддержки NPU

| NPU | Пакет ORT | Провайдер |
|-----|-----------|-----------|
| AMD Ryzen AI | `onnxruntime-directml` | DmlExecutionProvider |
| Intel NPU | `onnxruntime-openvino` | OpenVINOExecutionProvider |
| NVIDIA GPU | `onnxruntime-gpu` | CUDAExecutionProvider |
| AMD GPU | `onnxruntime-rocm` | ROCmExecutionProvider |
| Apple Silicon | `onnxruntime` | CoreMLExecutionProvider |
| CPU (запасной) | `onnxruntime` | CPUExecutionProvider |
