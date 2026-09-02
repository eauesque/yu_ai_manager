# Hailo-10H 디바이스 제어

## 개요

Hailo-10H NPU는 **여러 모델을 동시에 실행**할 수 있다.
내장 ROUND_ROBIN 스케줄러가 모델 간 하드웨어 접근을 자동으로 시분할한다.

yu_ai_manager는 단일 공유 VDevice를 유지하여, CLIP, YOLO, LLM, VLM, Speech2Text를
동시에 로드하고 추론할 수 있다. 외부 프로세스 (hailo-ollama)와의 공유도 `group_id`로 지원한다.

## 아키텍처

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

- InferModel API (CLIP, YOLO)와 GenAI API (LLM, VLM, S2T)는 동일한 VDevice에서 공존한다
- 모든 모델은 **동일한 VDevice 인스턴스**에 생성해야 한다 (별도 인스턴스에서는 동작하지 않음)

## 2가지 모드 비교

| | Python SDK (Hailo VLM) | hailo-ollama-vlm (OpenAI 호환) |
|---|---|---|
| 디바이스 관리 | yu의 device_manager | 외부 C++ 서버 |
| CLIP 검색과 공존 | 가능 (동시 동작) | 가능 (group_id 공유, v5.3.0+) |
| 추론 속도 | 동일 | 동일 |
| 오버헤드 | ~15ms | ~200-400ms (base64+HTTP) |
| 다중 클라이언트 | 불가 | 가능 |
| Flask 스레드 | 추론 중 블로킹 | HTTP 대기만 |

## VDevice 공유 (group_id)

### 프로세스 내 공유

`device_manager.py`가 자동으로 관리한다. 모든 모델이 동일한 VDevice를 공유한다.

환경 변수로 group_id를 변경할 수 있다:
```bash
export HAILO_VDEVICE_GROUP_ID=MY_GROUP
```

기본값: `YU_SHARED`

### hailo-ollama와의 공존 (v5.3.0+)

hailo-ollama v5.3.0 이후는 `HAILO_OLLAMA_VDEVICE_GROUP_ID` 환경 변수를 지원한다.
yu_ai_manager와 동일한 group_id를 설정하면, 두 프로세스가 디바이스를 공유할 수 있다:

```bash
# yu_ai_manager 측
export HAILO_VDEVICE_GROUP_ID=SHARED

# hailo-ollama 측
HAILO_OLLAMA_VDEVICE_GROUP_ID=SHARED hailo-ollama
```

**주의**: yu_ai_manager는 HailoRT 5.2.0 이상에서 group_id가 동작한다.
hailo-ollama는 v5.3.0 이상이어야 group_id를 수용한다.

## device_manager API

### 모델 취득

```python
from core.hailo_device_core.device_manager import acquire_device, acquire_genai

# InferModel (CLIP, YOLO)
infer_model, configured, quant_params = acquire_device("clip", "/path/to.hef")

# GenAI (LLM, VLM, S2T)
llm = acquire_genai("llm", "/path/to.hef", lambda vd, p: LLM(vd, p))
```

- 동일 owner + 동일 HEF -> 기존 세션 재사용
- 동일 owner + 다른 HEF -> 기존 모델을 해제하고 새 모델 생성
- 다른 owner -> **공존** (기존 모델은 해제되지 않음)

### 모델 해제

```python
from core.hailo_device_core.device_manager import release_device, shutdown_all

release_device("clip")   # CLIP만 해제, 나머지는 계속 동작
shutdown_all()            # 모든 모델 + VDevice 해제 (프로세스 종료 시)
```

### 상태 확인

```python
from core.hailo_device_core.device_manager import (
    get_active_owners, is_model_active,
    is_hailo_available, is_genai_available,
)

get_active_owners()       # ["clip", "yolo", "llm"]
is_model_active("clip")   # True
```

## 트러블슈팅

### VDevice 생성 에러

**증상**: `HAILO_OUT_OF_PHYSICAL_DEVICES(74)` 또는 `Failed to create VDevice`

**원인**: 다른 프로세스가 다른 group_id로 디바이스를 점유하고 있음

**대처**:
1. hailo-ollama가 가동 중인지 확인:
   ```bash
   ps aux | grep hailo-ollama
   ```
2. group_id를 맞추거나 정지:
   ```bash
   sudo systemctl stop hailo-ollama
   ```

### 디바이스가 해제되지 않음

**대처**:
1. yu 프로세스를 재시작
2. 좀비 프로세스를 확인:
   ```bash
   sudo lsof /dev/hailo* 2>/dev/null
   kill <PID>
   ```
3. Hailo 드라이버를 리셋:
   ```bash
   sudo systemctl restart hailort.service
   ```

## API 사용 가이드

| 모델 구조 | 권장 API | 이유 |
|---|---|---|
| 단순 (1입력, YOLO 등) | `InferModel` | `create_infer_model()` + `configure()`로 동작 |
| 복잡 (2입력+, Whisper 등) | `GenAI SDK` | InferModel은 `INVALID_ARGUMENT`를 반환 |
| CLIP 인코더 | `InferModel` | 1입력 1출력으로 문제 없음 |
| LLM (qwen2.5 등) | `GenAI SDK` | 자기회귀 디코딩이 필요 |

## 이력

- **v4.61.0**: 공유 VDevice 방식으로 전환. 배타 acquire/release를 폐지하고, CLIP + YOLO + LLM 동시 동작에 대응.
- **v4.60.1**: 모든 소비자를 device_manager 경유로 통일 (배타 방식).
- **v4.60.0 이전**: 각 소비자가 개별적으로 VDevice()를 호출하여, 충돌 에러가 빈발.
