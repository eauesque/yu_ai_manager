# Speech-to-Text Extension

**상태**: 구현 완료 (v3.28.0)
**대상**: `extensions/builtin_speech_to_text/`
**목적**: 자동 백엔드 감지를 통한 비디오 및 오디오 파일 전사

---

## 개요

이 Extension은 비디오 및 오디오 파일에서 오디오를 추출하고 Whisper 모델을 사용하여 전사합니다.
사용 가능한 하드웨어를 기반으로 최적의 백엔드를 자동 선택하며, Hailo NPU 없이도 GPU 또는 CPU에서 실행됩니다.

---

## 백엔드 우선순위

| 우선순위 | 백엔드 | 라이브러리 | 대상 하드웨어 |
|--------|-------------|-----------|-----------------|
| P100 | `hailo` | `hailo_platform.genai` | Hailo-10H NPU |
| P70 | `torch-whisper-rocm` | `torch` (ROCm) + `transformers` | AMD GPU (ROCm/HIP) |
| P50 | `faster-whisper-cuda` | `faster-whisper` (CTranslate2) | NVIDIA GPU (CUDA) |
| P40 | `torch-whisper-cuda` | `torch` (CUDA) + `transformers` | NVIDIA GPU (CUDA) |
| P20 | `torch-whisper-cpu` | `torch` + `transformers` | CPU |
| P50 | `faster-whisper-cpu` | `faster-whisper` (CTranslate2) | CPU |
| P10 | `whisper-cpp` | `pywhispercpp` | CPU (가장 가벼움) |

`auto` 모드에서는 `is_available() == True`를 반환하는 백엔드 중 가장 높은 우선순위의 백엔드가 선택됩니다.

---

## 환경별 설정

### 공통 요구 사항

- Python 3.11+
- ffmpeg (비디오에서 오디오 추출에 필요)

### Hailo-10H NPU (Raspberry Pi AI HAT 2)

추가 패키지가 필요하지 않습니다 (`hailo_platform`이 이미 설치되어 있어야 함).
모델 (`whisper-base` 등)은 GenAI Extension을 통해 미리 다운로드해야 합니다.

```bash
# 아직 없는 경우 GenAI Extension UI에서 모델 다운로드
```

### NVIDIA GPU (CUDA)

```bash
# 권장: faster-whisper (경량, PyTorch 불필요)
pip install faster-whisper

# CUDA가 감지되면 자동으로 GPU 사용 (float16)
# CUDA가 없으면 자동으로 CPU로 폴백 (int8)
```

### AMD GPU (ROCm)

```bash
# 1. PyTorch ROCm 에디션 설치
#    공식: https://pytorch.org/get-started/locally/
#    예시 (ROCm 6.x):
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/rocm6.2

# 2. HuggingFace transformers 설치
pip install transformers

# 3. config에서 백엔드 설정 ("auto" 모드에서 자동 감지됨)
#    Extension 설정에서: backend: "rocm" 또는 "auto"
```

**ROCm 감지 메커니즘**: PyTorch는 HIP을 통해 ROCm을 CUDA로 노출합니다.
시스템은 `torch.version.hip`이 `None`이 아닐 때 ROCm을 식별합니다.

**메모리 요구 사항** (ROCm):

| 모델 | VRAM 추정 |
|--------|----------|
| tiny | ~150 MB |
| base | ~300 MB |
| small | ~500 MB |
| medium | ~1.5 GB |

### CPU 전용

```bash
# 옵션 1: faster-whisper (권장, int8 양자화로 빠름)
pip install faster-whisper

# 옵션 2: whisper.cpp (가장 가벼움, PyTorch 불필요)
pip install pywhispercpp

# 옵션 3: torch + transformers (범용이나 무거움)
pip install torch transformers
```

**CPU 성능 추정** (base 모델, 1분 오디오):

| 백엔드 | RPi 5 | x86 (4코어) |
|---|---|---|
| faster-whisper (int8) | ~30초 | ~5초 |
| whisper.cpp | ~40초 | ~8초 |
| torch (float32) | ~90초 | ~15초 |

---

## 설정

Extension 설정 페이지 (`/ext/speech-to-text/`) 또는 config.json에서 설정합니다:

| 항목 | 선택지 | 기본값 | 설명 |
|------|--------|-----------|------|
| `backend` | auto / hailo / cuda / rocm / cpu | auto | 추론 백엔드 |
| `model_size` | tiny / base / small / medium | base | Whisper 모델 크기 |
| `default_language` | BCP-47 코드 (ja, en 등) | ja | 기본 언어 |

---

## API 엔드포인트

모든 엔드포인트는 `/ext/speech-to-text` 접두사 아래에 있습니다.

### POST `/api/s2t/transcribe`

업로드된 WAV 오디오를 전사합니다.

- **Content-Type**: `multipart/form-data`
- **파라미터**: `audio` (파일), `language` (선택 사항)
- **응답**: `{ status, text, segments, language, sample_rate, backend }`

### POST `/api/s2t/transcribe-video`

