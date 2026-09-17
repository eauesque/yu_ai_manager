# Hailo-10H 生態系統評估

**建立日期**: 2026-03-19
**對象**: Hailo-10H (AI HAT 2 for Raspberry Pi 5)
**HailoRT**: v5.2.0
**DFC**: v5.2.0
**目的**: 記錄本專案中的 Hailo-10H 開發經驗，整理現實的限制與未來展望

---

## 總體評估

**硬體表現優異。軟體生態系統嚴重不足。**

Hailo-10H 是一款擁有 40 TOPS 推論效能的 NPU，硬體潛力十分充足。然而，由於軟體工具鏈封閉且不成熟，開發者自行攜帶模型進行推論**實質上不可行**。

本專案嘗試了 CLIP 語意搜尋、YOLO 物體偵測、LLM/VLM 對話、Whisper 語音辨識、分散式標籤伺服器等多方面活用 Hailo-10H 的開發，但穩定運作的功能**全部使用了從 Hailo 官方 Model Zoo 下載的預編譯 HEF**，自行從 ONNX 轉換為 HEF 成功的案例**一次也沒有**。

---

## 本專案的實作狀態

### 正常運作的功能（全部使用官方 HEF 下載）

| 功能 | 使用 API | HEF 取得來源 |
|------|---------|-----------|
| CLIP 影像編碼器 | `VDevice.create_infer_model()` | Hailo Model Zoo (S3) |
| YOLO 物體偵測 | `VDevice.create_infer_model()` | Hailo Model Zoo (S3) |
| LLM 對話 | `hailo_platform.genai.LLM` | Hailo GenAI Model Zoo |
| VLM 影像+文字推論 | `hailo_platform.genai.VLM` | Hailo GenAI Model Zoo |
| Whisper 語音辨識 | `hailo_platform.genai.Speech2Text` | Hailo GenAI Model Zoo |

### 無法運作的功能（HEF 轉換失敗）

| 功能 | 嘗試內容 | 結果 |
|------|-----------|------|
| WD-Tagger (SwinV2) | ONNX → HEF 轉換 | DFC 無法處理 LayerNormalization 而失敗 |
| WD-Tagger (ViT) | ONNX → HEF 轉換 | 同上 |
| WD-Tagger (ConvNeXt) | ONNX → HEF 轉換 | DFC 無法處理 Transpose 操作而失敗 |

### 實作特殊事項

本專案**直接呼叫** `hailo_platform` wheel 的 Python API 實作了全部功能。未使用 hailo-ollama 或 hailo-apps。

特別是以下項目是在 Hailo 公司官方提供之前自行建構的：

- **VDevice 排他控制裝置管理器** — CLIP/YOLO/LLM/VLM/S2T 於單一 VDevice 自動切換。hailo-apps 沒有裝置共享機制
- **多後端備援機制** — Hailo → CoreML → ONNX Runtime 透明自動切換
- **uint8 反量化管線** — 從 `quant_info` 的 scale/zero_point 還原 float32
- **LAN 分散式推論架構** — 多台機器的工作竊取並行標記

這些開發是在 **API 文件幾乎不存在的狀態**下完成的。InferModel API 的輸入輸出規格、緩衝區大小要求、量化參數的取得方式全部是從錯誤訊息與原始碼推測中解析出來的。

---

## Hailo Dataflow Compiler (DFC) 的問題

### DFC 是什麼

將 ONNX / TensorFlow 模型轉換為 Hailo-10H 用 HEF (Hailo Executable Format) 的編譯器。在 x86_64 Linux 上運行，透過以下管線轉換模型：

```
model.onnx → HAR (float32) → 最佳化 → 量化 (INT8) → 編譯 → model.hef
```

### 現實

**DFC 只能正常轉換 Hailo 為自家 Model Zoo 事先驗證過的架構。**

本專案的轉換嘗試（2026-03-06，DFC v5.2.0）：

| 模型 | 大小 | 錯誤 | 到達階段 |
|--------|-------|--------|---------|
| wd-swinv2-tagger-v3 | 446 MB | `IndexError` in `_convert_axes_to_nhwc` | 最佳化前 |
| wd-vit-tagger-v3 | 362 MB | 同上 | 最佳化前 |
| wd-convnext-tagger-v3 | 377 MB | `UnsupportedShuffleLayerError` | 最佳化前 |

3 個模型全部**在到達最佳化階段之前**就在解析器層級失敗。雖然準備了 500 張校正用圖片，但連使用的機會都沒有。

