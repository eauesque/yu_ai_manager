# ONNX to HEF Conversion Guide

**Objective**: Convert ONNX models such as WD-Tagger to Hailo HEF format for inference on the Hailo-10H NPU
**Conversion environment**: x86_64 Linux (AI server) -- the Hailo Dataflow Compiler supports x86 only
**Inference environment**: Raspberry Pi 5 + AI HAT 2 (Hailo-10H)

---

## Prerequisites

### Why Conversion Is Necessary

| Item | ONNX Runtime (current) | Hailo HEF (target) |
|------|---------------------|-------------------|
| Execution target | CPU | Hailo-10H NPU (40 TOPS) |
| Quantization | float32 | INT8 (uint8) |
| Inference speed | ~500ms/image (Pi5 CPU) | ~20ms/image (estimated, based on CLIP benchmarks) |
| Memory | ~200MB (model load) | ~tens of MB (HEF) |

### Conversion Pipeline Overview

```
model.onnx (float32)
  |
  | [1] Hailo Model Zoo parser (ONNX -> HAR)
  v
model.har (Hailo Archive, float32)
  |
  | [2] Optimization (layer fusion, memory layout)
  v
model_optimized.har
  |
  | [3] Quantization (float32 -> INT8, using calibration images)
  v
model_quantized.har
  |
  | [4] Compilation (convert to HW instructions)
  v
model.hef (Hailo Executable Format)
```

---

## 1. AI Server Environment Setup

### 1-1. Installing the Hailo Dataflow Compiler

