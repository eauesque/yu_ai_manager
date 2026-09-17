# Pattern: Shared VDevice Manager for Multi-Model Hailo-10H Applications

Python 애플리케이션이 Hailo-10H NPU에서 같은 프로세스 내에서 여러 Hailo 모델
(YOLO / CLIP / LLM / VLM / Whisper 등)을 호스팅하고자 할 때 사용할 수 있는
구현 패턴입니다.

**대상**: 단일 애플리케이션에서 Hailo-10H 칩에 여러 모델을 함께 실행하려는
개발자들입니다.

---

## TL;DR

- Hailo-10H는 **정확히 하나의 물리 장치**를 가집니다.
- 같은 프로세스에서 `VDevice()`를 두 번 생성하면
  `HAILO_OUT_OF_PHYSICAL_DEVICES(74)` 오류가 발생합니다.
- 일반적인 원인: 모델 전환 중 지연된 해제, 백그라운드 프리로더 경쟁, 내부적으로
  `VDevice`를 구성하고 버리는 `is_available()` 검사.
- 해결책: **단일 프로세스 전역 `VDevice` 싱글톤**을 도입하고 모든 모델이
  owner 키 레지스트리를 통해 접근하도록 합니다.
- `VDevice.create_params().group_id`를 설정하면 같은 물리 장치를 **별도의
  여러 프로세스 간에도 공유**할 수 있습니다 (HailoRT 스케줄러가 시간 분할로
  접근을 관리합니다).

---

## 증상

```
[HailoRT] [error] Failed to create vdevice. there are not enough free devices. requested: 1, found: 0
[HailoRT] [error] CHECK_SUCCESS failed with status=HAILO_OUT_OF_PHYSICAL_DEVICES(74)
hailo_platform.pyhailort.pyhailort.HailoRTStatusException: 74
```

스택 트레이스는 보통 YOLO, CLIP 또는 LLM 초기화를 가리키지만, 실제 원인은
이전에 `VDevice`를 획득했으나 해제하지 않은 **다른 컴포넌트**입니다.

---

## 전형적인 실패 시나리오

### 시나리오 1: 백그라운드 프리로더 경쟁

```
app startup
  └─ preloader thread
       ├─ CLIP init → VDevice() [A]
       └─ YOLO init → VDevice() [B]  ← [A]이 여전히 장치를 보유 → 실패
```

### 시나리오 2: 파괴적인 `is_available()` 검사

```python
class YoloEngine:
    @staticmethod
    def is_available():
        try:
            vd = VDevice()   # 확인용으로만 획득
            del vd            # GC 타이밍에 따라 즉시 해제되지 않을 수 있음
            return True
        except Exception:
            return False

# 호출자
if YoloEngine.is_available():     # 여기서 VDevice를 획득한 후 버림
    engine = YoloEngine()          # 다시 획득하려고 시도 → 실패할 수 있음
```

### 시나리오 3: 모델 전환 중 지연된 해제

```python
# del만으로는 VDevice를 즉시 해제하지 않음
del self.vd                 # 참조 카운트 감소
self.vd = VDevice()         # 이전 VDevice가 아직 GC 대기 중일 수 있음 → 실패
```

해결책은 새 VDevice를 생성하기 전에 `self.vd.release()`를 명시적으로
호출하는 것입니다.

### 시나리오 4: 독립 모듈이 독립적으로 초기화

여러 기능 모듈 (확장, 플러그인 등)이 각각 로드 시 `VDevice()`를 호출하면
거의 확실히 충돌합니다.

---

## 안티패턴

```python
# ❌ module_yolo.py
from hailo_platform import VDevice

class YoloEngine:
    def __init__(self):
        self.vd = VDevice()    # 독립적 획득
        self.model = self.vd.create_infer_model("yolov8n.hef")
        self.configured = self.model.configure()

    @staticmethod
    def is_available():
        try:
            VDevice()              # 파괴적 상태 검사
            return True
        except Exception:
            return False


# ❌ module_clip.py
class ClipEngine:
    def __init__(self):
        self.vd = VDevice()    # YoloEngine과 충돌
        ...
```

