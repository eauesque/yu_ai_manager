# 分散推論伺服器 (Distributed Inference Server)

**狀態**: 實作完成 (v4.53.2)
**目標**: `deploy/hailo_tagger_server.py`
**目的**: 在區域網路內的多台機器上分散執行推論（標記、CLIP、YOLO、Whisper）

---

## 概述

將 YU AI Manager 的推論功能分散到區域網路內多台機器的獨立 HTTP 伺服器。
不需要安裝 YU AI Manager 本體，僅需 Python 和相關依賴套件即可運作。

```
┌─────────────────────────────┐
│   YU AI Manager（主機）      │
│   Inference Server Registry │
│   共享佇列 / 工作竊取        │
└──────────┬──────────────────┘
      ┌────┼────────────┐
 ┌────▼────┐ ┌─────▼─────┐ ┌────▼────┐
 │ Pi5 A   │ │ Windows B │ │ Pi5 C   │
 │Hailo NPU│ │CUDA GPU   │ │ONNX CPU │
 │:9090    │ │:9090      │ │:8080    │
 └─────────┘ └───────────┘ └─────────┘
```

### 支援的推論模式

| 模式 | 端點 | 說明 |
|------|------|------|
| **Tagger** | `POST /tag` | WD-Tagger 標記（僅在指定 `--model-dir` 時有效） |
| **CLIP** | `POST /clip-encode` | CLIP ViT-B/16 圖片編碼（語意搜尋用） |
| **YOLO** | `POST /yolo-detect` | YOLOv11n / YOLOv8n 物體偵測 |
| **Whisper** | `POST /whisper-transcribe` | 語音轉文字 |

所有模式皆採用延遲初始化（lazy-init），在首次請求時載入模型。
CLIP 和 YOLO 的 ONNX 模型在未部署時會自動下載。

---

## 推論後端與提供者

### 後端優先順序

每個推論模式按以下優先順序選擇後端：

| 模式 | 第1 | 第2 | 第3 |
|------|-----|-----|-----|
| Tagger | Hailo NPU | ONNX | — |
| CLIP | Hailo NPU | ONNX（自動下載） | — |
| YOLO | Hailo NPU | ONNX（自動下載） | — |
| Whisper | Hailo GenAI SDK | faster-whisper | whisper.cpp |

### ONNX Runtime 提供者自動選擇

ONNX 後端會根據平台自動選擇最快的提供者：

| 優先順序 | 提供者 | 平台 |
|---------|--------|------|
| 1 | TensorRT | NVIDIA GPU（最快，需 TensorRT SDK） |
| 2 | CUDA | NVIDIA GPU |
| 3 | ROCm | AMD GPU (Linux) |
| 4 | MIGraphX | AMD GPU (Linux) |
| 5 | DirectML | Windows GPU (NVIDIA/AMD/Intel) |
| 6 | OpenVINO | Intel GPU/NPU |
| 7 | QNN | Qualcomm NPU |
| 8 | CoreML | macOS Apple Silicon GPU/ANE |
| 9 | Azure | Copilot+ PC NPU |
| 10 | CPU | 備援（始終可用） |

也可以用 `--ort-provider cuda` 手動指定。

### Hailo 後端

適用於搭載 Hailo-10H NPU 的 Raspberry Pi 5。YOLO 和 CLIP 使用官方預編譯 HEF。
Tagger 用的 HEF 目前無法取得（DFC 不支援 WD-Tagger 的架構）。

---

## 設定步驟

### venv 自動偵測

腳本在 venv 外執行時，會自動使用 venv 的 Python 重新啟動：

```bash
# 忘記啟用 venv 也沒關係
python deploy/hailo_tagger_server.py --port 9090
# → [auto-venv] Re-launching with .../venv/bin/python
```

搜尋順序：腳本目錄 → 上層目錄 → 目前目錄

### 1. 依賴套件

```bash
# 通用（必要）
pip install numpy Pillow

# ONNX 後端
pip install onnxruntime           # 僅 CPU
pip install onnxruntime-gpu       # NVIDIA CUDA

# Whisper 後端（選用，擇一）
pip install faster-whisper        # faster-whisper (CUDA/CPU)
# pip install whisper-cpp-python  # whisper.cpp (CPU)

# Hailo 後端 (Pi5 + Hailo-10H)
# hailo_platform 從 Hailo Developer Zone 取得
```

