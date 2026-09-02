# Hailo-10H 裝置控制

## 概述

Hailo-10H NPU 可以**同時執行多個模型**。
內建的 ROUND_ROBIN 排程器會自動在模型之間分時共享硬體存取。

yu_ai_manager 維持一個共享的 VDevice，讓 CLIP、YOLO、LLM、VLM、Speech2Text
可同時載入並進行推論。透過 `group_id` 也可與外部程序 (hailo-ollama) 共享。

## 架構

```
┌─────────────────────────────────────────────┐
│              Shared VDevice                  │
│         (group_id = YU_SHARED)               │
│                                              │
│  ┌─────────┐ ┌─────────┐ ┌───────────────┐  │
│  │  CLIP   │ │  YOLO   │ │  LLM (GenAI)  │  │
│  │InferMdl │ │InferMdl │ │  VLM / S2T    │  │
│  └─────────┘ └─────────┘ └───────────────┘  │
│                                              │
│     HailoRT ROUND_ROBIN Scheduler            │
└─────────────────────────────────────────────┘
```

- InferModel API (CLIP, YOLO) 和 GenAI API (LLM, VLM, S2T) 在同一 VDevice 上共存
- 所有模型必須建立在**同一個 VDevice 實例**上（建立在不同實例上將無法運作）

## 兩種模式比較

| | Python SDK (Hailo VLM) | hailo-ollama-vlm (OpenAI 相容) |
|---|---|---|
| 裝置管理 | yu 的 device_manager | 外部 C++ 伺服器 |
| 與 CLIP 搜尋共存 | 可（同時動作） | 可（group_id 共享，v5.3.0+） |
| 推論速度 | 相同 | 相同 |
| 額外開銷 | ~15ms | ~200-400ms (base64+HTTP) |
| 多客戶端 | 不可 | 可能 |
| Flask 執行緒 | 推論中阻塞 | 僅 HTTP 等待 |

## VDevice 共享 (group_id)

### 程序內共享

`device_manager.py` 自動管理。所有模型共享同一個 VDevice。

可透過環境變數變更 group_id：
```bash
export HAILO_VDEVICE_GROUP_ID=MY_GROUP
```

預設值：`YU_SHARED`

### 與 hailo-ollama 共存 (v5.3.0+)

hailo-ollama v5.3.0 以後支援 `HAILO_OLLAMA_VDEVICE_GROUP_ID` 環境變數。
設定與 yu_ai_manager 相同的 group_id，即可讓兩個程序共享裝置：

```bash
# yu_ai_manager 端
export HAILO_VDEVICE_GROUP_ID=SHARED

# hailo-ollama 端
HAILO_OLLAMA_VDEVICE_GROUP_ID=SHARED hailo-ollama
```

**注意**：yu_ai_manager 需要 HailoRT 5.2.0 以上才能使 group_id 生效。
hailo-ollama 需要 v5.3.0 以上才能接受 group_id。

## device_manager API

### 取得模型

```python
from core.hailo_device_core.device_manager import acquire_device, acquire_genai

# InferModel (CLIP, YOLO)
infer_model, configured, quant_params = acquire_device("clip", "/path/to.hef")

# GenAI (LLM, VLM, S2T)
llm = acquire_genai("llm", "/path/to.hef", lambda vd, p: LLM(vd, p))
```

- 同一 owner + 同一 HEF -> 重複使用現有 session
- 同一 owner + 不同 HEF -> 釋放舊模型並建立新模型
- 不同 owner -> **共存**（舊模型不會被釋放）

### 釋放模型

```python
from core.hailo_device_core.device_manager import release_device, shutdown_all

release_device("clip")   # 僅釋放 CLIP，其他繼續運行
shutdown_all()            # 釋放所有模型 + VDevice（程序結束時）
```

### 狀態確認

```python
from core.hailo_device_core.device_manager import (
    get_active_owners, is_model_active,
    is_hailo_available, is_genai_available,
)

get_active_owners()       # ["clip", "yolo", "llm"]
is_model_active("clip")   # True
```

## 故障排除

### VDevice 建立錯誤

**症狀**：`HAILO_OUT_OF_PHYSICAL_DEVICES(74)` 或 `Failed to create VDevice`

**原因**：其他程序以不同的 group_id 佔用了裝置

**處理方式**：
1. 確認 hailo-ollama 是否正在運行：
   ```bash
   ps aux | grep hailo-ollama
   ```
2. 統一 group_id 或停止程序：
   ```bash
   sudo systemctl stop hailo-ollama
   ```

### 裝置未被釋放

**處理方式**：
1. 重新啟動 yu 的程序
2. 確認是否有殭屍程序：
   ```bash
   sudo lsof /dev/hailo* 2>/dev/null
   kill <PID>
   ```
3. 重設 Hailo 驅動程式：
   ```bash
   sudo systemctl restart hailort.service
   ```

## API 使用指南

| 模型結構 | 建議 API | 原因 |
|---|---|---|
| 簡單 (1 輸入, YOLO 等) | `InferModel` | 使用 `create_infer_model()` + `configure()` 即可運作 |
| 複雜 (2 輸入+, Whisper 等) | `GenAI SDK` | InferModel 會回傳 `INVALID_ARGUMENT` |
| CLIP 編碼器 | `InferModel` | 1 輸入 1 輸出，沒有問題 |
| LLM (qwen2.5 等) | `GenAI SDK` | 需要自回歸解碼 |

## 歷史記錄

- **v4.61.0**：遷移至共享 VDevice 方式。廢除排他 acquire/release，支援 CLIP + YOLO + LLM 同時動作。
- **v4.60.1**：統一所有消費者透過 device_manager（排他方式）。
- **v4.60.0 以前**：各消費者個別呼叫 VDevice()，頻繁發生衝突錯誤。
