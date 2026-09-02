# CLIP ONNX Embedding 개발 로그

## 개요

Hailo-10H 전용이었던 CLIP 시맨틱 이미지 검색을 ONNX Runtime 기반의 범용 인코더로 확장.
CPU / NVIDIA CUDA / AMD ROCm / DirectML (Ryzen AI NPU) / OpenVINO (Intel NPU) / CoreML에서 동작.

## 날짜: 2026-03-04

### Phase 1: 공유 코어 레이어 추출 (`core/clip_core/`, 현재 `extensions/builtin_clip_search/core_impl/`)

**생성 파일:**
- `encoder_abc.py` — `ClipImageEncoder` ABC (encode, encode_batch, close, output_dim, backend_name)
- `image_io.py` — 이미지 I/O (일반 파일 + ZIP/7z 아카이브 대응)
- `vector_store.py` — `hailo_clip_core`에서 그대로 이동
- `text_encoder.py` — `hailo_clip_core`에서 그대로 이동
- `search.py` — 이동 + import 대상을 상대 경로로 변경
- `indexer.py` — 범용화: `encoder_factory`와 `preprocess_fn`을 주입 매개변수화
- `event_handler.py` — 이동 + `indexer` import 대상 변경
- `encoder_factory.py` — `get_best_encoder()` (Hailo > ONNX 우선), `get_preprocessor()`, `get_encoder_info()`

**설계 판단:**
- `cv2`는 지연 import — opencv-python이 없는 머신에서도 모듈 로딩은 성공
- `indexer.py`의 `encoder_factory`/`preprocess_fn`이 None인 경우, `encoder_factory.py` 경유로 자동 해결
- `event_handler.py`는 extension config 키 `"builtin-hailo-semantic-search"`를 그대로 사용 (하위 호환)

### Phase 2: ONNX 인코더 (`core/clip_onnx_core/`, 현재 `extensions/builtin_clip_onnx/core_impl/`)

**생성 파일:**
- `onnx_encoder.py` — `OnnxClipEncoder(ClipImageEncoder)` 싱글톤
- `preprocess.py` — float32 NCHW 정규화 (mean/std는 CLIP 공식 값)
- `model_download.py` — HuggingFace `Xenova/clip-vit-base-patch16`의 `onnx/vision_model.onnx`

**기술 노트:**
- 모델: `Xenova/clip-vit-base-patch16` (HuggingFace Optimum으로 변환된 ONNX)
- 입력: `pixel_values` (batch, 3, 224, 224) float32
- 출력: `image_embeds` (batch, 512) float32 — L2 정규화하여 저장
- WD-Tagger `engine_onnx.py`의 패턴을 준수 (SessionOptions, batch inference)
- `ort_provider.select_providers()`로 ExecutionProvider 자동 선택

### Phase 3: Hailo 리팩터링

- `HailoClipEncoder`에 `ClipImageEncoder` ABC 상속 추가 + `backend_name` 프로퍼티
- `vector_store.py`, `text_encoder.py`, `search.py`, `event_handler.py` → `clip_core`에서의 재내보내기
- `indexer.py` → Hailo encoder/preprocess를 주입하는 얇은 래퍼
- `image_preprocess.py` → `clip_core.image_io.read_and_decode()`를 사용

### Phase 4: inference_core 확장

- `ort_provider.py`의 `_PROVIDER_PRIORITY`에 `OpenVINOExecutionProvider` 추가
- `gpu_detect.py`에 `openvino_available` 필드 + `_detect_openvino()` 추가
- `ort_install_helper.py`에 OpenVINO 패키지 정보 추가

### Phase 5: Extension 확장

- `extension.json`에 `preferred_backend` 설정 추가
- import 대상을 모두 `core.clip_core`로 변경
- 신규 API: `GET /api/backends`, `GET /api/model/status`, `POST /api/model/download`

### Phase 6: MCP 도구

- `mcp_server/semantic_tools.py` — 5개 도구
- `semantic_search`, `semantic_index_start/status/stop`, `semantic_backend_info`

### Phase 7: runtime_runner.py

- event handler import를 `core.clip_core.event_handler`로 변경

## 벡터 호환성

Hailo HEF (uint8 양자화→역양자화)와 ONNX (float32 직접 출력)는
같은 `openai/clip-vit-base-patch16` 모델 기반이므로, 출력은 동일한 512차원 임베딩 공간.
기존의 Hailo로 구축한 인덱스와 ONNX로 추가한 벡터는 혼재 가능.

## NPU 지원 매트릭스

| NPU | ORT 패키지 | 프로바이더 |
|---|---|---|
| AMD Ryzen AI | `onnxruntime-directml` | DmlExecutionProvider |
| Intel NPU | `onnxruntime-openvino` | OpenVINOExecutionProvider |
| NVIDIA GPU | `onnxruntime-gpu` | CUDAExecutionProvider |
| AMD GPU | `onnxruntime-rocm` | ROCmExecutionProvider |
| Apple Silicon | `onnxruntime` | CoreMLExecutionProvider |
| CPU (fallback) | `onnxruntime` | CPUExecutionProvider |
