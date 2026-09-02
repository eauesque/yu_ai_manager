# HailoRT 5.2.0 → 5.3.0 迁移笔记

在 Raspberry Pi 5 + AI HAT 2 (Hailo-10H) 上将 HailoRT 从 5.2.0 升级到
5.3.0 时,通过实机验证和官方 git 标签 (v5.2.0 / v5.3.0) 直接比对所得到
的整理笔记。

**目标读者**:使用 Python (pyhailort) 调用 Hailo-10H NPU 的开发者。

---

## TL;DR

- **实际的破坏性影响几乎为零**。虽然标题数字很大 (688 个文件变更、
  +12,035 / −8,987 行),但 `VDevice`、`InferModel`、以及 GenAI
  (`LLM` / `VLM` / `Speech2Text`) 的主要 API 都完全向后兼容
- 大部分的变更是 **Hailo-8 相机 / ISP / 固件管理 API 的大量删除** 和
  内部重构,与 Hailo-10H NPU 单独使用无关
- **v5.2.0 时代下载的 `.hef` 文件可以直接在 5.3.0 runtime 上加载并推理**
  (YOLOv8n / CLIP ViT-B/16 / Qwen2.5-1.5B / Qwen2-VL-2B / Whisper-Base
  五个模型均已实机验证)
- Linux 驱动程序从 `hailo_pci` 变更为 `hailo1x_pci`,设备节点从
  `/dev/hailort0` 重命名为 **`/dev/h1x-0`**。pyhailort 会在内部解析
  新节点,所以 Python 代码的 `VDevice()` 无需修改。**仅 Docker 的
  设备直通需要更新**
- `Speech2Text.SegmentInfo` 的属性是 `text` / `start_sec` / `end_sec`
  (与 5.2.0 相同。注意不是 `start` / `start_time`)

---

## 1. 变更规模

将官方 HailoRT GitHub 仓库的 `v5.2.0` / `v5.3.0` 标签直接比对的结果:

| 范围 | 文件数 | 新增 | 删除 |
|---|---:|---:|---:|
| 整体 | 688 | +12,035 | −8,987 |
| C++ 公开头文件 (`include/hailo/`) | 27 | +205 | **−383** |
| Python 绑定 (`bindings/python/`) | 35 | +306 | **−413** |
| `pyhailort.py` 单个文件 | 1 | +98 | **−158** |

**删除多于新增**的「剥离型」更新。大部分被删除的内容与核心推理路径
无关。

---

## 2. 被删除的 API — 仅 Hailo-8 相机 / ISP / 固件系统

从 `hailort/libhailort/include/hailo/device.hpp` 删除了 169 行,
`platform.h` 删除了 75 行。删除的对象全部都是这类低级设备控制:

- `firmware_update()` / `second_stage_update()` (固件改写)
- `store_sensor_config()` / `store_isp_config()`
- `sensor_dump_config()` / `sensor_reset()`
- `sensor_load_and_start_config()`
- `sensor_set_i2c_bus_index()` / `sensor_set_generic_i2c_slave()`
- `sensor_get_sections_info()`
- `examine_user_config()` / `read_user_config()` /
  `write_user_config()` / `erase_user_config()`

这些都是 **Hailo-8 AI Vision 相机模块** (ISP 和相机传感器由 Hailo 芯片
直接控制的 SoC 结构) 专用的 API。在 Hailo-10H NPU 单独运行时根本不会
使用。Python (pyhailort) 的典型 `VDevice` → `InferModel` → `generate`
流程不会调用这些函数。

**影响**:纯 NPU 推理应用程序零影响。只有实际使用 Hailo-8 相机模块的
应用程序才需要审查用法。

---

## 3. Python 签名变更

| API | v5.2.0 | v5.3.0 | 兼容性 |
|---|---|---|---|
| `Speech2Text.generate_all_segments(timeout_ms=)` | 默认 `10000` | 默认 `600000` | ✅ 仅默认值变更 (调用兼容) |
| `Speech2Text.generate_all_text(timeout_ms=)` | 同上 | 同上 | ✅ 同上 |
| `LLM.read_all(timeout_ms=10000)` | 有默认值 | 默认值删除 (变必需) | ⚠️ 不带参数调用 `read_all()` 会 TypeError |
| `DeviceArchitecture.__init__` | 9 个参数 | +`chip_serial_number` (10 个) | ⚠️ 直接构造会 TypeError |