---

## 추천 패턴: Owner 키 기반 공유 매니저

```python
"""device_manager.py — process-wide Hailo VDevice owner."""
import gc
import os
import threading
from typing import Callable, Dict, Optional, Tuple

_lock = threading.Lock()
_vdevice = None
_models: Dict[str, dict] = {}

# 다른 프로세스와 물리 장치를 공유하는 데 사용됩니다.
_GROUP_ID = os.environ.get("HAILO_VDEVICE_GROUP_ID", "MY_APP_SHARED")


def _ensure_vdevice():
    """단일 VDevice를 지연 생성합니다 (호출자는 _lock을 보유해야 함)."""
    global _vdevice
    if _vdevice is not None:
        return _vdevice
    from hailo_platform import VDevice
    params = VDevice.create_params()
    params.group_id = _GROUP_ID
    _vdevice = VDevice(params)
    return _vdevice


def acquire_infer_model(owner: str, hef_path: str) -> Tuple:
    """공유 VDevice에서 (InferModel, ConfiguredInferModel)을 획득합니다.

    같은 owner + 같은 HEF면 기존 세션을 재사용합니다. 같은 owner이지만
    다른 HEF면 먼저 이전을 해제한 후 새 것을 획득합니다.
    """
    with _lock:
        existing = _models.get(owner)
        if existing and existing["hef"] == hef_path:
            return existing["infer_model"], existing["configured"]

        if existing:
            _release_internal(owner)

        vd = _ensure_vdevice()
        infer_model = vd.create_infer_model(hef_path)
        configured = infer_model.configure()

        _models[owner] = {
            "type": "infer",
            "infer_model": infer_model,
            "configured": configured,
            "hef": hef_path,
        }
        return infer_model, configured


def acquire_genai(
    owner: str,
    model_path: str,
    factory: Callable,
) -> object:
    """GenAI 모델 (LLM / VLM / Speech2Text)을 획득합니다.

    `factory`는 `(vdevice, model_path) -> constructed_instance` 형태입니다.
    예: `lambda vd, p: LLM(vd, p)`
    """
    with _lock:
        existing = _models.get(owner)
        if existing and existing["hef"] == model_path:
            return existing["instance"]

        if existing:
            _release_internal(owner)

        vd = _ensure_vdevice()
        instance = factory(vd, model_path)

        _models[owner] = {
            "type": "genai",
            "instance": instance,
            "hef": model_path,
        }
        return instance


def release(owner: str) -> bool:
    """`owner`가 보유한 모델을 해제합니다. VDevice 자체는 유지합니다."""
    with _lock:
        return _release_internal(owner)


def _release_internal(owner: str) -> bool:
    entry = _models.pop(owner, None)
    if entry is None:
        return False
    if entry["type"] == "genai":
        try:
            entry["instance"].release()
        except Exception:
            pass
    # InferModel은 Python 참조를 버리면 됩니다
    gc.collect()
    return True


def shutdown() -> None:
    """프로세스 종료 시 호출: 모든 모델과 VDevice를 해제합니다."""
    global _vdevice
    with _lock:
        for owner in list(_models.keys()):
            _release_internal(owner)
        if _vdevice is not None:
            try:
                _vdevice.release()
            except Exception:
                pass
            _vdevice = None
        gc.collect()


def is_hailo_available() -> bool:
    """비파괴적 검사 — VDevice를 구성하지 않습니다."""
    try:
        import hailo_platform  # noqa: F401
        return True
    except ImportError:
        return False
```

---

## 사용 예제

### YOLO (InferModel)

