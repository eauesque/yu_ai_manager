# HailoRT 5.2.0 → 5.3.0 마이그레이션 노트

Raspberry Pi 5 + AI HAT 2 (Hailo-10H)에서 HailoRT 5.2.0에서 5.3.0으로 업그레이드한 결과로, 엔드-투-엔드 스모크 테스트 및 공식 `v5.2.0` / `v5.3.0` 태그의 직접 git diff 분석을 기반으로 합니다.

**대상 독자**: Python (`pyhailort`)에서 Hailo-10H NPU를 사용하는 개발자.

---

## TL;DR

- **일반적인 Python 추론 애플리케이션의 실질적 호환성 깨짐 영향은 거의 없습니다**. 제목 숫자(688개 파일 변경, +12,035 / −8,987 줄)에도 불구하고 `VDevice`, `InferModel`, 및 GenAI (`LLM` / `VLM` / `Speech2Text`) 인터페이스는 완전히 하위 호환입니다.
- 변경 용량 대부분은 **Hailo-8 카메라 / ISP / 펌웨어 관리 API 제거** 및 내부 리팩토링입니다. 이는 Hailo-10H의 순수 NPU 추론에 영향을 주지 않습니다.
- **v5.2.0 시대의 기존 `.hef` 파일은 5.3.0 런타임에서 변경 없이 로드됩니다.** 5개 모델(YOLOv8n, CLIP ViT-B/16, Qwen2.5-1.5B, Qwen2-VL-2B, Whisper-Base)에서 검증됨.
- Linux 드라이버는 `hailo_pci`에서 `hailo1x_pci`로 이름이 바뀌었고 장치 노드는 `/dev/hailort0`에서 **`/dev/h1x-0`**으로 변경되었습니다. `pyhailort`는 새 노드를 내부적으로 해석하므로 `VDevice()`를 사용하는 Python 코드는 변경이 필요하지 않습니다. **Docker 장치 통과만 업데이트하면 됩니다.**
- `Speech2Text.SegmentInfo`는 `text` / `start_sec` / `end_sec` 속성을 노출합니다 (5.2.0과 동일). `start` 또는 `start_time`을 노출하지 **않습니다** — 이 이름을 사용하는 방어적 코드는 조용히 0.0을 반환합니다.

---

## 1. 변경 범위

공식 HailoRT GitHub 저장소의 `v5.2.0` 및 `v5.3.0` 태그의 직접 diff:

| 범위 | 파일 | 추가됨 | 제거됨 |
|---|---:|---:|---:|
| 전체 | 688 | +12,035 | −8,987 |
| 공개 C++ 헤더 (`include/hailo/`) | 27 | +205 | **−383** |
| Python 바인딩 (`bindings/python/`) | 35 | +306 | **−413** |
| `pyhailort.py` 단독 | 1 | +98 | **−158** |

**제거가 추가를 초과합니다** — 이는 "기능 축소" 릴리스입니다. 제거된 대부분은 핵심 추론 경로와 무관합니다.

---

## 2. 제거된 API — Hailo-8 카메라 / ISP / 펌웨어만

`hailort/libhailort/include/hailo/device.hpp`는 169줄을 잃었고 `platform.h`는 75줄을 잃었습니다. 삭제된 모든 항목은 저수준 장치 제어입니다:

- `firmware_update()` / `second_stage_update()` (펌웨어 재작성)
- `store_sensor_config()` / `store_isp_config()`
- `sensor_dump_config()` / `sensor_reset()`
- `sensor_load_and_start_config()`
- `sensor_set_i2c_bus_index()` / `sensor_set_generic_i2c_slave()`
- `sensor_get_sections_info()`
- `examine_user_config()` / `read_user_config()` / `write_user_config()` / `erase_user_config()`

이들은 모두 **Hailo-8 AI Vision 카메라 모듈**(Hailo 칩이 ISP 및 이미지 센서를 직접 제어하는 SoC 스타일 보드) 용 API입니다. 일반적인 Hailo-10H NPU의 `VDevice` → `InferModel` → `generate` 흐름에서는 절대 호출되지 않습니다.

**영향**: 순수 NPU 추론 애플리케이션의 경우 영향 없음. Hailo-8 카메라 모듈을 실제로 구동하는 애플리케이션만 사용 가능 여부를 감시할 필요가 있습니다.

---

## 3. Python 서명 변경

| API | v5.2.0 | v5.3.0 | 호환성 |
|---|---|---|---|
| `Speech2Text.generate_all_segments(timeout_ms=)` | 기본값 `10000` | 기본값 `600000` | ✅ 기본값만; 기존 호출 미변경 |
| `Speech2Text.generate_all_text(timeout_ms=)` | 동일 | 동일 | ✅ 동일 |
| `LLM.read_all(timeout_ms=10000)` | 기본값 있음 | 기본값 **제거됨** (필수) | ⚠️ 인수 없는 `read_all()` → `TypeError` |
| `DeviceArchitecture.__init__` | 9개 위치 인수 | +`chip_serial_number` (10개 인수) | ⚠️ 직접 생성 손상 |

