# Pattern: 多模型 Hailo-10H 應用程式的共享 VDevice 管理

在單一 Hailo-10H NPU 的同一程序中託管多個 Hailo 模型 (YOLO / CLIP / LLM / VLM / Whisper 等) 的 Python 應用程式實現模式。

**目標受眾**：嘗試在單一應用程式的單個 Hailo-10H 晶片上並存多個模型的開發人員。

---

## TL;DR

- Hailo-10H 具有**恰好一個物理裝置**。
- 在同一程序中建立 `VDevice()` 兩次會失敗，錯誤為
  `HAILO_OUT_OF_PHYSICAL_DEVICES(74)`。
- 常見原因：模型交換期間的延遲釋放、背景預加載器競爭條件，以及在內部構造和丟棄 `VDevice` 的 `is_available()` 檢查。
- 解決方案：引入**單一程序範圍的 `VDevice` singleton**，讓每個模型透過擁有者鑰匙登錄表訪問它。
- 設定 `VDevice.create_params().group_id`，相同的物理裝置也可以在**多個獨立程序之間共享**（HailoRT 排程器進行時間切片訪問）。

---

## 症狀

```
[HailoRT] [error] Failed to create vdevice. there are not enough free devices. requested: 1, found: 0
[HailoRT] [error] CHECK_SUCCESS failed with status=HAILO_OUT_OF_PHYSICAL_DEVICES(74)
hailo_platform.pyhailort.pyhailort.HailoRTStatusException: 74
```

即時堆疊追蹤通常指向 YOLO、CLIP 或 LLM 的初始化，但真正的罪魁禍首是**不同的元件**，它較早取得了 `VDevice` 但從未釋放它。

---

## 典型失敗場景

### 場景 1：背景預加載器競爭條件

```
應用程式啟動
  └─ 預加載器執行緒
       ├─ CLIP 初始化 → VDevice() [A]
       └─ YOLO 初始化 → VDevice() [B]  ← [A] 仍然持有裝置 → 失敗
```

### 場景 2：破壞性 `is_available()` 檢查

```python
class YoloEngine:
    @staticmethod
    def is_available():
        try:
            vd = VDevice()   # 僅為檢查而取得
            del vd            # 可能不會立即釋放 (GC 時序)
            return True
        except Exception:
            return False

# 呼叫者
if YoloEngine.is_available():     # 在此處取得 VDevice 然後丟棄
    engine = YoloEngine()          # 嘗試再次取得 → 可能失敗
```

### 場景 3：模型交換期間的延遲釋放

```python
# del 單獨並不會立即釋放 VDevice
del self.vd                 # 參考計數下降
self.vd = VDevice()         # 先前的 VDevice 可能仍在 GC 待處理 → 失敗
```

修正方法是在建立新的 VDevice 之前顯式呼叫 `self.vd.release()`。

### 場景 4：獨立模組獨立初始化

如果多個功能模組 (擴充功能、外掛程式等) 各自在載入時呼叫 `VDevice()`，它們幾乎肯定會衝突。

---

## 反模式

```python
# ❌ module_yolo.py
from hailo_platform import VDevice

class YoloEngine:
    def __init__(self):
        self.vd = VDevice()    # 獨立取得
        self.model = self.vd.create_infer_model("yolov8n.hef")
        self.configured = self.model.configure()

    @staticmethod
    def is_available():
        try:
            VDevice()              # 破壞性的健康檢查
            return True
        except Exception:
            return False


# ❌ module_clip.py
class ClipEngine:
    def __init__(self):
        self.vd = VDevice()    # 與 YoloEngine 衝突
        ...
```

---

## 建議模式：擁有者鑰匙共享管理

```python
"""device_manager.py — 程序範圍的 Hailo VDevice 擁有者。"""
import gc
import os
import threading
from typing import Callable, Dict, Optional, Tuple

_lock = threading.Lock()
_vdevice = None
_models: Dict[str, dict] = {}

# 用於與其他程序共享物理裝置。
_GROUP_ID = os.environ.get("HAILO_VDEVICE_GROUP_ID", "MY_APP_SHARED")


def _ensure_vdevice():
    """延遲建立單一 VDevice (呼叫者必須持有 _lock)。"""
    global _vdevice
    if _vdevice is not None:
        return _vdevice
    from hailo_platform import VDevice
    params = VDevice.create_params()
    params.group_id = _GROUP_ID
    _vdevice = VDevice(params)
    return _vdevice


def acquire_infer_model(owner: str, hef_path: str) -> Tuple:
    """在共享 VDevice 上取得 (InferModel, ConfiguredInferModel)。

    相同的擁有者 + 相同的 HEF 重新使用現有會話。相同的擁有者但不同的
    HEF 會先釋放舊的，然後取得新的。
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
    """取得 GenAI 模型 (LLM / VLM / Speech2Text)。

    `factory` 是 `(vdevice, model_path) -> constructed_instance`。
    範例：`lambda vd, p: LLM(vd, p)`
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
    """釋放 `owner` 持有的模型。保持 VDevice 本身為活躍狀態。"""
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
    # InferModel 只需要丟棄 Python 參考
    gc.collect()
    return True


def shutdown() -> None:
    """在程序退出時呼叫：釋放每個模型和 VDevice。"""
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
    """非破壞性檢查 — 不構造 VDevice。"""
    try:
        import hailo_platform  # noqa: F401
        return True
    except ImportError:
        return False
```

---

## 使用範例

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
        return is_hailo_available()   # 不觸及 VDevice
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

### 並存 YOLO + CLIP + LLM

使用不同的擁有者名稱，您可以在同一 VDevice 上同時保持**兩個 InferModel 和一個 GenAI 模型已載入**。內部 HailoRT 排程器 (ROUND_ROBIN) 自動進行硬體訪問時間切片：