**`read_all()` 的修正是一行**:

```python
# 修改前 (5.2.0 风格,默认 10 秒)
text = generator.read_all()

# 修改后 (5.3.0 需要明确指定 timeout)
text = generator.read_all(timeout_ms=600000)  # 10 分钟
```

`DeviceArchitecture` 通常不会被用户代码直接构造,所以这个签名变更
很少会造成影响。

---

## 4. C++ 头文件重命名 (不会传递到 Python 层)

对于从 C++ 直接使用 HailoRT 的应用程序会造成破坏:

- **`Speech2Text::DEFAULT_OPERATION_TIMEOUT`** (10 秒) →
  **`DEFAULT_GENERATE_ALL_TIMEOUT`** (10 分钟),重命名并大幅延长
- 新增 **`LLM::DEFAULT_READ_ALL_TIMEOUT`** 常量,也是 10 分钟
- `vlm.hpp` 新增 4 种 `generate_from_embeddings()` 重载

通过 Python 绑定使用时,这些重命名是透明的。

---

## 5. NMS 边界框坐标错误修正 (行为差异)

`pyhailort.py` 的 NMS 后处理有实现错误修正:

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

改进点:

- 新增图像边界的 `max(0, …)` / `min(image_width, …)` clip
- `ceil` → `floor` (防止溢出)
- 以 clip 后的 `x_max - x_min` 重新计算 `bbox_width`

**行为差异**:相同模型、相同图像,NMS 输出坐标可能在边界附近出现 ±1
像素的偏移。自己实现 NMS 后处理的应用程序不受影响。调用 pyhailort
的 NMS 后处理函数 (`_output_raw_buffer_to_nms_with_byte_mask_*`) 的
应用程序,图像边缘附近的边界框形状会改变。

---

## 6. 新增的 API (新功能)

- **`VDevice::create_session(uint16_t port)`** — 基于网络的推理 Session
  API (新功能)
- **`VLM::generate_from_embeddings()`** — 直接输入预先计算好的图像 /
  视频 embedding 的 4 种重载。将图像编码器的结果缓存后可以省略每次
  VLM 调用时的图像编码
- **`InferModel::set_nms_classes_filter_mask(vector<bool>)`** — NMS
  输出的类别级过滤,可在 NPU 端剔除不需要的类别
- **`Device::query_performance_stats(sampling_period_ms)`** — 可指定
  采样周期
- **`Device::get_current_limit()`** — 查询电流限制
- **`DeviceArchitecture.chip_serial_number`** — 读取芯片序列号

这些全部都是可选项目 (不会破坏现有代码),根据需求采用。

---

## 7. 环境变化

### 7.1 Linux PCI 驱动程序刷新

| 项目 | 旧 | 新 |
|---|---|---|
| 内核模块 | `hailo_pci` | `hailo1x_pci` |
| 设备节点 | `/dev/hailort0` (或 `/dev/hailo0`) | `/dev/h1x-0` |

```bash
lsmod | grep hailo        # → hailo1x_pci
ls /dev/h1x-*             # → /dev/h1x-0
```

**pyhailort 会在内部解析新节点**,所以 Python 代码的 `VDevice()`
无需修改即可运行。只有直接 open `/dev/hailo*` 或 `/dev/hailort0` 的
代码才需要修改。

#### Docker 直通

若通过 Docker / Podman 使用 Hailo,需要更新设备直通的设置:

```yaml
# docker-compose.yml
services:
  my-app:
    devices:
      - /dev/h1x-0:/dev/h1x-0   # 旧:/dev/hailort0:/dev/hailort0
```

systemd unit 的 `DeviceAllow=` 和 udev 规则也要同步更新。

### 7.2 numpy 版本限制解除

- v5.2.0 的 `setup.py`:`numpy<2` 固定
- v5.3.0 的 `setup.py`:无限制 (`numpy`)

