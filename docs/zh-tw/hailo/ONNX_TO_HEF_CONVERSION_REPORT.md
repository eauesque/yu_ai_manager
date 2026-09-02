# ONNX to HEF 轉換報告

**實施日期**：2026-03-06
**目的**：將 WD-Tagger ONNX 模型轉換為 Hailo HEF 格式，使其可在 Raspberry Pi 5 + AI HAT 2 (Hailo-10H) 上進行推論
**結果**：失敗（所有模型變體均無法轉換）

---

## 環境

| 項目 | 詳細 |
|------|------|
| OS | Ubuntu 24.04 (WSL2) |
| Python | 3.11.13 (以 uv 安裝) |
| Hailo Dataflow Compiler | v5.2.0 |
| GPU | CUDA 12.8, Driver 591 |
| RAM | 151GB |

---

## 嘗試的模型

### 1. wd-swinv2-tagger-v3 (SwinTransformer V2)

- **來源**：`SmilingWolf/wd-swinv2-tagger-v3` (446MB)
- **輸入**：`[batch, 448, 448, 3]` float32
- **輸出**：`[batch, 10861]` float32
- **結果**：失敗
- **錯誤**：`IndexError: list index out of range` in `_convert_axes_to_nhwc`
- **原因**：LayerNormalization 的軸轉換在 DFC v5.2.0 中尚未支援

### 2. wd-vit-tagger-v3 (Vision Transformer)

- **來源**：`SmilingWolf/wd-vit-tagger-v3` (362MB)
- **輸入**：`[batch, 448, 448, 3]` float32
- **輸出**：`[batch, 10861]` float32
- **結果**：失敗
- **錯誤**：同上（`IndexError` in `_convert_axes_to_nhwc`）
- **原因**：ViT 同樣使用 LayerNormalization，在相同位置失敗

### 3. wd-convnext-tagger-v3 (ConvNeXt)

- **來源**：`SmilingWolf/wd-convnext-tagger-v3` (377MB)
- **輸入**：`[batch, 448, 448, 3]` float32
- **輸出**：`[batch, 10861]` float32
- **結果**：失敗
- **錯誤**：`UnsupportedShuffleLayerError`（大量 Transpose 節點）+ `UnsupportedModelError`（Mul 的 shape 不匹配）
- **原因**：ConvNeXt 的 channels-last 設計所伴隨的 Transpose 操作 DFC 不支援

---

## 失敗的根本原因

DFC v5.2.0 的 ONNX 解析器無法正確處理以下操作：

1. **LayerNormalization**：對 3 維以上張量進行 LayerNorm 的 NHWC 軸轉換時發生索引錯誤
2. **Transpose (Shuffle)**：ConvNeXt 中用於 channels-last/first 轉換的 Transpose 模式不支援

WD-Tagger 的所有變體（SwinV2、ViT、ConvNeXt）均大量使用 LayerNormalization 的現代架構，在 DFC v5.2.0 中無法轉換。

---

## 校準資料

- 從 ComfyUI / Stable Diffusion forge 的輸出圖片中隨機選取 500 張
- 套用與 WD-Tagger 相同的前處理（RGBA→RGB 白底合成、保持長寬比縮放、白色填充、BGR 轉換）
- 已儲存為 `calibration_data.npy`，但因未到達轉換步驟而未使用

---

## 未來展望

- **DFC 未來版本**：若 Hailo 改善了 LayerNormalization / Transpose 的支援，值得重新嘗試
- **模型修改**：將 LayerNorm 替換為 BatchNorm 的修改模型（工作量大，有精度劣化風險）
- **維持現狀**：繼續使用 ONNX Runtime (CPU) 進行推論
