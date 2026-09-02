# Hailo-10H AI Hat+ 開發文件

使用 Raspberry Pi 5 + Hailo AI Hat+ (Hailo-10H) 進行 AI 推論的實作記錄。

本文件分享在官方文件不足之處透過實際開發所獲得的實用知識。

## 文件索引

| 檔案 | 說明 |
|------|------|
| [HAILORT_5_3_0_MIGRATION.md](HAILORT_5_3_0_MIGRATION.md) | HailoRT 5.2.0 → 5.3.0 遷移記錄：API 差異、設備節點重命名（`/dev/h1x-0`）、HEF 相容性、煙測試指令碼 |
| [VDEVICE_SHARING_PATTERN.md](VDEVICE_SHARING_PATTERN.md) | 共享 VDevice 管理器的實作模式，允許多個模型（YOLO/CLIP/LLM/VLM/Whisper）在同一程序中共存 |
| [PI5_NUMA_CMA_CONSTRAINTS.md](PI5_NUMA_CMA_CONSTRAINTS.md) | Pi 5 在 `numa=fake=8` 下的 CMA 分配限制。為何 `cma=1G` 會默默失敗、已確認的上限且為建議值的 `cma-512`（`config.txt` 中的 `dtoverlay=cma,cma-512`）、Hailo GenAI 記憶體需求、`VDevice.release()` 的 CMA 未返還行為 |
| [HAILO_SEMANTIC_SEARCH_DEVLOG.md](HAILO_SEMANTIC_SEARCH_DEVLOG.md) | CLIP 語意搜尋開發日誌。各階段實作記錄、遭遇的問題與解決方案 |
| [HAILO_DEVICE_CONTROL.md](HAILO_DEVICE_CONTROL.md) | Hailo 設備控制方法、VDevice 管理、獨佔訪問控制、模型切換 |
| [ONNX_TO_HEF_CONVERSION_GUIDE.md](ONNX_TO_HEF_CONVERSION_GUIDE.md) | ONNX 轉 HEF 轉換程序。Dataflow Compiler、量化、故障排除 |
| [ONNX_TO_HEF_CONVERSION_REPORT.md](ONNX_TO_HEF_CONVERSION_REPORT.md) | 轉換驗證報告（DFC v5.2.0）。3 個 WD-Tagger 變體的詳細失敗分析 |
| [WD_TAGGER_DFC_5_3_0_FOLLOWUP.md](WD_TAGGER_DFC_5_3_0_FOLLOWUP.md) | DFC v5.3.0 後續追蹤。相同 3 個 WD-Tagger 模型的重新測試（仍失敗）、加上 v5.3.0 觀察到的改進（新增 `_create_layer_normalization_layer`、onnxsim 重試流程、端點建議） |
| [CLIP_ONNX_DEVLOG.md](CLIP_ONNX_DEVLOG.md) | CLIP ONNX 多後端開發日誌。無 Hailo 硬體環境的備用方案 |
| [HAILO_CMA_LEAK_HAILORT_5_3_0.md](HAILO_CMA_LEAK_HAILORT_5_3_0.md) | **CMA leak 的結構性限制與實測**。`VDevice.release()` 不會回收、推論中持續洩漏（約 14 MB/分鐘），以及**子程序 kill、程序結束、模組卸載均無法回收**（Phase 0 PoC 獨立實測 2 次，SIGTERM + 等待 30 秒僅 +8 MB）。確實的回收手段僅有 Pi 本體重新啟動 **（舊結論。經 HailoRT / driver 5.4.0 重新試驗後已於 [HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md](HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md) §8 訂正）** |
| [HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md](HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md) | **上述 CMA leak 判定的訂正與重新驗證**。以 HailoRT / driver 5.4.0 對官方 vanilla 與 `FOLL_LONGTERM` 修正版進行 A/B 比較，訂正舊判定僅著眼於首次 HEF 載入後 `CmaFree` 絕對回收量所導致的誤判。附 v5.3.0 → v5.4.0 原始碼差異、自行建置程序的陷阱、實測數據 |
| [HAILO_AUTO_REBOOT_PHASE05.md](HAILO_AUTO_REBOOT_PHASE05.md) | 因應上述而採用的自動 reboot 路線運用指南。觀測階段（僅記錄 `would_fire` 而不重新啟動）、判定閾值、預設 `mode = "off"` 的理由 |
| [HAILO_AUTO_REBOOT_PHASE05_RUNBOOK.md](HAILO_AUTO_REBOOT_PHASE05_RUNBOOK.md) | 同階段針對本環境的運行手冊。觀測的啟動、確認、結束程序 |
| [HAILO_LLM_SUBPROCESS_DEVLOG.md](HAILO_LLM_SUBPROCESS_DEVLOG.md) | 解決 cold_load（約 71 秒）期間 Quart event loop 因 GIL 而卡死問題的實作日誌，透過將 LLM chat 推論隔離至 subprocess 解決 |
| [HAILO_10H_ECOSYSTEM_ASSESSMENT.md](HAILO_10H_ECOSYSTEM_ASSESSMENT.md) | Hailo-10H 生態系評估（2026-03-19，HailoRT/DFC v5.2.0 時點） |

## 重要已知問題

### 環境 / Raspberry Pi 5

