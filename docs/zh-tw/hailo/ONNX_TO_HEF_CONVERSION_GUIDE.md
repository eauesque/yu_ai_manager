# ONNX → HEF 轉換手冊

**目的**：將 WD-Tagger 等 ONNX 模型轉換為 Hailo HEF 格式，使其可在 Hailo-10H NPU 上進行推論
**執行環境**：x86_64 Linux (AI 伺服器) — Hailo Dataflow Compiler 僅支援 x86
**推論環境**：Raspberry Pi 5 + AI HAT 2 (Hailo-10H)

---

## 前置知識

### 為什麼需要轉換

| 項目 | ONNX Runtime (現狀) | Hailo HEF (目標) |
|------|---------------------|-------------------|
| 執行位置 | CPU | Hailo-10H NPU (40 TOPS) |
| 量化 | float32 | INT8 (uint8) |
| 推論速度 | ~500ms/image (Pi5 CPU) | ~20ms/image (推估，基於 CLIP 實績) |
| 記憶體 | ~200MB (模型載入) | ~數十 MB (HEF) |

### 轉換流水線概述

```
model.onnx (float32)
  |
  | [1] Hailo Model Zoo 解析器 (ONNX → HAR)
  v
model.har (Hailo Archive, float32)
  |
  | [2] 最佳化 (層融合, 記憶體配置)
  v
model_optimized.har
  |
  | [3] 量化 (float32 → INT8, 使用校準圖片)
  v
model_quantized.har
  |
  | [4] 編譯 (轉換為硬體指令)
  v
model.hef (Hailo Executable Format)
```

---

## 1. AI 伺服器環境建置

### 1-1. Hailo Dataflow Compiler 安裝