过去无法升级到 numpy 2.x 的应用程序,可以在升级 HailoRT 的同时一并
升级 numpy。

### 7.3 HEF 二进制兼容性

**v5.2.0 时代下载的 `.hef` 文件可以直接在 hailort 5.3.0 runtime 上
加载并推理**。以下 5 个模型均已实机验证 (Raspberry Pi 5 + AI HAT 2):

| 模型 | 文件 | 结果 |
|---|---|---|
| YOLOv8n | `yolov8n.hef` | ✅ `create_infer_model()` + `.run()` 成功 |
| CLIP ViT-B/16 image encoder | `clip_vit_b_16_image_encoder.hef` | ✅ 512 维输出 |
| Qwen2.5-1.5B Instruct | `Qwen2.5-1.5B-Instruct.hef` | ✅ `LLM.generate_all()` 正常响应 |
| Qwen2-VL-2B Instruct | `Qwen2-VL-2B-Instruct.hef` | ✅ `VLM.generate_all(frames=[…])` 响应 |
| Whisper-Base | `Whisper-Base.hef` | ✅ `Speech2Text.generate_all_segments()` 获取 SegmentInfo |

一般而言主版本更新时 HEF 二进制格式可能会损坏,但 **5.2.0 → 5.3.0
并没有发生这个问题**。

### 7.4 HEF 下载 URL bucket

Hailo Developer Zone (`dev-public.hailo.ai`) 同时提供 v5.2.0 / v5.3.0
两个 bucket:

```
https://dev-public.hailo.ai/v5.2.0/blob/<model>.hef
https://dev-public.hailo.ai/v5.3.0/blob/<model>.hef
```

确认时间 (2026-04-06) 的 v5.3.0 bucket 状态:

| 模型 | v5.3.0 bucket |
|---|---|
| Qwen2.5-1.5B-Instruct | ✅ 200 |
| DeepSeek-R1-Distill-Qwen-1.5B | ✅ 200 |
| Qwen2.5-Coder-1.5B-Instruct | ✅ 200 |
| Qwen2-VL-2B-Instruct | ✅ 200 |
| Whisper-Base / Whisper-Small | ✅ 200 |
| **Llama-3.2-1B-Instruct** | ❌ **404** |

→ 使用 Llama-3.2-1B 的应用程序暂时需要从 v5.2.0 bucket 获取 (v5.2.0
的 HEF 在 hailort 5.3.0 runtime 上可正常加载)。

---

## 8. `Speech2Text.SegmentInfo` 的属性名称

5.2.0 / 5.3.0 共通,`Speech2Text.generate_all_segments()` 返回的
`SegmentInfo` 对象的公开属性为:

```python
seg.text        # str
seg.start_sec   # float (秒)
seg.end_sec     # float (秒)
```

**没有 `seg.start` 或 `seg.start_time`**。有些旧文档或示例代码会
使用 `seg.start` / `seg.start_time`,这会触发 `AttributeError`,
或者如果通过 `getattr(seg, "start", 0.0)` 这类防御性代码,会变成
**永远返回 0.0 的隐藏 bug**。

确认实际属性名称的方法:

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

## 9. 升级检查清单

升级前应该审查的项目:

- [ ] `VDevice()` / `create_infer_model()` / `InferModel.configure()`
      周边 — **无需修改**
- [ ] `LLM(vd, path)` / `VLM(vd, path)` / `Speech2Text(vd, path)` 的
      构造函数 — **无需修改**
- [ ] `LLM.generate()` / `.generate_all()` / `VLM.generate(frames=…)` /
      `.generate_all()` 的参数 — **无需修改**
- [ ] `Speech2Text.generate_all_segments(…)` — 若有明确指定 `timeout_ms`
      **无需修改**
- [ ] 确认是否有 **不带默认参数调用 `LLM.read_all()`** → 若有则改为
      `read_all(timeout_ms=…)`
- [ ] 确认是否直接构造 `DeviceArchitecture` → 若有则添加
      `chip_serial_number` 参数