```python
from device_manager import acquire_infer_model, release, is_hailo_available
import numpy as np

class YoloEngine:
    def __init__(self, hef_path: str):
        self.infer_model, self.configured = acquire_infer_model("yolo", hef_path)
        self.input_shape = tuple(self.infer_model.inputs[0].shape)

    def detect(self, image_uint8: np.ndarray):
        bindings = self.configured.create_bindings()
        bindings.input().set_buffer(image_uint8)
        for out in self.infer_model.outputs:
            fmt = str(getattr(out.format, "type", "")).lower()
            dtype = np.float32 if "float" in fmt else np.uint8
            buf = np.zeros(tuple(out.shape), dtype=dtype)
            bindings.output(out.name).set_buffer(buf)
        self.configured.run([bindings], timeout=10000)
        return bindings

    def close(self):
        release("yolo")

    @staticmethod
    def is_available() -> bool:
        return is_hailo_available()   # VDevice를 건드리지 않습니다
```

### LLM (GenAI)

```python
from hailo_platform.genai import LLM
from device_manager import acquire_genai, release

class MyLlm:
    def __init__(self, hef_path: str):
        self.llm = acquire_genai(
            "llm", hef_path,
            lambda vd, p: LLM(vd, p),
        )

    def generate(self, prompt: list, **kwargs) -> str:
        return self.llm.generate_all(prompt=prompt, **kwargs)

    def close(self):
        release("llm")
```

### 공존하는 YOLO + CLIP + LLM

서로 다른 owner 이름을 사용하면 **2개의 InferModel과 1개의 GenAI 모델을
같은 VDevice에서 동시에 로드**할 수 있습니다. 내부 HailoRT 스케줄러
(ROUND_ROBIN)가 자동으로 하드웨어 접근을 시간 분할합니다:

```python
yolo = YoloEngine("yolov8n.hef")           # owner="yolo"
clip = ClipEncoder("clip_vit_b_16.hef")    # owner="clip"
llm = MyLlm("Qwen2.5-1.5B-Instruct.hef")   # owner="llm"

# 한 물리 장치에서 활성화된 3개 모델
bbox = yolo.detect(image)
embedding = clip.encode(image)
text = llm.generate([{"role": "user", "content": "..."}])
```

---

## 중요 설계 사항

### 1. `is_available()`은 파괴적이면 안 됨

`VDevice`를 구성했다가 버리는 "상태 검사"가 이 종류의 버그를 일으키는
가장 흔한 원인입니다. 절대로 이렇게 하지 마세요.

대신 임포트가 작동하는지 확인하세요:

```python
def is_hailo_available() -> bool:
    try:
        import hailo_platform  # noqa: F401
        return True
    except ImportError:
        return False
```

VDevice를 구성하지 않고 하드웨어 존재를 확인하고 싶으면 파일시스템 수준에서
`/sys/class/hailo*` 또는 `/dev/h1x-*`를 확인하세요 — 하지만 순전히
버리기 위해 `VDevice`를 구성하지는 마세요.

### 2. Owner 이름 네임스페이스 설계

같은 HEF를 공유해야 하는 컴포넌트들은 **같은 owner 이름**을 사용합니다.
여러 모듈이 모두 같은 YOLOv8n을 사용하면, 모두 owner `"yolo"` 아래에서
획득하며 자동으로 세션을 공유합니다:

```python
# 모듈 A
yolo_a = acquire_infer_model("yolo", "yolov8n.hef")

# 모듈 B (같은 HEF)
yolo_b = acquire_infer_model("yolo", "yolov8n.hef")
# → 같은 infer_model / configured를 반환, 재로드 없음
```

고유한 HEF를 가진 컴포넌트들은 고유한 owner 이름을 얻습니다:

| 컴포넌트 | Owner | 참고 |
|---|---|---|
| General YOLO | `"yolo"` | 공유됨 |
| General CLIP | `"clip"` | 공유됨 |
| Custom tagger (고유 HEF) | `"my-tagger"` | 고유함 |
| LLM | `"llm"` | GenAI |
| VLM | `"vlm"` | GenAI |
| Speech2Text | `"s2t"` | GenAI |

### 3. 프로세스 간 공유를 위해 `group_id` 사용

`VDevice.create_params().group_id`를 설정하면 **서로 다른 프로세스**가
같은 물리 장치를 공유할 수 있습니다:

```python
params = VDevice.create_params()
params.group_id = "MY_APP_SHARED"   # 환경 변수, 설정 등으로 통일
vd = VDevice(params)
```

