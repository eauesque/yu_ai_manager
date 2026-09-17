# HailoRT 5.2.0 → 5.3.0 Migration Notes

Findings from upgrading HailoRT from 5.2.0 to 5.3.0 on a Raspberry Pi 5 +
AI HAT 2 (Hailo-10H), based on end-to-end smoke testing and direct git
diff analysis of the official `v5.2.0` / `v5.3.0` tags.

**Audience**: Developers using Hailo-10H NPUs from Python (`pyhailort`).

---

## TL;DR

- **The practical breaking-change impact is essentially zero** for a
  typical Python inference application. Despite the headline numbers
  (688 files changed, +12,035 / −8,987 lines), the `VDevice`,
  `InferModel`, and GenAI (`LLM` / `VLM` / `Speech2Text`) surfaces are
  fully backward compatible.
- Most of the change volume is **removals of Hailo-8 camera / ISP /
  firmware-management APIs** plus internal refactors. None of this
  affects bare NPU inference on Hailo-10H.
- **Existing `.hef` files from the v5.2.0 era load unchanged on the
  5.3.0 runtime.** Verified on 5 models (YOLOv8n, CLIP ViT-B/16,
  Qwen2.5-1.5B, Qwen2-VL-2B, Whisper-Base).
- The Linux driver was renamed from `hailo_pci` to `hailo1x_pci` and
  the device node from `/dev/hailort0` to **`/dev/h1x-0`**. `pyhailort`
  resolves the new node internally, so Python code that uses `VDevice()`
  needs no changes. **Only Docker device passthrough needs updating.**
- `Speech2Text.SegmentInfo` exposes `text` / `start_sec` / `end_sec`
  attributes (same as 5.2.0). It does **not** expose `start` or
  `start_time` — defensive code using those names silently returns 0.0.

---

## 1. Scope of Change

Direct diff of the `v5.2.0` and `v5.3.0` tags in the official HailoRT
GitHub repository:

| Scope | Files | Added | Removed |
|---|---:|---:|---:|
| Total | 688 | +12,035 | −8,987 |
| Public C++ headers (`include/hailo/`) | 27 | +205 | **−383** |
| Python bindings (`bindings/python/`) | 35 | +306 | **−413** |
| `pyhailort.py` alone | 1 | +98 | **−158** |

**Removals outnumber additions** — this is a "stripping down" release.
Most of what was stripped is unrelated to the core inference path.

---

## 2. Removed APIs — Hailo-8 Camera / ISP / Firmware Only

`hailort/libhailort/include/hailo/device.hpp` lost 169 lines and
`platform.h` lost 75. Everything deleted is low-level device control:

- `firmware_update()` / `second_stage_update()` (firmware rewriting)
- `store_sensor_config()` / `store_isp_config()`
- `sensor_dump_config()` / `sensor_reset()`
- `sensor_load_and_start_config()`
- `sensor_set_i2c_bus_index()` / `sensor_set_generic_i2c_slave()`
- `sensor_get_sections_info()`
- `examine_user_config()` / `read_user_config()` /
  `write_user_config()` / `erase_user_config()`

These are all APIs for **Hailo-8 AI Vision camera modules** (SoC-style
boards where the Hailo chip directly controls the ISP and image sensor).
They are never called by a typical `VDevice` → `InferModel` → `generate`
flow on a bare Hailo-10H NPU.

**Impact**: Zero for pure NPU inference applications. Only applications
that actually drive Hailo-8 camera modules need to audit their usage.

---

## 3. Python Signature Changes

| API | v5.2.0 | v5.3.0 | Compatibility |
|---|---|---|---|
| `Speech2Text.generate_all_segments(timeout_ms=)` | default `10000` | default `600000` | ✅ Default only; existing calls unchanged |
| `Speech2Text.generate_all_text(timeout_ms=)` | same | same | ✅ Same |
| `LLM.read_all(timeout_ms=10000)` | has default | default **removed** (required) | ⚠️ `read_all()` without args → `TypeError` |
| `DeviceArchitecture.__init__` | 9 positional args | +`chip_serial_number` (10 args) | ⚠️ Direct construction breaks |

**`read_all()` fix is a one-liner**:

```python
# Before (v5.2.0 style, 10 s default)
text = generator.read_all()

# After (v5.3.0 requires explicit timeout)
text = generator.read_all(timeout_ms=600000)  # 10 minutes
```

`DeviceArchitecture` is rarely constructed by user code, so its
signature change rarely matters.

---

## 4. C++ Header Renames (Transparent Through Python)

Breaking for applications that use HailoRT directly from C++:

