# CLIP ONNX Embedding 开发日志

## 概述

将原本 Hailo-10H 专用的 CLIP 语义图片搜索，扩展为基于 ONNX Runtime 的通用编码器。
支持 CPU / NVIDIA CUDA / AMD ROCm / DirectML (Ryzen AI NPU) / OpenVINO (Intel NPU) / CoreML。

## 日期：2026-03-04

### Phase 1：共享核心层的提取 (`core/clip_core/`，现已移至 `extensions/builtin_clip_search/core_impl/`)

**创建的文件：**
- `encoder_abc.py` — `ClipImageEncoder` ABC (encode, encode_batch, close, output_dim, backend_name)
- `image_io.py` — 图片 I/O（纯文件 + ZIP/7z 压缩包支持）
- `vector_store.py` — 从 `hailo_clip_core` 直接迁移
- `text_encoder.py` — 从 `hailo_clip_core` 直接迁移
- `search.py` — 迁移 + 将 import 路径改为相对路径
- `indexer.py` — 通用化：将 `encoder_factory` 和 `preprocess_fn` 改为注入参数
- `event_handler.py` — 迁移 + 变更 `indexer` 的 import 路径
- `encoder_factory.py` — `get_best_encoder()` (Hailo > ONNX 优先), `get_preprocessor()`, `get_encoder_info()`

**设计决策：**
- `cv2` 采用延迟 import — 即使没有 opencv-python 的机器也能成功加载模块
- `indexer.py` 的 `encoder_factory`/`preprocess_fn` 为 None 时，通过 `encoder_factory.py` 自动解析
- `event_handler.py` 沿用 extension config 键 `"builtin-hailo-semantic-search"`（向后兼容）

### Phase 2：ONNX 编码器 (`core/clip_onnx_core/`，现已移至 `extensions/builtin_clip_onnx/core_impl/`)

**创建的文件：**
- `onnx_encoder.py` — `OnnxClipEncoder(ClipImageEncoder)` 单例模式
- `preprocess.py` — float32 NCHW 归一化（mean/std 使用 CLIP 官方值）
- `model_download.py` — HuggingFace `Xenova/clip-vit-base-patch16` 的 `onnx/vision_model.onnx`

**技术笔记：**
- 模型：`Xenova/clip-vit-base-patch16`（以 HuggingFace Optimum 转换的 ONNX）
- 输入：`pixel_values` (batch, 3, 224, 224) float32
- 输出：`image_embeds` (batch, 512) float32 — L2 归一化后存储
- 遵循 WD-Tagger `engine_onnx.py` 的模式（SessionOptions, batch inference）
- 通过 `ort_provider.select_providers()` 自动选择 ExecutionProvider

### Phase 3：Hailo 重构

- 为 `HailoClipEncoder` 新增 `ClipImageEncoder` ABC 继承 + `backend_name` 属性
- `vector_store.py`, `text_encoder.py`, `search.py`, `event_handler.py` → 从 `clip_core` 重新导出
- `indexer.py` → 注入 Hailo encoder/preprocess 的薄层封装
- `image_preprocess.py` → 使用 `clip_core.image_io.read_and_decode()`

### Phase 4：inference_core 扩展

- 在 `ort_provider.py` 的 `_PROVIDER_PRIORITY` 中新增 `OpenVINOExecutionProvider`
- 在 `gpu_detect.py` 中新增 `openvino_available` 字段 + `_detect_openvino()`
- 在 `ort_install_helper.py` 中新增 OpenVINO 包信息

### Phase 5：Extension 扩展

- 在 `extension.json` 中新增 `preferred_backend` 设置
- 将所有 import 路径改为 `core.clip_core`
- 新增 API：`GET /api/backends`, `GET /api/model/status`, `POST /api/model/download`

### Phase 6：MCP 工具

- `mcp_server/semantic_tools.py` — 5 个工具
- `semantic_search`, `semantic_index_start/status/stop`, `semantic_backend_info`

### Phase 7：runtime_runner.py

- 将 event handler import 改为 `core.clip_core.event_handler`

## 向量兼容性

Hailo HEF（uint8 量化→反量化）与 ONNX（float32 直接输出）
基于相同的 `openai/clip-vit-base-patch16` 模型，因此输出为相同的 512 维 embedding 空间。
以 Hailo 构建的现有索引与以 ONNX 新增的向量可以混合使用。

## NPU 支持矩阵

| NPU | ORT 包 | 提供者 |
|---|---|---|
| AMD Ryzen AI | `onnxruntime-directml` | DmlExecutionProvider |
| Intel NPU | `onnxruntime-openvino` | OpenVINOExecutionProvider |
| NVIDIA GPU | `onnxruntime-gpu` | CUDAExecutionProvider |
| AMD GPU | `onnxruntime-rocm` | ROCmExecutionProvider |
| Apple Silicon | `onnxruntime` | CoreMLExecutionProvider |
| CPU (fallback) | `onnxruntime` | CPUExecutionProvider |
