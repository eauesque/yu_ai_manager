# ONNX to HEF 转换报告

**实施日期**：2026-03-06
**目的**：将 WD-Tagger ONNX 模型转换为 Hailo HEF 格式，使其可在 Raspberry Pi 5 + AI HAT 2 (Hailo-10H) 上进行推理
**结果**：失败（所有模型变体均无法转换）

---

## 环境

| 项目 | 详细 |
|------|------|
| OS | Ubuntu 24.04 (WSL2) |
| Python | 3.11.13 (以 uv 安装) |
| Hailo Dataflow Compiler | v5.2.0 |
| GPU | CUDA 12.8, Driver 591 |
| RAM | 151GB |

---

## 尝试的模型

### 1. wd-swinv2-tagger-v3 (SwinTransformer V2)

- **来源**：`SmilingWolf/wd-swinv2-tagger-v3` (446MB)
- **输入**：`[batch, 448, 448, 3]` float32
- **输出**：`[batch, 10861]` float32
- **结果**：失败
- **错误**：`IndexError: list index out of range` in `_convert_axes_to_nhwc`
- **原因**：LayerNormalization 的轴转换在 DFC v5.2.0 中尚未支持

### 2. wd-vit-tagger-v3 (Vision Transformer)

- **来源**：`SmilingWolf/wd-vit-tagger-v3` (362MB)
- **输入**：`[batch, 448, 448, 3]` float32
- **输出**：`[batch, 10861]` float32
- **结果**：失败
- **错误**：同上（`IndexError` in `_convert_axes_to_nhwc`）
- **原因**：ViT 同样使用 LayerNormalization，在相同位置失败

### 3. wd-convnext-tagger-v3 (ConvNeXt)

- **来源**：`SmilingWolf/wd-convnext-tagger-v3` (377MB)
- **输入**：`[batch, 448, 448, 3]` float32
- **输出**：`[batch, 10861]` float32
- **结果**：失败
- **错误**：`UnsupportedShuffleLayerError`（大量 Transpose 节点）+ `UnsupportedModelError`（Mul 的 shape 不匹配）
- **原因**：ConvNeXt 的 channels-last 设计所伴随的 Transpose 操作 DFC 不支持

---

## 失败的根本原因

DFC v5.2.0 的 ONNX 解析器无法正确处理以下操作：

1. **LayerNormalization**：对 3 维以上张量进行 LayerNorm 的 NHWC 轴转换时发生索引错误
2. **Transpose (Shuffle)**：ConvNeXt 中用于 channels-last/first 转换的 Transpose 模式不支持

WD-Tagger 的所有变体（SwinV2、ViT、ConvNeXt）均大量使用 LayerNormalization 的现代架构，在 DFC v5.2.0 中无法转换。

---

## 校准数据

- 从 ComfyUI / Stable Diffusion forge 的输出图片中随机选取 500 张
- 应用与 WD-Tagger 相同的预处理（RGBA→RGB 白底合成、保持宽高比缩放、白色填充、BGR 转换）
- 已保存为 `calibration_data.npy`，但因未到达转换步骤而未使用

---

## 未来展望

- **DFC 未来版本**：若 Hailo 改善了 LayerNormalization / Transpose 的支持，值得重新尝试
- **模型修改**：将 LayerNorm 替换为 BatchNorm 的修改模型（工作量大，有精度劣化风险）
- **维持现状**：继续使用 ONNX Runtime (CPU) 进行推理