### CUDA + cuDNN 設定 (NVIDIA GPU)

使用 ONNX Runtime GPU 版需要 CUDA + cuDNN 的執行期 DLL：

| ONNX Runtime 版本 | 需要的 CUDA | 需要的 cuDNN |
|-------------------|-----------|-------------|
| 穩定版 (1.x) | CUDA 12.x | cuDNN 9.x |
| nightly | CUDA 13.x | cuDNN 9.x |

**Windows 的場合：**

1. 安裝 CUDA Toolkit
2. 安裝 cuDNN（DLL 位於 `C:\Program Files\NVIDIA\CUDNN\v9.x\bin\<version>\x64\`）
3. 將包含 `cudnn64_9.dll` 的目錄加入 PATH
4. **重新啟動 PowerShell**（需要重新載入環境變數）

確認：
```powershell
where.exe cudnn64_9.dll
# → 若顯示路徑即表示正常
```

### 2. 模型檔案

| 模式 | 模型 | 位置 | 備註 |
|------|------|------|------|
| Tagger | WD-SwinV2 等 | 以 `--model-dir` 指定 | `model.onnx` + `selected_tags.csv` |
| CLIP | ViT-B/16 | `~/.cache/yu_ai_manager/clip_onnx/` | **自動下載**（329 MB） |
| YOLO | YOLOv11n | `~/.cache/yu_ai_manager/yolo_onnx/` | **自動下載** |
| Whisper | faster-whisper-base | HuggingFace cache | **自動下載** |

### 3. 啟動伺服器

```bash
# 全模式（CLIP + YOLO + Whisper）— 不含 Tagger
python deploy/hailo_tagger_server.py --port 9090

# 同時啟用 Tagger
python deploy/hailo_tagger_server.py --port 9090 --model-dir ./models/wd-swinv2-tagger-v3

# 附帶認證權杖
python deploy/hailo_tagger_server.py --port 9090 --token "my-secret-token"

# 使用設定檔
python deploy/hailo_tagger_server.py --config tagger.json
```

### 4. 在 YU AI Manager 中註冊

#### 註冊為推論伺服器（YOLO、Whisper、CLIP）

在 WebUI 的 **設定 → 推論伺服器** 中註冊，或使用 MCP 工具：

```
inference_servers_add:
  name: "Windows ONNX"
  endpoint_url: "http://192.168.50.247:9090"
  inference_types: ["clip", "yolo", "whisper"]
  priority: 50
```

#### 註冊為 Tagger 伺服器

在 WebUI 的 **設定 → Tagger → Tagger Server Registry** 中註冊。

---

## API 端點

### GET /health

```json
{
  "status": "idle",
  "queue_depth": 0,
  "model": "wd-swinv2-tagger-v3",
  "backend": "onnx",
  "device": "onnx-cuda",
  "auth_required": false,
  "inference_types": ["clip", "yolo", "whisper"]
}
```

**device 的值：**

| 值 | 意義 |
|----|------|
| `hailo-10h` | Hailo-10H NPU |
| `onnx-cuda` | ONNX Runtime CUDA |
| `onnx-tensorrt` | ONNX Runtime TensorRT |
| `onnx-rocm` | ONNX Runtime ROCm |
| `onnx-migraphx` | ONNX Runtime MIGraphX |
| `onnx-directml` | ONNX Runtime DirectML |
| `onnx-openvino` | ONNX Runtime OpenVINO |
| `onnx-qnn` | ONNX Runtime QNN |
| `onnx-coreml` | ONNX Runtime CoreML |
| `onnx-azure` | ONNX Runtime Azure NPU |
| `onnx-cpu` | ONNX Runtime CPU |

### POST /tag

標記圖片。僅在指定 `--model-dir` 時有效。

```bash
curl -X POST -F "image=@test.png" http://host:9090/tag
```

```json
{
  "tags": [
    {"tag": "1girl", "confidence": 0.97, "category": "general"},
    {"tag": "hatsune_miku", "confidence": 0.88, "category": "character"}
  ],
  "model": "wd-swinv2-tagger-v3",
  "elapsed_ms": 145
}
```

### POST /clip-encode

生成圖片的 CLIP 嵌入向量。

```bash
curl -X POST -F "images=@test.png" http://host:9090/clip-encode
```

```json
{
  "vectors": ["<base64-encoded float32 array>"],
  "model": "clip_vit_b_16",
  "count": 1
}
```

### POST /yolo-detect

偵測圖片中的物體。

```bash
curl -X POST -F "images=@test.png" http://host:9090/yolo-detect
```

```json
{
  "detections": [[
    {"class": "person", "confidence": 0.92, "bbox": [100, 50, 300, 400]}
  ]],
  "model": "yolov11n",
  "count": 1
}
```

### POST /whisper-transcribe

將語音轉為文字。

```bash
# Raw WAV
curl -X POST -H "Content-Type: application/octet-stream" \
  --data-binary @audio.wav "http://host:9090/whisper-transcribe?language=ja"

