# ONNX → HEF 변환 절차서

**목적**: WD-Tagger 등의 ONNX 모델을 Hailo HEF 형식으로 변환하여, Hailo-10H NPU에서 추론 가능하게 만들기
**실행 환경**: x86_64 Linux (AI 서버) — Hailo Dataflow Compiler는 x86만 지원
**추론 환경**: Raspberry Pi 5 + AI HAT 2 (Hailo-10H)

---

## 사전 지식

### 변환이 필요한 이유

| 항목 | ONNX Runtime (현재) | Hailo HEF (목표) |
|------|---------------------|-------------------|
| 실행 대상 | CPU | Hailo-10H NPU (40 TOPS) |
| 양자화 | float32 | INT8 (uint8) |
| 추론 속도 | ~500ms/image (Pi5 CPU) | ~20ms/image (추정, CLIP 실적 기반) |
| 메모리 | ~200MB (모델 로드) | ~수십MB (HEF) |

### 변환 파이프라인 개요

```
model.onnx (float32)
  |
  | [1] Hailo Model Zoo 파서 (ONNX → HAR)
  v
model.har (Hailo Archive, float32)
  |
  | [2] 최적화 (레이어 융합, 메모리 배치)
  v
model_optimized.har
  |
  | [3] 양자화 (float32 → INT8, 캘리브레이션 이미지 사용)
  v
model_quantized.har
  |
  | [4] 컴파일 (HW 명령으로 변환)
  v
model.hef (Hailo Executable Format)
```

---

## 1. AI 서버 환경 구축

### 1-1. Hailo Dataflow Compiler 설치

