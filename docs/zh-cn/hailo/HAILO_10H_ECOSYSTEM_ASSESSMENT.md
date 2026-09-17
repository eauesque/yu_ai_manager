# Hailo-10H 生态系统评估

**创建日期**: 2026-03-19
**对象**: Hailo-10H (AI HAT 2 for Raspberry Pi 5)
**HailoRT**: v5.2.0
**DFC**: v5.2.0
**目的**: 记录本项目中 Hailo-10H 的开发经验，整理现实中的制约条件与未来展望

---

## 综合评估

**硬件优秀。软件生态系统严重不足。**

Hailo-10H 是一款拥有 40 TOPS 推理性能的 NPU，硬件潜力充足。然而，由于软件工具链封闭且不成熟，开发者自由导入并运行模型**实质上是不可能的**。

本项目对 Hailo-10H 进行了多方面的开发应用，包括 CLIP 语义搜索、YOLO 物体检测、LLM/VLM 聊天、Whisper 语音识别以及分布式标注服务器。但稳定运行的功能**全部使用了从 Hailo 官方 Model Zoo 下载的预编译 HEF**，自行从 ONNX 转换为 HEF 的尝试**从未成功过**。

---

## 本项目的实现状况

### 正常运行的功能（全部使用官方 HEF 下载）

| 功能 | 使用的 API | HEF 来源 |
|------|---------|-----------|
| CLIP 图像编码器 | `VDevice.create_infer_model()` | Hailo Model Zoo (S3) |
| YOLO 物体检测 | `VDevice.create_infer_model()` | Hailo Model Zoo (S3) |
| LLM 聊天 | `hailo_platform.genai.LLM` | Hailo GenAI Model Zoo |
| VLM 图像+文本推理 | `hailo_platform.genai.VLM` | Hailo GenAI Model Zoo |
| Whisper 语音识别 | `hailo_platform.genai.Speech2Text` | Hailo GenAI Model Zoo |

### 未能实现的功能（HEF 转换失败）

| 功能 | 尝试内容 | 结果 |
|------|-----------|------|
| WD-Tagger (SwinV2) | ONNX → HEF 转换 | DFC 无法处理 LayerNormalization，转换失败 |
| WD-Tagger (ViT) | ONNX → HEF 转换 | 同上 |
| WD-Tagger (ConvNeXt) | ONNX → HEF 转换 | DFC 无法处理 Transpose 操作，转换失败 |

### 实现方面的特别说明

本项目**直接调用** `hailo_platform` wheel 的 Python API 实现了所有功能。未使用 hailo-ollama 或 hailo-apps。

特别是以下内容是在 Hailo 公司官方提供之前自主构建的：

- **VDevice 互斥控制设备管理器** — 在单个 VDevice 上自动切换 CLIP/YOLO/LLM/VLM/S2T。hailo-apps 没有设备共享机制
- **多后端回退** — Hailo → CoreML → ONNX Runtime 的透明自动切换
- **uint8 反量化流水线** — 从 `quant_info` 的 scale/zero_point 恢复 float32
- **LAN 分布式推理架构** — 多台机器的工作窃取并行标注

这些开发是在 **API 文档几乎不存在的状态**下进行的。InferModel API 的输入输出规格、缓冲区大小要求、量化参数的获取方法全部是通过错误信息和源代码推测来解明的。

---

## Hailo Dataflow Compiler (DFC) 的问题

### DFC 是什么

用于将 ONNX / TensorFlow 模型转换为 Hailo-10H 专用 HEF (Hailo Executable Format) 的编译器。在 x86_64 Linux 上运行，通过以下流水线转换模型：

```
model.onnx → HAR (float32) → 优化 → 量化 (INT8) → 编译 → model.hef
```

### 现实情况

**DFC 只能正常转换 Hailo 为自家 Model Zoo 预先验证过的架构。**

本项目的转换尝试（2026-03-06，DFC v5.2.0）：

| 模型 | 大小 | 错误 | 到达阶段 |
|--------|-------|--------|---------|
| wd-swinv2-tagger-v3 | 446 MB | `IndexError` in `_convert_axes_to_nhwc` | 优化前 |
| wd-vit-tagger-v3 | 362 MB | 同上 | 优化前 |
| wd-convnext-tagger-v3 | 377 MB | `UnsupportedShuffleLayerError` | 优化前 |