# Multipart
curl -X POST -F "image=@audio.wav" "http://host:9090/whisper-transcribe?language=ja"
```

```json
{
  "status": "ok",
  "text": "こんにちは世界",
  "segments": [
    {"text": "こんにちは世界", "start": 0.0, "end": 1.5}
  ],
  "language": "ja",
  "backend": "faster-whisper-cuda"
}
```

---

## 設定檔

```json
{
  "port": 9090,
  "host": "0.0.0.0",
  "backend": "auto",
  "model": "wd-swinv2-tagger-v3",
  "model_dir": "./models/wd-swinv2-tagger-v3",
  "ort_provider": "",
  "general_threshold": 0.35,
  "character_threshold": 0.85,
  "bearer_token": ""
}
```

---

## 分散配置範例

### 範例 1：Pi5 (Hailo NPU) + Windows (CUDA GPU)

實際驗證過的配置：

```
Pi5 (192.168.50.4:9090)
  ├── Tagger: Hailo NPU
  ├── CLIP: Hailo NPU
  ├── YOLO: Hailo NPU
  └── Whisper: Hailo GenAI SDK (NPU)

Windows (192.168.50.247:9090)
  ├── CLIP: ONNX CUDAExecutionProvider
  ├── YOLO: ONNX CUDAExecutionProvider
  └── Whisper: faster-whisper CUDA
```

### 範例 2：macOS (CoreML) + Linux (ROCm)

```
Mac (192.168.1.10:9090)
  ├── CLIP: ONNX CoreMLExecutionProvider (Apple Silicon ANE)
  ├── YOLO: ONNX CoreMLExecutionProvider
  └── Whisper: faster-whisper CPU

Linux (192.168.1.20:9090)
  ├── CLIP: ONNX ROCMExecutionProvider (AMD GPU)
  ├── YOLO: ONNX ROCMExecutionProvider
  └── Whisper: faster-whisper ROCm
```

### 範例 3：備援配置

```
Server A (priority 10) -- 通常使用此台
Server B (priority 50) -- 僅在 A 故障時使用
```

Mode：`single`（僅使用最高優先順序）

---

## 使用 systemd 常駐化

```ini
# /etc/systemd/system/inference-server.service
[Unit]
Description=YU AI Manager Inference Server
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/yu_ai_manager
ExecStart=/home/pi/yu_ai_manager/venv/bin/python deploy/hailo_tagger_server.py \
  --config /home/pi/tagger.json
Restart=on-failure
RestartSec=5
Environment=TAGGER_BEARER_TOKEN=my-secret-token

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now inference-server
```

---

## 疑難排解

### ONNX Runtime 降級為 CPU

```
[W] Failed to create CUDAExecutionProvider. Require cuDNN 9.* and CUDA 12/13.*
```

→ 透過 `/health` 的 `device` 欄位確認
→ 使用 `where.exe cudnn64_9.dll`（Windows）/ `find / -name cudnn64_9.dll`（Linux）確認函式庫位置
→ 加入 PATH 後，**重新啟動終端機**（需要重新載入環境變數）

### CLIP 回傳 503

→ 首次請求時會從 HuggingFace 自動下載模型（329 MB）。請確認網路連線。
→ 確認日誌中是否出現 `CLIP ONNX: downloading ...`

### auto-venv 無限迴圈

→ 已在 v4.53.2 修正。使用 `sys.prefix != sys.base_prefix` 判定 venv。

### 舊的 Python 行程殘留

→ Windows：使用 `tasklist | findstr python` 確認，`taskkill /F /IM python.exe` 全部終止
→ Linux：`pkill -f hailo_tagger_server`

### Hailo VDevice 排他錯誤

→ Hailo NPU 同時只能執行 1 個模型。若 LLM、VLM、S2T 正在執行，請先停止後再重試。