DB에 등록된 비디오/오디오 파일을 전사합니다. 결과는 어노테이션으로 저장됩니다.

- **본문**: `{ file_id: int, language?: string }`
- **응답**: `{ status, text, segments, language, backend }`
- **어노테이션**: `source="s2t"`, 키: `transcript`, `transcript_segments`, `transcript_backend`

### POST `/api/s2t/batch-transcribe`

여러 파일의 배치 전사 (백그라운드에서 실행).

세 가지 입력 방법 중 **하나**를 선택 (상호 배타적):

#### 방법 1: 파일 ID 목록 (레거시)

```json
{
  "file_ids": [123, 456, 789],
  "language": "ja"
}
```

#### 방법 2: 디렉터리

지정된 디렉터리에서 비디오/오디오 파일을 자동 감지하고 DB에 등록된 파일만 처리합니다.

```json
{
  "directory": "/path/to/videos/",
  "recursive": true,
  "language": "en"
}
```

- `recursive` (기본값: `true`): 하위 디렉터리 재귀 검색
- 대상 확장자: `.webm`, `.mp4`, `.avi`, `.mov`, `.mkv`, `.m4v`, `.ogv`, `.mp3`, `.wav`, `.ogg`, `.opus`, `.m4a`, `.aac`, `.flac`

#### 방법 3: 텍스트/CSV 목록

파일 경로가 나열된 텍스트 파일 또는 CSV를 지정합니다.

```json
{
  "list_file": "/path/to/targets.txt",
  "language": "ja"
}
```

**텍스트 파일 형식** (`.txt` 등):
```
# 주석 행 (#으로 시작하는 행은 무시됨)
/mnt/videos/interview_01.mp4
/mnt/videos/interview_02.webm
/mnt/audio/podcast_03.mp3
```

**CSV 형식** (`.csv`):
```csv
/mnt/videos/interview_01.mp4
/mnt/videos/interview_02.webm
/mnt/audio/podcast_03.mp3
```
첫 번째 열이 파일 경로로 사용됩니다. `#`으로 시작하는 행은 건너뜁니다.

#### 공통 옵션

| 파라미터 | 타입 | 기본값 | 설명 |
|-----------|---|-----------|------|
| `language` | string | 설정값 (통상 `ja`) | 언어 코드 (아래 참조) |
| `recursive` | bool | `true` | 디렉터리 방법 전용: 하위 디렉터리 재귀 검색 |

#### 제한 사항 및 제약

- 최대 대상 파일 수: **500**
- DB에 등록된 파일 (`files` 테이블)만 처리됨
- 삭제된 파일 (`is_deleted=1`)은 제외

#### 응답 예시

```json
{
  "status": "started",
  "total": 15,
  "mode": "directory",
  "directory": "/mnt/videos/",
  "recursive": true,
  "files_found": 23,
  "matched_in_db": 15
}
```

- **SSE 이벤트**: `s2t.batch_start`, `s2t.batch_progress`, `s2t.batch_complete`

### GET `/api/s2t/transcript/<file_id>`

저장된 전사 결과를 조회합니다. 하위 호환을 위해 `source="s2t"`와 `source="hailo:s2t"` 모두 확인합니다.

### GET `/api/s2t/status`

백엔드 상태와 사용 가능한 백엔드 목록을 반환합니다.

---

## MCP 도구

| 도구 이름 | 설명 |
|---------|------|
| `s2t_status` | 백엔드 상태 조회 |
| `s2t_transcribe_video` | 단일 비디오 파일 전사 |
| `s2t_batch_transcribe` | 배치 전사 시작 (file_ids / directory / list_file) |
| `s2t_get_transcript` | 저장된 전사 결과 조회 |

### `s2t_batch_transcribe` 파라미터

| 파라미터 | 타입 | 필수 | 설명 |
|-----------|---|------|------|
| `file_ids` | list[int] | *1 | 파일 ID 목록 (최대 500) |
| `directory` | string | *1 | 디렉터리 경로 (비디오/오디오 자동 감지) |
| `list_file` | string | *1 | 텍스트/CSV 파일 경로 |
| `recursive` | bool | | 디렉터리 방법 전용. 하위 디렉터리 재귀 검색 (기본값 true) |
| `language` | string | | 언어 코드. 비어 있으면 = 설정 기본값 |
| `expected_count` | int | | file_ids 잘림 감지용 |

*1: `file_ids`, `directory`, `list_file` 중 정확히 하나만 지정 (상호 배타적)

---

## 파일 구조

```
extensions/builtin_speech_to_text/
  extension.json                      # 매니페스트
  speech_to_text_ext.py               # 진입점 (Blueprint)
  s2t_routes.py                       # 단일 파일 API 라우트
  s2t_batch_routes.py                 # 배치 API 라우트
  core_impl/
    base.py                           # S2TBackend 추상 기본 클래스
    backend_hailo.py                  # Hailo-10H NPU
    backend_faster_whisper.py         # faster-whisper (CUDA/CPU)
    backend_torch_whisper.py          # PyTorch transformers (ROCm/CUDA/CPU)
    backend_whisper_cpp.py            # whisper.cpp (CPU)
    backend_registry.py               # 자동 감지 + 싱글톤 관리
  templates/speech_to_text/
    s2t.html                          # UI 페이지
mcp_server/
  s2t_tools.py                        # MCP 도구 정의
```

