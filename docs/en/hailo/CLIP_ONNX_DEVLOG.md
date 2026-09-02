# CLIP ONNX Embedding Development Log

## Overview

Extended the CLIP semantic image search, which was previously Hailo-10H exclusive, to a general-purpose encoder based on ONNX Runtime.
Supports CPU / NVIDIA CUDA / AMD ROCm / DirectML (Ryzen AI NPU) / OpenVINO (Intel NPU) / CoreML.

## Date: 2026-03-04

### Phase 1: Extracting the Shared Core Layer (`core/clip_core/`, now at `extensions/builtin_clip_search/core_impl/`)

**Files created:**
- `encoder_abc.py` -- `ClipImageEncoder` ABC (encode, encode_batch, close, output_dim, backend_name)
- `image_io.py` -- Image I/O (plain files + ZIP/7z archive support)
- `vector_store.py` -- Moved directly from `hailo_clip_core`
- `text_encoder.py` -- Moved directly from `hailo_clip_core`
- `search.py` -- Moved + changed imports to relative
- `indexer.py` -- Generalized: `encoder_factory` and `preprocess_fn` made injectable parameters
- `event_handler.py` -- Moved + changed `indexer` import path
- `encoder_factory.py` -- `get_best_encoder()` (Hailo > ONNX priority), `get_preprocessor()`, `get_encoder_info()`

**Design decisions:**
- `cv2` is lazily imported -- module loading succeeds even on machines without opencv-python
- When `indexer.py`'s `encoder_factory`/`preprocess_fn` are None, they are auto-resolved via `encoder_factory.py`
- `event_handler.py` continues using the extension config key `"builtin-hailo-semantic-search"` (backward compatibility)

### Phase 2: ONNX Encoder (`core/clip_onnx_core/`, now at `extensions/builtin_clip_onnx/core_impl/`)

**Files created:**
- `onnx_encoder.py` -- `OnnxClipEncoder(ClipImageEncoder)` singleton
- `preprocess.py` -- float32 NCHW normalization (mean/std use official CLIP values)
- `model_download.py` -- HuggingFace `Xenova/clip-vit-base-patch16`'s `onnx/vision_model.onnx`

**Technical notes:**
- Model: `Xenova/clip-vit-base-patch16` (ONNX converted via HuggingFace Optimum)
- Input: `pixel_values` (batch, 3, 224, 224) float32
- Output: `image_embeds` (batch, 512) float32 -- L2 normalized before storage
- Follows the WD-Tagger `engine_onnx.py` pattern (SessionOptions, batch inference)
- `ort_provider.select_providers()` handles automatic ExecutionProvider selection

### Phase 3: Hailo Refactoring

- Added `ClipImageEncoder` ABC inheritance + `backend_name` property to `HailoClipEncoder`
- `vector_store.py`, `text_encoder.py`, `search.py`, `event_handler.py` -> re-exported from `clip_core`
- `indexer.py` -> thin wrapper that injects Hailo encoder/preprocess
- `image_preprocess.py` -> uses `clip_core.image_io.read_and_decode()`

### Phase 4: inference_core Extension

- Added `OpenVINOExecutionProvider` to `_PROVIDER_PRIORITY` in `ort_provider.py`
- Added `openvino_available` field + `_detect_openvino()` to `gpu_detect.py`
- Added OpenVINO package info to `ort_install_helper.py`

### Phase 5: Extension Updates

- Added `preferred_backend` setting to `extension.json`
- Changed all imports to `core.clip_core`
- New APIs: `GET /api/backends`, `GET /api/model/status`, `POST /api/model/download`

### Phase 6: MCP Tools

- `mcp_server/semantic_tools.py` -- 5 tools
- `semantic_search`, `semantic_index_start/status/stop`, `semantic_backend_info`

### Phase 7: runtime_runner.py

- Changed event handler import to `core.clip_core.event_handler`

## Vector Compatibility

Hailo HEF (uint8 quantized -> dequantized) and ONNX (direct float32 output) are both based on the same `openai/clip-vit-base-patch16` model, so outputs share the same 512-dimensional embedding space.
Indices built with Hailo and vectors added via ONNX can coexist without issues.

## NPU Support Matrix

| NPU | ORT Package | Provider |
|---|---|---|
| AMD Ryzen AI | `onnxruntime-directml` | DmlExecutionProvider |
| Intel NPU | `onnxruntime-openvino` | OpenVINOExecutionProvider |
| NVIDIA GPU | `onnxruntime-gpu` | CUDAExecutionProvider |
| AMD GPU | `onnxruntime-rocm` | ROCmExecutionProvider |
| Apple Silicon | `onnxruntime` | CoreMLExecutionProvider |
| CPU (fallback) | `onnxruntime` | CPUExecutionProvider |
