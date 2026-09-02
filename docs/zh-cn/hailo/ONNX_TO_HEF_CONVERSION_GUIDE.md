# ONNX → HEF 转换手册

**目的**：将 WD-Tagger 等 ONNX 模型转换为 Hailo HEF 格式，使其可在 Hailo-10H NPU 上进行推理
**执行环境**：x86_64 Linux (AI 服务器) — Hailo Dataflow Compiler 仅支持 x86
**推理环境**：Raspberry Pi 5 + AI HAT 2 (Hailo-10H)

---

## 前置知识

### 为什么需要转换

| 项目 | ONNX Runtime (现状) | Hailo HEF (目标) |
|------|---------------------|-------------------|
| 执行位置 | CPU | Hailo-10H NPU (40 TOPS) |
| 量化 | float32 | INT8 (uint8) |
| 推理速度 | ~500ms/image (Pi5 CPU) | ~20ms/image (估计，基于 CLIP 实绩) |
| 内存 | ~200MB (模型加载) | ~数十 MB (HEF) |

### 转换流水线概述

```
model.onnx (float32)
  |
  | [1] Hailo Model Zoo 解析器 (ONNX → HAR)
  v
model.har (Hailo Archive, float32)
  |
  | [2] 优化 (层融合, 内存布局)
  v
model_optimized.har
  |
  | [3] 量化 (float32 → INT8, 使用校准图片)
  v
model_quantized.har
  |
  | [4] 编译 (转换为硬件指令)
  v
model.hef (Hailo Executable Format)
```

---

## 1. AI 服务器环境搭建

### 1-1. Hailo Dataflow Compiler 安装

