# Guida alla Conversione ONNX → HEF

**Scopo**: Convertire modelli ONNX come WD-Tagger nel formato Hailo HEF per l'inferenza su Hailo-10H NPU
**Ambiente di esecuzione**: x86_64 Linux (server AI) — Hailo Dataflow Compiler supporta solo x86
**Ambiente di inferenza**: Raspberry Pi 5 + AI HAT 2 (Hailo-10H)

---

## Prerequisiti

### Perché è Necessaria la Conversione

| Elemento | ONNX Runtime (attuale) | Hailo HEF (obiettivo) |
|----------|------------------------|----------------------|
| Esecuzione | CPU | Hailo-10H NPU (40 TOPS) |
| Quantizzazione | float32 | INT8 (uint8) |
| Velocità inferenza | ~500ms/immagine (Pi5 CPU) | ~20ms/immagine (stima, basata su CLIP) |
| Memoria | ~200MB (caricamento modello) | ~decine MB (HEF) |

### Panoramica della Pipeline di Conversione

```
model.onnx (float32)
  |
  | [1] Parser Hailo Model Zoo (ONNX → HAR)
  v
model.har (Hailo Archive, float32)
  |
  | [2] Ottimizzazione (fusione layer, layout memoria)
  v
model_optimized.har
  |
  | [3] Quantizzazione (float32 → INT8, usando immagini di calibrazione)
  v
model_quantized.har
  |
  | [4] Compilazione (conversione in istruzioni HW)
  v
model.hef (Hailo Executable Format)
```

---

## 1. Configurazione dell'Ambiente sul Server AI

### 1-1. Installazione di Hailo Dataflow Compiler

