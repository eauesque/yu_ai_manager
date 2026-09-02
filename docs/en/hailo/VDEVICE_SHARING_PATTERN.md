# Pattern: Shared VDevice Manager for Multi-Model Hailo-10H Applications

An implementation pattern for Python applications that want to host
multiple Hailo models (YOLO / CLIP / LLM / VLM / Whisper, etc.) in the
same process on a Hailo-10H NPU.

**Audience**: Developers trying to coexist multiple models in a single
application on a single Hailo-10H chip.

---

## TL;DR

- Hailo-10H has **exactly one physical device**.
- Creating `VDevice()` twice in the same process fails with
  `HAILO_OUT_OF_PHYSICAL_DEVICES(74)`.
- Common causes: lazy release during model swap, background preloader
  races, and an `is_available()` check that internally constructs and
  discards a `VDevice`.
- Solution: introduce a **single process-wide `VDevice` singleton** and
  have every model access it through an owner-keyed registry.
- Set `VDevice.create_params().group_id` and the same physical device
  can also be **shared across separate processes** (the HailoRT
  scheduler time-slices access).

---

## Symptoms

```
[HailoRT] [error] Failed to create vdevice. there are not enough free devices. requested: 1, found: 0
[HailoRT] [error] CHECK_SUCCESS failed with status=HAILO_OUT_OF_PHYSICAL_DEVICES(74)
hailo_platform.pyhailort.pyhailort.HailoRTStatusException: 74
```

The immediate stack trace usually points at the initialization of YOLO,
CLIP, or an LLM — but the real culprit is a **different component** that
acquired a `VDevice` earlier and never released it.

---

## Typical Failure Scenarios

### Scenario 1: Background preloader race

```
app startup
  └─ preloader thread
       ├─ CLIP init → VDevice() [A]
       └─ YOLO init → VDevice() [B]  ← [A] still holds the device → fails
```

### Scenario 2: Destructive `is_available()` check

```python
class YoloEngine:
    @staticmethod
    def is_available():
        try:
            vd = VDevice()   # acquire just to check
            del vd            # may not release immediately (GC timing)
            return True
        except Exception:
            return False

# Caller
if YoloEngine.is_available():     # acquires then drops a VDevice here
    engine = YoloEngine()          # tries to acquire again → may fail
```

### Scenario 3: Lazy release during model swap

```python
# del alone does NOT immediately release the VDevice
del self.vd                 # reference count drops
self.vd = VDevice()         # previous VDevice may still be GC-pending → fails
```

The fix is to call `self.vd.release()` explicitly before creating a new
one.

### Scenario 4: Independent modules initializing independently

If several feature modules (extensions, plugins, etc.) each call
`VDevice()` at load time, they will almost certainly collide.

---

## Anti-pattern

```python
# ❌ module_yolo.py
from hailo_platform import VDevice

class YoloEngine:
    def __init__(self):
        self.vd = VDevice()    # independent acquisition
        self.model = self.vd.create_infer_model("yolov8n.hef")
        self.configured = self.model.configure()

    @staticmethod
    def is_available():
        try:
            VDevice()              # destructive health check
            return True
        except Exception:
            return False


# ❌ module_clip.py
class ClipEngine:
    def __init__(self):
        self.vd = VDevice()    # collides with YoloEngine
        ...
```

---

## Recommended Pattern: Owner-Keyed Shared Manager

```python
"""device_manager.py — process-wide Hailo VDevice owner."""
import gc
import os
import threading
from typing import Callable, Dict, Optional, Tuple

_lock = threading.Lock()
_vdevice = None
_models: Dict[str, dict] = {}

# Used to share the physical device with other processes.
_GROUP_ID = os.environ.get("HAILO_VDEVICE_GROUP_ID", "MY_APP_SHARED")


def _ensure_vdevice():
    """Lazily create the single VDevice (caller must hold _lock)."""
    global _vdevice
    if _vdevice is not None:
        return _vdevice
    from hailo_platform import VDevice
    params = VDevice.create_params()
    params.group_id = _GROUP_ID
    _vdevice = VDevice(params)
    return _vdevice


def acquire_infer_model(owner: str, hef_path: str) -> Tuple:
    """Acquire (InferModel, ConfiguredInferModel) on the shared VDevice.

    Same owner + same HEF reuses the existing session. Same owner but
    a different HEF releases the old one first, then acquires the new.
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
    """Acquire a GenAI model (LLM / VLM / Speech2Text).

    `factory` is `(vdevice, model_path) -> constructed_instance`.
    Example: `lambda vd, p: LLM(vd, p)`
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
    """Release the model held by `owner`. Keeps the VDevice itself alive."""
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
    # InferModel just needs the Python references dropped
    gc.collect()
    return True


def shutdown() -> None:
    """Call on process exit: release every model and the VDevice."""
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
    """Non-destructive check — does NOT construct a VDevice."""
    try:
        import hailo_platform  # noqa: F401
        return True
    except ImportError:
        return False
```

---

## Usage Examples

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
        return is_hailo_available()   # does NOT touch VDevice
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

### Coexisting YOLO + CLIP + LLM

Using distinct owner names, you can keep **two InferModels and one
GenAI model loaded on the same VDevice simultaneously**. The internal
HailoRT scheduler (ROUND_ROBIN) time-slices hardware access
automatically:

