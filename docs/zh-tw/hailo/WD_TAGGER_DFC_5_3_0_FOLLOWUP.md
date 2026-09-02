# DFC 轉換後續：DFC v5.3.0 上的 WD-Tagger 模型

**日期**: 2026-04-06
**DFC 版本**: 5.3.0
**後續報告**: [`ONNX_TO_HEF_CONVERSION_REPORT.md`](ONNX_TO_HEF_CONVERSION_REPORT.md) (2026-03-06)
**環境**: WSL2 (Ubuntu 24.04), x86_64

---

## 背景

在 2026 年 3 月，我報告了三個 WD-Tagger 變體（SwinV2、ViT、ConvNeXt）在 Hailo Dataflow Compiler v5.2.0 下的剖析器階段全部失敗，未能到達量化步驟。原始報告保存在 [`ONNX_TO_HEF_CONVERSION_REPORT.md`](ONNX_TO_HEF_CONVERSION_REPORT.md)。

我現已在 DFC v5.3.0 下重新測試所有三個模型。本文件為後續報告。

---

## 結果摘要

| 模型 | 大小 | DFC 5.2.0 錯誤 | DFC 5.3.0 錯誤 | 變化 |
|---|---|---|---|---|
| `wd-swinv2-tagger-v3` | 446 MB | `_convert_axes_to_nhwc` 中的 `IndexError` | 相同 | **無** |
| `wd-vit-tagger-v3` | 362 MB | 相同 | 相同（onnxsim 重試後） | 新增重試流程 |
| `wd-convnext-tagger-v3` | 377 MB | `UnsupportedShuffleLayerError` | 相同 + 額外 `UnsupportedModelError` | **錯誤增加** |

**三個模型仍然全部在剖析器階段失敗。** 量化步驟（已準備 500 張校準影像）仍未可達，與 v5.2.0 執行時相同。

---

## DFC v5.3.0 中的變化

雖然失敗依然存在，但與 v5.2.0 相比，DFC v5.3.0 中可見以下改進：

### 1. 新增 `_create_layer_normalization_layer` 方法

此方法在 v5.2.0 中根本不存在。DFC v5.3.0 現在透過專用程式碼路徑嘗試明確處理 `LayerNormalization` 運算子。這清楚顯示了正在進行中的開發努力。

然而，**內部實現不完整**：該方法被呼叫，但其內部呼叫 `_convert_axes_to_nhwc` 仍會在 v5.2.0 中失敗的相同張量形狀上拋出 `IndexError: list index out of range`。

### 2. onnxsim 簡化 + 重試流程新增

對於 ViT 和 ConvNeXt，DFC v5.3.0 現在自動使用 `onnxsim` 簡化輸入 ONNX 模型並重試剖析。簡化後的模型被保存為 `model.sim.onnx`，位於輸入檔案旁。這對於具有冗餘或複雜 ONNX 圖的模型是有用的新安全機制。

但對於這些特定模型，重試**在完全相同的位置失敗**，因為根本問題在 `_convert_axes_to_nhwc` 中，而非 ONNX 圖結構。

### 3. 終端節點建議

對於 ConvNeXt，DFC v5.3.0 現在會在剖析器退出時產生特定的終端節點建議，並提示使用者使用這些節點重試。這是一項貼心的使用者體驗改進。

使用建議的終端節點重試也失敗，同樣因為根本原因在於 LayerNormalization / Transpose 處理，而非終端節點選擇。

---

## 根本原因（自 3 月起未變）

DFC ONNX 剖析器仍無法正確轉換 `LayerNormalization` 運算子的軸，當輸入張量不遵循預期的 NCHW 格式時。相關呼叫鏈現在是：

```
_create_layer_normalization_layer
  → get_layer_normalization_info
    → _convert_axes_to_nhwc
      → IndexError: list index out of range
```

特別是對於 ConvNeXt，在多個 `Transpose` 節點（`token_5` 至 `token_34`）上的額外 `UnsupportedShuffleLayerError` 表明 Transpose 運算子處理在此架構使用的 channels-last 模式上仍未完整。

簡而言之：**新程式碼路徑存在，但尚未處理原本失敗的情況。**

---

## 需求（自 3 月起未變）

3 月文章中的兩項需求均仍然成立：

### 1. 修復多維 `LayerNormalization` 的 `_convert_axes_to_nhwc`

該方法現在可以被觸及（很好），但軸對應邏輯本身對於非 NCHW 輸入張量會失敗。現代 Transformer 架構（SwinV2、ViT、ConvNeXt）全部需要此功能。

### 2. Hailo-10H 的 ONNX Runtime 執行提供者

這將使完整的 DFC 轉換成為可選項，並從結構上解決此類問題。許多社群使用者將受益於能在 Hailo-10H 上執行未修改的 ONNX 模型，即使吞吐量低於完全量化的 HEF。

---

## 關於「ONNX Runtime Hailo Pipeline」元件的說明

DFC v5.3.0 發行說明提及「ONNX Runtime Hailo Pipeline」元件。如果此元件可被用於在 Hailo-10H 上執行 WD-Tagger 推論，**無須**完整 DFC 轉換（即作為 ONNX Runtime 執行提供者，將支援的子圖委派到 NPU），我非常希望得到官方對正確方法的指導。

具體而言：

- 此元件是否旨在成為 DFC 目前無法剖析之模型的前進路徑？
- 是否需要部分 HEF（即可剖析的子圖編譯為 HEF，其餘透過 ORT 在 CPU 上執行）？
- 是否有樣本程式碼或教學說明如何將其用於 Transformer 風格的 ONNX 模型？

---

## 復現

重現這些結果的確切步驟：

```bash
# 1. 在乾淨的 Python venv 中設定 DFC v5.3.0
python3.11 -m venv venv
source venv/bin/activate
pip install hailo_dataflow_compiler-5.3.0-py3-none-linux_x86_64.whl

# 2. 下載三個 WD-Tagger ONNX 模型
for variant in swinv2 vit convnext; do
  huggingface-cli download \
    "SmilingWolf/wd-${variant}-tagger-v3" \
    model.onnx --local-dir "./wd-${variant}-tagger-v3"
done

# 3. 嘗試剖析各模型
for variant in swinv2 vit convnext; do
  hailo parser onnx "./wd-${variant}-tagger-v3/model.onnx" \
    --hw-arch hailo10h \
    --tensor-shapes input_1:1,448,448,3 2>&1 | tee "${variant}_5.3.0.log"
done
```

各執行的完整錯誤日誌可應要求提供。

---

## 測試環境

| 項目 | 詳細 |
|---|---|
| OS | Ubuntu 24.04 (WSL2) |
| CPU | AMD Ryzen 5 5600X |
| RAM | 151 GB |
| Python | 3.11 |
| DFC | 5.3.0 |
| 模型 | `SmilingWolf/wd-{swinv2,vit,convnext}-tagger-v3` (HuggingFace) |
| 校準數據 | 500 個 ComfyUI / SD 輸出（未使用——未達量化步驟） |

---

## 結語

DFC v5.3.0 中可見的開發努力（`_create_layer_normalization_layer`、onnxsim 重試流程、終端節點建議）確實令人鼓舞——這正是社群一直希望看到的進展類型。剩餘的差距是 `_convert_axes_to_nhwc` 內的實際實現，現已可達但對這些模型尚未正確。

我將在每個 DFC 發行版本中繼續重新測試，並在情況改變時發佈後續更新。如果任何 Hailo 人員閱讀此文，並希望取得完整錯誤日誌、ONNX 模型 SHA-256 雜湊或最小復現器，我樂於提供。