### 根本原因

DFC 的 ONNX 解析器無法處理以下運算子：

- `LayerNormalization`（多維張量的軸變換）
- `Transpose`（channels-last/first 轉換模式）

這些是 Transformer 系架構（SwinV2、ViT、ConvNeXt 等）的基本構成元素，2022 年以後的主流模型大多都在使用。

### DFC 的實質支援範圍

| 架構 | DFC 支援 | 依據 |
|---------------|---------|------|
| ResNet、MobileNet 等 CNN 系 | ✓ 支援 | Model Zoo 中大量存在 |
| YOLO v5/v8/v11 | ✓ 支援 | Model Zoo 中有 HEF |
| CLIP ViT (Hailo 版) | ✓ 支援 | Model Zoo 中有 HEF（由 Hailo 公司轉換） |
| SwinTransformer V2 | ✗ 不支援 | LayerNorm 轉換失敗 |
| Vision Transformer (通用) | ✗ 不支援 | LayerNorm 轉換失敗 |
| ConvNeXt | ✗ 不支援 | Transpose 轉換失敗 |

> **備註**: CLIP ViT 存在於 Model Zoo 中，很可能是 Hailo 公司內部進行了特殊處理（手動圖形轉換或自訂解析器）。即使是相同的 ViT，一般使用者用 DFC 轉換也會失敗。

---

## HEF 格式的問題

- **二進位規格未公開** — Hailo 未公開格式文件
- **除 DFC 外沒有其他生成方式** — 第三方工具無法製作 HEF
- **逆向工程也不切實際** — 需要 NPU 的指令集與資料流架構知識

也就是說，DFC 無法轉換的模型**無論如何都無法在 Hailo-10H 上執行**。不存在替代方案。

---

## 開發工具鏈評估

### hailo_platform (Python SDK)

| 項目 | 評估 |
|------|------|
| InferModel API | 可以運作，但文件極度不足 |
| GenAI API (LLM/VLM/S2T) | 相對易用。但有許多 undocumented 的行為 |
| Python wheel 發佈 | PyPI 上沒有。aarch64 wheel 需從原始碼建構 |
| 錯誤訊息 | 極為簡略。難以定位緩衝區大小不匹配的原因 |
| VDevice 管理 | 僅支援排他存取。不可多模型同時使用 |

### 開發中發現的 undocumented 行為

1. **InferModel API 才是正解** — 舊版 VStreams API（`InferVStreams`、`ConfigureParams.create_from_hef`）在 Hailo-10H 上會回傳 `HAILO_NOT_IMPLEMENTED`
2. **輸出為 uint8 量化** — 以 float32 分配緩衝區會出現 `buffer size mismatch`。需以 uint8 分配後再進行反量化
3. **`input()`/`output()` 是屬性** — 不是方法（與其他 Hailo API 不一致）
4. **`quant_info` 的取得** — 可透過 `infer_model.output().quant_info` 取得 scale/zero_point，但沒有任何文件說明這一點
5. **與 hailo-ollama 的排他** — 使用 VDevice 時需停止 hailo-ollama。從錯誤訊息難以判斷原因

---

## 競爭產品比較

### Ryzen AI (XDNA) NPU

| 項目 | Hailo-10H | Ryzen AI (XDNA) |
|------|----------|-----------------|
| 效能 | 40 TOPS | 16〜50 TOPS（依世代而異） |
| 模型攜入 | 需透過 DFC 轉換，通常失敗 | **ONNX Runtime 直接支援** |
| 開發者體驗 | 獨有工具鏈、文件不足 | `pip install onnxruntime-directml` 即可完成 |
| 生態系統 | 封閉、依賴 Model Zoo | ONNX / DirectML / Microsoft 合作 |
| 普及數量 | Pi + AI HAT、USB 加密狗（計劃中） | **數百萬台筆記型電腦已內建** |

Ryzen AI 的整合只需以下即可完成：

```python
import onnxruntime as ort
session = ort.InferenceSession("model.onnx", providers=["DmlExecutionProvider"])
```

Hailo-10H 無法做到同樣的事。不存在 ONNX Runtime Execution Provider。

### NVIDIA CUDA

