# ONNX to HEF Conversion Report

**Date**: 2026-03-06
**Objective**: Convert WD-Tagger ONNX models to Hailo HEF format for inference on Raspberry Pi 5 + AI HAT 2 (Hailo-10H)
**Result**: Failed (conversion impossible for all model variants)

---

## Environment

| Item | Details |
|------|---------|
| OS | Ubuntu 24.04 (WSL2) |
| Python | 3.11.13 (installed via uv) |
| Hailo Dataflow Compiler | v5.2.0 |
| GPU | CUDA 12.8, Driver 591 |
| RAM | 151GB |

---

## Models Tested

### 1. wd-swinv2-tagger-v3 (SwinTransformer V2)

- **Source**: `SmilingWolf/wd-swinv2-tagger-v3` (446MB)
- **Input**: `[batch, 448, 448, 3]` float32
- **Output**: `[batch, 10861]` float32
- **Result**: Failed
- **Error**: `IndexError: list index out of range` in `_convert_axes_to_nhwc`
- **Cause**: LayerNormalization axis conversion is unsupported in DFC v5.2.0

### 2. wd-vit-tagger-v3 (Vision Transformer)

- **Source**: `SmilingWolf/wd-vit-tagger-v3` (362MB)
- **Input**: `[batch, 448, 448, 3]` float32
- **Output**: `[batch, 10861]` float32
- **Result**: Failed
- **Error**: Same as above (`IndexError` in `_convert_axes_to_nhwc`)
- **Cause**: ViT also uses LayerNormalization and fails at the same point

### 3. wd-convnext-tagger-v3 (ConvNeXt)

- **Source**: `SmilingWolf/wd-convnext-tagger-v3` (377MB)
- **Input**: `[batch, 448, 448, 3]` float32
- **Output**: `[batch, 10861]` float32
- **Result**: Failed
- **Error**: `UnsupportedShuffleLayerError` (numerous Transpose nodes) + `UnsupportedModelError` (Mul shape mismatch)
- **Cause**: Transpose operations arising from ConvNeXt's channels-last design are unsupported by DFC

---

## Root Cause of Failures

The ONNX parser in DFC v5.2.0 cannot correctly process the following operations:

1. **LayerNormalization**: An index error occurs during NHWC axis conversion of LayerNorm on tensors with 3 or more dimensions
2. **Transpose (Shuffle)**: The Transpose patterns used for channels-last/first conversion in ConvNeXt are unsupported

All WD-Tagger variants (SwinV2, ViT, ConvNeXt) are modern architectures that heavily use LayerNormalization, making conversion impossible with DFC v5.2.0.

---

## Calibration Data

- 500 images randomly selected from ComfyUI / Stable Diffusion forge outputs
- Applied the same preprocessing as WD-Tagger (RGBA to RGB white-background compositing, aspect-ratio-preserving resize, white padding, BGR conversion)
- Saved as `calibration_data.npy` but was unused as the conversion step was never reached

---

## Future Possibilities

- **Future DFC versions**: If Hailo improves LayerNormalization / Transpose support, it is worth reattempting conversion
- **Model modification**: Creating modified models with LayerNorm replaced by BatchNorm (high effort, risk of accuracy degradation)
- **Status quo**: Continue inference using ONNX Runtime (CPU)