Download from the Hailo Developer Zone (https://hailo.ai/developer-zone/).
Account registration is required.

```bash
# Python 3.10 or 3.11 recommended (3.12+ may not be supported)
python3 --version

# Create venv
python3 -m venv ~/hailo_env
source ~/hailo_env/bin/activate

# Install Hailo Dataflow Compiler (DFC)
# Specify the .whl downloaded from Developer Zone
uv pip install hailo_dataflow_compiler-3.29.0-py3-none-linux_x86_64.whl

# Dependencies
uv pip install numpy pillow onnx onnxruntime
```

**Verification**:
```bash
python -c "from hailo_sdk_client import ClientRunner; print('DFC OK')"
```

### 1-2. Hailo Model Zoo (optional but recommended)

```bash
git clone https://github.com/hailo-ai/hailo_model_zoo.git ~/hailo_model_zoo
uv pip install -e ~/hailo_model_zoo
```

The Model Zoo contains conversion configurations (YAML) for many models, which serve as useful references.

---

## 2. Preparing the Target Model

### 2-1. WD-Tagger Model

Currently used model:
- **Repository**: `SmilingWolf/wd-swinv2-tagger-v3` etc. on HuggingFace
- **File**: `model.onnx` (~110MB, float32)
- **Input**: `(1, 448, 448, 3)` float32, BGR, [0, 255] unnormalized
- **Output**: `(1, num_tags)` float32, sigmoid-applied probabilities

```bash
# Download from HuggingFace
mkdir -p ~/hailo_convert/wd_tagger
cd ~/hailo_convert/wd_tagger

# Fetch model.onnx and selected_tags.csv
wget https://huggingface.co/SmilingWolf/wd-swinv2-tagger-v3/resolve/main/model.onnx
wget https://huggingface.co/SmilingWolf/wd-swinv2-tagger-v3/resolve/main/selected_tags.csv
```

### 2-2. Inspecting ONNX Model Inputs and Outputs

```python
import onnx

model = onnx.load("model.onnx")

print("=== Inputs ===")
for inp in model.graph.input:
    shape = [d.dim_value for d in inp.type.tensor_type.shape.dim]
    print(f"  {inp.name}: {shape}")

print("=== Outputs ===")
for out in model.graph.output:
    shape = [d.dim_value for d in out.type.tensor_type.shape.dim]
    print(f"  {out.name}: {shape}")
```

Take note of the input/output shapes and names. They are needed during conversion.

---

## 3. Preparing Calibration Images

INT8 quantization requires a representative image set (calibration data).
This is used to determine quantization parameters (scale/zero_point).

```bash
mkdir -p ~/hailo_convert/calibration_images
```

### Requirements

- **Count**: Approximately 100-1000 images (more images improve accuracy stability but increase processing time)
- **Content**: Representative samples of images used in actual inference (variety of AI-generated images)
- **Format**: JPEG/PNG
- **Size**: Any (the preprocessing script handles resizing)

```bash
# Example: randomly copy 500 images from the yu_ai_manager library
# (Transfer from Pi to AI server via scp, etc.)
scp pi@raspberrypi:/path/to/images/*.png ~/hailo_convert/calibration_images/
```

### Calibration Preprocessing Script

The same preprocessing as WD-Tagger must be applied:

```python
# calibration_preprocess.py
"""Preprocess calibration images to WD-Tagger format."""
import numpy as np
from PIL import Image
from pathlib import Path

INPUT_SIZE = 448

def preprocess(image_path: str) -> np.ndarray:
    """Same preprocessing as yu_ai_manager's engine_onnx.py."""
    with Image.open(image_path) as raw:
        img = raw.convert("RGBA")

    # Composite onto white background (transparency handling)
    canvas = Image.new("RGBA", img.size, (255, 255, 255, 255))
    canvas.alpha_composite(img)
    img = canvas.convert("RGB")

    # Resize preserving aspect ratio
    old_w, old_h = img.size
    scale = INPUT_SIZE / max(old_w, old_h)
    new_w = int(old_w * scale)
    new_h = int(old_h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)

    # Pad to square with white
    padded = Image.new("RGB", (INPUT_SIZE, INPUT_SIZE), (255, 255, 255))
    padded.paste(img, ((INPUT_SIZE - new_w) // 2, (INPUT_SIZE - new_h) // 2))

    # HWC, float32, RGB -> BGR
    arr = np.array(padded, dtype=np.float32)
    arr = arr[:, :, ::-1]  # RGB -> BGR

    return arr  # (448, 448, 3)


def load_calibration_set(image_dir: str, max_images: int = 500) -> np.ndarray:
    """Return calibration images as a batch tensor."""
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

## 4. Running the HEF Conversion

### 4-1. Conversion Script

```python
# convert_wd_tagger.py
"""WD-Tagger ONNX to Hailo HEF conversion script."""
from hailo_sdk_client import ClientRunner
import numpy as np

# ========== Configuration ==========
ONNX_PATH = "model.onnx"
MODEL_NAME = "wd_swinv2_tagger_v3"
CALIBRATION_NPY = "calibration_data.npy"
HW_ARCH = "hailo10h"  # For Hailo-10H
# ==========================

# --- Step 1: Parse ONNX -> HAR ---
print("[1/4] Parsing ONNX model...")
runner = ClientRunner(hw_arch=HW_ARCH)

# start_node / end_node are the model's input/output node names
# (Use the names identified in Step 2-2)
hn, npz = runner.translate_onnx_model(
    ONNX_PATH,
    MODEL_NAME,
    # net_input_shapes={"input": [1, 448, 448, 3]},  # Specify if needed
)
print(f"  Parsed: {len(npz)} layers")

# --- Step 2: Model optimization ---
print("[2/4] Optimizing model...")
runner.optimize(npz)

# --- Step 3: INT8 quantization ---
print("[3/4] Quantizing (INT8)...")
calib_data = np.load(CALIBRATION_NPY)
print(f"  Calibration set: {calib_data.shape}")

runner.quantize(calib_data)

# --- Step 4: Compile -> HEF ---
print("[4/4] Compiling to HEF...")
hef = runner.compile()

hef_path = f"{MODEL_NAME}.hef"
with open(hef_path, "wb") as f:
    f.write(hef)
print(f"Done: {hef_path} ({len(hef) / 1024 / 1024:.1f} MB)")

# Save HAR (intermediate file) for debugging
har_path = f"{MODEL_NAME}.har"
runner.save_har(har_path)
print(f"HAR saved: {har_path}")
```

### 4-2. Execution

```bash
source ~/hailo_env/bin/activate
cd ~/hailo_convert/wd_tagger

# Preprocess calibration images
python calibration_preprocess.py

# Run HEF conversion
python convert_wd_tagger.py
```

**Estimated duration**: Ranges from tens of minutes to several hours depending on model size and number of calibration images.

### 4-3. Common Errors and Solutions

| Error | Cause | Solution |
|-------|-------|----------|
| `UnsupportedOp: <op_name>` | ONNX operator not supported by DFC | Check the Hailo supported operator list. Remove unsupported ops via model modification or `onnx-simplifier` |
| `Shape mismatch` | Input shape is dynamic | Explicitly specify a fixed shape with `net_input_shapes` |
| `Quantization error` / accuracy degradation | Inappropriate calibration data | Increase image count, use actual production images |
| `Memory allocation failed` | Model too large for NPU memory | Fix batch size to 1, or consider a lighter model |
| `hailo_sdk_client not found` | DFC not installed | Refer to Step 1-1 |

### 4-4. (Recommended) Preprocessing with onnx-simplifier

Simplifying the ONNX model before conversion increases the success rate:

```bash
uv pip install onnx-simplifier
python -m onnxsim model.onnx model_simplified.onnx
```

---

## 5. Post-Conversion Verification (on AI Server)

### 5-1. Accuracy Verification with the Hailo Emulator

You can verify the accuracy of the HEF-converted model without physical hardware:

```python
# verify_hef.py
"""Compare HEF output against ONNX output to check accuracy degradation."""
import numpy as np
import onnxruntime as ort

# ONNX inference (float32, reference values)
sess = ort.InferenceSession("model.onnx")
test_image = np.load("calibration_data.npy")[0:1]  # Extract 1 image
input_name = sess.get_inputs()[0].name
onnx_output = sess.run(None, {input_name: test_image})[0][0]

# HEF emulator inference
from hailo_sdk_client import ClientRunner

runner = ClientRunner(har="wd_swinv2_tagger_v3.har")
hef_output = runner.infer(test_image)[0]

# Comparison
diff = np.abs(onnx_output - hef_output)
print(f"Max diff:  {diff.max():.6f}")
print(f"Mean diff: {diff.mean():.6f}")
print(f"Cosine similarity: {np.dot(onnx_output, hef_output) / (np.linalg.norm(onnx_output) * np.linalg.norm(hef_output)):.6f}")

# Tag match rate (at threshold 0.35)
threshold = 0.35
onnx_tags = set(np.where(onnx_output > threshold)[0])
hef_tags = set(np.where(hef_output > threshold)[0])
overlap = len(onnx_tags & hef_tags)
print(f"Tag match: {overlap}/{len(onnx_tags)} ({overlap/max(len(onnx_tags),1)*100:.1f}%)")
```

**Acceptance criteria**:
- Cosine similarity > 0.95: Good
- Tag match rate > 90%: Production-ready
- Tag match rate < 80%: Calibration data needs revision

---

## 6. Transfer to Pi and On-Device Testing

### 6-1. Transferring the HEF File

```bash
scp ~/hailo_convert/wd_tagger/wd_swinv2_tagger_v3.hef pi@raspberrypi:~/hailo_models/
```

### 6-2. On-Device Inference Test

```python
# test_wd_tagger_hef.py (Run on Pi5)
"""On-device inference test for HEF-converted WD-Tagger."""
import numpy as np
from hailo_platform import VDevice
from PIL import Image
import time

HEF_PATH = "~/.hailo_models/wd_swinv2_tagger_v3.hef"
INPUT_SIZE = 448

def preprocess(image_path: str) -> np.ndarray:
    """Same preprocessing as engine_onnx.py (but outputs uint8)."""
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

# Test image
test_img = preprocess("/path/to/test/image.png")

with VDevice() as vdevice:
    infer_model = vdevice.create_infer_model(HEF_PATH)
    configured = infer_model.configure()
    bindings = configured.create_bindings()

    # Input
    bindings.input().set_buffer(test_img)

    # Output buffer (uint8)
    out_info = infer_model.outputs[0]
    output_buf = np.empty(out_info.shape, dtype=np.uint8)
    bindings.output().set_buffer(output_buf)

    # Inference
    t0 = time.perf_counter()
    configured.run([bindings], timeout=10000)
    elapsed = (time.perf_counter() - t0) * 1000

    print(f"Inference: {elapsed:.1f} ms")
    print(f"Output shape: {output_buf.shape}")
    print(f"Output range: [{output_buf.min()}, {output_buf.max()}]")

    # Dequantization
    try:
        qi = out_info.quant_infos[0]
        scale = qi.qp_scale
        zp = qi.qp_zp
    except Exception:
        scale, zp = 1.0 / 255.0, 0.0

    probs = (output_buf.astype(np.float32) - zp) * scale
    print(f"Dequantized range: [{probs.min():.4f}, {probs.max():.4f}]")
```

### 6-3. Accuracy Comparison (ONNX vs HEF)

Run inference on the same image with both ONNX Runtime and Hailo HEF, then compare tag outputs:

```bash
# Run on Pi
python test_wd_tagger_hef.py
python -c "
from extensions.builtin_wd_tagger.core_impl.engine_onnx import OnnxWdTaggerEngine
e = OnnxWdTaggerEngine(Path('cache/wd_tagger/...'))
r = e.tag_image('/path/to/test/image.png')
for t in r.tags[:20]: print(f'{t.tag}: {t.confidence}')
"
```

---

## 7. Known Concerns

### SwinV2 Architecture Convertibility

WD-Tagger v3 is based on **Swin Transformer V2**. The following ops may be unsupported by DFC:

- **Window Attention** (shifted window)
- **Roll** operation
- **Relative position bias**

Alternative options if SwinV2 is not convertible:
1. **wd-vit-tagger-v3** (Vision Transformer based) -- ViT is in the same family as CLIP and has proven Hailo conversion track record
2. **wd-convnext-tagger-v3** (ConvNeXt based) -- CNN-based, easier to convert
3. **wd-eva02-large-tagger-v3** (EVA-02 based) -- Large model (300MB+), NPU memory constraints may apply

### Preprocessing Differences

- **ONNX version**: float32 input (0-255 range, no normalization)
- **HEF version**: uint8 input (normalization handled internally by HEF)

Conversion to HEF may embed preprocessing into the HEF itself.
Verify preprocessing handling when calling DFC's `translate_onnx_model()`.

### Dequantization Parameters

Outputs are uint8 quantized. To correctly recover tag probabilities (0.0-1.0),
dequantization using the HEF's quantization parameters (scale/zero_point) is essential.
Refer to the CLIP implementation (`extensions/builtin_hailo_semantic_search/core_impl/dequantize.py`) for reference.

---

## 8. Prompt Template for Claude

Example prompt for delegating conversion work to Claude on the AI server:

```
Please convert the WD-Tagger ONNX model to Hailo HEF following these steps:

1. Activate ~/hailo_env
2. Download model.onnx to ~/hailo_convert/wd_tagger/
3. Create calibration data using sample images prepared in calibration_images/
4. Run convert_wd_tagger.py to convert to HEF
5. Run verify_hef.py to compare accuracy against ONNX
6. Report the results

If conversion fails:
- Report the error message
- Try onnx-simplifier
- If SwinV2 is unsupported, retry with wd-vit-tagger-v3

Target model: SmilingWolf/wd-swinv2-tagger-v3
Target HW: hailo10h
```

---

## References

- [Hailo Dataflow Compiler Documentation](https://hailo.ai/developer-zone/documentation/dataflow-compiler/)
- [Hailo Model Zoo](https://github.com/hailo-ai/hailo_model_zoo)
- [WD-Tagger Models (HuggingFace)](https://huggingface.co/SmilingWolf)
- [ONNX Simplifier](https://github.com/daquexian/onnx-simplifier)
