# 분산 추론 서버 (Distributed Inference Server)

**상태**: 구현 완료 (v4.53.2)
**대상**: `deploy/hailo_tagger_server.py`
**목적**: LAN 내 여러 머신에서 추론(태깅, CLIP, YOLO, Whisper)을 분산 실행

---

## 개요

YU AI Manager의 추론 기능을 LAN 내 여러 머신에 분산시키는 독립형 HTTP 서버입니다.
YU AI Manager 본체가 필요 없으며, Python과 의존 패키지만으로 동작합니다.

```
┌─────────────────────────────┐
│   YU AI Manager (메인)       │
│   Inference Server Registry │
│   공유 큐 / 작업 훔치기      │
└──────────┬──────────────────┘
      ┌────┼────────────┐
 ┌────▼────┐ ┌─────▼─────┐ ┌────▼────┐
 │ Pi5 A   │ │ Windows B │ │ Pi5 C   │
 │Hailo NPU│ │CUDA GPU   │ │ONNX CPU │
 │:9090    │ │:9090      │ │:8080    │
 └─────────┘ └───────────┘ └─────────┘
```

### 지원 추론 모드

| 모드 | 엔드포인트 | 설명 |
|------|-----------|------|
| **Tagger** | `POST /tag` | WD-Tagger 태깅 (`--model-dir` 지정 시에만 유효) |
| **CLIP** | `POST /clip-encode` | CLIP ViT-B/16 이미지 인코딩 (시맨틱 검색용) |
| **YOLO** | `POST /yolo-detect` | YOLOv11n / YOLOv8n 객체 감지 |
| **Whisper** | `POST /whisper-transcribe` | 음성 텍스트 변환 |

모든 모드는 지연 초기화(lazy-init)를 사용하여 첫 번째 요청 시 모델을 로드합니다.
CLIP 및 YOLO의 ONNX 모델은 미배치 시 자동으로 다운로드됩니다.

---

## 추론 백엔드 및 프로바이더

### 백엔드 우선순위

각 추론 모드는 다음 우선순위로 백엔드를 선택합니다:

| 모드 | 1순위 | 2순위 | 3순위 |
|------|-------|-------|-------|
| Tagger | Hailo NPU | ONNX | — |
| CLIP | Hailo NPU | ONNX (자동 다운로드) | — |
| YOLO | Hailo NPU | ONNX (자동 다운로드) | — |
| Whisper | Hailo GenAI SDK | faster-whisper | whisper.cpp |

### ONNX Runtime 프로바이더 자동 선택

ONNX 백엔드는 플랫폼에 따라 가장 빠른 프로바이더를 자동으로 선택합니다:

| 우선순위 | 프로바이더 | 플랫폼 |
|---------|-----------|--------|
| 1 | TensorRT | NVIDIA GPU (가장 빠름, TensorRT SDK 필요) |
| 2 | CUDA | NVIDIA GPU |
| 3 | ROCm | AMD GPU (Linux) |
| 4 | MIGraphX | AMD GPU (Linux) |
| 5 | DirectML | Windows GPU (NVIDIA/AMD/Intel) |
| 6 | OpenVINO | Intel GPU/NPU |
| 7 | QNN | Qualcomm NPU |
| 8 | CoreML | macOS Apple Silicon GPU/ANE |
| 9 | Azure | Copilot+ PC NPU |
| 10 | CPU | 폴백 (항상 사용 가능) |

`--ort-provider cuda`와 같이 수동 지정도 가능합니다.

### Hailo 백엔드

Hailo-10H NPU가 탑재된 Raspberry Pi 5에서 사용 가능합니다. YOLO 및 CLIP은 공식 사전 컴파일 HEF를 사용합니다.
Tagger용 HEF는 현재 입수 불가합니다 (DFC가 WD-Tagger 아키텍처를 미지원).

---

## 설정

### venv 자동 감지

스크립트가 venv 외부에서 실행된 경우, 자동으로 venv의 Python으로 재시작합니다:

```bash
# venv 활성화를 잊어도 OK
python deploy/hailo_tagger_server.py --port 9090
# → [auto-venv] Re-launching with .../venv/bin/python
```

검색 순서: 스크립트 디렉터리 → 상위 디렉터리 → 현재 디렉터리

### 1. 의존 패키지

```bash
# 공통 (필수)
pip install numpy Pillow

# ONNX 백엔드
pip install onnxruntime           # CPU 전용
pip install onnxruntime-gpu       # NVIDIA CUDA

# Whisper 백엔드 (선택, 택일)
pip install faster-whisper        # faster-whisper (CUDA/CPU)
# pip install whisper-cpp-python  # whisper.cpp (CPU)

# Hailo 백엔드 (Pi5 + Hailo-10H)
# hailo_platform은 Hailo Developer Zone에서 설치
```