Hailo Developer Zone (https://hailo.ai/developer-zone/)에서 다운로드.
계정 등록이 필요.

```bash
# Python 3.10 or 3.11 권장 (3.12+는 미지원 가능성 있음)
python3 --version

# venv 생성
python3 -m venv ~/hailo_env
source ~/hailo_env/bin/activate

# Hailo Dataflow Compiler (DFC) 설치
# Developer Zone에서 다운로드한 .whl을 지정
uv pip install hailo_dataflow_compiler-3.29.0-py3-none-linux_x86_64.whl

# 의존 패키지
uv pip install numpy pillow onnx onnxruntime
```

**확인**:
```bash
python -c "from hailo_sdk_client import ClientRunner; print('DFC OK')"
```

### 1-2. Hailo Model Zoo (선택사항이나 권장)

```bash
git clone https://github.com/hailo-ai/hailo_model_zoo.git ~/hailo_model_zoo
uv pip install -e ~/hailo_model_zoo
```

Model Zoo에는 많은 모델의 변환 설정 (YAML)이 포함되어 있어 참고가 된다.

---

## 2. 대상 모델 준비

### 2-1. WD-Tagger 모델

현재 사용 중인 모델:
- **리포지터리**: HuggingFace의 `SmilingWolf/wd-swinv2-tagger-v3` 등
- **파일**: `model.onnx` (~110MB, float32)
- **입력**: `(1, 448, 448, 3)` float32, BGR, [0, 255] 정규화 없음
- **출력**: `(1, num_tags)` float32, 시그모이드 적용된 확률

```bash
# HuggingFace에서 다운로드
mkdir -p ~/hailo_convert/wd_tagger
cd ~/hailo_convert/wd_tagger

# model.onnx와 selected_tags.csv를 취득
wget https://huggingface.co/SmilingWolf/wd-swinv2-tagger-v3/resolve/main/model.onnx
wget https://huggingface.co/SmilingWolf/wd-swinv2-tagger-v3/resolve/main/selected_tags.csv
```

### 2-2. ONNX 모델의 입출력 확인

```python
import onnx

model = onnx.load("model.onnx")

print("=== 입력 ===")
for inp in model.graph.input:
    shape = [d.dim_value for d in inp.type.tensor_type.shape.dim]
    print(f"  {inp.name}: {shape}")

print("=== 출력 ===")
for out in model.graph.output:
    shape = [d.dim_value for d in out.type.tensor_type.shape.dim]
    print(f"  {out.name}: {shape}")
```

입출력의 shape과 이름을 메모해 둔다. 변환 시 필요.

---

## 3. 캘리브레이션 이미지 준비

INT8 양자화에는 대표적인 이미지 세트 (캘리브레이션 데이터)가 필요하다.
양자화 매개변수 (scale/zero_point)를 결정하는 데 사용한다.

```bash
mkdir -p ~/hailo_convert/calibration_images
```

### 요건

- **매수**: 100~1000장 정도 (많을수록 정확도가 안정되지만, 시간도 소요)
- **내용**: 실제로 추론할 이미지의 대표 샘플 (AI 생성 이미지의 다양한 변형)
- **형식**: JPEG/PNG
- **크기**: 임의 (전처리 스크립트에서 리사이즈됨)

```bash
# yu_ai_manager의 라이브러리에서 랜덤으로 500장 복사하는 예
# (Pi에서 AI 서버로 scp 등으로 전송)
scp pi@raspberrypi:/path/to/images/*.png ~/hailo_convert/calibration_images/
```

### 캘리브레이션 전처리 스크립트

WD-Tagger의 전처리와 동일한 처리를 적용해야 한다:

```python
# calibration_preprocess.py
"""캘리브레이션 이미지를 WD-Tagger 형식으로 전처리한다."""
import numpy as np
from PIL import Image
from pathlib import Path

INPUT_SIZE = 448

def preprocess(image_path: str) -> np.ndarray:
    """yu_ai_manager의 engine_onnx.py와 동일한 전처리."""
    with Image.open(image_path) as raw:
        img = raw.convert("RGBA")

    # 흰색 배경에 합성 (투명도 대응)
    canvas = Image.new("RGBA", img.size, (255, 255, 255, 255))
    canvas.alpha_composite(img)
    img = canvas.convert("RGB")

    # 종횡비를 유지하여 리사이즈
    old_w, old_h = img.size
    scale = INPUT_SIZE / max(old_w, old_h)
    new_w = int(old_w * scale)
    new_h = int(old_h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)

    # 흰색 패딩으로 정사각형으로 만들기
    padded = Image.new("RGB", (INPUT_SIZE, INPUT_SIZE), (255, 255, 255))
    padded.paste(img, ((INPUT_SIZE - new_w) // 2, (INPUT_SIZE - new_h) // 2))

    # HWC, float32, RGB -> BGR
    arr = np.array(padded, dtype=np.float32)
    arr = arr[:, :, ::-1]  # RGB -> BGR

    return arr  # (448, 448, 3)


def load_calibration_set(image_dir: str, max_images: int = 500) -> np.ndarray:
    """캘리브레이션 이미지를 배치 텐서로 반환한다."""
    images = []
    for p in sorted(Path(image_dir).glob("*")):
        if p.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
            continue
        try:
            images.append(preprocess(str(p)))
        except Exception as e:
            print(f"  skip {p.name}: {e}")
        if len(images) >= max_images:
            break

    print(f"Loaded {len(images)} calibration images")
    return np.stack(images, axis=0)  # (N, 448, 448, 3)


if __name__ == "__main__":
    dataset = load_calibration_set("calibration_images")
    np.save("calibration_data.npy", dataset)
    print(f"Saved: calibration_data.npy {dataset.shape}")
```

---

## 4. HEF 변환 실행

### 4-1. 변환 스크립트

```python
# convert_wd_tagger.py
"""WD-Tagger ONNX → Hailo HEF 변환 스크립트."""
from hailo_sdk_client import ClientRunner
import numpy as np

# ========== 설정 ==========
ONNX_PATH = "model.onnx"
MODEL_NAME = "wd_swinv2_tagger_v3"
CALIBRATION_NPY = "calibration_data.npy"
HW_ARCH = "hailo10h"  # Hailo-10H 용
# ==========================

# --- Step 1: ONNX 파싱 → HAR ---
print("[1/4] Parsing ONNX model...")
runner = ClientRunner(hw_arch=HW_ARCH)

# start_node / end_node는 모델의 입출력 노드명
# (Step 2-2에서 확인한 이름을 지정)
hn, npz = runner.translate_onnx_model(
    ONNX_PATH,
    MODEL_NAME,
    # net_input_shapes={"input": [1, 448, 448, 3]},  # 필요에 따라 지정
)
print(f"  Parsed: {len(npz)} layers")

# --- Step 2: 모델 최적화 ---
print("[2/4] Optimizing model...")
runner.optimize(npz)

# --- Step 3: INT8 양자화 ---
print("[3/4] Quantizing (INT8)...")
calib_data = np.load(CALIBRATION_NPY)
print(f"  Calibration set: {calib_data.shape}")

runner.quantize(calib_data)

# --- Step 4: 컴파일 → HEF ---
print("[4/4] Compiling to HEF...")
hef = runner.compile()

hef_path = f"{MODEL_NAME}.hef"
with open(hef_path, "wb") as f:
    f.write(hef)
print(f"Done: {hef_path} ({len(hef) / 1024 / 1024:.1f} MB)")

# HAR (중간 파일)도 저장 (디버그용)
har_path = f"{MODEL_NAME}.har"
runner.save_har(har_path)
print(f"HAR saved: {har_path}")
```

### 4-2. 실행

```bash
source ~/hailo_env/bin/activate
cd ~/hailo_convert/wd_tagger

# 캘리브레이션 이미지 전처리
python calibration_preprocess.py

# HEF 변환
python convert_wd_tagger.py
```

**소요 시간 목안**: 모델 크기와 캘리브레이션 매수에 따라 다르지만, 수십 분~수 시간.

### 4-3. 자주 발생하는 오류와 대처

| 오류 | 원인 | 대처 |
|--------|------|------|
| `UnsupportedOp: <op_name>` | ONNX 연산자가 DFC 미지원 | Hailo의 지원 연산자 목록을 확인. 미지원 op는 모델 수정이나 `onnx-simplifier`로 제거 |
| `Shape mismatch` | 입력 shape이 동적 | `net_input_shapes`로 고정 shape을 명시적으로 지정 |
| `Quantization error` / 정확도 열화 | 캘리브레이션 데이터가 부적절 | 이미지 매수를 늘리거나, 실제 운용 이미지를 사용 |
| `Memory allocation failed` | 모델이 너무 커서 NPU 메모리에 수용 불가 | 배치 사이즈=1로 고정, 또는 경량 모델을 검토 |
| `hailo_sdk_client not found` | DFC 미설치 | Step 1-1을 확인 |

### 4-4. (권장) onnx-simplifier로 전처리

변환 전에 ONNX 모델을 단순화해 두면 성공률이 올라간다:

```bash
uv pip install onnx-simplifier
python -m onnxsim model.onnx model_simplified.onnx
```

---

## 5. 변환 후 검증 (AI 서버에서)

### 5-1. Hailo Emulator로 정확도 검증

HEF로 변환한 모델의 정확도를 실기 없이 검증할 수 있다:

```python
# verify_hef.py
"""HEF의 출력을 ONNX의 출력과 비교하여 정확도 열화를 확인한다."""
import numpy as np
import onnxruntime as ort

# ONNX 추론 (float32, 기준값)
sess = ort.InferenceSession("model.onnx")
test_image = np.load("calibration_data.npy")[0:1]  # 1장 추출
input_name = sess.get_inputs()[0].name
onnx_output = sess.run(None, {input_name: test_image})[0][0]

# HEF 에뮬레이터 추론
from hailo_sdk_client import ClientRunner

runner = ClientRunner(har="wd_swinv2_tagger_v3.har")
hef_output = runner.infer(test_image)[0]

# 비교
diff = np.abs(onnx_output - hef_output)
print(f"Max diff:  {diff.max():.6f}")
print(f"Mean diff: {diff.mean():.6f}")
print(f"Cosine similarity: {np.dot(onnx_output, hef_output) / (np.linalg.norm(onnx_output) * np.linalg.norm(hef_output)):.6f}")

# 태그 일치율 (임계값 0.35에서의 일치)
threshold = 0.35
onnx_tags = set(np.where(onnx_output > threshold)[0])
hef_tags = set(np.where(hef_output > threshold)[0])
overlap = len(onnx_tags & hef_tags)
print(f"Tag match: {overlap}/{len(onnx_tags)} ({overlap/max(len(onnx_tags),1)*100:.1f}%)")
```

**판정 기준**:
- 코사인 유사도 > 0.95: 양호
- 태그 일치율 > 90%: 실용 수준
- 태그 일치율 < 80%: 캘리브레이션 데이터 재검토 필요

---

## 6. Pi로의 전송 및 실기 테스트

### 6-1. HEF 파일 전송

```bash
scp ~/hailo_convert/wd_tagger/wd_swinv2_tagger_v3.hef pi@raspberrypi:~/hailo_models/
```

### 6-2. 실기 추론 테스트

```python
# test_wd_tagger_hef.py (Pi5에서 실행)
"""HEF로 변환한 WD-Tagger의 실기 추론 테스트."""
import numpy as np
from hailo_platform import VDevice
from PIL import Image
import time

HEF_PATH = "~/.hailo_models/wd_swinv2_tagger_v3.hef"
INPUT_SIZE = 448

def preprocess(image_path: str) -> np.ndarray:
    """engine_onnx.py와 동일한 전처리 (단, uint8로 출력)."""
    with Image.open(image_path) as raw:
        img = raw.convert("RGBA")
    canvas = Image.new("RGBA", img.size, (255, 255, 255, 255))
    canvas.alpha_composite(img)
    img = canvas.convert("RGB")
    old_w, old_h = img.size
    scale = INPUT_SIZE / max(old_w, old_h)
    img = img.resize((int(old_w * scale), int(old_h * scale)), Image.LANCZOS)
    padded = Image.new("RGB", (INPUT_SIZE, INPUT_SIZE), (255, 255, 255))
    padded.paste(img, ((INPUT_SIZE - img.width) // 2, (INPUT_SIZE - img.height) // 2))
    arr = np.array(padded, dtype=np.uint8)
    arr = arr[:, :, ::-1]  # RGB -> BGR
    return arr

# 테스트 이미지
test_img = preprocess("/path/to/test/image.png")

with VDevice() as vdevice:
    infer_model = vdevice.create_infer_model(HEF_PATH)
    configured = infer_model.configure()
    bindings = configured.create_bindings()

    # 입력
    bindings.input().set_buffer(test_img)

    # 출력 버퍼 (uint8)
    out_info = infer_model.outputs[0]
    output_buf = np.empty(out_info.shape, dtype=np.uint8)
    bindings.output().set_buffer(output_buf)

    # 추론
    t0 = time.perf_counter()
    configured.run([bindings], timeout=10000)
    elapsed = (time.perf_counter() - t0) * 1000

    print(f"Inference: {elapsed:.1f} ms")
    print(f"Output shape: {output_buf.shape}")
    print(f"Output range: [{output_buf.min()}, {output_buf.max()}]")

    # 역양자화
    try:
        qi = out_info.quant_infos[0]
        scale = qi.qp_scale
        zp = qi.qp_zp
    except Exception:
        scale, zp = 1.0 / 255.0, 0.0

    probs = (output_buf.astype(np.float32) - zp) * scale
    print(f"Dequantized range: [{probs.min():.4f}, {probs.max():.4f}]")
```

### 6-3. 정확도 비교 (ONNX vs HEF)

같은 이미지를 ONNX Runtime과 Hailo HEF 양쪽에서 추론하여 태그 출력을 비교:

```bash
# Pi에서 실행
python test_wd_tagger_hef.py
python -c "
from extensions.builtin_wd_tagger.core_impl.engine_onnx import OnnxWdTaggerEngine
e = OnnxWdTaggerEngine(Path('cache/wd_tagger/...'))
r = e.tag_image('/path/to/test/image.png')
for t in r.tags[:20]: print(f'{t.tag}: {t.confidence}')
"
```

---

## 7. 알려진 우려 사항

### SwinV2 아키텍처의 변환 가능성

WD-Tagger v3는 **Swin Transformer V2** 기반. 다음 Op가 DFC에서 미지원일 가능성이 있다:

- **Window Attention** (shifted window)
- **Roll** 연산
- **상대 위치 바이어스**

SwinV2가 변환 불가인 경우의 대안:
1. **wd-vit-tagger-v3** (Vision Transformer 기반) — ViT는 CLIP과 동일 계열로 Hailo 변환 실적 있음
2. **wd-convnext-tagger-v3** (ConvNeXt 기반) — CNN 계열로 변환이 용이
3. **wd-eva02-large-tagger-v3** (EVA-02 기반) — 모델이 큼 (300MB+)이므로 NPU 메모리 주의

### 전처리의 차이

- **ONNX 버전**: float32 입력 (0-255 범위, 정규화 없음)
- **HEF 버전**: uint8 입력 (HEF 내부에서 정규화)

HEF로 변환하면 전처리가 HEF에 내장되는 경우가 있다.
DFC의 `translate_onnx_model()` 시 전처리 처리 방식을 확인할 것.

### 역양자화 매개변수

출력은 uint8로 양자화된다. 태그 확률 (0.0-1.0)을 올바르게 복원하려면,
HEF의 양자화 매개변수 (scale/zero_point)를 사용한 역양자화가 필수.
CLIP의 실적 (`extensions/builtin_hailo_semantic_search/core_impl/dequantize.py`)을 참고할 것.

---

## 8. Claude에 대한 지시 템플릿

AI 서버에서 Claude에게 변환 작업을 의뢰할 때의 프롬프트 예:

```
다음 절차로 WD-Tagger ONNX 모델을 Hailo HEF로 변환해 주세요.

1. ~/hailo_env를 활성화
2. model.onnx를 ~/hailo_convert/wd_tagger/에 다운로드
3. calibration_images/에 준비한 샘플 이미지로 캘리브레이션 데이터를 생성
4. convert_wd_tagger.py를 실행하여 HEF로 변환
5. verify_hef.py로 ONNX와의 정확도 비교를 실시
6. 결과를 보고해 주세요

변환이 실패한 경우:
- 오류 메시지를 보고
- onnx-simplifier를 시도
- SwinV2가 미지원인 경우 wd-vit-tagger-v3로 재시도

대상 모델: SmilingWolf/wd-swinv2-tagger-v3
대상 HW: hailo10h
```

---

## 참고 링크

- [Hailo Dataflow Compiler 문서](https://hailo.ai/developer-zone/documentation/dataflow-compiler/)
- [Hailo Model Zoo](https://github.com/hailo-ai/hailo_model_zoo)
- [WD-Tagger 모델 (HuggingFace)](https://huggingface.co/SmilingWolf)
- [ONNX Simplifier](https://github.com/daquexian/onnx-simplifier)
