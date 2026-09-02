# Distributed Inference Server

**Status**: Implemented (v4.53.2)
**Target**: `deploy/hailo_tagger_server.py`
**Purpose**: Distribute inference (tagging, CLIP, YOLO, Whisper) across multiple machines on a LAN

---

## Overview

A standalone HTTP server that distributes YU AI Manager's inference capabilities across multiple machines on a LAN.
The main YU AI Manager installation is not required — it runs with just Python and its dependencies.

```
┌─────────────────────────────┐
│   YU AI Manager (Main)      │
│   Inference Server Registry │
│   Shared Queue / Work-Stealing │
└──────────┬──────────────────┘
      ┌────┼────────────┐
 ┌────▼────┐ ┌─────▼─────┐ ┌────▼────┐
 │ Pi5 A   │ │ Windows B │ │ Pi5 C   │
 │Hailo NPU│ │CUDA GPU   │ │ONNX CPU │
 │:9090    │ │:9090      │ │:8080    │
 └─────────┘ └───────────┘ └─────────┘
```

### Supported Inference Modes

| Mode | Endpoint | Description |
|------|----------|-------------|
| **Tagger** | `POST /tag` | WD-Tagger tagging (only available when `--model-dir` is specified) |
| **CLIP** | `POST /clip-encode` | CLIP ViT-B/16 image encoding (for semantic search) |
| **YOLO** | `POST /yolo-detect` | YOLOv11n / YOLOv8n object detection |
| **Whisper** | `POST /whisper-transcribe` | Speech-to-text transcription |

All modes use lazy initialization — models are loaded on the first request.
CLIP and YOLO ONNX models are automatically downloaded if not present.

---

## Inference Backends and Providers

### Backend Priority

Each inference mode selects a backend in the following priority order:

| Mode | 1st | 2nd | 3rd |
|------|-----|-----|-----|
| Tagger | Hailo NPU | ONNX | — |
| CLIP | Hailo NPU | ONNX (auto-download) | — |
| YOLO | Hailo NPU | ONNX (auto-download) | — |
| Whisper | Hailo GenAI SDK | faster-whisper | whisper.cpp |

### ONNX Runtime Provider Auto-Selection

The ONNX backend automatically selects the fastest provider for your platform:

| Priority | Provider | Platform |
|----------|----------|----------|
| 1 | TensorRT | NVIDIA GPU (fastest, requires TensorRT SDK) |
| 2 | CUDA | NVIDIA GPU |
| 3 | ROCm | AMD GPU (Linux) |
| 4 | MIGraphX | AMD GPU (Linux) |
| 5 | DirectML | Windows GPU (NVIDIA/AMD/Intel) |
| 6 | OpenVINO | Intel GPU/NPU |
| 7 | QNN | Qualcomm NPU |
| 8 | CoreML | macOS Apple Silicon GPU/ANE |
| 9 | Azure | Copilot+ PC NPU |
| 10 | CPU | Fallback (always available) |

You can also specify manually with `--ort-provider cuda`.

### Hailo Backend

Available on Raspberry Pi 5 with Hailo-10H NPU. YOLO and CLIP use official pre-compiled HEFs.
The Tagger HEF is currently unavailable (DFC does not support the WD-Tagger architecture).

---

## Setup

### Auto-venv Detection

The script automatically re-launches with the venv Python if run outside a venv:

```bash
# Forgetting to activate venv is OK
python deploy/hailo_tagger_server.py --port 9090
# → [auto-venv] Re-launching with .../venv/bin/python
```

Search order: script directory → parent directory → current directory

### 1. Dependencies

```bash
# Common (required)
pip install numpy Pillow

# ONNX backend
pip install onnxruntime           # CPU only
pip install onnxruntime-gpu       # NVIDIA CUDA

# Whisper backend (optional, choose one)
pip install faster-whisper        # faster-whisper (CUDA/CPU)
# pip install whisper-cpp-python  # whisper.cpp (CPU)

# Hailo backend (Pi5 + Hailo-10H)
# hailo_platform from Hailo Developer Zone
```

### CUDA + cuDNN Setup (NVIDIA GPU)

