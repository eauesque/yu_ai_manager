# 模式：多模型 Hailo-10H 应用的共享 VDevice 管理器

一种 Python 应用程序的实现模式，用于在 Hailo-10H NPU 的同一进程中托管多个 Hailo 模型（YOLO / CLIP / LLM / VLM / Whisper 等）。

**目标受众**：尝试在单个 Hailo-10H 芯片的单个应用程序中共存多个模型的开发者。

---

## 摘要

- Hailo-10H **恰好有一个物理设备**。
- 在同一进程中两次创建 `VDevice()` 会失败，错误为 `HAILO_OUT_OF_PHYSICAL_DEVICES(74)`。
- 常见原因：模型切换期间的延迟释放、后台预加载器竞争、以及内部构造和丢弃 `VDevice` 的 `is_available()` 检查。
- 解决方案：引入一个**单一进程级 `VDevice` 单例**，让每个模型通过所有者键控的注册表访问它。
- 设置 `VDevice.create_params().group_id`，同一物理设备也可以**跨多个进程共享**（HailoRT 调度器对访问进行时间分片）。

---

## 症状

```
[HailoRT] [error] Failed to create vdevice. there are not enough free devices. requested: 1, found: 0
[HailoRT] [error] CHECK_SUCCESS failed with status=HAILO_OUT_OF_PHYSICAL_DEVICES(74)
hailo_platform.pyhailort.pyhailort.HailoRTStatusException: 74
```

直接的堆栈跟踪通常指向 YOLO、CLIP 或 LLM 的初始化——但真正的罪魁祸首是**另一个组件**，它之前获取了 `VDevice` 但从未释放。

---

## 典型故障场景

### 场景 1：后台预加载器竞争

```
app startup
  └─ preloader thread
       ├─ CLIP init → VDevice() [A]
       └─ YOLO init → VDevice() [B]  ← [A] 仍然持有设备 → 失败
```

### 场景 2：破坏性 `is_available()` 检查

```python
class YoloEngine:
    @staticmethod
    def is_available():
        try:
            vd = VDevice()   # 仅为了检查而获取
            del vd            # 可能不会立即释放（GC 时序问题）
            return True
        except Exception:
            return False

# 调用者
if YoloEngine.is_available():     # 在这里获取然后丢弃一个 VDevice
    engine = YoloEngine()          # 尝试再次获取 → 可能失败
```

### 场景 3：模型切换期间的延迟释放

```python
# del 单独不会立即释放 VDevice
del self.vd                 # 引用计数下降
self.vd = VDevice()         # 之前的 VDevice 可能仍在 GC 待处理中 → 失败
```

解决方法是在创建新的 VDevice 之前显式调用 `self.vd.release()`。

### 场景 4：独立模块独立初始化

如果多个功能模块（扩展、插件等）各自在加载时调用 `VDevice()`，它们几乎肯定会产生碰撞。

---

## 反模式

```python
# ❌ module_yolo.py
from hailo_platform import VDevice

class YoloEngine:
    def __init__(self):
        self.vd = VDevice()    # 独立获取
        self.model = self.vd.create_infer_model("yolov8n.hef")
        self.configured = self.model.configure()

    @staticmethod
    def is_available():
        try:
            VDevice()              # 破坏性健康检查
            return True
        except Exception:
            return False


# ❌ module_clip.py
class ClipEngine:
    def __init__(self):
        self.vd = VDevice()    # 与 YoloEngine 冲突
        ...
```

---

## 推荐模式：所有者键控共享管理器

```python
"""device_manager.py — 进程级 Hailo VDevice 所有者。"""
import gc
import os
import threading
from typing import Callable, Dict, Optional, Tuple

_lock = threading.Lock()
_vdevice = None
_models: Dict[str, dict] = {}

# 用于与其他进程共享物理设备。
_GROUP_ID = os.environ.get("HAILO_VDEVICE_GROUP_ID", "MY_APP_SHARED")


def _ensure_vdevice():
    """懒惰地创建单一 VDevice（调用者必须持有 _lock）。"""
    global _vdevice
    if _vdevice is not None:
        return _vdevice
    from hailo_platform import VDevice
    params = VDevice.create_params()
    params.group_id = _GROUP_ID
    _vdevice = VDevice(params)
    return _vdevice


def acquire_infer_model(owner: str, hef_path: str) -> Tuple:
    """在共享 VDevice 上获取 (InferModel, ConfiguredInferModel)。

    同一所有者 + 相同 HEF 重用现有会话。同一所有者但不同 HEF 则先释放旧的，
    然后获取新的。
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
    """获取 GenAI 模型（LLM / VLM / Speech2Text）。

    `factory` 是 `(vdevice, model_path) -> constructed_instance`。
    示例：`lambda vd, p: LLM(vd, p)`
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
    """释放由 `owner` 持有的模型。保持 VDevice 本身活跃。"""
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
    # InferModel 只需要 Python 引用被丢弃
    gc.collect()
    return True


def shutdown() -> None:
    """在进程退出时调用：释放每个模型和 VDevice。"""
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
    """非破坏性检查 — 不构造 VDevice。"""
    try:
        import hailo_platform  # noqa: F401
        return True
    except ImportError:
        return False
```

---

## 使用示例

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
        return is_hailo_available()   # 不会触碰 VDevice
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

### 共存 YOLO + CLIP + LLM

使用不同的所有者名称，您可以在同一 VDevice 上同时保持**两个 InferModel 和一个 GenAI 模型加载**。内部 HailoRT 调度器 (ROUND_ROBIN) 自动对硬件访问进行时间分片：