从 Hailo Developer Zone (https://hailo.ai/developer-zone/) 下载。
需要注册账号。

```bash
# Python 3.10 or 3.11 推荐 (3.12+ 可能尚未支持)
python3 --version

# 创建 venv
python3 -m venv ~/hailo_env
source ~/hailo_env/bin/activate

# Hailo Dataflow Compiler (DFC) 安装
# 指定从 Developer Zone 下载的 .whl
uv pip install hailo_dataflow_compiler-3.29.0-py3-none-linux_x86_64.whl

# 依赖包
uv pip install numpy pillow onnx onnxruntime
```

**验证**：
```bash
python -c "from hailo_sdk_client import ClientRunner; print('DFC OK')"
```

### 1-2. Hailo Model Zoo（可选但推荐）

```bash
git clone https://github.com/hailo-ai/hailo_model_zoo.git ~/hailo_model_zoo
uv pip install -e ~/hailo_model_zoo
```

Model Zoo 包含许多模型的转换配置 (YAML)，可作为参考。

---

## 2. 目标模型的准备

### 2-1. WD-Tagger 模型

当前使用的模型：
- **仓库**：HuggingFace 的 `SmilingWolf/wd-swinv2-tagger-v3` 等
- **文件**：`model.onnx` (~110MB, float32)
- **输入**：`(1, 448, 448, 3)` float32, BGR, [0, 255] 不做归一化
- **输出**：`(1, num_tags)` float32, 已应用 sigmoid 的概率值

```bash
# 從 HuggingFace 下載
mkdir -p ~/hailo_convert/wd_tagger
cd ~/hailo_convert/wd_tagger

# 获取 model.onnx 和 selected_tags.csv
wget https://huggingface.co/SmilingWolf/wd-swinv2-tagger-v3/resolve/main/model.onnx
wget https://huggingface.co/SmilingWolf/wd-swinv2-tagger-v3/resolve/main/selected_tags.csv
```

### 2-2. 确认 ONNX 模型的输入输出

```python
import onnx

model = onnx.load("model.onnx")

print("=== 输入 ===")
for inp in model.graph.input:
    shape = [d.dim_value for d in inp.type.tensor_type.shape.dim]
    print(f"  {inp.name}: {shape}")

print("=== 输出 ===")
for out in model.graph.output:
    shape = [d.dim_value for d in out.type.tensor_type.shape.dim]
    print(f"  {out.name}: {shape}")
```

记下输入输出的 shape 和名称。转换时会用到。

---

## 3. 校准图片的准备

INT8 量化需要代表性的图片集（校准数据）。
用于决定量化参数 (scale/zero_point)。

```bash
mkdir -p ~/hailo_convert/calibration_images
```

### 要求

- **张数**：约 100～1000 张（越多精度越稳定，但耗时也更长）
- **内容**：实际推理图片的代表性样本（AI 生成图片的各种变化）
- **格式**：JPEG/PNG
- **尺寸**：任意（预处理脚本会进行缩放）

```bash
# 从 yu_ai_manager 的图库中随机复制 500 张的示例
# （从 Pi 通过 scp 等方式传输到 AI 服务器）
scp pi@raspberrypi:/path/to/images/*.png ~/hailo_convert/calibration_images/
```

### 校准预处理脚本

需要应用与 WD-Tagger 相同的预处理：

```python
# calibration_preprocess.py
"""将校准图片预处理为 WD-Tagger 格式。"""
import numpy as np
from PIL import Image
from pathlib import Path

INPUT_SIZE = 448

def preprocess(image_path: str) -> np.ndarray:
    """与 yu_ai_manager 的 engine_onnx.py 相同的预处理。"""
    with Image.open(image_path) as raw:
        img = raw.convert("RGBA")

    # 合成到白色背景上 (支持透明度)
    canvas = Image.new("RGBA", img.size, (255, 255, 255, 255))
    canvas.alpha_composite(img)
    img = canvas.convert("RGB")

    # 保持宽高比缩放
    old_w, old_h = img.size
    scale = INPUT_SIZE / max(old_w, old_h)
    new_w = int(old_w * scale)
    new_h = int(old_h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)

    # 以白色填充为正方形
    padded = Image.new("RGB", (INPUT_SIZE, INPUT_SIZE), (255, 255, 255))
    padded.paste(img, ((INPUT_SIZE - new_w) // 2, (INPUT_SIZE - new_h) // 2))

    # HWC, float32, RGB -> BGR
    arr = np.array(padded, dtype=np.float32)
    arr = arr[:, :, ::-1]  # RGB -> BGR

    return arr  # (448, 448, 3)


def load_calibration_set(image_dir: str, max_images: int = 500) -> np.ndarray:
    """将校准图片作为批量张量返回。"""
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

## 4. HEF 转换的执行

### 4-1. 转换脚本

```python
# convert_wd_tagger.py
"""WD-Tagger ONNX → Hailo HEF 转换脚本。"""
from hailo_sdk_client import ClientRunner
import numpy as np

# ========== 设置 ==========
ONNX_PATH = "model.onnx"
MODEL_NAME = "wd_swinv2_tagger_v3"
CALIBRATION_NPY = "calibration_data.npy"
HW_ARCH = "hailo10h"  # Hailo-10H 用
# ==========================

# --- Step 1: ONNX 解析 → HAR ---
print("[1/4] Parsing ONNX model...")
runner = ClientRunner(hw_arch=HW_ARCH)

# start_node / end_node 为模型的输入输出节点名
# (指定在 Step 2-2 中确认的名称)
hn, npz = runner.translate_onnx_model(
    ONNX_PATH,
    MODEL_NAME,
    # net_input_shapes={"input": [1, 448, 448, 3]},  # 根据需要指定
)
print(f"  Parsed: {len(npz)} layers")

# --- Step 2: 模型优化 ---
print("[2/4] Optimizing model...")
runner.optimize(npz)

# --- Step 3: INT8 量化 ---
print("[3/4] Quantizing (INT8)...")
calib_data = np.load(CALIBRATION_NPY)
print(f"  Calibration set: {calib_data.shape}")

runner.quantize(calib_data)

# --- Step 4: 编译 → HEF ---
print("[4/4] Compiling to HEF...")
hef = runner.compile()

hef_path = f"{MODEL_NAME}.hef"
with open(hef_path, "wb") as f:
    f.write(hef)
print(f"Done: {hef_path} ({len(hef) / 1024 / 1024:.1f} MB)")

# 同时保存 HAR (中间文件) (用于调试)
har_path = f"{MODEL_NAME}.har"
runner.save_har(har_path)
print(f"HAR saved: {har_path}")
```

### 4-2. 执行

```bash
source ~/hailo_env/bin/activate
cd ~/hailo_convert/wd_tagger

# 校准图片预处理
python calibration_preprocess.py

# HEF 转换
python convert_wd_tagger.py
```

**所需时间估计**：取决于模型大小和校准图片数量，约数十分钟至数小时。

### 4-3. 常见错误与对策

| 错误 | 原因 | 对策 |
|--------|------|------|
| `UnsupportedOp: <op_name>` | ONNX 算子 DFC 不支持 | 确认 Hailo 支持的算子列表。不支持的 op 需修改模型或以 `onnx-simplifier` 移除 |
| `Shape mismatch` | 输入 shape 为动态 | 以 `net_input_shapes` 明确指定固定 shape |
| `Quantization error` / 精度劣化 | 校准数据不合适 | 增加图片数量、使用实际运营图片 |
| `Memory allocation failed` | 模型过大无法容纳于 NPU 内存 | 固定 batch size=1，或考虑使用轻量模型 |
| `hailo_sdk_client not found` | DFC 未安装 | 确认步骤 1-1 |

### 4-4.（推荐）以 onnx-simplifier 预处理

转换前先简化 ONNX 模型可提高成功率：

```bash
uv pip install onnx-simplifier
python -m onnxsim model.onnx model_simplified.onnx
```

---

## 5. 转换后的验证（AI 服务器上）

### 5-1. 以 Hailo Emulator 验证精度

可在无实机的情况下验证转换为 HEF 的模型精度：

```python
# verify_hef.py
"""将 HEF 的输出与 ONNX 的输出进行比较，确认精度劣化情况。"""
import numpy as np
import onnxruntime as ort

# ONNX 推理 (float32, 基准值)
sess = ort.InferenceSession("model.onnx")
test_image = np.load("calibration_data.npy")[0:1]  # 取出 1 张
input_name = sess.get_inputs()[0].name
onnx_output = sess.run(None, {input_name: test_image})[0][0]

# HEF 模拟器推理
from hailo_sdk_client import ClientRunner

runner = ClientRunner(har="wd_swinv2_tagger_v3.har")
hef_output = runner.infer(test_image)[0]

# 比较
diff = np.abs(onnx_output - hef_output)
print(f"Max diff:  {diff.max():.6f}")
print(f"Mean diff: {diff.mean():.6f}")
print(f"Cosine similarity: {np.dot(onnx_output, hef_output) / (np.linalg.norm(onnx_output) * np.linalg.norm(hef_output)):.6f}")

# 标签一致率 (阈值 0.35 下的一致情况)
threshold = 0.35
onnx_tags = set(np.where(onnx_output > threshold)[0])
hef_tags = set(np.where(hef_output > threshold)[0])
overlap = len(onnx_tags & hef_tags)
print(f"Tag match: {overlap}/{len(onnx_tags)} ({overlap/max(len(onnx_tags),1)*100:.1f}%)")
```

**判定标准**：
- 余弦相似度 > 0.95：良好
- 标签一致率 > 90%：实用级别
- 标签一致率 < 80%：需要重新审视校准数据

---

## 6. 传输至 Pi 并进行实机测试

### 6-1. HEF 文件的传输

```bash
scp ~/hailo_convert/wd_tagger/wd_swinv2_tagger_v3.hef pi@raspberrypi:~/hailo_models/
```

### 6-2. 实机推理测试

```python
# test_wd_tagger_hef.py (在 Pi5 上执行)
"""HEF 转换后的 WD-Tagger 实机推理测试。"""
import numpy as np
from hailo_platform import VDevice
from PIL import Image
import time

HEF_PATH = "~/.hailo_models/wd_swinv2_tagger_v3.hef"
INPUT_SIZE = 448

def preprocess(image_path: str) -> np.ndarray:
    """与 engine_onnx.py 相同的预处理 (但以 uint8 输出)。"""
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

# 测试图片
test_img = preprocess("/path/to/test/image.png")

with VDevice() as vdevice:
    infer_model = vdevice.create_infer_model(HEF_PATH)
    configured = infer_model.configure()
    bindings = configured.create_bindings()

    # 输入
    bindings.input().set_buffer(test_img)

    # 输出缓冲区 (uint8)
    out_info = infer_model.outputs[0]
    output_buf = np.empty(out_info.shape, dtype=np.uint8)
    bindings.output().set_buffer(output_buf)

    # 推理
    t0 = time.perf_counter()
    configured.run([bindings], timeout=10000)
    elapsed = (time.perf_counter() - t0) * 1000

    print(f"Inference: {elapsed:.1f} ms")
    print(f"Output shape: {output_buf.shape}")
    print(f"Output range: [{output_buf.min()}, {output_buf.max()}]")

    # 反量化
    try:
        qi = out_info.quant_infos[0]
        scale = qi.qp_scale
        zp = qi.qp_zp
    except Exception:
        scale, zp = 1.0 / 255.0, 0.0

    probs = (output_buf.astype(np.float32) - zp) * scale
    print(f"Dequantized range: [{probs.min():.4f}, {probs.max():.4f}]")
```

### 6-3. 精度比较 (ONNX vs HEF)

使用同一张图片分别以 ONNX Runtime 和 Hailo HEF 进行推理，比较标签输出：

```bash
# 在 Pi 上执行
python test_wd_tagger_hef.py
python -c "
from extensions.builtin_wd_tagger.core_impl.engine_onnx import OnnxWdTaggerEngine
e = OnnxWdTaggerEngine(Path('cache/wd_tagger/...'))
r = e.tag_image('/path/to/test/image.png')
for t in r.tags[:20]: print(f'{t.tag}: {t.confidence}')
"
```

---

## 7. 已知注意事项

### SwinV2 架构的转换可行性

WD-Tagger v3 基于 **Swin Transformer V2**。以下 Op 可能在 DFC 中不支持：

- **Window Attention** (shifted window)
- **Roll** 操作
- **相对位置偏置**

若 SwinV2 无法转换的替代方案：
1. **wd-vit-tagger-v3** (Vision Transformer 架构) — ViT 与 CLIP 同系，Hailo 有转换实绩
2. **wd-convnext-tagger-v3** (ConvNeXt 架构) — CNN 系列，较容易转换
3. **wd-eva02-large-tagger-v3** (EVA-02 架构) — 模型较大 (300MB+)，需注意 NPU 内存

### 预处理的差异

- **ONNX 版**：float32 输入 (0-255 范围, 不做归一化)
- **HEF 版**：uint8 输入 (HEF 内部进行归一化)

转换为 HEF 后，预处理可能会被内建到 HEF 中。
在 DFC 的 `translate_onnx_model()` 时需确认预处理的处理方式。

### 反量化参数

输出会被 uint8 量化。要正确还原标签概率 (0.0-1.0)，
必须使用 HEF 的量化参数 (scale/zero_point) 进行反量化。
请参考 CLIP 的实绩 (`extensions/builtin_hailo_semantic_search/core_impl/dequantize.py`)。

---

## 8. 给 Claude 的指示模板

在 AI 服务器上委托 Claude 进行转换作业时的提示示例：

```
请按照以下步骤将 WD-Tagger ONNX 模型转换为 Hailo HEF。

1. 激活 ~/hailo_env
2. 将 model.onnx 下载到 ~/hailo_convert/wd_tagger/
3. 使用 calibration_images/ 中准备的样本图片创建校准数据
4. 执行 convert_wd_tagger.py 转换为 HEF
5. 使用 verify_hef.py 进行与 ONNX 的精度比较
6. 请报告结果

转换失败时:
- 报告错误信息
- 尝试 onnx-simplifier
- 如果 SwinV2 不支持，则使用 wd-vit-tagger-v3 重试

目标模型: SmilingWolf/wd-swinv2-tagger-v3
目标硬件: hailo10h
```

---

## 参考链接

- [Hailo Dataflow Compiler 文档](https://hailo.ai/developer-zone/documentation/dataflow-compiler/)
- [Hailo Model Zoo](https://github.com/hailo-ai/hailo_model_zoo)
- [WD-Tagger 模型 (HuggingFace)](https://huggingface.co/SmilingWolf)
- [ONNX Simplifier](https://github.com/daquexian/onnx-simplifier)