```python
yolo = YoloEngine("yolov8n.hef")           # owner="yolo"
clip = ClipEncoder("clip_vit_b_16.hef")    # owner="clip"
llm = MyLlm("Qwen2.5-1.5B-Instruct.hef")   # owner="llm"

# 三個模型在一個物理裝置上活躍
bbox = yolo.detect(image)
embedding = clip.encode(image)
text = llm.generate([{"role": "user", "content": "..."}])
```

---

## 重要設計要點

### 1. `is_available()` 必須不具破壞性

建立 `VDevice` 且丟棄它的「健康檢查」是此類錯誤最常見的單一原因。永遠不要這樣做。

相反，檢查匯入是否有效：

```python
def is_hailo_available() -> bool:
    try:
        import hailo_platform  # noqa: F401
        return True
    except ImportError:
        return False
```

如果您想在不匯入的情況下確認硬體存在，檢查檔案系統層級的 `/sys/class/hailo*` 或 `/dev/h1x-*` — 但不要建立 `VDevice` 僅為了丟棄它。

### 2. 擁有者名稱命名空間設計

應該共享相同 HEF 的元件使用**相同的擁有者名稱**。如果多個模組都使用相同的 YOLOv8n，它們都在擁有者 `"yolo"` 下取得，並自動共享會話：

```python
# 模組 A
yolo_a = acquire_infer_model("yolo", "yolov8n.hef")

# 模組 B (相同的 HEF)
yolo_b = acquire_infer_model("yolo", "yolov8n.hef")
# → 傳回相同的 infer_model / configured，無需重新載入
```

具有獨特 HEF 的元件獲得獨特的擁有者名稱：

| 元件 | 擁有者 | 備註 |
|---|---|---|
| 一般 YOLO | `"yolo"` | 共享 |
| 一般 CLIP | `"clip"` | 共享 |
| 自訂標籤器 (獨特 HEF) | `"my-tagger"` | 獨特 |
| LLM | `"llm"` | GenAI |
| VLM | `"vlm"` | GenAI |
| Speech2Text | `"s2t"` | GenAI |

### 3. 使用 `group_id` 進行跨程序共享

設定 `VDevice.create_params().group_id` 讓**不同的程序**共享相同的物理裝置：

```python
params = VDevice.create_params()
params.group_id = "MY_APP_SHARED"   # 透過環境變數、組態等統一
vd = VDevice(params)
```

另一個呼叫 `VDevice(params)` 且具有相同 `group_id` 的程序將看到其請求由 HailoRT 排程器與您的請求一起進行時間切片。這是外部工具 (如 `hailo-ollama`) 如何能與您自己的推論程序平行執行的方式。

### 4. 關閉鉤子是強制的

如果程序當機，`VDevice` 不會被釋放，`/dev/h1x-0` 保持由殭屍檔案描述符持有。後續啟動將獲得 `HAILO_OUT_OF_PHYSICAL_DEVICES(74)`，直到您殺死殭屍。安裝關閉鉤子：

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

當事情出現問題時恢復：

```bash
# 找到持有裝置的程序
lsof /dev/h1x-0        # hailort 5.3.0+
lsof /dev/hailort0     # hailort 5.2.0 及更早版本

# 強制終止它
kill -9 <PID>
```

### 5. 在同一 VDevice 上混合 InferModel 和 GenAI

在 HailoRT 5.2.0 和 5.3.0 上驗證：**多個 InferModel (例如 YOLO + CLIP) 和多個 GenAI 模型 (LLM、VLM、Speech2Text) 可以在同一 `VDevice` 上同時並存。**

注意事項：

- 建立 `VDevice` 後，您可以對同一實例呼叫 `create_infer_model()` 和 `LLM(vd, path)`。
- 但是，`VDevice` 實例本身**必須是同一個 Python 物件**。使用相同的 `group_id` 建立第二個 `VDevice()` 並期望從不同的 Python 變數重新使用會話無效 — `InferModel.run()` 將失敗。

### 6. 初始化失敗時的冷卻期

Hailo 初始化成本高昂 (~1 秒)。失敗後立即重試通常只會產生更多失敗。引入短暫冷卻期 (例如 60 秒) 來抑制重試風暴：

```python
import time
from typing import Optional

_init_failed_at: Optional[float] = None
_INIT_COOLDOWN_SEC = 60.0

def try_initialize():
    global _init_failed_at
    now = time.time()
    if _init_failed_at and (now - _init_failed_at) < _INIT_COOLDOWN_SEC:
        return None  # 仍在冷卻期
    try:
        return acquire_infer_model("yolo", "yolov8n.hef")
    except Exception:
        _init_failed_at = now
        raise
```

---

## 在 HailoRT 5.2.0 和 5.3.0 上驗證

此模式已在 Raspberry Pi 5 + AI HAT 2 上驗證，具備：

- HailoRT 5.2.0 和 5.3.0
- 2× InferModel (YOLOv8n + CLIP ViT-B/16) + 1× GenAI LLM (Qwen2.5-1.5B)
  同時
- 2× InferModel + 1× GenAI VLM (Qwen2-VL-2B) 同時
- 2× InferModel + 1× GenAI Speech2Text (Whisper-Base) 同時

物理約束 (每個程序一個物理裝置) 在 5.3.0 中未改變。基於 `group_id` 的共享和內部 ROUND_ROBIN 排程器仍然受支援。

---

## 相關

- HailoRT 5.2.0 → 5.3.0 遷移註記 (`HAILORT_5_3_0_MIGRATION.md`)
- 裝置節點在新 `hailo1x_pci` 驅動程式的 5.3.0 中從 `/dev/hailort0` 重新命名為 `/dev/h1x-0`