- **`Speech2Text::DEFAULT_OPERATION_TIMEOUT`** (10 s) →
  **`DEFAULT_GENERATE_ALL_TIMEOUT`** (10 min), renamed and lengthened
- **`LLM::DEFAULT_READ_ALL_TIMEOUT`** added, also 10 min
- `vlm.hpp` adds four `generate_from_embeddings()` overloads

These renames do not propagate through the Python bindings.

---

## 5. NMS Bounding-Box Coordinate Fix (Behavior Change)

A logic fix in `pyhailort.py`'s NMS post-processing:

```python
# v5.2.0
y_min = numpy.ceil(bbox[0] * image_height)
x_min = numpy.ceil(bbox[1] * image_width)
bbox_width = numpy.ceil((bbox[3] - bbox[1]) * image_width)

# v5.3.0
y_min = int(max(numpy.floor(bbox[0] * image_height), 0))
x_min = int(max(numpy.floor(bbox[1] * image_width), 0))
x_max = int(min(numpy.ceil(bbox[3] * image_width), image_width))
bbox_width = x_max - x_min
```

Improvements:

- Image-boundary `max(0, …)` / `min(image_width, …)` clipping added
- `ceil` → `floor` (prevents overshoot)
- `bbox_width` recomputed from clipped `x_max - x_min`

**Behavior difference**: With the same model and the same image, NMS
outputs may shift by ±1 pixel at boundaries. Applications that write
their own NMS post-processing are unaffected. Applications calling
pyhailort's `_output_raw_buffer_to_nms_with_byte_mask_*` helpers will
see bounding boxes near image edges change shape.

---

## 6. New APIs (Additive)

- **`VDevice::create_session(uint16_t port)`** — network-based inference
  session API (new feature)
- **`VLM::generate_from_embeddings()`** — 4 overloads that accept
  pre-computed image / video embeddings as `MemoryView` inputs.
  Lets you compute image embeddings once and reuse them across multiple
  VLM calls, skipping re-encoding
- **`InferModel::set_nms_classes_filter_mask(vector<bool>)`** — class-
  level filtering for NMS outputs on-chip
- **`Device::query_performance_stats(sampling_period_ms)`** —
  configurable sampling period
- **`Device::get_current_limit()`** — query the current limit
- **`DeviceArchitecture.chip_serial_number`** — read the chip serial

All additive, so no existing code breaks. Adopt as needed.

---

## 7. Environment Changes

### 7.1 New Linux PCI Driver

| Item | Old | New |
|---|---|---|
| Kernel module | `hailo_pci` | `hailo1x_pci` |
| Device node | `/dev/hailort0` (or `/dev/hailo0`) | `/dev/h1x-0` |

```bash
lsmod | grep hailo        # → hailo1x_pci
ls /dev/h1x-*             # → /dev/h1x-0
```

**`pyhailort` resolves the new device node internally**, so Python code
using `VDevice()` continues to work without modification. Only code
that directly opens `/dev/hailo*` or `/dev/hailort0` needs updating.

#### Docker / Podman passthrough

Update the device passthrough declarations:

```yaml
# docker-compose.yml
services:
  my-app:
    devices:
      - /dev/h1x-0:/dev/h1x-0   # was: /dev/hailort0:/dev/hailort0
```

Also update any systemd unit `DeviceAllow=` lines and udev rules.

### 7.2 numpy Constraint Lifted

- v5.2.0 `setup.py`: `numpy<2` (pinned)
- v5.3.0 `setup.py`: `numpy` (no upper bound)

Applications previously pinned to numpy 1.x can upgrade to numpy 2.x
alongside the HailoRT bump.

### 7.3 HEF Binary Compatibility

**`.hef` files downloaded under the v5.2.0 bucket load and run unchanged
on the 5.3.0 runtime.** Verified on 5 models (Raspberry Pi 5 + AI HAT 2):

| Model | File | Result |
|---|---|---|
| YOLOv8n | `yolov8n.hef` | ✅ `create_infer_model()` + `.run()` |
| CLIP ViT-B/16 image encoder | `clip_vit_b_16_image_encoder.hef` | ✅ 512-dim output |
| Qwen2.5-1.5B Instruct | `Qwen2.5-1.5B-Instruct.hef` | ✅ `LLM.generate_all()` returns valid text |
| Qwen2-VL-2B Instruct | `Qwen2-VL-2B-Instruct.hef` | ✅ `VLM.generate_all(frames=[…])` returns valid text |
| Whisper-Base | `Whisper-Base.hef` | ✅ `Speech2Text.generate_all_segments()` returns `SegmentInfo` |

HEF binary format can break across major runtime updates in theory, but
**this did not happen between 5.2.0 and 5.3.0**.

