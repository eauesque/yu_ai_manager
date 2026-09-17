# Registro de desarrollo de CLIP ONNX Embedding

## Resumen

Se amplió la búsqueda semántica de imágenes CLIP, que era exclusiva de Hailo-10H, a un codificador universal basado en ONNX Runtime.
Funciona con CPU / NVIDIA CUDA / AMD ROCm / DirectML (Ryzen AI NPU) / OpenVINO (Intel NPU) / CoreML.

## Fecha: 2026-03-04

### Fase 1: Extracción de la capa core compartida (`core/clip_core/`, actualmente `extensions/builtin_clip_search/core_impl/`)

**Archivos creados:**
- `encoder_abc.py` — ABC `ClipImageEncoder` (encode, encode_batch, close, output_dim, backend_name)
- `image_io.py` — E/S de imágenes (archivos normales + compatibilidad con archivos ZIP/7z)
- `vector_store.py` — Movido directamente desde `hailo_clip_core`
- `text_encoder.py` — Movido directamente desde `hailo_clip_core`
- `search.py` — Movido + cambio de importaciones a relativas
- `indexer.py` — Generalizado: `encoder_factory` y `preprocess_fn` como parámetros inyectables
- `event_handler.py` — Movido + cambio de importación de `indexer`
- `encoder_factory.py` — `get_best_encoder()` (prioridad Hailo > ONNX), `get_preprocessor()`, `get_encoder_info()`

**Decisiones de diseño:**
- `cv2` es una importación lazy — la carga del módulo tiene éxito incluso en máquinas sin opencv-python
- Si `encoder_factory`/`preprocess_fn` en `indexer.py` es None, se resuelve automáticamente a través de `encoder_factory.py`
- `event_handler.py` usa la clave de configuración de extensión `"builtin-hailo-semantic-search"` tal cual (compatibilidad hacia atrás)

### Fase 2: Codificador ONNX (`core/clip_onnx_core/`, actualmente `extensions/builtin_clip_onnx/core_impl/`)

**Archivos creados:**
- `onnx_encoder.py` — Singleton `OnnxClipEncoder(ClipImageEncoder)`
- `preprocess.py` — Normalización float32 NCHW (mean/std son valores oficiales de CLIP)
- `model_download.py` — `onnx/vision_model.onnx` de HuggingFace `Xenova/clip-vit-base-patch16`

**Notas técnicas:**
- Modelo: `Xenova/clip-vit-base-patch16` (ONNX convertido con HuggingFace Optimum)
- Entrada: `pixel_values` (batch, 3, 224, 224) float32
- Salida: `image_embeds` (batch, 512) float32 — normalizado con L2 para almacenamiento
- Cumple con el patrón de `engine_onnx.py` de WD-Tagger (SessionOptions, batch inference)
- Selección automática de ExecutionProvider con `ort_provider.select_providers()`

### Fase 3: Refactorización de Hailo

- Agregar herencia ABC `ClipImageEncoder` a `HailoClipEncoder` + propiedad `backend_name`
- `vector_store.py`, `text_encoder.py`, `search.py`, `event_handler.py` → re-exportación desde `clip_core`
- `indexer.py` → wrapper delgado que inyecta codificador/preprocesador de Hailo
- `image_preprocess.py` → usar `clip_core.image_io.read_and_decode()`

### Fase 4: Extensión de inference_core

- Agregar `OpenVINOExecutionProvider` a `_PROVIDER_PRIORITY` de `ort_provider.py`
- Agregar campo `openvino_available` + `_detect_openvino()` a `gpu_detect.py`
- Agregar información del paquete OpenVINO a `ort_install_helper.py`

### Fase 5: Extensión de Extension

- Agregar configuración `preferred_backend` a `extension.json`
- Cambiar todas las importaciones a `core.clip_core`
- Nueva API: `GET /api/backends`, `GET /api/model/status`, `POST /api/model/download`

### Fase 6: Herramientas MCP

- `mcp_server/semantic_tools.py` — 5 herramientas
- `semantic_search`, `semantic_index_start/status/stop`, `semantic_backend_info`

### Fase 7: runtime_runner.py

- Cambiar importación del handler de eventos a `core.clip_core.event_handler`

## Compatibilidad de vectores

Hailo HEF (uint8 cuantizado→descuantizado) y ONNX (salida float32 directa) se basan en el mismo modelo `openai/clip-vit-base-patch16`, por lo que la salida es el mismo espacio de embedding de 512 dimensiones.
Los vectores del índice construido con Hailo y los agregados con ONNX pueden coexistir.

## Matriz de soporte NPU

| NPU | Paquete ORT | Proveedor |
|---|---|---|
| AMD Ryzen AI | `onnxruntime-directml` | DmlExecutionProvider |
| Intel NPU | `onnxruntime-openvino` | OpenVINOExecutionProvider |
| NVIDIA GPU | `onnxruntime-gpu` | CUDAExecutionProvider |
| AMD GPU | `onnxruntime-rocm` | ROCmExecutionProvider |
| Apple Silicon | `onnxruntime` | CoreMLExecutionProvider |
| CPU (fallback) | `onnxruntime` | CPUExecutionProvider |