- [ ] `grep` 是否有直接 open `/dev/hailo*` / `/dev/hailort0` 的地方 →
      若有则改为 `/dev/h1x-0` (或改用 pyhailort)
- [ ] 将 Docker / Podman 的 `devices:` 部分更新为 `/dev/h1x-0`
- [ ] 更新 systemd unit 的 `DeviceAllow=` 和 udev 规则
- [ ] 有无引用 `SegmentInfo` 的 `.start` / `.start_time` 的旧代码 →
      改为 `.start_sec` / `.end_sec`。确认 Whisper 输出的 timestamp
      是否在应用程序中静默变成 0.0
- [ ] 因为 `numpy<2` 而固定使用 numpy 1.x 的话,可以解除上限
- [ ] 现有 `.hef` 文件无需重新下载
- [ ] 有硬编码 `v5.2.0` bucket 的 HEF 下载 URL → 升级为 `v5.3.0`
      (Llama-3.2-1B 保持 `v5.2.0`)
- [ ] 若依赖 pyhailort 内置的 NMS 后处理,请留意边界框在图像边缘可能
      出现 ±1 像素的偏移

---

## 10. 烟雾测试脚本

升级到 5.3.0 后验证环境是否正常工作的最小脚本:

```python
"""HailoRT 5.3.0 烟雾测试 — VDevice / InferModel / LLM / Speech2Text"""
import numpy as np
from hailo_platform import VDevice

# 1. 创建 VDevice
params = VDevice.create_params()
params.group_id = "SMOKE_TEST"
vd = VDevice(params)
print("1. VDevice OK")

# 2. InferModel 路径 (YOLOv8n 或任何现存的 HEF)
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

# 3. GenAI LLM 路径
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

# 4. Speech2Text 路径
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

## 11. 调查使用的命令

假设你已克隆了官方 HailoRT 仓库:

```bash
cd ~/hailort

# 整体变更规模
git diff --stat v5.2.0 v5.3.0 | tail

# 公开 C++ 头文件差异
git diff --stat v5.2.0 v5.3.0 -- 'hailort/libhailort/include/hailo/'

# Python 绑定差异
git diff --stat v5.2.0 v5.3.0 -- 'hailort/libhailort/bindings/python/'

# pyhailort.py 完整差异
git diff v5.2.0 v5.3.0 -- \
  'hailort/libhailort/bindings/python/platform/hailo_platform/pyhailort/pyhailort.py'

# 特定头文件的公开 API 差异 (仅函数签名)
git diff v5.2.0 v5.3.0 -- 'hailort/libhailort/include/hailo/genai/llm/llm.hpp' \
  | grep -E '^[+-]' | grep -E 'Expected|hailo_status|void|static'

# 从 device.hpp 删除的 API
git diff v5.2.0 v5.3.0 -- 'hailort/libhailort/include/hailo/device.hpp' \
  | grep '^-' | grep 'virtual'
```

对于 API 分析,C++ 头文件提供的信息密度最高 — Python 绑定主要是
pybind11 样板代码,所以直接对行数的差异分析会出现误导。应该用
grep 检索公开符号来替代。

---

## 12. 结论

从「688 个文件变更」的外观与实际的影响有相当大的差距。在一般的
Hailo-10H NPU 推理应用程序上:

- **核心 NPU 推理 API (`VDevice` / `InferModel` / GenAI) 完全向后兼容**
- 被删除的 API 全部都是 **Hailo-8 相机 / 传感器 / ISP / 固件管理**
  系统,与 NPU 单独使用无关
- **现有的 `.hef` 全部无需重新下载即可运作**
- 环境方面必要的对应只有 **Docker 直通改为 `/dev/h1x-0`**

5.3.0 升级后可感受到的主要改善:

- Timeout 默认值大幅延长 (10 秒 → 10 分钟),减少长时间生成的超时问题
- `FormatType.FLOAT32` 可用 (5.2.0 需要手动量化 / 反量化)
- NMS 坐标计算的边界 clip
- numpy 2.x 升级路径开通
- `VLM.generate_from_embeddings()` 可重用预先计算好的图像 embedding

希望这些笔记对考虑在相同环境下升级的开发者有帮助。