3 个模型全部在**到达优化阶段之前**就在解析器层面失败了。准备好的 500 张校准图片甚至从未被使用过。

### 根本原因

DFC 的 ONNX 解析器无法处理以下算子：

- `LayerNormalization`（多维张量的轴变换）
- `Transpose`（channels-last/first 转换模式）

这些是 Transformer 系列架构（SwinV2、ViT、ConvNeXt 等）的基本构成要素，2022 年以后的主流模型大部分都在使用。

### DFC 的实际支持范围

| 架构 | DFC 支持 | 依据 |
|---------------|---------|------|
| ResNet、MobileNet 等 CNN 系列 | ✓ 支持 | Model Zoo 中有大量存在 |
| YOLO v5/v8/v11 | ✓ 支持 | Model Zoo 中有 HEF |
| CLIP ViT (Hailo 版) | ✓ 支持 | Model Zoo 中有 HEF（由 Hailo 公司转换） |
| SwinTransformer V2 | ✗ 不支持 | LayerNorm 转换失败 |
| Vision Transformer (通用) | ✗ 不支持 | LayerNorm 转换失败 |
| ConvNeXt | ✗ 不支持 | Transpose 转换失败 |

> **注**: CLIP ViT 之所以在 Model Zoo 中存在，很可能是 Hailo 公司内部进行了特殊处理（手动图变换或自定义解析器）。即使是同样的 ViT，普通用户使用 DFC 转换也会失败。

---

## HEF 格式的问题

- **二进制规范未公开** — Hailo 没有公开格式文档
- **除 DFC 外没有其他生成方式** — 第三方工具无法生成 HEF
- **逆向工程也不现实** — 需要了解 NPU 的指令集和数据流架构

也就是说，DFC 无法转换的模型**无论如何都无法在 Hailo-10H 上运行**。不存在替代方案。

---

## 开发工具链评估

### hailo_platform (Python SDK)

| 项目 | 评价 |
|------|------|
| InferModel API | 可以工作，但文档极其不足 |
| GenAI API (LLM/VLM/S2T) | 相对易用。但有大量未记录的行为 |
| Python wheel 分发 | PyPI 上没有。aarch64 wheel 需要从源代码构建 |
| 错误信息 | 最低限度。缓冲区大小不匹配的原因难以定位 |
| VDevice 管理 | 仅支持互斥访问。不支持多模型同时使用 |

### 开发中发现的未记录行为

1. **InferModel API 才是正确的** — 旧的 VStreams API（`InferVStreams`、`ConfigureParams.create_from_hef`）在 Hailo-10H 上会返回 `HAILO_NOT_IMPLEMENTED`
2. **输出是 uint8 量化的** — 用 float32 分配缓冲区会导致 `buffer size mismatch`。需要用 uint8 分配后再进行反量化
3. **`input()`/`output()` 是属性** — 不是方法（与其他 Hailo API 不一致）
4. **`quant_info` 的获取** — 可以通过 `infer_model.output().quant_info` 获取 scale/zero_point，但不存在说明此功能的文档
5. **与 hailo-ollama 互斥** — 使用 VDevice 时需要停止 hailo-ollama。从错误信息中难以判断原因

---

## 竞品比较

### Ryzen AI (XDNA) NPU

| 项目 | Hailo-10H | Ryzen AI (XDNA) |
|------|----------|-----------------|
| 性能 | 40 TOPS | 16~50 TOPS（因世代而异） |
| 模型导入 | 必须通过 DFC 转换，大多数会失败 | **ONNX Runtime 直接支持** |
| 开发者体验 | 独有工具链，文档不足 | `pip install onnxruntime-directml` 即可完成 |
| 生态系统 | 封闭，依赖 Model Zoo | ONNX / DirectML / Microsoft 联合 |
| 普及数量 | Pi + AI HAT、USB 加密狗（计划中） | **数百万台笔记本电脑已内置** |

Ryzen AI 的集成只需以下代码即可完成：

```python
import onnxruntime as ort
session = ort.InferenceSession("model.onnx", providers=["DmlExecutionProvider"])
```

在 Hailo-10H 上无法做到同样的事情。不存在 ONNX Runtime Execution Provider。

### NVIDIA CUDA

