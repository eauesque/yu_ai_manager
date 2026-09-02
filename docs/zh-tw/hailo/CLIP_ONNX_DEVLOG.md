# CLIP ONNX Embedding 開發日誌

## 概述

將原本 Hailo-10H 專用的 CLIP 語義圖片搜尋，擴展為基於 ONNX Runtime 的通用編碼器。
支援 CPU / NVIDIA CUDA / AMD ROCm / DirectML (Ryzen AI NPU) / OpenVINO (Intel NPU) / CoreML。

## 日期：2026-03-04

### Phase 1：共用核心層的提取 (`core/clip_core/`，現已移至 `extensions/builtin_clip_search/core_impl/`)

**建立的檔案：**
- `encoder_abc.py` — `ClipImageEncoder` ABC (encode, encode_batch, close, output_dim, backend_name)
- `image_io.py` — 圖片 I/O（純檔案 + ZIP/7z 壓縮檔支援）
- `vector_store.py` — 從 `hailo_clip_core` 直接搬移
- `text_encoder.py` — 從 `hailo_clip_core` 直接搬移
- `search.py` — 搬移 + 將 import 路徑改為相對路徑
- `indexer.py` — 通用化：將 `encoder_factory` 和 `preprocess_fn` 改為注入參數
- `event_handler.py` — 搬移 + 變更 `indexer` 的 import 路徑
- `encoder_factory.py` — `get_best_encoder()` (Hailo > ONNX 優先), `get_preprocessor()`, `get_encoder_info()`

**設計決策：**
- `cv2` 採延遲 import — 即使沒有 opencv-python 的機器也能成功載入模組
- `indexer.py` 的 `encoder_factory`/`preprocess_fn` 為 None 時，透過 `encoder_factory.py` 自動解析
- `event_handler.py` 沿用 extension config 鍵 `"builtin-hailo-semantic-search"`（向後相容）

### Phase 2：ONNX 編碼器 (`core/clip_onnx_core/`，現已移至 `extensions/builtin_clip_onnx/core_impl/`)

**建立的檔案：**
- `onnx_encoder.py` — `OnnxClipEncoder(ClipImageEncoder)` 單例模式
- `preprocess.py` — float32 NCHW 正規化（mean/std 使用 CLIP 官方值）
- `model_download.py` — HuggingFace `Xenova/clip-vit-base-patch16` 的 `onnx/vision_model.onnx`

**技術筆記：**
- 模型：`Xenova/clip-vit-base-patch16`（以 HuggingFace Optimum 轉換的 ONNX）
- 輸入：`pixel_values` (batch, 3, 224, 224) float32
- 輸出：`image_embeds` (batch, 512) float32 — L2 正規化後儲存
- 遵循 WD-Tagger `engine_onnx.py` 的模式（SessionOptions, batch inference）
- 透過 `ort_provider.select_providers()` 自動選擇 ExecutionProvider

### Phase 3：Hailo 重構

- 為 `HailoClipEncoder` 新增 `ClipImageEncoder` ABC 繼承 + `backend_name` 屬性
- `vector_store.py`, `text_encoder.py`, `search.py`, `event_handler.py` → 從 `clip_core` 重新匯出
- `indexer.py` → 注入 Hailo encoder/preprocess 的薄層封裝
- `image_preprocess.py` → 使用 `clip_core.image_io.read_and_decode()`

### Phase 4：inference_core 擴展

- 在 `ort_provider.py` 的 `_PROVIDER_PRIORITY` 中新增 `OpenVINOExecutionProvider`
- 在 `gpu_detect.py` 中新增 `openvino_available` 欄位 + `_detect_openvino()`
- 在 `ort_install_helper.py` 中新增 OpenVINO 套件資訊

### Phase 5：Extension 擴展

- 在 `extension.json` 中新增 `preferred_backend` 設定
- 將所有 import 路徑改為 `core.clip_core`
- 新增 API：`GET /api/backends`, `GET /api/model/status`, `POST /api/model/download`

### Phase 6：MCP 工具

- `mcp_server/semantic_tools.py` — 5 個工具
- `semantic_search`, `semantic_index_start/status/stop`, `semantic_backend_info`

### Phase 7：runtime_runner.py

- 將 event handler import 改為 `core.clip_core.event_handler`

## 向量相容性

Hailo HEF（uint8 量化→反量化）與 ONNX（float32 直接輸出）
基於相同的 `openai/clip-vit-base-patch16` 模型，因此輸出為相同的 512 維 embedding 空間。
以 Hailo 建置的現有索引與以 ONNX 新增的向量可以混合使用。

## NPU 支援矩陣

| NPU | ORT 套件 | 提供者 |
|---|---|---|
| AMD Ryzen AI | `onnxruntime-directml` | DmlExecutionProvider |
| Intel NPU | `onnxruntime-openvino` | OpenVINOExecutionProvider |
| NVIDIA GPU | `onnxruntime-gpu` | CUDAExecutionProvider |
| AMD GPU | `onnxruntime-rocm` | ROCmExecutionProvider |
| Apple Silicon | `onnxruntime` | CoreMLExecutionProvider |
| CPU (fallback) | `onnxruntime` | CPUExecutionProvider |