### 7.4 HEF Download URL Buckets

Hailo Developer Zone (`dev-public.hailo.ai`) hosts both v5.2.0 and
v5.3.0 buckets in parallel:

```
https://dev-public.hailo.ai/v5.2.0/blob/<model>.hef
https://dev-public.hailo.ai/v5.3.0/blob/<model>.hef
```

As of 2026-04-06, the v5.3.0 bucket status:

| Model | v5.3.0 bucket |
|---|---|
| Qwen2.5-1.5B-Instruct | ✅ 200 |
| DeepSeek-R1-Distill-Qwen-1.5B | ✅ 200 |
| Qwen2.5-Coder-1.5B-Instruct | ✅ 200 |
| Qwen2-VL-2B-Instruct | ✅ 200 |
| Whisper-Base / Whisper-Small | ✅ 200 |
| **Llama-3.2-1B-Instruct** | ❌ **404** |

→ Applications that need Llama-3.2-1B must continue pulling from the
v5.2.0 bucket for now. The v5.2.0 HEF loads correctly on the 5.3.0
runtime.

---

## 8. `Speech2Text.SegmentInfo` Attribute Names

On both v5.2.0 and v5.3.0, `Speech2Text.generate_all_segments()` returns
`SegmentInfo` objects with these public attributes:

```python
seg.text        # str
seg.start_sec   # float (seconds)
seg.end_sec     # float (seconds)
```

**There is no `seg.start` or `seg.start_time`.** Older documentation and
sample code sometimes references those names, but they will either
raise `AttributeError` or — more insidiously — silently return 0.0
when wrapped in defensive code like
`getattr(seg, "start", 0.0) or getattr(seg, "start_time", 0.0)`.

To confirm the actual attribute names on your runtime:

```python
from hailo_platform import VDevice
from hailo_platform.genai import Speech2Text, Speech2TextTask
import numpy as np

vd = VDevice()
s2t = Speech2Text(vd, "/path/to/Whisper-Base.hef")
audio = (np.random.default_rng(0).standard_normal(32000) * 0.01).astype("<f4")
segments = s2t.generate_all_segments(
    audio_data=audio, task=Speech2TextTask.TRANSCRIBE,
    language="en", timeout_ms=30000,
)
if segments:
    print([a for a in dir(segments[0]) if not a.startswith("_")])
    # => ['end_sec', 'start_sec', 'text']
```

---

## 9. Smoke Test Script

Minimal script to verify that your environment actually works after
upgrading to 5.3.0:

```python
"""HailoRT 5.3.0 smoke test — VDevice / InferModel / LLM / Speech2Text."""
import numpy as np
from hailo_platform import VDevice

# 1. Create VDevice
params = VDevice.create_params()
params.group_id = "SMOKE_TEST"
vd = VDevice(params)
print("1. VDevice OK")

# 2. InferModel path (YOLOv8n or any existing HEF)
im = vd.create_infer_model("/path/to/yolov8n.hef")
conf = im.configure()
inp = im.inputs[0]
bindings = conf.create_bindings()
bindings.input().set_buffer(np.zeros(tuple(inp.shape), dtype=np.uint8))
for o in im.outputs:
    fmt = str(getattr(o.format, "type", "")).lower()
    dtype = np.float32 if "float" in fmt else np.uint8
    bindings.output(o.name).set_buffer(np.zeros(tuple(o.shape), dtype=dtype))
conf.run([bindings], timeout=10000)
print("2. InferModel (YOLO) OK")
del conf, im

vd.release()
del vd

# 3. GenAI LLM path
from hailo_platform.genai import LLM
params = VDevice.create_params(); params.group_id = "SMOKE_TEST"
vd = VDevice(params)
llm = LLM(vd, "/path/to/Qwen2.5-1.5B-Instruct.hef")
text = llm.generate_all(
    prompt=[{"role": "user", "content": "Say hi in one word."}],
    temperature=0.1, max_generated_tokens=16,
)
print(f"3. LLM OK: {text!r}")
llm.release(); vd.release()

# 4. Speech2Text path
from hailo_platform.genai import Speech2Text, Speech2TextTask
params = VDevice.create_params(); params.group_id = "SMOKE_TEST"
vd = VDevice(params)
s2t = Speech2Text(vd, "/path/to/Whisper-Base.hef")
audio = (np.random.default_rng(0).standard_normal(32000) * 0.01).astype("<f4")
segments = s2t.generate_all_segments(
    audio_data=audio, task=Speech2TextTask.TRANSCRIBE,
    language="en", timeout_ms=30000,
)
print(f"4. Speech2Text OK: {len(segments)} segments")
if segments:
    seg = segments[0]
    print(f"   attrs: text={seg.text!r} start_sec={seg.start_sec} end_sec={seg.end_sec}")
s2t.release(); vd.release()

print("\nAll smoke tests passed.")
```

