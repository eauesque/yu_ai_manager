# 分布式推理服务器 (Distributed Inference Server)

**状态**: 实现完成 (v4.53.2)
**目标**: `deploy/hailo_tagger_server.py`
**目的**: 在局域网内的多台机器上分布执行推理（标记、CLIP、YOLO、Whisper）

---

## 概述

将 YU AI Manager 的推理功能分布到局域网内多台机器的独立 HTTP 服务器。
不需要安装 YU AI Manager 本体，仅需 Python 和相关依赖包即可运行。

```
┌─────────────────────────────┐
│   YU AI Manager（主机）      │
│   Inference Server Registry │
│   共享队列 / 工作窃取        │
└──────────┬──────────────────┘
      ┌────┼────────────┐
 ┌────▼────┐ ┌─────▼─────┐ ┌────▼────┐
 │ Pi5 A   │ │ Windows B │ │ Pi5 C   │
 │Hailo NPU│ │CUDA GPU   │ │ONNX CPU │
 │:9090    │ │:9090      │ │:8080    │
 └─────────┘ └───────────┘ └─────────┘
```

### 支持的推理模式

| 模式 | 端点 | 说明 |
|------|------|------|
| **Tagger** | `POST /tag` | WD-Tagger 标记（仅在指定 `--model-dir` 时有效） |
| **CLIP** | `POST /clip-encode` | CLIP ViT-B/16 图片编码（语义搜索用） |
| **YOLO** | `POST /yolo-detect` | YOLOv11n / YOLOv8n 物体检测 |
| **Whisper** | `POST /whisper-transcribe` | 语音转文字 |

所有模式均采用延迟初始化（lazy-init），在首次请求时加载模型。
CLIP 和 YOLO 的 ONNX 模型在未部署时会自动下载。

---

## 推理后端与提供者

### 后端优先顺序

每个推理模式按以下优先顺序选择后端：

| 模式 | 第1 | 第2 | 第3 |
|------|-----|-----|-----|
| Tagger | Hailo NPU | ONNX | — |
| CLIP | Hailo NPU | ONNX（自动下载） | — |
| YOLO | Hailo NPU | ONNX（自动下载） | — |
| Whisper | Hailo GenAI SDK | faster-whisper | whisper.cpp |

### ONNX Runtime 提供者自动选择

ONNX 后端会根据平台自动选择最快的提供者：

| 优先顺序 | 提供者 | 平台 |
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
| 10 | CPU | 回退（始终可用） |

也可以用 `--ort-provider cuda` 手动指定。

### Hailo 后端

适用于搭载 Hailo-10H NPU 的 Raspberry Pi 5。YOLO 和 CLIP 使用官方预编译 HEF。
Tagger 用的 HEF 目前无法获取（DFC 不支持 WD-Tagger 的架构）。

---

## 设置步骤

### venv 自动检测

脚本在 venv 外执行时，会自动使用 venv 的 Python 重新启动：

```bash
# 忘记激活 venv 也没关系
python deploy/hailo_tagger_server.py --port 9090
# → [auto-venv] Re-launching with .../venv/bin/python
```

搜索顺序：脚本目录 → 上级目录 → 当前目录

### 1. 依赖包

```bash
# 通用（必要）
pip install numpy Pillow

# ONNX 后端
pip install onnxruntime           # 仅 CPU
pip install onnxruntime-gpu       # NVIDIA CUDA

# Whisper 后端（可选，任选其一）
pip install faster-whisper        # faster-whisper (CUDA/CPU)
# pip install whisper-cpp-python  # whisper.cpp (CPU)

# Hailo 后端 (Pi5 + Hailo-10H)
# hailo_platform 从 Hailo Developer Zone 获取
```

### CUDA + cuDNN 设置 (NVIDIA GPU)

使用 ONNX Runtime GPU 版需要 CUDA + cuDNN 的运行时 DLL：

| ONNX Runtime 版本 | 需要的 CUDA | 需要的 cuDNN |
|-------------------|-----------|-------------|
| 稳定版 (1.x) | CUDA 12.x | cuDNN 9.x |
| nightly | CUDA 13.x | cuDNN 9.x |