Scaricare da Hailo Developer Zone (https://hailo.ai/developer-zone/).
È richiesta la registrazione di un account.

```bash
# Python 3.10 o 3.11 consigliato (3.12+ potrebbe non essere supportato)
python3 --version

# Creazione venv
python3 -m venv ~/hailo_env
source ~/hailo_env/bin/activate

# Installazione Hailo Dataflow Compiler (DFC)
# Specificare il file .whl scaricato da Developer Zone
uv pip install hailo_dataflow_compiler-3.29.0-py3-none-linux_x86_64.whl

# Pacchetti dipendenti
uv pip install numpy pillow onnx onnxruntime
```

**Verifica**:
```bash
python -c "from hailo_sdk_client import ClientRunner; print('DFC OK')"
```

### 1-2. Hailo Model Zoo (opzionale ma consigliato)

```bash
git clone https://github.com/hailo-ai/hailo_model_zoo.git ~/hailo_model_zoo
uv pip install -e ~/hailo_model_zoo
```

---

## 2. Preparazione del Modello Target

### 2-1. Modelli WD-Tagger

Modelli attualmente in uso:
- **Repository**: `SmilingWolf/wd-swinv2-tagger-v3` ecc. su HuggingFace
- **File**: `model.onnx` (~110MB, float32)
- **Input**: `(1, 448, 448, 3)` float32, BGR, normalizzazione [0, 255] assente
- **Output**: `(1, num_tags)` float32, probabilità sigmoid

```bash
# Download da HuggingFace
mkdir -p ~/hailo_convert/wd_tagger
cd ~/hailo_convert/wd_tagger

wget https://huggingface.co/SmilingWolf/wd-swinv2-tagger-v3/resolve/main/model.onnx
wget https://huggingface.co/SmilingWolf/wd-swinv2-tagger-v3/resolve/main/selected_tags.csv
```

### 2-2. Verifica dell'Input/Output del Modello ONNX

```python
import onnx

model = onnx.load("model.onnx")

print("=== Input ===")
for inp in model.graph.input:
    shape = [d.dim_value for d in inp.type.tensor_type.shape.dim]
    print(f"  {inp.name}: {shape}")

print("=== Output ===")
for out in model.graph.output:
    shape = [d.dim_value for d in out.type.tensor_type.shape.dim]
    print(f"  {out.name}: {shape}")
```

---

## 3. Preparazione delle Immagini di Calibrazione

Per la quantizzazione INT8 è necessario un set di immagini rappresentative (dati di calibrazione).

```bash
mkdir -p ~/hailo_convert/calibration_images
```

### Requisiti

- **Quantità**: circa 100~1000 immagini (più numerose, più stabile la precisione)
- **Contenuto**: campioni rappresentativi delle immagini da inferire
- **Formato**: JPEG/PNG

### Script di Preprocessing per la Calibrazione

```python
# calibration_preprocess.py
"""Pre-processa immagini di calibrazione nel formato WD-Tagger."""
import numpy as np
from PIL import Image
from pathlib import Path

INPUT_SIZE = 448

def preprocess(image_path: str) -> np.ndarray:
    """Stesso preprocessing di engine_onnx.py in yu_ai_manager."""
    with Image.open(image_path) as raw:
        img = raw.convert("RGBA")

    # Composizione su sfondo bianco (gestione trasparenza)
    canvas = Image.new("RGBA", img.size, (255, 255, 255, 255))
    canvas.alpha_composite(img)
    img = canvas.convert("RGB")

    # Resize mantenendo aspect ratio
    old_w, old_h = img.size
    scale = INPUT_SIZE / max(old_w, old_h)
    new_w = int(old_w * scale)
    new_h = int(old_h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)

    # Padding bianco per ottenere immagine quadrata
    padded = Image.new("RGB", (INPUT_SIZE, INPUT_SIZE), (255, 255, 255))
    padded.paste(img, ((INPUT_SIZE - new_w) // 2, (INPUT_SIZE - new_h) // 2))

    # HWC, float32, RGB -> BGR
    arr = np.array(padded, dtype=np.float32)
    arr = arr[:, :, ::-1]  # RGB -> BGR

    return arr  # (448, 448, 3)


def load_calibration_set(image_dir: str, max_images: int = 500) -> np.ndarray:
    """Restituisce le immagini di calibrazione come batch tensor."""
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

## 4. Esecuzione della Conversione HEF

### 4-1. Script di Conversione

```python
# convert_wd_tagger.py
"""Script di conversione WD-Tagger ONNX → Hailo HEF."""
from hailo_sdk_client import ClientRunner
import numpy as np

# ========== Configurazione ==========
ONNX_PATH = "model.onnx"
MODEL_NAME = "wd_swinv2_tagger_v3"
CALIBRATION_NPY = "calibration_data.npy"
HW_ARCH = "hailo10h"  # Per Hailo-10H
# ====================================

# --- Step 1: Parse ONNX → HAR ---
print("[1/4] Parsing ONNX model...")
runner = ClientRunner(hw_arch=HW_ARCH)

hn, npz = runner.translate_onnx_model(
    ONNX_PATH,
    MODEL_NAME,
)
print(f"  Parsed: {len(npz)} layers")

# --- Step 2: Ottimizzazione modello ---
print("[2/4] Optimizing model...")
runner.optimize(npz)

# --- Step 3: Quantizzazione INT8 ---
print("[3/4] Quantizing (INT8)...")
calib_data = np.load(CALIBRATION_NPY)
print(f"  Calibration set: {calib_data.shape}")

runner.quantize(calib_data)

# --- Step 4: Compilazione → HEF ---
print("[4/4] Compiling to HEF...")
hef = runner.compile()

hef_path = f"{MODEL_NAME}.hef"
with open(hef_path, "wb") as f:
    f.write(hef)
print(f"Done: {hef_path} ({len(hef) / 1024 / 1024:.1f} MB)")

# Salva anche HAR (file intermedio per debug)
har_path = f"{MODEL_NAME}.har"
runner.save_har(har_path)
print(f"HAR saved: {har_path}")
```

### 4-2. Esecuzione

```bash
source ~/hailo_env/bin/activate
cd ~/hailo_convert/wd_tagger

# Preprocessing immagini di calibrazione
python calibration_preprocess.py

# Conversione HEF
python convert_wd_tagger.py
```

### 4-3. Errori Comuni e Soluzioni

| Errore | Causa | Soluzione |
|--------|-------|-----------|
| `UnsupportedOp: <op_name>` | Operatore ONNX non supportato da DFC | Verificare la lista operatori supportati da Hailo |
| `Shape mismatch` | Shape dell'input dinamico | Specificare shape fissa con `net_input_shapes` |
| `Quantization error` / degradazione precisione | Dati di calibrazione inadeguati | Aumentare le immagini, usare immagini operative reali |
| `Memory allocation failed` | Modello troppo grande per la memoria NPU | Fissare batch size=1, o considerare modello più leggero |

### 4-4. (Consigliato) Pre-processing con onnx-simplifier

Semplificare il modello ONNX prima della conversione aumenta il tasso di successo:

```bash
uv pip install onnx-simplifier
python -m onnxsim model.onnx model_simplified.onnx
```

---

## 5. Verifica Dopo la Conversione (sul Server AI)

### 5-1. Verifica Precisione con Hailo Emulator

```python
# verify_hef.py
"""Verifica la degradazione di precisione confrontando output HEF con ONNX."""
import numpy as np
import onnxruntime as ort

# Inferenza ONNX (float32, valore di riferimento)
sess = ort.InferenceSession("model.onnx")
test_image = np.load("calibration_data.npy")[0:1]  # 1 immagine
input_name = sess.get_inputs()[0].name
onnx_output = sess.run(None, {input_name: test_image})[0][0]

# Inferenza con emulatore HEF
from hailo_sdk_client import ClientRunner

runner = ClientRunner(har="wd_swinv2_tagger_v3.har")
hef_output = runner.infer(test_image)[0]

# Confronto
diff = np.abs(onnx_output - hef_output)
print(f"Max diff:  {diff.max():.6f}")
print(f"Mean diff: {diff.mean():.6f}")
print(f"Cosine similarity: {np.dot(onnx_output, hef_output) / (np.linalg.norm(onnx_output) * np.linalg.norm(hef_output)):.6f}")

# Tasso di corrispondenza tag (con soglia 0.35)
threshold = 0.35
onnx_tags = set(np.where(onnx_output > threshold)[0])
hef_tags = set(np.where(hef_output > threshold)[0])
overlap = len(onnx_tags & hef_tags)
print(f"Tag match: {overlap}/{len(onnx_tags)} ({overlap/max(len(onnx_tags),1)*100:.1f}%)")
```

**Criteri di valutazione**:
- Similarità coseno > 0.95: Buona
- Tasso corrispondenza tag > 90%: Livello pratico
- Tasso corrispondenza tag < 80%: Necessario rivedere i dati di calibrazione

---

## 6. Trasferimento su Pi e Test su Hardware Reale

### 6-1. Trasferimento del File HEF

```bash
scp ~/hailo_convert/wd_tagger/wd_swinv2_tagger_v3.hef pi@raspberrypi:~/hailo_models/
```

### 6-2. Test di Inferenza su Hardware Reale

```python
# test_wd_tagger_hef.py (eseguire su Pi5)
"""Test di inferenza su hardware reale del WD-Tagger convertito in HEF."""
import numpy as np
from hailo_platform import VDevice
from PIL import Image
import time

HEF_PATH = "~/.hailo_models/wd_swinv2_tagger_v3.hef"
INPUT_SIZE = 448

def preprocess(image_path: str) -> np.ndarray:
    """Stesso preprocessing di engine_onnx.py (output uint8)."""
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

# Immagine di test
test_img = preprocess("/path/to/test/image.png")

with VDevice() as vdevice:
    infer_model = vdevice.create_infer_model(HEF_PATH)
    configured = infer_model.configure()
    bindings = configured.create_bindings()

    # Input
    bindings.input().set_buffer(test_img)

    # Buffer output (uint8)
    out_info = infer_model.outputs[0]
    output_buf = np.empty(out_info.shape, dtype=np.uint8)
    bindings.output().set_buffer(output_buf)

    # Inferenza
    t0 = time.perf_counter()
    configured.run([bindings], timeout=10000)
    elapsed = (time.perf_counter() - t0) * 1000

    print(f"Inference: {elapsed:.1f} ms")
    print(f"Output shape: {output_buf.shape}")

    # Dequantizzazione
    try:
        qi = out_info.quant_infos[0]
        scale = qi.qp_scale
        zp = qi.qp_zp
    except Exception:
        scale, zp = 1.0 / 255.0, 0.0

    probs = (output_buf.astype(np.float32) - zp) * scale
    print(f"Dequantized range: [{probs.min():.4f}, {probs.max():.4f}]")
```

---

## 7. Problemi Noti

### Convertibilità dell'Architettura SwinV2

WD-Tagger v3 è basato su **Swin Transformer V2**. I seguenti Op potrebbero non essere supportati da DFC:

- **Window Attention** (shifted window)
- Operazione **Roll**
- **Bias di posizione relativa**

Alternative se SwinV2 non è convertibile:
1. **wd-vit-tagger-v3** (Vision Transformer) — ViT è della stessa famiglia di CLIP
2. **wd-convnext-tagger-v3** (ConvNeXt) — Più facile da convertire in quanto CNN
3. **wd-eva02-large-tagger-v3** (EVA-02) — Modello grande (300MB+), attenzione alla memoria NPU

---

## Riferimenti

- [Documentazione Hailo Dataflow Compiler](https://hailo.ai/developer-zone/documentation/dataflow-compiler/)
- [Hailo Model Zoo](https://github.com/hailo-ai/hailo_model_zoo)
- [WD-Tagger Models (HuggingFace)](https://huggingface.co/SmilingWolf)
- [ONNX Simplifier](https://github.com/daquexian/onnx-simplifier)