| 項目 | Hailo-10H | NVIDIA CUDA |
|------|----------|-------------|
| 模型攜入 | 透過 DFC，Model Zoo 以外通常失敗 | ONNX / PyTorch / TensorFlow → 直接可用 |
| 工具鏈 | 不成熟、半封閉 | 成熟、公開、大量文件 |
| 開發者社群 | 極小 | 全球最大 |
| 價格帶 | 便宜（約 $70） | 昂貴（$200〜$2000+） |

Hailo 唯一的優勢是**價格與功耗**。

---

## 與 hailo-apps (2025-10) 的關係

### hailo-apps 概要

Hailo 公司於 2025 年 10 月發布的官方應用程式集。包含 20 個以上的範例應用：

- GenAI: voice_assistant、vlm_chat、agent_tools_example、whisper
- Pipeline: 物體偵測、姿態估計、人臉辨識、CLIP 分類、OCR
- Standalone: Python/C++ 的 HailoRT 學習用範例

### 與本專案的比較

| 項目 | hailo-apps | 本專案 |
|------|-----------|-------------|
| VLM 支援 | vlm_chat 應用 | `hailo_platform.genai.VLM` 直接實作 |
| CLIP | clip 應用 | 作為語意搜尋系統整合 |
| LLM | simple_llm_chat | 作為 GenAI Extension 整合 |
| Whisper | simple_whisper_chat | 作為 Speech-to-Text Extension 整合 |
| 裝置管理 | 無（假設單一應用） | **排他控制裝置管理器（CLIP/YOLO/LLM/VLM/S2T 自動切換）** |
| 後端備援 | 無 | **Hailo → CoreML → ONNX 自動切換** |
| 分散式推論 | 無 | **LAN 分散式工作竊取** |
| 整合度 | 個別範例應用 | 單一整合 WebUI 應用程式 |

本專案在 hailo-apps 公開之前，就已從 `hailo_platform` wheel 的低階 API 自行實作了同等以上的功能。

---

## 未來展望

### 短期（務實方案）

- **ONNX Runtime + LAN 分散式是唯一的實用解決方案** — 以分散式標籤伺服器的 ONNX 後端運行
- Hailo-10H 僅限於有官方 HEF 的用途（YOLO、CLIP、LLM、Whisper）使用
- 放棄自訂模型的 NPU 執行

### 中期（樂觀預期）

- ASUS 等廠商推出搭載 Hailo-10H 的 USB 加密狗 → 使用者增加
- 隨著使用者增加，可能對 Hailo 公司形成工具改善壓力
- DFC 的未來版本可能新增 Transformer 系支援

### 長期（結構性課題）

- 除非 Hailo 提供 ONNX Runtime EP，否則在開發者生態系統方面將輸給 Ryzen AI (XDNA)
- 即使硬體透過 USB 加密狗普及，若軟體自由度不足，將僅止於「跑得快的 YOLO 加速棒」
- 40 TOPS 的潛力持續僅能用於 Model Zoo 的數十個模型

---

## 總結

Hailo-10H 擁有 40 TOPS 的優異硬體效能，但由於軟體生態系統的封閉性與不成熟，開發者自行攜帶模型進行活用**實質上不可能**。

本專案在摸索 undocumented API 的過程中，建構了超越 Hailo 公司官方應用程式集（hailo-apps）的整合軟體。然而即便如此，自訂模型（WD-Tagger）的 NPU 執行仍因 DFC 的限制而無法實現。

**「工具嚴重不足，開發實質上無法進行」** — 這是經過數個月 Hailo-10H 開發後的真實結論。

---

## 相關文件

- [`HAILO_SEMANTIC_SEARCH_DEVLOG.md`](./HAILO_SEMANTIC_SEARCH_DEVLOG.md) — CLIP 語意搜尋開發日誌（Phase 1〜12+）
- [`ONNX_TO_HEF_CONVERSION_GUIDE.md`](./ONNX_TO_HEF_CONVERSION_GUIDE.md) — DFC 轉換指南（參考資料）
- [`ONNX_TO_HEF_CONVERSION_REPORT.md`](./ONNX_TO_HEF_CONVERSION_REPORT.md) — WD-Tagger 轉換失敗報告
- [`CLIP_ONNX_DEVLOG.md`](./CLIP_ONNX_DEVLOG.md) — CLIP ONNX 備援開發日誌
- [`HAILO_DEVICE_CONTROL.md`](./HAILO_DEVICE_CONTROL.md) — VDevice 裝置管理設計
- [`../features/distributed-tagger-server.md`](../features/distributed-tagger-server.md) — 分散式標籤伺服器文件