---

## 지원 언어 코드

Whisper가 지원하는 주요 언어 코드 (BCP-47):

| 코드 | 언어 | 코드 | 언어 |
|--------|------|--------|------|
| `ja` | 일본어 | `en` | 영어 |
| `zh` | 중국어 | `ko` | 한국어 |
| `de` | 독일어 | `fr` | 프랑스어 |
| `es` | 스페인어 | `it` | 이탈리아어 |
| `pt` | 포르투갈어 | `ru` | 러시아어 |
| `ar` | 아랍어 | `hi` | 힌디어 |
| `th` | 태국어 | `vi` | 베트남어 |
| `nl` | 네덜란드어 | `tr` | 터키어 |
| `pl` | 폴란드어 | `uk` | 우크라이나어 |
| `id` | 인도네시아어 | `sv` | 스웨덴어 |

기타 Whisper 지원 언어도 지정할 수 있습니다. 빈 문자열은 자동 감지를 트리거합니다.
기본 언어는 Extension 설정 `default_language` (초기값: `ja`)에서 변경할 수 있습니다.

---

## 알려진 제한 사항

- **초기 로딩 지연**: transformers / faster-whisper가 HuggingFace Hub에서 모델을 다운로드 (base: ~150MB). 첫 실행 시 수 분이 걸릴 수 있음
- **Hailo HEF 모델**: GenAI Extension을 통해 다운로드해야 합니다. S2T Extension 자체에는 다운로드 기능 없음
- **메모리**: medium 모델은 RPi 5 (8GB)에서 메모리 부족 오류를 일으킬 수 있음. base 모델을 권장
- **동시성**: 백엔드가 싱글톤으로 관리됨. 배치 처리 중 도착하는 요청은 동일한 인스턴스를 공유
- **입력 형식**: WAV (PCM s16le, mono, 16kHz)를 가정. 비디오 파일은 ffmpeg를 통해 자동 변환
- **배치 입력**: 디렉터리 / list_file 방법은 DB에 등록된 파일만 처리. 스캔되지 않은 파일은 먼저 `start_scan`으로 등록해야 함

---

## 실시간 스트리밍 전사

인터넷 라디오, RTSP 스트림, 동영상 파일의 오디오를 실시간으로 텍스트로 변환하고 WebUI에 자막으로 표시합니다.

### 두 가지 모드

- **Chunk 모드** (기본값): RMS 기반 무음 감지를 사용하여 청크로 분할합니다. 모든 백엔드 (Hailo/CUDA/CPU) 지원. 발화 종료 후 결과를 표시합니다.
- **Live 모드**: faster-whisper의 Silero VAD를 사용하여 순차적으로 전사합니다. 발화 중에도 중간 결과 (interim)를 표시합니다. ONNX/faster-whisper 백엔드가 필요합니다.

### 지원 입력 소스

- HTTP/HTTPS 스트림 (인터넷 라디오 등)
- RTSP 카메라
- RTMP 스트림

### API 엔드포인트

| 엔드포인트 | 메서드 | 기능 |
|---|---|---|
| `/api/s2t/stream/start` | POST | 스트리밍 시작 (`source_url`, `language`, `mode`) |
| `/api/s2t/stream/stop` | POST | 스트리밍 중지 |
| `/api/s2t/stream/status` | GET | 상태 조회 |
| `/api/s2t/stream/transcript` | GET | 전체 텍스트 조회 |
| `/api/s2t/stream/export/txt` | GET | 텍스트 내보내기 |
| `/api/s2t/stream/export/srt` | GET | SRT 자막 내보내기 |

### SSE 이벤트

| 이벤트 | 설명 |
|---|---|
| `s2t.stream_chunk` | 확정 텍스트 |
| `s2t.stream_interim` | 중간 텍스트 (Live 모드만) |
| `s2t.stream_complete` | 스트리밍 완료 |

### MCP 도구

| 도구 이름 | 설명 |
|---|---|
| `s2t_stream_start(source_url, language)` | 스트리밍 시작 |
| `s2t_stream_stop()` | 스트리밍 중지 |
| `s2t_stream_status()` | 상태 조회 |
| `s2t_stream_transcript()` | 전체 텍스트 조회 |

### 스트리밍 설정

`extension.json`에서 설정 가능한 항목:

| 항목 | 설명 | 기본값 |
|---|---|---|
| `stream_chunk_min_sec` | Chunk 모드 최소 청크 길이 (초) | — |
| `stream_chunk_max_sec` | Chunk 모드 최대 청크 길이 (초) | — |
| `stream_silence_threshold` | 무음 감지 RMS 임계값 | — |
| `stream_silence_ms` | 무음 판정 시간 (밀리초) | — |
| `live_interval_sec` | Live 모드 전사 간격 (초) | — |