ONNX Runtime GPU requires CUDA + cuDNN runtime DLLs:

| ONNX Runtime Version | Required CUDA | Required cuDNN |
|----------------------|---------------|----------------|
| Stable (1.x) | CUDA 12.x | cuDNN 9.x |
| nightly | CUDA 13.x | cuDNN 9.x |

**On Windows:**

1. Install CUDA Toolkit
2. Install cuDNN (DLLs are in `C:\Program Files\NVIDIA\CUDNN\v9.x\bin\<version>\x64\`)
3. Add the directory containing `cudnn64_9.dll` to PATH
4. **Restart PowerShell** (required to pick up environment variable changes)

Verify:
```powershell
where.exe cudnn64_9.dll
# → If a path is shown, you're good
```

### 2. Model Files

| Mode | Model | Location | Notes |
|------|-------|----------|-------|
| Tagger | WD-SwinV2 etc. | Specified via `--model-dir` | `model.onnx` + `selected_tags.csv` |
| CLIP | ViT-B/16 | `~/.cache/yu_ai_manager/clip_onnx/` | **Auto-download** (329 MB) |
| YOLO | YOLOv11n | `~/.cache/yu_ai_manager/yolo_onnx/` | **Auto-download** |
| Whisper | faster-whisper-base | HuggingFace cache | **Auto-download** |

### 3. Start the Server

```bash
# All modes (CLIP + YOLO + Whisper) — without Tagger
python deploy/hailo_tagger_server.py --port 9090

# Also enable Tagger
python deploy/hailo_tagger_server.py --port 9090 --model-dir ./models/wd-swinv2-tagger-v3

# With auth token
python deploy/hailo_tagger_server.py --port 9090 --token "my-secret-token"

# Using a config file
python deploy/hailo_tagger_server.py --config tagger.json
```

### 4. Register in YU AI Manager

#### Register as Inference Server (YOLO, Whisper, CLIP)

Register in the WebUI under **Settings → Inference Servers**, or via MCP tool:

```
inference_servers_add:
  name: "Windows ONNX"
  endpoint_url: "http://192.168.50.247:9090"
  inference_types: ["clip", "yolo", "whisper"]
  priority: 50
```

#### Register as Tagger Server

Register in the WebUI under **Settings → Tagger → Tagger Server Registry**.

---

## API Endpoints

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

**device values:**

| Value | Meaning |
|-------|---------|
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

Tag an image. Only available when `--model-dir` is specified.

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

Generate CLIP embedding vectors for images.

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

Detect objects in images.

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

Transcribe speech to text.

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

## Configuration File

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

## Distributed Configuration Examples

### Example 1: Pi5 (Hailo NPU) + Windows (CUDA GPU)

A verified working configuration:

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

### Example 2: macOS (CoreML) + Linux (ROCm)

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

### Example 3: Failover Configuration

```
Server A (priority 10) -- normally used
Server B (priority 50) -- used only when A is down
```

Mode: `single` (use highest priority only)

---

## Daemonize with systemd

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

## Troubleshooting

### ONNX Runtime falls back to CPU

```
[W] Failed to create CUDAExecutionProvider. Require cuDNN 9.* and CUDA 12/13.*
```

→ Check the `device` field in `/health`
→ Verify library location with `where.exe cudnn64_9.dll` (Windows) / `find / -name cudnn64_9.dll` (Linux)
→ After adding to PATH, **restart your terminal** (required to pick up environment variable changes)

### CLIP returns 503

→ On the first request, the model (329 MB) is automatically downloaded from HuggingFace. Check your network connection.
→ Verify that `CLIP ONNX: downloading ...` appears in the logs.

### auto-venv enters an infinite loop

→ Fixed in v4.53.2. Now uses `sys.prefix != sys.base_prefix` for venv detection.

### Old Python processes remain

→ Windows: Check with `tasklist | findstr python`, terminate all with `taskkill /F /IM python.exe`
→ Linux: `pkill -f hailo_tagger_server`

### Hailo VDevice exclusive access error

→ The Hailo NPU can only run one model at a time. Stop any running LLM, VLM, or S2T before retrying.
