# HailoRT 5.2.0 → 5.3.0 遷移注記

在 Raspberry Pi 5 + AI HAT 2（Hailo-10H）上從 HailoRT 5.2.0 升級至 5.3.0 的發現，基於端對端冒煙測試以及對官方 `v5.2.0` / `v5.3.0` 標籤的直接 git 差異分析。

**受眾**：使用 Hailo-10H NPU 的 Python 開發者（`pyhailort`）。

---

## TL;DR

- **對於典型的 Python 推論應用程式，實際的破壞性變更影響基本上為零**。儘管標題數字很大（688 個檔案變更、+12,035 / −8,987 行），但 `VDevice`、`InferModel` 和 GenAI（`LLM` / `VLM` / `Speech2Text`）的 API 表面完全向後相容。
- 變更量的大部分是**移除 Hailo-8 攝影機 / ISP / 韌體管理 API** 以及內部重構。這些都不影響 Hailo-10H 上的純 NPU 推論。
- **v5.2.0 時代的現有 `.hef` 檔案在 5.3.0 執行時上載入並執行無異**。已在 5 個模型上驗證（YOLOv8n、CLIP ViT-B/16、Qwen2.5-1.5B、Qwen2-VL-2B、Whisper-Base）。
- Linux 驅動程式從 `hailo_pci` 重新命名為 `hailo1x_pci`，設備節點從 `/dev/hailort0` 重新命名為 **`/dev/h1x-0`**。`pyhailort` 內部解析新節點，因此使用 `VDevice()` 的 Python 程式碼無需變更。**只有 Docker 設備透傳需要更新**。
- `Speech2Text.SegmentInfo` 公開 `text` / `start_sec` / `end_sec` 屬性（與 5.2.0 相同）。它**不**公開 `start` 或 `start_time` — 使用這些名稱的防禦性程式碼會靜默返回 0.0。

---

## 1. 變更範圍

官方 HailoRT GitHub 倉庫中 `v5.2.0` 和 `v5.3.0` 標籤的直接差異：

| 範圍 | 檔案 | 新增 | 移除 |
|---|---:|---:|---:|
| 總計 | 688 | +12,035 | −8,987 |
| 公開 C++ 標頭（`include/hailo/`） | 27 | +205 | **−383** |
| Python 綁定（`bindings/python/`） | 35 | +306 | **−413** |
| 單獨 `pyhailort.py` | 1 | +98 | **−158** |

**移除數量多於新增** — 這是一個「精簡版」發佈。大部分被移除的內容與核心推論路徑無關。

---

## 2. 已移除的 API — 僅限 Hailo-8 攝影機 / ISP / 韌體

`hailort/libhailort/include/hailo/device.hpp` 失去 169 行，`platform.h` 失去 75 行。所有刪除的內容都是低階設備控制：

- `firmware_update()` / `second_stage_update()`（韌體改寫）
- `store_sensor_config()` / `store_isp_config()`
- `sensor_dump_config()` / `sensor_reset()`
- `sensor_load_and_start_config()`
- `sensor_set_i2c_bus_index()` / `sensor_set_generic_i2c_slave()`
- `sensor_get_sections_info()`
- `examine_user_config()` / `read_user_config()` / `write_user_config()` / `erase_user_config()`

這些都是**Hailo-8 AI Vision 攝影機模組**（Hailo 晶片直接控制 ISP 和影像感測器的 SoC 樣式主板）的 API。在典型的 `VDevice` → `InferModel` → `generate` 流程中，在純 Hailo-10H NPU 上不會呼叫它們。

**影響**：對純 NPU 推論應用程式沒有影響。只有實際驅動 Hailo-8 攝影機模組的應用程式需要稽核其使用情況。

---

## 3. Python 簽名變更

| API | v5.2.0 | v5.3.0 | 相容性 |
|---|---|---|---|
| `Speech2Text.generate_all_segments(timeout_ms=)` | 預設 `10000` | 預設 `600000` | ✅ 只有預設值；現有呼叫無變化 |
| `Speech2Text.generate_all_text(timeout_ms=)` | 相同 | 相同 | ✅ 相同 |
| `LLM.read_all(timeout_ms=10000)` | 有預設值 | 預設值**已移除**（必需） | ⚠️ 不帶引數的 `read_all()` → `TypeError` |
| `DeviceArchitecture.__init__` | 9 個位置引數 | +`chip_serial_number`（10 個引數） | ⚠️ 直接建構會中斷 |