**`read_all()` 수정은 한 줄 수정입니다**:

```python
# Before (v5.2.0 스타일, 10초 기본값)
text = generator.read_all()

# After (v5.3.0 명시적 타임아웃 필요)
text = generator.read_all(timeout_ms=600000)  # 10분
```

`DeviceArchitecture`는 사용자 코드에서 거의 직접 생성되지 않으므로 서명 변경이 거의 중요하지 않습니다.

---

## 4. C++ 헤더 이름 바꾸기 (Python을 통해 투명함)

HailoRT을 C++에서 직접 사용하는 애플리케이션의 경우 호환성 깨짐:

- **`Speech2Text::DEFAULT_OPERATION_TIMEOUT`** (10초) → **`DEFAULT_GENERATE_ALL_TIMEOUT`** (10분), 이름 변경 및 연장
- **`LLM::DEFAULT_READ_ALL_TIMEOUT`** 추가, 역시 10분
- `vlm.hpp` 4개 `generate_from_embeddings()` 오버로드 추가

이 이름 바꾸기는 Python 바인딩을 통해 전파되지 않습니다.

---

## 5. NMS 바운딩박스 좌표 수정 (동작 변경)

`pyhailort.py`의 NMS 후처리에서 로직 수정:

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

개선 사항:

- 이미지 경계 `max(0, …)` / `min(image_width, …)` 클리핑 추가
- `ceil` → `floor` (오버슈트 방지)
- `bbox_width` 클리핑된 `x_max - x_min`에서 재계산

**동작 차이**: 동일한 모델과 동일한 이미지로, NMS 출력은 경계 근처에서 ±1 픽셀만큼 이동할 수 있습니다. pyhailort의 자체 NMS 후처리를 작성하는 애플리케이션은 영향을 받지 않습니다. pyhailort의 `_output_raw_buffer_to_nms_with_byte_mask_*` 헬퍼를 호출하는 애플리케이션은 이미지 가장자리 근처의 바운딩박스 모양이 변경되는 것을 볼 것입니다.

---

## 6. 새로운 API (추가)

- **`VDevice::create_session(uint16_t port)`** — 네트워크 기반 추론 세션 API (새 기능)
- **`VLM::generate_from_embeddings()`** — 사전 계산된 이미지 / 비디오 임베딩을 `MemoryView` 입력으로 수용하는 4개 오버로드. 이미지 임베딩을 한 번 계산하고 여러 VLM 호출에 재사용하여 재인코딩을 건너뜀
- **`InferModel::set_nms_classes_filter_mask(vector<bool>)`** — NMS 출력에 대한 클래스 수준 필터링 온칩
- **`Device::query_performance_stats(sampling_period_ms)`** — 구성 가능한 샘플링 주기
- **`Device::get_current_limit()`** — 현재 제한 쿼리
- **`DeviceArchitecture.chip_serial_number`** — 칩 일련번호 읽음

모두 추가이므로 기존 코드는 손상되지 않습니다. 필요에 따라 채택하세요.

---

## 7. 환경 변경

### 7.1 새로운 Linux PCI 드라이버

| 항목 | 이전 | 새로운 |
|---|---|---|
| 커널 모듈 | `hailo_pci` | `hailo1x_pci` |
| 장치 노드 | `/dev/hailort0` (또는 `/dev/hailo0`) | `/dev/h1x-0` |

```bash
lsmod | grep hailo        # → hailo1x_pci
ls /dev/h1x-*             # → /dev/h1x-0
```

**`pyhailort`는 새 장치 노드를 내부적으로 해석하므로** `VDevice()`를 사용하는 Python 코드는 수정 없이 계속 작동합니다. `/dev/hailo*` 또는 `/dev/hailort0`을 직접 열고 있는 코드만 업데이트해야 합니다.

#### Docker / Podman 통과

장치 통과 선언을 업데이트하세요:

```yaml
# docker-compose.yml
services:
  my-app:
    devices:
      - /dev/h1x-0:/dev/h1x-0   # 이전: /dev/hailort0:/dev/hailort0
```

또한 systemd 단위 `DeviceAllow=` 줄과 udev 규칙을 업데이트하세요.

### 7.2 numpy 제약 제거됨

- v5.2.0 `setup.py`: `numpy<2` (고정)
- v5.3.0 `setup.py`: `numpy` (상한 없음)