| 项目 | Hailo-10H | NVIDIA CUDA |
|------|----------|-------------|
| 模型导入 | 通过 DFC，Model Zoo 以外大多数会失败 | ONNX / PyTorch / TensorFlow → 直接运行 |
| 工具链 | 不成熟、半封闭 | 成熟、公开、大量文档 |
| 开发者社区 | 极小 | 全球最大 |
| 价格区间 | 便宜（约 $70） | 昂贵（$200~$2000+） |

Hailo 唯一的优势是**价格和功耗**。

---

## 与 hailo-apps (2025-10) 的关系

### hailo-apps 概述

Hailo 公司于 2025 年 10 月发布的官方应用程序集。包含 20 多个示例应用：

- GenAI: voice_assistant、vlm_chat、agent_tools_example、whisper
- Pipeline: 物体检测、姿态估计、人脸识别、CLIP 分类、OCR
- Standalone: Python/C++ 的 HailoRT 学习用演示

### 与本项目的比较

| 项目 | hailo-apps | 本项目 |
|------|-----------|-------------|
| VLM 支持 | vlm_chat 应用 | 直接实现 `hailo_platform.genai.VLM` |
| CLIP | clip 应用 | 作为语义搜索系统集成 |
| LLM | simple_llm_chat | 作为 GenAI Extension 集成 |
| Whisper | simple_whisper_chat | 作为 Speech-to-Text Extension 集成 |
| 设备管理 | 无（假定单一应用） | **互斥控制设备管理器（CLIP/YOLO/LLM/VLM/S2T 自动切换）** |
| 后端回退 | 无 | **Hailo → CoreML → ONNX 自动切换** |
| 分布式推理 | 无 | **LAN 分布式工作窃取** |
| 集成度 | 独立的演示应用 | 单一的集成 WebUI 应用程序 |

本项目在 hailo-apps 公开之前，就已经通过 `hailo_platform` wheel 的低级 API 自主实现了同等以上的功能。

---

## 未来展望

### 短期（现实的）

- **ONNX Runtime + LAN 分布式是唯一的实用方案** — 使用分布式标注服务器的 ONNX 后端运营
- Hailo-10H 仅限于有官方 HEF 的用途（YOLO、CLIP、LLM、Whisper）使用
- 放弃自定义模型的 NPU 执行

### 中期（期望的）

- ASUS 等发售搭载 Hailo-10H 的 USB 加密狗 → 用户增加
- 随着用户增加，可能会对 Hailo 公司形成工具改善压力
- DFC 的未来版本可能会添加 Transformer 系列支持

### 长期（结构性课题）

- 除非 Hailo 提供 ONNX Runtime EP，否则在开发者生态系统方面将输给 Ryzen AI (XDNA)
- 即使通过 USB 加密狗普及了硬件，如果软件缺乏自由度，也只不过是"能跑快速 YOLO 的加速棒"
- 40 TOPS 的潜力只能用于 Model Zoo 的几十个模型的状态将会持续

---

## 总结

Hailo-10H 拥有 40 TOPS 的优秀硬件性能，但由于软件生态系统的封闭性和不成熟，开发者自由导入并活用模型**实质上是不可能的**。

本项目在摸索未记录的 API 的同时，构建了超越 Hailo 公司官方应用程序集（hailo-apps）的集成软件。然而，即便如此，自定义模型（WD-Tagger）的 NPU 执行仍因 DFC 的限制而未能实现。

**"工具严重不足，开发实质上无法进行"** — 这是经过数月 Hailo-10H 开发后的真实结论。

---

## 相关文档

- [`HAILO_SEMANTIC_SEARCH_DEVLOG.md`](./HAILO_SEMANTIC_SEARCH_DEVLOG.md) — CLIP 语义搜索开发日志（Phase 1~12+）
- [`ONNX_TO_HEF_CONVERSION_GUIDE.md`](./ONNX_TO_HEF_CONVERSION_GUIDE.md) — DFC 转换指南（参考资料）
- [`ONNX_TO_HEF_CONVERSION_REPORT.md`](./ONNX_TO_HEF_CONVERSION_REPORT.md) — WD-Tagger 转换失败报告
- [`CLIP_ONNX_DEVLOG.md`](./CLIP_ONNX_DEVLOG.md) — CLIP ONNX 回退开发日志
- [`HAILO_DEVICE_CONTROL.md`](./HAILO_DEVICE_CONTROL.md) — VDevice 设备管理设计
- [`../features/distributed-tagger-server.md`](../features/distributed-tagger-server.md) — 分布式标注服务器文档