**`read_all()` 修復是一行程式碼**：

```python
# 之前（v5.2.0 樣式，10 秒預設）
text = generator.read_all()

# 之後（v5.3.0 需要明確的逾時）
text = generator.read_all(timeout_ms=600000)  # 10 分鐘
```

`DeviceArchitecture` 很少由使用者程式碼直接建構，因此其簽名變更很少重要。

---

## 4. C++ 標頭重新命名（通過 Python 透明）

對於直接從 C++ 使用 HailoRT 的應用程式會破壞相容性：

- **`Speech2Text::DEFAULT_OPERATION_TIMEOUT`**（10 秒）→ **`DEFAULT_GENERATE_ALL_TIMEOUT`**（10 分鐘），重新命名並延長
- **`LLM::DEFAULT_READ_ALL_TIMEOUT`** 新增，同樣 10 分鐘
- `vlm.hpp` 新增四個 `generate_from_embeddings()` 多載

這些重新命名不會通過 Python 綁定傳播。

---

## 5. NMS 邊界框座標修復（行為變更）

`pyhailort.py` NMS 後處理中的邏輯修復：

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

改進：

- 新增影像邊界 `max(0, …)` / `min(image_width, …)` 裁切
- `ceil` → `floor`（防止超出）
- `bbox_width` 從裁切的 `x_max - x_min` 重新計算

**行為差異**：使用相同的模型和相同的影像，NMS 輸出可能在邊界處移動 ±1 像素。編寫自己的 NMS 後處理的應用程式不受影響。呼叫 pyhailort 的 `_output_raw_buffer_to_nms_with_byte_mask_*` 幫手的應用程式會看到影像邊緣附近的邊界框改變形狀。

---

## 6. 新增 API（附加）

- **`VDevice::create_session(uint16_t port)`** — 基於網路的推論工作階段 API（新功能）
- **`VLM::generate_from_embeddings()`** — 4 個多載，接受預先計算的影像 / 影片嵌入作為 `MemoryView` 輸入。讓您計算一次影像嵌入並在多個 VLM 呼叫中重複使用，跳過重新編碼
- **`InferModel::set_nms_classes_filter_mask(vector<bool>)`** — NMS 輸出的類級過濾晶片上
- **`Device::query_performance_stats(sampling_period_ms)`** — 可配置的採樣週期
- **`Device::get_current_limit()`** — 查詢目前限制
- **`DeviceArchitecture.chip_serial_number`** — 讀取晶片序號

全部是附加的，因此沒有現有程式碼中斷。視需要採用。

---

## 7. 環境變更

### 7.1 新 Linux PCI 驅動程式

| 項目 | 舊版 | 新版 |
|---|---|---|
| 核心模組 | `hailo_pci` | `hailo1x_pci` |
| 設備節點 | `/dev/hailort0`（或 `/dev/hailo0`） | `/dev/h1x-0` |

```bash
lsmod | grep hailo        # → hailo1x_pci
ls /dev/h1x-*             # → /dev/h1x-0
```

**`pyhailort` 內部解析新設備節點**，因此使用 `VDevice()` 的 Python 程式碼繼續工作而無需修改。只有直接開啟 `/dev/hailo*` 或 `/dev/hailort0` 的程式碼需要更新。

#### Docker / Podman 透傳

更新設備透傳宣告：

```yaml
# docker-compose.yml
services:
  my-app:
    devices:
      - /dev/h1x-0:/dev/h1x-0   # 之前是：/dev/hailort0:/dev/hailort0
```

同時更新任何 systemd 單位 `DeviceAllow=` 行和 udev 規則。

### 7.2 numpy 約束已解除

- v5.2.0 `setup.py`：`numpy<2`（固定）
- v5.3.0 `setup.py`：`numpy`（無上界）

之前因 v5.2.0 的 `numpy<2` 而固定到 numpy 1.x 的應用程式現在可以連同 HailoRT 凸起升級到 numpy 2.x。