이전에 numpy 1.x로 고정된 애플리케이션은 HailoRT 업그레이드와 함께 numpy 2.x로 업그레이드할 수 있습니다.

### 7.3 HEF 바이너리 호환성

**v5.2.0 버킷에서 다운로드한 `.hef` 파일은 5.3.0 런타임에서 변경 없이 로드되고 실행됩니다.** 5개 모델에서 검증됨 (Raspberry Pi 5 + AI HAT 2):

| 모델 | 파일 | 결과 |
|---|---|---|
| YOLOv8n | `yolov8n.hef` | ✅ `create_infer_model()` + `.run()` |
| CLIP ViT-B/16 이미지 인코더 | `clip_vit_b_16_image_encoder.hef` | ✅ 512차원 출력 |
| Qwen2.5-1.5B Instruct | `Qwen2.5-1.5B-Instruct.hef` | ✅ `LLM.generate_all()`은 유효한 텍스트 반환 |
| Qwen2-VL-2B Instruct | `Qwen2-VL-2B-Instruct.hef` | ✅ `VLM.generate_all(frames=[…])`은 유효한 텍스트 반환 |
| Whisper-Base | `Whisper-Base.hef` | ✅ `Speech2Text.generate_all_segments()`는 `SegmentInfo` 반환 |

HEF 바이너리 형식은 이론상 주요 런타임 업데이트 간에 손상될 수 있지만, **5.2.0과 5.3.0 사이에는 이것이 발생하지 않았습니다.**

### 7.4 HEF 다운로드 URL 버킷

Hailo Developer Zone (`dev-public.hailo.ai`)는 v5.2.0 및 v5.3.0 버킷을 병렬로 호스팅합니다:

```
https://dev-public.hailo.ai/v5.2.0/blob/<model>.hef
https://dev-public.hailo.ai/v5.3.0/blob/<model>.hef
```

2026-04-06 기준 v5.3.0 버킷 상태:

| 모델 | v5.3.0 버킷 |
|---|---|
| Qwen2.5-1.5B-Instruct | ✅ 200 |
| DeepSeek-R1-Distill-Qwen-1.5B | ✅ 200 |
| Qwen2.5-Coder-1.5B-Instruct | ✅ 200 |
| Qwen2-VL-2B-Instruct | ✅ 200 |
| Whisper-Base / Whisper-Small | ✅ 200 |
| **Llama-3.2-1B-Instruct** | ❌ **404** |

→ Llama-3.2-1B가 필요한 애플리케이션은 지금 v5.2.0 버킷에서 계속 끌어와야 합니다. v5.2.0 HEF는 5.3.0 런타임에서 올바르게 로드됩니다.

---

## 8. `Speech2Text.SegmentInfo` 속성 이름

v5.2.0 및 v5.3.0 모두에서 `Speech2Text.generate_all_segments()`는 이러한 공개 속성을 갖는 `SegmentInfo` 객체를 반환합니다:

```python
seg.text        # str
seg.start_sec   # float (초)
seg.end_sec     # float (초)
```

**`seg.start` 또는 `seg.start_time`은 없습니다.** 더 오래된 문서 및 샘플 코드는 때때로 이 이름을 참조하지만, `AttributeError`를 발생시키거나 — 더 교활하게 — `getattr(seg, "start", 0.0) or getattr(seg, "start_time", 0.0)`과 같은 방어적 코드로 래핑될 때 조용히 0.0을 반환합니다.

런타임의 실제 속성 이름을 확인하려면:

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

## 9. 스모크 테스트 스크립트

5.3.0으로 업그레이드한 후 환경이 실제로 작동하는지 확인하기 위한 최소 스크립트:

```python
"""HailoRT 5.3.0 스모크 테스트 — VDevice / InferModel / LLM / Speech2Text."""
import numpy as np
from hailo_platform import VDevice

# 1. VDevice 생성
params = VDevice.create_params()
params.group_id = "SMOKE_TEST"
vd = VDevice(params)
print("1. VDevice OK")

# 2. InferModel 경로 (YOLOv8n 또는 기존 HEF)
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

# 3. GenAI LLM 경로
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

# 4. Speech2Text 경로
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

## 10. 업그레이드 체크리스트

5.2.0 → 5.3.0 업그레이드 전이나 중에 코드를 감시할 사항:

- [ ] `VDevice()` / `create_infer_model()` / `InferModel.configure()` — **변경 불필요**
- [ ] `LLM(vd, path)` / `VLM(vd, path)` / `Speech2Text(vd, path)` 생성자 — **변경 불필요**
- [ ] `LLM.generate()` / `.generate_all()` / `VLM.generate(frames=…)` / `.generate_all()` 키워드 인수 — **변경 불필요**
- [ ] `Speech2Text.generate_all_segments(audio_data=, task=, language=, timeout_ms=)` — **`timeout_ms`를 명시적으로 전달하면 변경 불필요**
- [ ] `LLM.read_all()`을 `timeout_ms` 인수 없이 호출하는지 확인 → 그렇다면 명시적 타임아웃 추가
- [ ] `DeviceArchitecture`를 직접 생성하는지 확인 → 그렇다면 `chip_serial_number` 추가
- [ ] `/dev/hailo*` 또는 `/dev/hailort0`의 직접 열기에 대해 `grep` → 있다면 `/dev/h1x-0`으로 교체 (또는 더 나음, `pyhailort`를 통해)
- [ ] Docker / Podman `devices:` 섹션을 `/dev/h1x-0`으로 업데이트
- [ ] systemd 단위 `DeviceAllow=` 줄 및 udev 규칙 업데이트
- [ ] `.start` 또는 `.start_time`을 사용하는 `SegmentInfo` 속성 액세스에 대해 `grep` → `.start_sec` / `.end_sec`로 전환. Whisper 출력 타임스탬프가 앱에서 조용히 0.0이 아닌지 확인
- [ ] numpy를 v5.2.0의 `numpy<2` 때문에 1.x로 고정한 경우 핀을 해제할 수 있음
- [ ] 기존 `.hef` 파일은 재다운로드 **필요 없음**
- [ ] HEF 다운로드 URL에 `v5.2.0` 버킷을 하드코드한 경우 `v5.3.0`으로 승격 (Llama-3.2-1B의 경우 `v5.2.0` 유지)
- [ ] pyhailort의 기본 제공 NMS 후처리를 사용하는 경우 이미지 가장자리 근처의 바운딩박스가 ±1 픽셀만큼 이동할 수 있다는 점 인식

---

## 11. 조사에 사용된 명령

공식 HailoRT 저장소를 복제했다고 가정:

```bash
cd ~/hailort

# 전체 diff 크기
git diff --stat v5.2.0 v5.3.0 | tail

# 공개 C++ 헤더 diff
git diff --stat v5.2.0 v5.3.0 -- 'hailort/libhailort/include/hailo/'

# Python 바인딩 diff
git diff --stat v5.2.0 v5.3.0 -- 'hailort/libhailort/bindings/python/'

# pyhailort.py의 전체 diff
git diff v5.2.0 v5.3.0 -- \
  'hailort/libhailort/bindings/python/platform/hailo_platform/pyhailort/pyhailort.py'

# 특정 헤더의 공개 API diff (함수 서명만)
git diff v5.2.0 v5.3.0 -- 'hailort/libhailort/include/hailo/genai/llm/llm.hpp' \
  | grep -E '^[+-]' | grep -E 'Expected|hailo_status|void|static'

# device.hpp에서 제거된 API
git diff v5.2.0 v5.3.0 -- 'hailort/libhailort/include/hailo/device.hpp' \
  | grep '^-' | grep 'virtual'
```

API 분석의 경우 C++ 헤더가 줄당 가장 많은 정보를 포함합니다 — Python 바인딩은 대부분 pybind11 보일러플레이트이므로 순진한 줄 수 diff는 오해의 소지가 있습니다. 대신 공개 기호를 grep하세요.

---

## 12. 결론

제목 "688개 파일 변경"은 실제 영향과 매우 거리가 멀습니다. 일반적인 Hailo-10H NPU 추론 애플리케이션에서:

- **핵심 NPU 추론 API(`VDevice` / `InferModel` / GenAI)는 완전히 하위 호환입니다**
- 모든 제거된 API는 NPU 전용 사용과 무관한 Hailo-8 카메라 / 센서 / ISP / 펌웨어 관리 인터페이스입니다
- **모든 기존 `.hef` 파일은 재다운로드 없이 로드됩니다**
- Docker 장치 통과를 `/dev/h1x-0`으로 업데이트하는 것이 유일한 환경 수준 변경입니다

업그레이드 후 눈에 띄는 주요 품질 개선:

- 타임아웃 기본값 대폭 연장 (10초 → 10분), 장형식 생성에서 가짜 타임아웃 감소
- `FormatType.FLOAT32`가 이제 사용 가능 (5.2.0에서는 수동 양자화 / 역양자화 필요)
- NMS 좌표 클리핑 버그 수정
- numpy 2.x 업그레이드 경로 개설
- `VLM.generate_from_embeddings()`은 여러 VLM 호출 간 사전 계산된 이미지 임베딩 재사용 허용

5.2.0에 고정된 Hailo-10H Python 애플리케이션을 유지하면서 업그레이드를 미루어온 경우, 이는 마이그레이션이 거의 무관한 것임을 확신시켜야 합니다.