같은 `group_id`로 `VDevice(params)`를 호출하는 다른 프로세스는 HailoRT
스케줄러에 의해 당신과 나란히 요청이 시간 분할될 것입니다. 이것이
`hailo-ollama` 같은 외부 도구가 당신의 추론 프로세스와 병렬로 실행될 수
있는 방식입니다.

### 4. 종료 훅은 필수

프로세스가 충돌하면 `VDevice`가 해제되지 않으며 `/dev/h1x-0`이
좀비 파일 디스크립터에 의해 유지됩니다. 이후 시작은
`HAILO_OUT_OF_PHYSICAL_DEVICES(74)` 오류가 발생할 때까지 좀비를 kill할
필요가 있습니다. 종료 훅을 설치하세요:

```python
import atexit
import signal
from device_manager import shutdown

atexit.register(shutdown)

def _signal_handler(signum, frame):
    shutdown()
    raise KeyboardInterrupt

signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)
```

문제가 발생했을 때의 복구:

```bash
# 장치를 보유한 프로세스 찾기
lsof /dev/h1x-0        # hailort 5.3.0+
lsof /dev/hailort0     # hailort 5.2.0 이전

# 강제 종료
kill -9 <PID>
```

### 5. 같은 VDevice에서 InferModel과 GenAI 혼합

HailoRT 5.2.0과 5.3.0에서 검증됨: **여러 InferModel (예: YOLO + CLIP)과
여러 GenAI 모델 (LLM, VLM, Speech2Text)이 같은 `VDevice`에서 동시에
공존할 수 있습니다.**

주의사항:

- `VDevice`를 생성한 후 같은 인스턴스에 대해
  `create_infer_model()`과 `LLM(vd, path)`을 모두 호출할 수 있습니다.
- 그러나 `VDevice` 인스턴스 자체는 **같은 Python 객체**여야 합니다.
  같은 `group_id`로 두 번째 `VDevice()`를 생성하고 다른 Python
  변수에서 세션을 재사용하려고 하면 작동하지 않습니다 —
  `InferModel.run()`이 실패합니다.

### 6. 초기화 실패 시 쿨다운

Hailo 초기화는 비용이 많이 듭니다 (~1초). 실패 후 즉시 재시도하면
더 많은 실패만 초래합니다. 재시도 폭증을 억제하려면 짧은 쿨다운
(예: 60초)을 도입하세요:

```python
import time
from typing import Optional

_init_failed_at: Optional[float] = None
_INIT_COOLDOWN_SEC = 60.0

def try_initialize():
    global _init_failed_at
    now = time.time()
    if _init_failed_at and (now - _init_failed_at) < _INIT_COOLDOWN_SEC:
        return None  # 여전히 쿨다운 중
    try:
        return acquire_infer_model("yolo", "yolov8n.hef")
    except Exception:
        _init_failed_at = now
        raise
```

---

## HailoRT 5.2.0과 5.3.0 모두에서 검증됨

이 패턴은 Raspberry Pi 5 + AI HAT 2에서 다음 환경으로 검증되었습니다:

- HailoRT 5.2.0 및 5.3.0
- 2× InferModel (YOLOv8n + CLIP ViT-B/16) + 1× GenAI LLM (Qwen2.5-1.5B)
  동시 실행
- 2× InferModel + 1× GenAI VLM (Qwen2-VL-2B) 동시 실행
- 2× InferModel + 1× GenAI Speech2Text (Whisper-Base) 동시 실행

물리적 제약 (프로세스당 하나의 물리 장치)은 5.3.0에서도 변경되지 않습니다.
`group_id` 기반 공유 및 내부 ROUND_ROBIN 스케줄러는 여전히 지원됩니다.

---

## 관련 문서

- HailoRT 5.2.0 → 5.3.0 마이그레이션 노트 (`HAILORT_5_3_0_MIGRATION.md`)
- 5.3.0의 새로운 `hailo1x_pci` 드라이버에서 장치 노드가 `/dev/hailort0`에서
  `/dev/h1x-0`으로 변경됨