### 7.3 HEF 二進位相容性

**在 v5.2.0 時段下載的 `.hef` 檔案在 5.3.0 執行時上載入並執行無異**。已在 5 個模型上驗證（Raspberry Pi 5 + AI HAT 2）：

| 模型 | 檔案 | 結果 |
|---|---|---|
| YOLOv8n | `yolov8n.hef` | ✅ `create_infer_model()` + `.run()` |
| CLIP ViT-B/16 影像編碼器 | `clip_vit_b_16_image_encoder.hef` | ✅ 512 維輸出 |
| Qwen2.5-1.5B Instruct | `Qwen2.5-1.5B-Instruct.hef` | ✅ `LLM.generate_all()` 返回有效文字 |
| Qwen2-VL-2B Instruct | `Qwen2-VL-2B-Instruct.hef` | ✅ `VLM.generate_all(frames=[…])` 返回有效文字 |
| Whisper-Base | `Whisper-Base.hef` | ✅ `Speech2Text.generate_all_segments()` 返回 `SegmentInfo` |

理論上 HEF 二進位格式可能在主要執行時更新間中斷，但**這在 5.2.0 和 5.3.0 之間沒有發生**。

### 7.4 HEF 下載 URL 時段

Hailo Developer Zone（`dev-public.hailo.ai`）並行主持 v5.2.0 和 v5.3.0 時段：

```
https://dev-public.hailo.ai/v5.2.0/blob/<model>.hef
https://dev-public.hailo.ai/v5.3.0/blob/<model>.hef
```

截至 2026-04-06，v5.3.0 時段狀態：

| 模型 | v5.3.0 時段 |
|---|---|
| Qwen2.5-1.5B-Instruct | ✅ 200 |
| DeepSeek-R1-Distill-Qwen-1.5B | ✅ 200 |
| Qwen2.5-Coder-1.5B-Instruct | ✅ 200 |
| Qwen2-VL-2B-Instruct | ✅ 200 |
| Whisper-Base / Whisper-Small | ✅ 200 |
| **Llama-3.2-1B-Instruct** | ❌ **404** |

→ 需要 Llama-3.2-1B 的應用程式目前必須繼續從 v5.2.0 時段提取。v5.2.0 HEF 在 5.3.0 執行時上正確載入。

---

## 8. `Speech2Text.SegmentInfo` 屬性名稱

在 v5.2.0 和 v5.3.0 上，`Speech2Text.generate_all_segments()` 都會返回包含這些公開屬性的 `SegmentInfo` 物件：

```python
seg.text        # str
seg.start_sec   # float（秒）
seg.end_sec     # float（秒）
```

**沒有 `seg.start` 或 `seg.start_time`。** 較舊的文件和範例程式碼有時會引用這些名稱，但它們要麼會引發 `AttributeError`，要麼——更隱險的是——在包裝在防禦性程式碼中時靜默返回 0.0，例如 `getattr(seg, "start", 0.0) or getattr(seg, "start_time", 0.0)`。

要確認執行時上的實際屬性名稱：

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

## 9. 冒煙測試指令碼

升級至 5.3.0 後驗證環境實際工作的最小指令碼：

