# ONNX → HEF Konvertierungsanleitung

**Zweck**: ONNX-Modelle wie WD-Tagger in das Hailo-HEF-Format konvertieren und auf Hailo-10H NPU inferenzfähig machen
**Ausführungsumgebung**: x86_64 Linux (KI-Server) — Hailo Dataflow Compiler unterstützt nur x86
**Inferenzumgebung**: Raspberry Pi 5 + AI HAT 2 (Hailo-10H)

---

## Voraussetzungen

### Warum Konvertierung notwendig ist

| Element | ONNX Runtime (aktuell) | Hailo HEF (Ziel) |
|------|---------------------|-------------------|
| Ausführungsort | CPU | Hailo-10H NPU (40 TOPS) |
| Quantisierung | float32 | INT8 (uint8) |
| Inferenzgeschwindigkeit | ~500ms/Bild (Pi5 CPU) | ~20ms/Bild (geschätzt, basierend auf CLIP-Erfahrung) |
| Speicher | ~200MB (Modell-Load) | ~Dutzende MB (HEF) |

### Konvertierungspipeline-Überblick

```
model.onnx (float32)
  |
  | [1] Hailo Model Zoo Parser (ONNX → HAR)
  v
model.har (Hailo Archive, float32)
  |
  | [2] Optimierung (Layer-Fusion, Speicherlayout)
  v
model_optimized.har
  |
  | [3] Quantisierung (float32 → INT8, Kalibrierungsbilder verwenden)
  v
model_quantized.har
  |
  | [4] Kompilierung (zu HW-Befehlen konvertieren)
  v
model.hef (Hailo Executable Format)
```

---

## 1. KI-Server-Umgebungsaufbau

### 1-1. Hailo Dataflow Compiler installieren