---

## 10. Upgrade Checklist

Points to audit in your code before or during the 5.2.0 → 5.3.0 upgrade:

- [ ] `VDevice()` / `create_infer_model()` / `InferModel.configure()` —
      **no changes needed**
- [ ] `LLM(vd, path)` / `VLM(vd, path)` / `Speech2Text(vd, path)`
      constructors — **no changes needed**
- [ ] `LLM.generate()` / `.generate_all()` / `VLM.generate(frames=…)` /
      `.generate_all()` keyword arguments — **no changes needed**
- [ ] `Speech2Text.generate_all_segments(audio_data=, task=, language=,
      timeout_ms=)` — **no changes needed** if you pass `timeout_ms`
      explicitly
- [ ] Check whether you call `LLM.read_all()` without a `timeout_ms`
      argument → if so, add an explicit timeout
- [ ] Check whether you construct `DeviceArchitecture` directly → if so,
      add `chip_serial_number`
- [ ] `grep` for direct opens of `/dev/hailo*` or `/dev/hailort0` → if
      any, replace with `/dev/h1x-0` (or better, go through `pyhailort`)
- [ ] Update Docker / Podman `devices:` sections to `/dev/h1x-0`
- [ ] Update systemd unit `DeviceAllow=` lines and udev rules
- [ ] `grep` for `SegmentInfo` attribute access using `.start` or
      `.start_time` → switch to `.start_sec` / `.end_sec`. Verify that
      Whisper output timestamps are not silently 0.0 in your app
- [ ] If you pinned numpy to 1.x because of v5.2.0's `numpy<2`, you can
      now lift the pin
- [ ] Existing `.hef` files do **not** need to be re-downloaded
- [ ] If you hardcode a `v5.2.0` bucket in your HEF download URLs,
      promote to `v5.3.0` (keep `v5.2.0` for Llama-3.2-1B)
- [ ] If you rely on pyhailort's built-in NMS post-processing, be
      aware that bounding boxes near image edges may shift by ±1 pixel

---

## 11. Commands Used for the Investigation

Assumes you have the official HailoRT repository cloned:

```bash
cd ~/hailort

# Overall diff size
git diff --stat v5.2.0 v5.3.0 | tail

# Public C++ header diff
git diff --stat v5.2.0 v5.3.0 -- 'hailort/libhailort/include/hailo/'

# Python bindings diff
git diff --stat v5.2.0 v5.3.0 -- 'hailort/libhailort/bindings/python/'

# Full diff of pyhailort.py
git diff v5.2.0 v5.3.0 -- \
  'hailort/libhailort/bindings/python/platform/hailo_platform/pyhailort/pyhailort.py'

# Public API diff of a specific header (function signatures only)
git diff v5.2.0 v5.3.0 -- 'hailort/libhailort/include/hailo/genai/llm/llm.hpp' \
  | grep -E '^[+-]' | grep -E 'Expected|hailo_status|void|static'

# APIs removed from device.hpp
git diff v5.2.0 v5.3.0 -- 'hailort/libhailort/include/hailo/device.hpp' \
  | grep '^-' | grep 'virtual'
```

For API analysis, the C++ headers carry the most information per line —
the Python bindings are mostly pybind11 boilerplate, so naive line-count
diffs are misleading. Grep for public symbols instead.

---

## 12. Conclusion

The headline "688 files changed" is very far from the actual impact.
On a typical Hailo-10H NPU inference application:

- **Core NPU inference APIs (`VDevice` / `InferModel` / GenAI) are
  fully backward compatible**
- All removed APIs are Hailo-8 camera / sensor / ISP / firmware
  management surfaces that have nothing to do with NPU-only usage
- **All existing `.hef` files load without re-downloading**
- The only environment-level change required is updating Docker device
  passthrough to `/dev/h1x-0`

The main quality-of-life improvements visible after upgrading:

- Timeout defaults extended massively (10 s → 10 min), reducing
  spurious timeouts on long-form generation
- `FormatType.FLOAT32` is now available (manual quantization /
  dequantization was required on 5.2.0)
- NMS coordinate clipping bugfix
- numpy 2.x upgrade path is now open
- `VLM.generate_from_embeddings()` allows reusing precomputed image
  embeddings across multiple VLM calls

If you maintain a Hailo-10H Python application that was pinned to
5.2.0 and have been putting off the upgrade, this should reassure
you that the migration is nearly a no-op.