**Windows 的情况：**

1. 安装 CUDA Toolkit
2. 安装 cuDNN（DLL 位于 `C:\Program Files\NVIDIA\CUDNN\v9.x\bin\<version>\x64\`）
3. 将包含 `cudnn64_9.dll` 的目录添加到 PATH
4. **重新启动 PowerShell**（需要重新加载环境变量）

确认：
```powershell
where.exe cudnn64_9.dll
# → 若显示路径即表示正常
```

### 2. 模型文件

| 模式 | 模型 | 位置 | 备注 |
|------|------|------|------|
| Tagger | WD-SwinV2 等 | 以 `--model-dir` 指定 | `model.onnx` + `selected_tags.csv` |
| CLIP | ViT-B/16 | `~/.cache/yu_ai_manager/clip_onnx/` | **自动下载**（329 MB） |
| YOLO | YOLOv11n | `~/.cache/yu_ai_manager/yolo_onnx/` | **自动下载** |
| Whisper | faster-whisper-base | HuggingFace cache | **自动下载** |

### 3. 启动服务器

```bash
# 全模式（CLIP + YOLO + Whisper）— 不含 Tagger
python deploy/hailo_tagger_server.py --port 9090

# 同时启用 Tagger
python deploy/hailo_tagger_server.py --port 9090 --model-dir ./models/wd-swinv2-tagger-v3

# 附带认证令牌
python deploy/hailo_tagger_server.py --port 9090 --token "my-secret-token"

# 使用配置文件
python deploy/hailo_tagger_server.py --config tagger.json
```

### 4. 在 YU AI Manager 中注册

#### 注册为推理服务器（YOLO、Whisper、CLIP）

在 WebUI 的 **设置 → 推理服务器** 中注册，或使用 MCP 工具：

```
inference_servers_add:
  name: "Windows ONNX"
  endpoint_url: "http://192.168.50.247:9090"
  inference_types: ["clip", "yolo", "whisper"]
  priority: 50
```

#### 注册为 Tagger 服务器

在 WebUI 的 **设置 → Tagger → Tagger Server Registry** 中注册。

---

## API 端点

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

| 值 | 含义 |
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

标记图片。仅在指定 `--model-dir` 时有效。

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

生成图片的 CLIP 嵌入向量。

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

检测图片中的物体。

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

将语音转为文字。

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

## 配置文件

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

## 分布式配置示例

### 示例 1：Pi5 (Hailo NPU) + Windows (CUDA GPU)

实际验证过的配置：

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

### 示例 2：macOS (CoreML) + Linux (ROCm)

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

### 示例 3：备援配置

```
Server A (priority 10) -- 通常使用此台
Server B (priority 50) -- 仅在 A 故障时使用
```

Mode：`single`（仅使用最高优先级）

---

## 使用 systemd 守护进程化

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

## 故障排除

### ONNX Runtime 降级为 CPU

```
[W] Failed to create CUDAExecutionProvider. Require cuDNN 9.* and CUDA 12/13.*
```

→ 通过 `/health` 的 `device` 字段确认
→ 使用 `where.exe cudnn64_9.dll`（Windows）/ `find / -name cudnn64_9.dll`（Linux）确认库文件位置
→ 添加到 PATH 后，**重新启动终端**（需要重新加载环境变量）

### CLIP 返回 503

→ 首次请求时会从 HuggingFace 自动下载模型（329 MB）。请确认网络连接。
→ 确认日志中是否出现 `CLIP ONNX: downloading ...`

### auto-venv 无限循环

→ 已在 v4.53.2 修复。使用 `sys.prefix != sys.base_prefix` 判定 venv。

### 旧的 Python 进程残留

→ Windows：使用 `tasklist | findstr python` 确认，`taskkill /F /IM python.exe` 全部终止
→ Linux：`pkill -f hailo_tagger_server`

### Hailo VDevice 排他错误

→ Hailo NPU 同时只能运行 1 个模型。若 LLM、VLM、S2T 正在运行，请先停止后再重试。