Download von der Hailo Developer Zone (https://hailo.ai/developer-zone/).
Kontoanmeldung erforderlich.

```bash
# Python 3.10 oder 3.11 empfohlen (3.12+ möglicherweise nicht unterstützt)
python3 --version

# venv erstellen
python3 -m venv ~/hailo_env
source ~/hailo_env/bin/activate

# Hailo Dataflow Compiler (DFC) installieren
# Heruntergeladene .whl von Developer Zone angeben
uv pip install hailo_dataflow_compiler-3.29.0-py3-none-linux_x86_64.whl

# Abhängigkeitspakete
uv pip install numpy pillow onnx onnxruntime
```

**Überprüfung**:
```bash
python -c "from hailo_sdk_client import ClientRunner; print('DFC OK')"
```

### 1-2. Hailo Model Zoo (optional, empfohlen)

```bash
git clone https://github.com/hailo-ai/hailo_model_zoo.git ~/hailo_model_zoo
uv pip install -e ~/hailo_model_zoo
```

Der Model Zoo enthält Konvertierungskonfigurationen (YAML) für viele Modelle und dient als Referenz.

---

## 2. Zielmodell vorbereiten

### 2-1. WD-Tagger-Modell

Aktuell verwendete Modelle:
- **Repository**: HuggingFace `SmilingWolf/wd-swinv2-tagger-v3` usw.
- **Datei**: `model.onnx` (~110MB, float32)
- **Eingabe**: `(1, 448, 448, 3)` float32, BGR, keine [0, 255]-Normalisierung
- **Ausgabe**: `(1, num_tags)` float32, Sigmoid-Wahrscheinlichkeiten

```bash
# Von HuggingFace herunterladen
mkdir -p ~/hailo_convert/wd_tagger
cd ~/hailo_convert/wd_tagger

# model.onnx und selected_tags.csv abrufen
wget https://huggingface.co/SmilingWolf/wd-swinv2-tagger-v3/resolve/main/model.onnx
wget https://huggingface.co/SmilingWolf/wd-swinv2-tagger-v3/resolve/main/selected_tags.csv
```

### 2-2. ONNX-Modell-Eingabe/-Ausgabe prüfen

```python
import onnx

model = onnx.load("model.onnx")

print("=== Eingabe ===")
for inp in model.graph.input:
    shape = [d.dim_value for d in inp.type.tensor_type.shape.dim]
    print(f"  {inp.name}: {shape}")

print("=== Ausgabe ===")
for out in model.graph.output:
    shape = [d.dim_value for d in out.type.tensor_type.shape.dim]
    print(f"  {out.name}: {shape}")
```

Eingabe-/Ausgabe-Shape und -Namen für spätere Konvertierung notieren.

---

## 3. Kalibrierungsbilder vorbereiten

Für INT8-Quantisierung wird ein repräsentativer Bildsatz (Kalibrierungsdaten) benötigt.

```bash
mkdir -p ~/hailo_convert/calibration_images
```

### Anforderungen

- **Anzahl**: Ca. 100–1000 Bilder (mehr = stabilere Genauigkeit, aber mehr Zeit)
- **Inhalt**: Repräsentative Stichproben der tatsächlich zu inferenzierenden Bilder
- **Format**: JPEG/PNG
- **Größe**: Beliebig (wird im Vorverarbeitungsskript skaliert)

### Kalibrierungs-Vorverarbeitungsskript

WD-Tagger dieselbe Vorverarbeitung wie in `engine_onnx.py` anwenden:

```python
# calibration_preprocess.py
"""Kalibrierungsbilder im WD-Tagger-Format vorverarbeiten."""
import numpy as np
from PIL import Image
from pathlib import Path

INPUT_SIZE = 448

def preprocess(image_path: str) -> np.ndarray:
    """Gleiche Vorverarbeitung wie engine_onnx.py in yu_ai_manager."""
    with Image.open(image_path) as raw:
        img = raw.convert("RGBA")

    # Auf weißem Hintergrund zusammensetzen (Transparenz-Unterstützung)
    canvas = Image.new("RGBA", img.size, (255, 255, 255, 255))
    canvas.alpha_composite(img)
    img = canvas.convert("RGB")

    # Mit Seitenverhältnis skalieren
    old_w, old_h = img.size
    scale = INPUT_SIZE / max(old_w, old_h)
    new_w = int(old_w * scale)
    new_h = int(old_h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)

    # Mit weißem Padding zu Quadrat
    padded = Image.new("RGB", (INPUT_SIZE, INPUT_SIZE), (255, 255, 255))
    padded.paste(img, ((INPUT_SIZE - new_w) // 2, (INPUT_SIZE - new_h) // 2))

    # HWC, float32, RGB -> BGR
    arr = np.array(padded, dtype=np.float32)
    arr = arr[:, :, ::-1]  # RGB -> BGR

    return arr  # (448, 448, 3)


def load_calibration_set(image_dir: str, max_images: int = 500) -> np.ndarray:
    """Kalibrierungsbilder als Batch-Tensor zurückgeben."""
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

## 4. HEF-Konvertierung ausführen

### 4-1. Konvertierungsskript

```python
# convert_wd_tagger.py
"""WD-Tagger ONNX → Hailo HEF Konvertierungsskript."""
from hailo_sdk_client import ClientRunner
import numpy as np

# ========== Konfiguration ==========
ONNX_PATH = "model.onnx"
MODEL_NAME = "wd_swinv2_tagger_v3"
CALIBRATION_NPY = "calibration_data.npy"
HW_ARCH = "hailo10h"  # Für Hailo-10H
# ===================================

# --- Schritt 1: ONNX parsen → HAR ---
print("[1/4] ONNX-Modell parsen...")
runner = ClientRunner(hw_arch=HW_ARCH)

hn, npz = runner.translate_onnx_model(
    ONNX_PATH,
    MODEL_NAME,
)
print(f"  Geparst: {len(npz)} Layer")

# --- Schritt 2: Modell optimieren ---
print("[2/4] Modell optimieren...")
runner.optimize(npz)

# --- Schritt 3: INT8-Quantisierung ---
print("[3/4] Quantisieren (INT8)...")
calib_data = np.load(CALIBRATION_NPY)
print(f"  Kalibrierungssatz: {calib_data.shape}")

runner.quantize(calib_data)

# --- Schritt 4: Kompilieren → HEF ---
print("[4/4] Zu HEF kompilieren...")
hef = runner.compile()

hef_path = f"{MODEL_NAME}.hef"
with open(hef_path, "wb") as f:
    f.write(hef)
print(f"Fertig: {hef_path} ({len(hef) / 1024 / 1024:.1f} MB)")

# HAR (Zwischendatei) auch speichern (für Debugging)
har_path = f"{MODEL_NAME}.har"
runner.save_har(har_path)
print(f"HAR gespeichert: {har_path}")
```

### 4-2. Ausführung

```bash
source ~/hailo_env/bin/activate
cd ~/hailo_convert/wd_tagger

# Kalibrierungsbilder vorverarbeiten
python calibration_preprocess.py

# HEF-Konvertierung
python convert_wd_tagger.py
```

**Zeitabschätzung**: Je nach Modellgröße und Kalibrierungsbildanzahl Dutzende Minuten bis mehrere Stunden.

### 4-3. Häufige Fehler und Lösungen

| Fehler | Ursache | Lösung |
|--------|------|------|
| `UnsupportedOp: <op_name>` | ONNX-Operator von DFC nicht unterstützt | Hailo-Operator-Liste prüfen. Nicht unterstützte Ops durch Modellmodifikation oder onnx-simplifier entfernen |
| `Shape mismatch` | Dynamische Eingabe-Shape | `net_input_shapes` mit fester Shape explizit angeben |
| `Quantization error` / Genauigkeitsverlust | Ungeeignete Kalibrierungsdaten | Bildanzahl erhöhen, tatsächliche Betriebsbilder verwenden |
| `Memory allocation failed` | Modell zu groß für NPU-Speicher | Batch-Size auf 1 fixieren oder leichteres Modell erwägen |
| `hailo_sdk_client not found` | DFC nicht installiert | Schritt 1-1 prüfen |

### 4-4. (Empfohlen) Vorverarbeitung mit onnx-simplifier

Vor der Konvertierung das ONNX-Modell vereinfachen erhöht die Erfolgsrate:

```bash
uv pip install onnx-simplifier
python -m onnxsim model.onnx model_simplified.onnx
```

---

## 5. Verifizierung nach der Konvertierung (auf KI-Server)

### 5-1. Genauigkeitsverifizierung mit Hailo-Emulator

Die Genauigkeit des zu HEF konvertierten Modells kann ohne echte Hardware verifiziert werden:

```python
# verify_hef.py
"""HEF-Ausgabe mit ONNX-Ausgabe zum Genauigkeitsverlust vergleichen."""
import numpy as np
import onnxruntime as ort

# ONNX-Inferenz (float32, Referenz)
sess = ort.InferenceSession("model.onnx")
test_image = np.load("calibration_data.npy")[0:1]  # 1 Bild entnehmen
input_name = sess.get_inputs()[0].name
onnx_output = sess.run(None, {input_name: test_image})[0][0]

# HEF-Emulator-Inferenz
from hailo_sdk_client import ClientRunner

runner = ClientRunner(har="wd_swinv2_tagger_v3.har")
hef_output = runner.infer(test_image)[0]

# Vergleich
diff = np.abs(onnx_output - hef_output)
print(f"Max diff:  {diff.max():.6f}")
print(f"Mean diff: {diff.mean():.6f}")
print(f"Cosine similarity: {np.dot(onnx_output, hef_output) / (np.linalg.norm(onnx_output) * np.linalg.norm(hef_output)):.6f}")

# Tag-Übereinstimmungsrate (Schwellenwert 0,35)
threshold = 0.35
onnx_tags = set(np.where(onnx_output > threshold)[0])
hef_tags = set(np.where(hef_output > threshold)[0])
overlap = len(onnx_tags & hef_tags)
print(f"Tag match: {overlap}/{len(onnx_tags)} ({overlap/max(len(onnx_tags),1)*100:.1f}%)")
```

**Bewertungskriterien**:
- Kosinus-Ähnlichkeit > 0,95: Gut
- Tag-Übereinstimmungsrate > 90%: Praxistauglich
- Tag-Übereinstimmungsrate < 80%: Kalibrierungsdaten überarbeiten

---

## 6. Übertragung auf Pi und Praxistests

### 6-1. HEF-Datei übertragen

```bash
scp ~/hailo_convert/wd_tagger/wd_swinv2_tagger_v3.hef pi@raspberrypi:~/hailo_models/
```

### 6-2. Praxis-Inferenztest

```python
# test_wd_tagger_hef.py (auf Pi5 ausführen)
"""Praxis-Inferenztest für HEF-konvertiertes WD-Tagger."""
import numpy as np
from hailo_platform import VDevice
from PIL import Image
import time

HEF_PATH = "~/.hailo_models/wd_swinv2_tagger_v3.hef"
INPUT_SIZE = 448

def preprocess(image_path: str) -> np.ndarray:
    """Gleiche Vorverarbeitung wie engine_onnx.py (aber uint8-Ausgabe)."""
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

test_img = preprocess("/path/to/test/image.png")

with VDevice() as vdevice:
    infer_model = vdevice.create_infer_model(HEF_PATH)
    configured = infer_model.configure()
    bindings = configured.create_bindings()

    bindings.input().set_buffer(test_img)

    out_info = infer_model.outputs[0]
    output_buf = np.empty(out_info.shape, dtype=np.uint8)
    bindings.output().set_buffer(output_buf)

    t0 = time.perf_counter()
    configured.run([bindings], timeout=10000)
    elapsed = (time.perf_counter() - t0) * 1000

    print(f"Inference: {elapsed:.1f} ms")
    print(f"Output shape: {output_buf.shape}")

    # Dequantisierung
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

## 7. Bekannte Bedenken

### SwinV2-Architektur-Konvertierbarkeit

WD-Tagger v3 basiert auf **Swin Transformer V2**. Folgende Ops könnten von DFC nicht unterstützt werden:
- **Window Attention** (verschobenes Fenster)
- **Roll**-Operation
- **Relative Positions-Bias**

Alternativen bei nicht konvertierbarem SwinV2:
1. **wd-vit-tagger-v3** (Vision Transformer) — ViT ist mit CLIP verwandt, Hailo-Konvertierungserfahrung vorhanden
2. **wd-convnext-tagger-v3** (ConvNeXt) — CNN-basiert, leichter konvertierbar
3. **wd-eva02-large-tagger-v3** (EVA-02) — Großes Modell (300MB+), NPU-Speicher beachten

### Vorverarbeitungsunterschiede

- **ONNX-Version**: float32-Eingabe (Bereich 0-255, keine Normalisierung)
- **HEF-Version**: uint8-Eingabe (Normalisierung intern in HEF)

### Dequantisierungsparameter

Ausgabe wird uint8-quantisiert. Für korrekte Wiederherstellung der Tag-Wahrscheinlichkeiten (0.0-1.0) sind die HEF-Quantisierungsparameter (scale/zero_point) zur Dequantisierung erforderlich.

---

## 8. Claude-Anweisungsvorlage

Beispiel-Prompt für die Beauftragung von Claude mit der Konvertierung:

```
Bitte konvertieren Sie das WD-Tagger ONNX-Modell zu Hailo HEF mit folgenden Schritten:

1. ~/hailo_env aktivieren
2. model.onnx nach ~/hailo_convert/wd_tagger/ herunterladen
3. Kalibrierungsdaten mit vorbereiteten Stichprobenbildern in calibration_images/ erstellen
4. convert_wd_tagger.py ausführen und in HEF konvertieren
5. Genauigkeitsvergleich mit ONNX über verify_hef.py durchführen
6. Ergebnisse berichten

Bei Konvertierungsfehler:
- Fehlermeldung berichten
- onnx-simplifier versuchen
- Bei nicht unterstütztem SwinV2 mit wd-vit-tagger-v3 erneut versuchen

Zielmodell: SmilingWolf/wd-swinv2-tagger-v3
Ziel-HW: hailo10h
```

---

## Referenz-Links

- [Hailo Dataflow Compiler Dokumentation](https://hailo.ai/developer-zone/documentation/dataflow-compiler/)
- [Hailo Model Zoo](https://github.com/hailo-ai/hailo_model_zoo)
- [WD-Tagger Modelle (HuggingFace)](https://huggingface.co/SmilingWolf)
- [ONNX Simplifier](https://github.com/daquexian/onnx-simplifier)