```python
yolo = YoloEngine("yolov8n.hef")           # owner="yolo"
clip = ClipEncoder("clip_vit_b_16.hef")    # owner="clip"
llm = MyLlm("Qwen2.5-1.5B-Instruct.hef")   # owner="llm"

# 三个模型在一个物理设备上活跃
bbox = yolo.detect(image)
embedding = clip.encode(image)
text = llm.generate([{"role": "user", "content": "..."}])
```

---

## 重要的设计要点

### 1. `is_available()` 必须非破坏性

一个"健康检查"，构造 `VDevice` 然后丢弃它是这类 bug 最常见的原因。永远不要这样做。

改为检查导入是否有效：

```python
def is_hailo_available() -> bool:
    try:
        import hailo_platform  # noqa: F401
        return True
    except ImportError:
        return False
```

如果您想在不导入的情况下确认硬件存在，请在文件系统级别检查 `/sys/class/hailo*` 或 `/dev/h1x-*` ——但不要仅为了丢弃而构造 `VDevice`。

### 2. 所有者名称命名空间设计

应该共享相同 HEF 的组件使用**相同的所有者名称**。如果多个模块都使用相同的 YOLOv8n，它们都在所有者 `"yolo"` 下获取，并自动共享会话：

```python
# 模块 A
yolo_a = acquire_infer_model("yolo", "yolov8n.hef")

# 模块 B（相同 HEF）
yolo_b = acquire_infer_model("yolo", "yolov8n.hef")
# → 返回相同的 infer_model / configured，无重新加载
```

具有唯一 HEF 的组件获得唯一的所有者名称：

| 组件 | 所有者 | 备注 |
|---|---|---|
| 通用 YOLO | `"yolo"` | 共享 |
| 通用 CLIP | `"clip"` | 共享 |
| 自定义标记器（唯一 HEF） | `"my-tagger"` | 唯一 |
| LLM | `"llm"` | GenAI |
| VLM | `"vlm"` | GenAI |
| Speech2Text | `"s2t"` | GenAI |

### 3. 使用 `group_id` 进行跨进程共享

设置 `VDevice.create_params().group_id` 让**不同进程**共享同一物理设备：

```python
params = VDevice.create_params()
params.group_id = "MY_APP_SHARED"   # 通过环境变量、配置等统一
vd = VDevice(params)
```

另一个进程调用 `VDevice(params)` 并使用相同的 `group_id` 将看到其请求由 HailoRT 调度器与您的请求进行时间分片。这是外部工具（如 `hailo-ollama`）如何能与您自己的推理进程并行运行的方式。

### 4. 关闭钩子是强制的

如果进程崩溃，`VDevice` 不会被释放，`/dev/h1x-0` 保持被僵尸文件描述符持有。后续启动将获得 `HAILO_OUT_OF_PHYSICAL_DEVICES(74)` 直到您杀死僵尸。安装关闭钩子：

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

当事情出错时的恢复：

```bash
# 找到持有设备的进程
lsof /dev/h1x-0        # hailort 5.3.0+
lsof /dev/hailort0     # hailort 5.2.0 及更早版本

# 强制杀死它
kill -9 <PID>
```

### 5. 在同一 VDevice 上混合 InferModel 和 GenAI

在 HailoRT 5.2.0 和 5.3.0 上已验证：**多个 InferModel（例如 YOLO + CLIP）和多个 GenAI 模型（LLM、VLM、Speech2Text）可以在同一 `VDevice` 上同时共存。**

注意事项：

- 创建 `VDevice` 后，您可以对同一实例调用 `create_infer_model()` 和 `LLM(vd, path)` 两者。
- 但是，`VDevice` 实例本身**必须是相同的 Python 对象**。创建具有相同 `group_id` 的第二个 `VDevice()` 并希望从不同的 Python 变量重用会话不起作用——`InferModel.run()` 将失败。

### 6. 初始化失败时的冷却期

Hailo 初始化成本昂贵（~1 秒）。失败后立即重试通常只会产生更多失败。引入短冷却期（例如 60 秒）来抑制重试风暴：

```python
import time
from typing import Optional

_init_failed_at: Optional[float] = None
_INIT_COOLDOWN_SEC = 60.0

def try_initialize():
    global _init_failed_at
    now = time.time()
    if _init_failed_at and (now - _init_failed_at) < _INIT_COOLDOWN_SEC:
        return None  # 仍在冷却期
    try:
        return acquire_infer_model("yolo", "yolov8n.hef")
    except Exception:
        _init_failed_at = now
        raise
```

---

## 在 HailoRT 5.2.0 和 5.3.0 上验证

此模式已在树莓派 5 + AI HAT 2 上验证，配置如下：

- HailoRT 5.2.0 和 5.3.0
- 2× InferModel（YOLOv8n + CLIP ViT-B/16）+ 1× GenAI LLM（Qwen2.5-1.5B）同时运行
- 2× InferModel + 1× GenAI VLM（Qwen2-VL-2B）同时运行
- 2× InferModel + 1× GenAI Speech2Text（Whisper-Base）同时运行

物理约束（每个进程一个物理设备）在 5.3.0 中未改变。基于 `group_id` 的共享和内部 ROUND_ROBIN 调度器仍然得到支持。

---

## 相关资源

- HailoRT 5.2.0 → 5.3.0 迁移注释 (`HAILORT_5_3_0_MIGRATION.md`)
- 设备节点在 5.3.0 中的新 `hailo1x_pci` 驱动程序下从 `/dev/hailort0` 重命名为 `/dev/h1x-0`