### CUDA + cuDNN 설정 (NVIDIA GPU)

ONNX Runtime GPU 버전을 사용하려면 CUDA + cuDNN 런타임 DLL이 필요합니다:

| ONNX Runtime 버전 | 필요한 CUDA | 필요한 cuDNN |
|-------------------|-----------|-------------|
| 안정 버전 (1.x) | CUDA 12.x | cuDNN 9.x |
| nightly | CUDA 13.x | cuDNN 9.x |

**Windows의 경우:**

1. CUDA Toolkit 설치
2. cuDNN 설치 (DLL은 `C:\Program Files\NVIDIA\CUDNN\v9.x\bin\<version>\x64\`에 위치)
3. `cudnn64_9.dll`이 있는 디렉터리를 PATH에 추가
4. **PowerShell 재시작** (환경 변수 반영에 필요)

확인:
```powershell
where.exe cudnn64_9.dll
# → 경로가 표시되면 정상
```

### 2. 모델 파일

| 모드 | 모델 | 위치 | 비고 |
|------|------|------|------|
| Tagger | WD-SwinV2 등 | `--model-dir`로 지정 | `model.onnx` + `selected_tags.csv` |
| CLIP | ViT-B/16 | `~/.cache/yu_ai_manager/clip_onnx/` | **자동 다운로드** (329 MB) |
| YOLO | YOLOv11n | `~/.cache/yu_ai_manager/yolo_onnx/` | **자동 다운로드** |
| Whisper | faster-whisper-base | HuggingFace cache | **자동 다운로드** |

### 3. 서버 시작

```bash
# 전체 모드 (CLIP + YOLO + Whisper) — Tagger 제외
python deploy/hailo_tagger_server.py --port 9090

# Tagger도 활성화
python deploy/hailo_tagger_server.py --port 9090 --model-dir ./models/wd-swinv2-tagger-v3

# 인증 토큰 포함
python deploy/hailo_tagger_server.py --port 9090 --token "my-secret-token"

# 설정 파일 사용
python deploy/hailo_tagger_server.py --config tagger.json
```

### 4. YU AI Manager에서 등록

#### 추론 서버로 등록 (YOLO, Whisper, CLIP)

WebUI의 **설정 → 추론 서버**에서 등록하거나 MCP 도구 사용:

```
inference_servers_add:
  name: "Windows ONNX"
  endpoint_url: "http://192.168.50.247:9090"
  inference_types: ["clip", "yolo", "whisper"]
  priority: 50
```

#### Tagger 서버로 등록

WebUI의 **설정 → Tagger → Tagger Server Registry**에서 등록.

---

## API 엔드포인트

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

**device 값:**

| 값 | 의미 |
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

이미지를 태깅합니다. `--model-dir` 지정 시에만 유효.

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

이미지의 CLIP 임베딩 벡터를 생성합니다.

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

이미지 내의 객체를 감지합니다.

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

음성을 텍스트로 변환합니다.

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

## 설정 파일

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

## 분산 구성 예시

### 예시 1: Pi5 (Hailo NPU) + Windows (CUDA GPU)

실제 동작 확인된 구성:

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

### 예시 2: macOS (CoreML) + Linux (ROCm)

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

### 예시 3: 페일오버 구성

```
Server A (priority 10) -- 통상적으로 사용
Server B (priority 50) -- A가 다운된 경우에만 사용
```

Mode: `single` (최고 우선순위만 사용)

---

## systemd로 데몬화

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

## 문제 해결

### ONNX Runtime이 CPU로 폴백됨

```
[W] Failed to create CUDAExecutionProvider. Require cuDNN 9.* and CUDA 12/13.*
```

→ `/health`의 `device` 필드로 확인
→ `where.exe cudnn64_9.dll` (Windows) / `find / -name cudnn64_9.dll` (Linux)로 라이브러리 위치 확인
→ PATH에 추가 후, **터미널을 재시작** (환경 변수 반영에 필요)

### CLIP이 503을 반환

→ 첫 번째 요청 시 HuggingFace에서 모델 (329 MB)을 자동 다운로드합니다. 네트워크 연결을 확인하세요.
→ 로그에 `CLIP ONNX: downloading ...`이 출력되는지 확인

### auto-venv가 무한 루프

→ v4.53.2에서 수정 완료. `sys.prefix != sys.base_prefix`로 venv 판정.

### 이전 Python 프로세스가 남아 있음

→ Windows: `tasklist | findstr python`으로 확인, `taskkill /F /IM python.exe`로 전체 종료
→ Linux: `pkill -f hailo_tagger_server`

### Hailo VDevice 배타적 접근 오류

→ Hailo NPU는 동시에 1개의 모델만 실행 가능합니다. LLM, VLM, S2T가 실행 중이면 먼저 중지한 후 재시도하세요.