```python
yolo = YoloEngine("yolov8n.hef")           # owner="yolo"
clip = ClipEncoder("clip_vit_b_16.hef")    # owner="clip"
llm = MyLlm("Qwen2.5-1.5B-Instruct.hef")   # owner="llm"

# Three models active on one physical device
bbox = yolo.detect(image)
embedding = clip.encode(image)
text = llm.generate([{"role": "user", "content": "..."}])
```

---

## Important Design Points

### 1. `is_available()` must not be destructive

A "health check" that constructs a `VDevice` and discards it is the
single most common cause of this class of bug. Never do this.

Instead, check whether the import works:

```python
def is_hailo_available() -> bool:
    try:
        import hailo_platform  # noqa: F401
        return True
    except ImportError:
        return False
```

If you want to confirm hardware presence without importing, check for
`/sys/class/hailo*` or `/dev/h1x-*` at the filesystem level — but do
not construct a `VDevice` solely to discard it.

### 2. Owner-name namespace design

Components that should share the same HEF use the **same owner name**.
If several modules all use the same YOLOv8n, they all acquire under
owner `"yolo"` and automatically share the session:

```python
# Module A
yolo_a = acquire_infer_model("yolo", "yolov8n.hef")

# Module B (same HEF)
yolo_b = acquire_infer_model("yolo", "yolov8n.hef")
# → returns the same infer_model / configured, no reload
```

Components with unique HEFs get unique owner names:

| Component | Owner | Notes |
|---|---|---|
| General YOLO | `"yolo"` | Shared |
| General CLIP | `"clip"` | Shared |
| Custom tagger (unique HEF) | `"my-tagger"` | Unique |
| LLM | `"llm"` | GenAI |
| VLM | `"vlm"` | GenAI |
| Speech2Text | `"s2t"` | GenAI |

### 3. Use `group_id` for cross-process sharing

Setting `VDevice.create_params().group_id` lets **different processes**
share the same physical device:

```python
params = VDevice.create_params()
params.group_id = "MY_APP_SHARED"   # unify via env var, config, etc.
vd = VDevice(params)
```

Another process that calls `VDevice(params)` with the same `group_id`
will see its requests time-sliced alongside yours by the HailoRT
scheduler. This is how external tools like `hailo-ollama` can run in
parallel with your own inference process.

### 4. Shutdown hooks are mandatory

If the process crashes, the `VDevice` is not released and `/dev/h1x-0`
stays held by a zombie file descriptor. Subsequent startups will get
`HAILO_OUT_OF_PHYSICAL_DEVICES(74)` until you kill the zombie. Install
shutdown hooks:

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

Recovery when things go wrong:

```bash
# Find the process holding the device
lsof /dev/h1x-0        # hailort 5.3.0+
lsof /dev/hailort0     # hailort 5.2.0 and earlier

# Force-kill it
kill -9 <PID>
```

### 5. Mixing InferModel and GenAI on the same VDevice

Verified on HailoRT 5.2.0 and 5.3.0: **multiple InferModels (e.g. YOLO
+ CLIP) and multiple GenAI models (LLM, VLM, Speech2Text) can coexist
on the same `VDevice` simultaneously.**

Caveats:

- After creating the `VDevice`, you can call both
  `create_infer_model()` and `LLM(vd, path)` against the same instance.
- However, the `VDevice` instance itself **must be the same Python
  object**. Creating a second `VDevice()` with the same `group_id` and
  hoping to reuse the session from a different Python variable does
  not work — `InferModel.run()` will fail.

### 6. Cooldown on initialization failures

Hailo initialization is expensive (~1 second). Immediate retry after
a failure often just produces more failures. Introduce a short cooldown
(e.g. 60 s) to suppress retry storms:

```python
import time
from typing import Optional

_init_failed_at: Optional[float] = None
_INIT_COOLDOWN_SEC = 60.0

def try_initialize():
    global _init_failed_at
    now = time.time()
    if _init_failed_at and (now - _init_failed_at) < _INIT_COOLDOWN_SEC:
        return None  # still in cooldown
    try:
        return acquire_infer_model("yolo", "yolov8n.hef")
    except Exception:
        _init_failed_at = now
        raise
```

---

## Verified on Both HailoRT 5.2.0 and 5.3.0

This pattern has been verified on a Raspberry Pi 5 + AI HAT 2 with:

- HailoRT 5.2.0 and 5.3.0
- 2× InferModel (YOLOv8n + CLIP ViT-B/16) + 1× GenAI LLM (Qwen2.5-1.5B)
  simultaneously
- 2× InferModel + 1× GenAI VLM (Qwen2-VL-2B) simultaneously
- 2× InferModel + 1× GenAI Speech2Text (Whisper-Base) simultaneously

The physical constraint (one physical device per process) is unchanged
in 5.3.0. `group_id`-based sharing and the internal ROUND_ROBIN
scheduler are still supported.

---

## Related

- HailoRT 5.2.0 → 5.3.0 migration notes (`HAILORT_5_3_0_MIGRATION.md`)
- Device node renamed from `/dev/hailort0` to `/dev/h1x-0` under the
  new `hailo1x_pci` driver in 5.3.0