- **Pi 5（8 GB）上的 CMA 上限為 512 MB，設定位置在 `config.txt`**：預設核心採用 `numa=fake=8`，將 RAM 分成 8 × 1 GB 的 NUMA 節點。CMA 必須收斂在單一節點邊界內，`cma-1024` 與 `cma-768` 會默默失敗（`CmaTotal=0`，無核心恐慌）。**`cma-512` 是已確認的上限且為建議值**（於 2026-05-16 透過 overlay 重新驗證，`CmaTotal: 524288 kB`）。因 2026-05 的 firmware 迴歸，應使用 `/boot/firmware/config.txt` 中的 `dtoverlay=cma,cma-512`，而非 cmdline 的 `cma=`。詳見 [PI5_NUMA_CMA_CONSTRAINTS.md](PI5_NUMA_CMA_CONSTRAINTS.md)
- **重新啟動後務必驗證 CMA**：`grep CmaTotal /proc/meminfo` — 值為 0 表示設定被忽略
- **`VDevice.release()` 不會返還 CMA**：CMA 在整個 OS 會話期間內保留。請將 VDevice 視為會話範圍的單例。**即使程序重新啟動也不會回收** —— Phase 0 PoC 獨立實測 2 次，證實無論是子程序 kill、程序結束、還是模組卸載，皆無法回收（SIGTERM + 等待 30 秒僅 +8 MB，預期值 ≥250 MB）。確實的回收手段僅有 Pi 本體的 `sudo reboot`（PCIe power-cycle）。詳情與採用的對策參見 [HAILO_CMA_LEAK_HAILORT_5_3_0.md](HAILO_CMA_LEAK_HAILORT_5_3_0.md)。**訂正**：本項基於舊測量。經 HailoRT / driver 5.4.0 的 A/B 重新試驗，實用上的 CMA 洩漏並未再現，已於 [HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md](HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md) §8 訂正
- **`numa=fake=8` 影響 Node.js 安裝**：每 NUMA 節點記憶體（1 GB）被誤認為總 RAM，導致 npm/node 安裝程式中止。已上報上游作為 [anthropics/claude-code#33864](https://github.com/anthropics/claude-code/issues/33864)
- **Python wheel 需要源碼構建**：PyPI 或 Hailo Developer Zone 上沒有 aarch64 wheel
- **與 hailo-ollama 互斥**：使用 VDevice 時必須停止 hailo-ollama
- **程序退出時 VDevice 洩漏**：用 `lsof /dev/hailo*` 檢查，用 `kill PID` 解決

### VDevice / API

- **使用 InferModel API**：`VDevice.create_infer_model()` 是正確的方法。在 Hailo-10H 上，舊版 VStreams API（`InferVStreams`、`ConfigureParams.create_from_hef`）返回 `HAILO_NOT_IMPLEMENTED`
- **InferModel 僅支援簡單模型**：單輸入 YOLO HEF 可行，但對 2 輸入 4 輸出的 Whisper HEF，`configure()` 返回 `HAILO_INVALID_ARGUMENT`。對複雜模型使用 GenAI SDK
- **VDevice 對應一個實體設備**：同時建立兩個 `VDevice()` 實例會導致 `HAILO_OUT_OF_PHYSICAL_DEVICES(74)`
- **切換模型時完全釋放 VDevice**：單純將 Python 參考設為 `None` 不夠。在建立新 VDevice 之前，用 `VDevice.release()` 明確釋放實體設備
- **`set_format_type(FormatType.FLOAT32)` 在 hailort 5.2.0 中不支援**：`format_type` 屬性不存在。手動處理 uint8 量化/去量化，或使用 GenAI SDK
- **輸出為 uint8 量化**：將輸出緩衝區分配為 float32 會導致 `buffer size mismatch`。分配為 uint8，並使用去量化參數（scale、zero_point）轉換為 float32

### GenAI（LLM / VLM / Speech2Text）

- **HailoRT 5.3.0 中 `temperature=0.0` 被拒絕**：`LLM.generate()` 使用 `temperature=0` 時拋出 `HAILO_INVALID_ARGUMENT`。呼叫前進行鉗制：`temperature = max(temperature, 0.01)`。影響任何預設發送 `temperature=0` 的 OpenAI 相容客戶端
- **GenAI × 2 並行載入是可能的**：LLM + Whisper-tiny 可在同一 VDevice 上同時載入（HailoRT 5.3.0 確認）。兩者都載入時的 CMA 餘裕：256 MB 中約 10 MB。Whisper-base 或更大將可能溢位
- **LLM + Whisper-tiny CMA 預算**：約 246 MB 合計（實測）。參見 [PI5_NUMA_CMA_CONSTRAINTS.md](PI5_NUMA_CMA_CONSTRAINTS.md) 查看完整模型 CMA 數據

### Whisper（語音識別）

- **使用 GenAI SDK**：`hailo_platform.genai.Speech2Text` 提供完整管線。編碼器+解碼器完全在 NPU 上運行
- **HEF 為僅解碼器**：`Whisper-Base.hef` 有 2 個輸入（encoder_features + token_embeddings）和 4 個輸出（詞彙分成 4 部分）。不與 InferModel API 配合使用
- **GenAI SDK 輸入**：小端 float32（`<f4`）、PCM 音訊資料歸一化至 [-1,1]
- **ONNX 備用方案**：GenAI SDK 無可用時，使用 HuggingFace ONNX 模型在 CPU 上執行編碼器+解碼器

### YOLO（物體偵測）

- **與 InferModel API 配合使用**：單輸入 HEF 無問題
- **ONNX 備用方案**：Hailo 無可用時，自動下載 `yolo11n.onnx`。輸出 `(1,84,8400)` 與 yolov8n 相容
- **初始化失敗冷卻期**：引擎初始化失敗後，60 秒內抑制重試

### 分散推論

- **需要健康檢查**：在開始分散處理前，使用 `filter_available()` 驗證遠端節點狀態
- **遠端失敗時**：剩餘項目回退至本機處理。恢復的節點在下一批次自動偵測
- **工作負載分散**：GPU 與 NPU 之間的速度差異很大，使得均勻分散效率不佳。基於吞吐量量測的動態分配是未來任務