```python
"""HailoRT 5.3.0 冒煙測試 — VDevice / InferModel / LLM / Speech2Text。"""
import numpy as np
from hailo_platform import VDevice

# 1. 建立 VDevice
params = VDevice.create_params()
params.group_id = "SMOKE_TEST"
vd = VDevice(params)
print("1. VDevice OK")

# 2. InferModel 路徑（YOLOv8n 或任何現有 HEF）
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

# 3. GenAI LLM 路徑
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

# 4. Speech2Text 路徑
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

## 10. 升級檢查清單

在 5.2.0 → 5.3.0 升級前或期間稽核程式碼的要點：

- [ ] `VDevice()` / `create_infer_model()` / `InferModel.configure()` — **無需變更**
- [ ] `LLM(vd, path)` / `VLM(vd, path)` / `Speech2Text(vd, path)` 建構函式 — **無需變更**
- [ ] `LLM.generate()` / `.generate_all()` / `VLM.generate(frames=…)` / `.generate_all()` 關鍵字引數 — **無需變更**
- [ ] `Speech2Text.generate_all_segments(audio_data=, task=, language=, timeout_ms=)` — 如果明確傳遞 `timeout_ms`，**無需變更**
- [ ] 檢查是否呼叫不帶 `timeout_ms` 引數的 `LLM.read_all()` → 如果有，新增明確的逾時
- [ ] 檢查是否直接建構 `DeviceArchitecture` → 如果有，新增 `chip_serial_number`
- [ ] `grep` 直接開啟 `/dev/hailo*` 或 `/dev/hailort0` 的位置 → 如果有，替換為 `/dev/h1x-0`（或更好的是，通過 `pyhailort`）
- [ ] 更新 Docker / Podman `devices:` 部分為 `/dev/h1x-0`
- [ ] 更新 systemd 單位 `DeviceAllow=` 行和 udev 規則
- [ ] `grep` 使用 `.start` 或 `.start_time` 存取 `SegmentInfo` 屬性 → 切換為 `.start_sec` / `.end_sec`。驗證 Whisper 輸出時間戳記在您的應用程式中不是靜默 0.0
- [ ] 如果您因 v5.2.0 的 `numpy<2` 而將 numpy 固定到 1.x，您現在可以解除固定
- [ ] 現有的 `.hef` 檔案**不需要**重新下載
- [ ] 如果您在 HEF 下載 URL 中硬式編碼 `v5.2.0` 時段，升級至 `v5.3.0`（為 Llama-3.2-1B 保留 `v5.2.0`）
- [ ] 如果您依賴 pyhailort 的內建 NMS 後處理，請注意影像邊緣附近的邊界框可能移動 ±1 像素

---

## 11. 用於調查的命令

假設您已克隆官方 HailoRT 倉庫：

```bash
cd ~/hailort

# 整體差異大小
git diff --stat v5.2.0 v5.3.0 | tail

# 公開 C++ 標頭差異
git diff --stat v5.2.0 v5.3.0 -- 'hailort/libhailort/include/hailo/'

# Python 綁定差異
git diff --stat v5.2.0 v5.3.0 -- 'hailort/libhailort/bindings/python/'

# 完整 pyhailort.py 差異
git diff v5.2.0 v5.3.0 -- \
  'hailort/libhailort/bindings/python/platform/hailo_platform/pyhailort/pyhailort.py'

# 特定標頭的公開 API 差異（只有函數簽名）
git diff v5.2.0 v5.3.0 -- 'hailort/libhailort/include/hailo/genai/llm/llm.hpp' \
  | grep -E '^[+-]' | grep -E 'Expected|hailo_status|void|static'

# 從 device.hpp 移除的 API
git diff v5.2.0 v5.3.0 -- 'hailort/libhailort/include/hailo/device.hpp' \
  | grep '^-' | grep 'virtual'
```

對於 API 分析，C++ 標頭每行攜帶最多資訊 — Python 綁定大多是 pybind11 樣板，因此天真的行計數差異很容易誤導。改為 grep 公開符號。

---

## 12. 結論

標題「688 個檔案變更」遠遠不符實際影響。在典型的 Hailo-10H NPU 推論應用程式上：

- **核心 NPU 推論 API（`VDevice` / `InferModel` / GenAI）完全向後相容**
- 所有移除的 API 都是 Hailo-8 攝影機 / 感測器 / ISP / 韌體管理表面，與 NPU 限用無關
- **所有現有的 `.hef` 檔案載入無需重新下載**
- 只需在環境級別進行的變更是更新 Docker 設備透傳至 `/dev/h1x-0`

升級後可見的主要生活品質改進：

- 逾時預設大幅延長（10 秒 → 10 分鐘），減少長形式生成上的虛假逾時
- `FormatType.FLOAT32` 現在可用（5.2.0 上需要手動量化 / 反量化）
- NMS 座標裁切 bugfix
- numpy 2.x 升級路徑現已開放
- `VLM.generate_from_embeddings()` 允許在多個 VLM 呼叫中重複使用預先計算的影像嵌入

如果您維護被固定到 5.2.0 的 Hailo-10H Python 應用程式，並且一直在推遲升級，這應該能讓您確信遷移幾乎是無操作的。