從 Hailo Developer Zone (https://hailo.ai/developer-zone/) 下載。
需要註冊帳號。

```bash
# Python 3.10 or 3.11 推薦 (3.12+ 可能尚未支援)
python3 --version

# 建立 venv
python3 -m venv ~/hailo_env
source ~/hailo_env/bin/activate

# 安裝 Hailo Dataflow Compiler (DFC)
# 指定從 Developer Zone 下載的 .whl
uv pip install hailo_dataflow_compiler-3.29.0-py3-none-linux_x86_64.whl

# 依賴套件
uv pip install numpy pillow onnx onnxruntime
```

**驗證**：
```bash
python -c "from hailo_sdk_client import ClientRunner; print('DFC OK')"
```

### 1-2. Hailo Model Zoo（選用但推薦）

```bash
git clone https://github.com/hailo-ai/hailo_model_zoo.git ~/hailo_model_zoo
uv pip install -e ~/hailo_model_zoo
```

Model Zoo 包含許多模型的轉換設定 (YAML)，可作為參考。

---

## 2. 目標模型的準備

### 2-1. WD-Tagger 模型

目前使用的模型：
- **儲存庫**：HuggingFace 的 `SmilingWolf/wd-swinv2-tagger-v3` 等
- **檔案**：`model.onnx` (~110MB, float32)
- **輸入**：`(1, 448, 448, 3)` float32, BGR, [0, 255] 不做正規化
- **輸出**：`(1, num_tags)` float32, 已套用 sigmoid 的機率值

```bash
# 從 HuggingFace 下載
mkdir -p ~/hailo_convert/wd_tagger
cd ~/hailo_convert/wd_tagger

# 取得 model.onnx 和 selected_tags.csv
wget https://huggingface.co/SmilingWolf/wd-swinv2-tagger-v3/resolve/main/model.onnx
wget https://huggingface.co/SmilingWolf/wd-swinv2-tagger-v3/resolve/main/selected_tags.csv
```

### 2-2. 確認 ONNX 模型的輸入輸出

```python
import onnx

model = onnx.load("model.onnx")

print("=== 輸入 ===")
for inp in model.graph.input:
    shape = [d.dim_value for d in inp.type.tensor_type.shape.dim]
    print(f"  {inp.name}: {shape}")

print("=== 輸出 ===")
for out in model.graph.output:
    shape = [d.dim_value for d in out.type.tensor_type.shape.dim]
    print(f"  {out.name}: {shape}")
```

記下輸入輸出的 shape 和名稱。轉換時會用到。

---

## 3. 校準圖片的準備

INT8 量化需要代表性的圖片集（校準資料）。
用於決定量化參數 (scale/zero_point)。

```bash
mkdir -p ~/hailo_convert/calibration_images
```

### 要求

- **張數**：約 100～1000 張（越多精度越穩定，但耗時也更長）
- **內容**：實際推論圖片的代表性樣本（AI 生成圖片的各種變化）
- **格式**：JPEG/PNG
- **尺寸**：任意（前處理腳本會進行縮放）

```bash
# 從 yu_ai_manager 的圖庫中隨機複製 500 張的範例
# （從 Pi 透過 scp 等方式傳輸到 AI 伺服器）
scp pi@raspberrypi:/path/to/images/*.png ~/hailo_convert/calibration_images/
```

### 校準前處理腳本

需要套用與 WD-Tagger 相同的前處理：

```python
# calibration_preprocess.py
"""將校準圖片預處理為 WD-Tagger 格式。"""
import numpy as np
from PIL import Image
from pathlib import Path

INPUT_SIZE = 448

def preprocess(image_path: str) -> np.ndarray:
    """與 yu_ai_manager 的 engine_onnx.py 相同的前處理。"""
    with Image.open(image_path) as raw:
        img = raw.convert("RGBA")

    # 合成到白色背景上 (支援透明度)
    canvas = Image.new("RGBA", img.size, (255, 255, 255, 255))
    canvas.alpha_composite(img)
    img = canvas.convert("RGB")

    # 保持寬高比縮放
    old_w, old_h = img.size
    scale = INPUT_SIZE / max(old_w, old_h)
    new_w = int(old_w * scale)
    new_h = int(old_h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)

    # 以白色填充為正方形
    padded = Image.new("RGB", (INPUT_SIZE, INPUT_SIZE), (255, 255, 255))
    padded.paste(img, ((INPUT_SIZE - new_w) // 2, (INPUT_SIZE - new_h) // 2))

    # HWC, float32, RGB -> BGR
    arr = np.array(padded, dtype=np.float32)
    arr = arr[:, :, ::-1]  # RGB -> BGR

    return arr  # (448, 448, 3)


def load_calibration_set(image_dir: str, max_images: int = 500) -> np.ndarray:
    """將校準圖片作為批次張量返回。"""
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

## 4. HEF 轉換的執行

### 4-1. 轉換腳本

```python
# convert_wd_tagger.py
"""WD-Tagger ONNX → Hailo HEF 轉換腳本。"""
from hailo_sdk_client import ClientRunner
import numpy as np

# ========== 設定 ==========
ONNX_PATH = "model.onnx"
MODEL_NAME = "wd_swinv2_tagger_v3"
CALIBRATION_NPY = "calibration_data.npy"
HW_ARCH = "hailo10h"  # Hailo-10H 用
# ==========================

# --- Step 1: ONNX 解析 → HAR ---
print("[1/4] Parsing ONNX model...")
runner = ClientRunner(hw_arch=HW_ARCH)

# start_node / end_node 為模型的輸入輸出節點名
# (指定在 Step 2-2 中確認的名稱)
hn, npz = runner.translate_onnx_model(
    ONNX_PATH,
    MODEL_NAME,
    # net_input_shapes={"input": [1, 448, 448, 3]},  # 根據需要指定
)
print(f"  Parsed: {len(npz)} layers")

# --- Step 2: 模型最佳化 ---
print("[2/4] Optimizing model...")
runner.optimize(npz)

# --- Step 3: INT8 量化 ---
print("[3/4] Quantizing (INT8)...")
calib_data = np.load(CALIBRATION_NPY)
print(f"  Calibration set: {calib_data.shape}")

runner.quantize(calib_data)

# --- Step 4: 編譯 → HEF ---
print("[4/4] Compiling to HEF...")
hef = runner.compile()

hef_path = f"{MODEL_NAME}.hef"
with open(hef_path, "wb") as f:
    f.write(hef)
print(f"Done: {hef_path} ({len(hef) / 1024 / 1024:.1f} MB)")

# 同時儲存 HAR (中間檔案) (用於除錯)
har_path = f"{MODEL_NAME}.har"
runner.save_har(har_path)
print(f"HAR saved: {har_path}")
```

### 4-2. 執行

```bash
source ~/hailo_env/bin/activate
cd ~/hailo_convert/wd_tagger

# 校準圖片前處理
python calibration_preprocess.py

# HEF 轉換
python convert_wd_tagger.py
```

**所需時間估計**：取決於模型大小和校準圖片數量，約數十分鐘至數小時。

### 4-3. 常見錯誤與對策

| 錯誤 | 原因 | 對策 |
|--------|------|------|
| `UnsupportedOp: <op_name>` | ONNX 運算子 DFC 不支援 | 確認 Hailo 支援的運算子清單。不支援的 op 需修改模型或以 `onnx-simplifier` 移除 |
| `Shape mismatch` | 輸入 shape 為動態 | 以 `net_input_shapes` 明確指定固定 shape |
| `Quantization error` / 精度劣化 | 校準資料不適當 | 增加圖片數量、使用實際營運圖片 |
| `Memory allocation failed` | 模型過大無法容納於 NPU 記憶體 | 固定 batch size=1，或考慮使用輕量模型 |
| `hailo_sdk_client not found` | DFC 未安裝 | 確認步驟 1-1 |

### 4-4. （推薦）以 onnx-simplifier 前處理

轉換前先簡化 ONNX 模型可提高成功率：

```bash
uv pip install onnx-simplifier
python -m onnxsim model.onnx model_simplified.onnx
```

---

## 5. 轉換後的驗證（AI 伺服器上）

### 5-1. 以 Hailo Emulator 驗證精度

可在無實機的情況下驗證轉換為 HEF 的模型精度：

```python
# verify_hef.py
"""將 HEF 的輸出與 ONNX 的輸出進行比較，確認精度劣化情況。"""
import numpy as np
import onnxruntime as ort

# ONNX 推論 (float32, 基準值)
sess = ort.InferenceSession("model.onnx")
test_image = np.load("calibration_data.npy")[0:1]  # 取出 1 張
input_name = sess.get_inputs()[0].name
onnx_output = sess.run(None, {input_name: test_image})[0][0]

# HEF 模擬器推論
from hailo_sdk_client import ClientRunner

runner = ClientRunner(har="wd_swinv2_tagger_v3.har")
hef_output = runner.infer(test_image)[0]

# 比較結果
diff = np.abs(onnx_output - hef_output)
print(f"Max diff:  {diff.max():.6f}")
print(f"Mean diff: {diff.mean():.6f}")
print(f"Cosine similarity: {np.dot(onnx_output, hef_output) / (np.linalg.norm(onnx_output) * np.linalg.norm(hef_output)):.6f}")

# 標籤一致率 (閾值 0.35 下的一致情況)
threshold = 0.35
onnx_tags = set(np.where(onnx_output > threshold)[0])
hef_tags = set(np.where(hef_output > threshold)[0])
overlap = len(onnx_tags & hef_tags)
print(f"Tag match: {overlap}/{len(onnx_tags)} ({overlap/max(len(onnx_tags),1)*100:.1f}%)")
```

**判定基準**：
- 餘弦相似度 > 0.95：良好
- 標籤一致率 > 90%：實用等級
- 標籤一致率 < 80%：需要重新檢視校準資料

---

## 6. 傳輸至 Pi 並進行實機測試

### 6-1. HEF 檔案的傳輸

```bash
scp ~/hailo_convert/wd_tagger/wd_swinv2_tagger_v3.hef pi@raspberrypi:~/hailo_models/
```

### 6-2. 實機推論測試

```python
# test_wd_tagger_hef.py (在 Pi5 上執行)
"""HEF 轉換後的 WD-Tagger 實機推論測試。"""
import numpy as np
from hailo_platform import VDevice
from PIL import Image
import time

HEF_PATH = "~/.hailo_models/wd_swinv2_tagger_v3.hef"
INPUT_SIZE = 448

def preprocess(image_path: str) -> np.ndarray:
    """與 engine_onnx.py 相同的前處理 (但以 uint8 輸出)。"""
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

# 測試圖片
test_img = preprocess("/path/to/test/image.png")

with VDevice() as vdevice:
    infer_model = vdevice.create_infer_model(HEF_PATH)
    configured = infer_model.configure()
    bindings = configured.create_bindings()

    # 輸入
    bindings.input().set_buffer(test_img)

    # 輸出緩衝區 (uint8)
    out_info = infer_model.outputs[0]
    output_buf = np.empty(out_info.shape, dtype=np.uint8)
    bindings.output().set_buffer(output_buf)

    # 推論執行
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

### 6-3. 精度比較 (ONNX vs HEF)

使用同一張圖片分別以 ONNX Runtime 和 Hailo HEF 進行推論，比較標籤輸出：

```bash
# 在 Pi 上執行
python test_wd_tagger_hef.py
python -c "
from extensions.builtin_wd_tagger.core_impl.engine_onnx import OnnxWdTaggerEngine
e = OnnxWdTaggerEngine(Path('cache/wd_tagger/...'))
r = e.tag_image('/path/to/test/image.png')
for t in r.tags[:20]: print(f'{t.tag}: {t.confidence}')
"
```

---

## 7. 已知注意事項

### SwinV2 架構的轉換可行性

WD-Tagger v3 基於 **Swin Transformer V2**。以下 Op 可能在 DFC 中不支援：

- **Window Attention** (shifted window)
- **Roll** 操作
- **相對位置偏差**

若 SwinV2 無法轉換的替代方案：
1. **wd-vit-tagger-v3** (Vision Transformer 架構) — ViT 與 CLIP 同系，Hailo 有轉換實績
2. **wd-convnext-tagger-v3** (ConvNeXt 架構) — CNN 系列，較容易轉換
3. **wd-eva02-large-tagger-v3** (EVA-02 架構) — 模型較大 (300MB+)，需注意 NPU 記憶體

### 前處理的差異

- **ONNX 版**：float32 輸入 (0-255 範圍, 不做正規化)
- **HEF 版**：uint8 輸入 (HEF 內部進行正規化)

轉換為 HEF 後，前處理可能會被內建到 HEF 中。
在 DFC 的 `translate_onnx_model()` 時需確認前處理的處理方式。

### 反量化參數

輸出會被 uint8 量化。要正確還原標籤機率 (0.0-1.0)，
必須使用 HEF 的量化參數 (scale/zero_point) 進行反量化。
請參考 CLIP 的實績 (`extensions/builtin_hailo_semantic_search/core_impl/dequantize.py`)。

---

## 8. 給 Claude 的指示範本

在 AI 伺服器上委託 Claude 進行轉換作業時的提示範例：

```
請按照以下步驟將 WD-Tagger ONNX 模型轉換為 Hailo HEF。

1. 啟用 ~/hailo_env
2. 將 model.onnx 下載到 ~/hailo_convert/wd_tagger/
3. 使用 calibration_images/ 中準備的樣本圖片建立校準資料
4. 執行 convert_wd_tagger.py 轉換為 HEF
5. 使用 verify_hef.py 進行與 ONNX 的精度比較
6. 請回報結果

轉換失敗時:
- 回報錯誤訊息
- 嘗試 onnx-simplifier
- 如果 SwinV2 不支援，則使用 wd-vit-tagger-v3 重試

目標模型: SmilingWolf/wd-swinv2-tagger-v3
目標硬體: hailo10h
```

---

## 參考連結

- [Hailo Dataflow Compiler 文件](https://hailo.ai/developer-zone/documentation/dataflow-compiler/)
- [Hailo Model Zoo](https://github.com/hailo-ai/hailo_model_zoo)
- [WD-Tagger 模型 (HuggingFace)](https://huggingface.co/SmilingWolf)
- [ONNX Simplifier](https://github.com/daquexian/onnx-simplifier)
