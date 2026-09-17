# Guide de conversion ONNX → HEF

**Objectif** : Convertir des modèles ONNX comme WD-Tagger au format Hailo HEF pour permettre l'inférence sur Hailo-10H NPU
**Environnement d'exécution** : x86_64 Linux (serveur AI) — Hailo Dataflow Compiler supporte uniquement x86
**Environnement d'inférence** : Raspberry Pi 5 + AI HAT 2 (Hailo-10H)

---

## Connaissances préalables

### Pourquoi la conversion est nécessaire

| Élément | ONNX Runtime (état actuel) | Hailo HEF (objectif) |
|------|---------------------|-------------------|
| Exécution | CPU | Hailo-10H NPU (40 TOPS) |
| Quantification | float32 | INT8 (uint8) |
| Vitesse d'inférence | ~500ms/image (Pi5 CPU) | ~20ms/image (estimé, basé sur les résultats CLIP) |
| Mémoire | ~200MB (chargement du modèle) | ~quelques dizaines MB (HEF) |

### Vue d'ensemble du pipeline de conversion

```
model.onnx (float32)
  |
  | [1] Parser Hailo Model Zoo (ONNX → HAR)
  v
model.har (Hailo Archive, float32)
  |
  | [2] Optimisation (fusion de couches, placement mémoire)
  v
model_optimized.har
  |
  | [3] Quantification (float32 → INT8, avec images de calibration)
  v
model_quantized.har
  |
  | [4] Compilation (conversion en instructions HW)
  v
model.hef (Hailo Executable Format)
```

---

## 1. Configuration de l'environnement serveur AI

### 1-1. Installation du Hailo Dataflow Compiler

Télécharger depuis la Hailo Developer Zone (https://hailo.ai/developer-zone/).
Inscription requise.

```bash
# Python 3.10 ou 3.11 recommandé
python3 --version

# Créer l'environnement virtuel
python3 -m venv ~/hailo_env
source ~/hailo_env/bin/activate

# Installer DFC (spécifier le .whl téléchargé)
uv pip install hailo_dataflow_compiler-3.29.0-py3-none-linux_x86_64.whl

# Paquets de dépendances
uv pip install numpy pillow onnx onnxruntime
```

**Vérification** :
```bash
python -c "from hailo_sdk_client import ClientRunner; print('DFC OK')"
```

### 1-2. Hailo Model Zoo (optionnel mais recommandé)

```bash
git clone https://github.com/hailo-ai/hailo_model_zoo.git ~/hailo_model_zoo
uv pip install -e ~/hailo_model_zoo
```

---

## 2. Préparation du modèle cible

### 2-1. Modèle WD-Tagger

Modèles actuellement utilisés :
- **Dépôt** : `SmilingWolf/wd-swinv2-tagger-v3`, etc. sur HuggingFace
- **Fichier** : `model.onnx` (~110MB, float32)
- **Entrée** : `(1, 448, 448, 3)` float32, BGR, sans normalisation [0, 255]
- **Sortie** : `(1, num_tags)` float32, probabilités après sigmoid

```bash
mkdir -p ~/hailo_convert/wd_tagger
cd ~/hailo_convert/wd_tagger

wget https://huggingface.co/SmilingWolf/wd-swinv2-tagger-v3/resolve/main/model.onnx
wget https://huggingface.co/SmilingWolf/wd-swinv2-tagger-v3/resolve/main/selected_tags.csv
```

### 2-2. Vérification des entrées/sorties du modèle ONNX

```python
import onnx

model = onnx.load("model.onnx")

print("=== Entrées ===")
for inp in model.graph.input:
    shape = [d.dim_value for d in inp.type.tensor_type.shape.dim]
    print(f"  {inp.name}: {shape}")

print("=== Sorties ===")
for out in model.graph.output:
    shape = [d.dim_value for d in out.type.tensor_type.shape.dim]
    print(f"  {out.name}: {shape}")
```

---

## 3. Préparation des images de calibration

La quantification INT8 nécessite un ensemble d'images représentatives (données de calibration).

```bash
mkdir -p ~/hailo_convert/calibration_images
```

### Exigences

- **Quantité** : 100~1000 images environ (plus il y en a, plus la précision est stable)
- **Contenu** : Échantillon représentatif des images qui seront inférées
- **Format** : JPEG/PNG

### Script de pré-traitement de calibration

```python
# calibration_preprocess.py
import numpy as np
from PIL import Image
from pathlib import Path

INPUT_SIZE = 448

def preprocess(image_path: str) -> np.ndarray:
    """Même pré-traitement que engine_onnx.py de yu_ai_manager."""
    with Image.open(image_path) as raw:
        img = raw.convert("RGBA")

    # Composite sur fond blanc (gestion de la transparence)
    canvas = Image.new("RGBA", img.size, (255, 255, 255, 255))
    canvas.alpha_composite(img)
    img = canvas.convert("RGB")

    # Redimensionnement en conservant le ratio d'aspect
    old_w, old_h = img.size
    scale = INPUT_SIZE / max(old_w, old_h)
    new_w = int(old_w * scale)
    new_h = int(old_h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)

    # Padding blanc pour obtenir un carré
    padded = Image.new("RGB", (INPUT_SIZE, INPUT_SIZE), (255, 255, 255))
    padded.paste(img, ((INPUT_SIZE - new_w) // 2, (INPUT_SIZE - new_h) // 2))

    # HWC, float32, RGB -> BGR
    arr = np.array(padded, dtype=np.float32)
    arr = arr[:, :, ::-1]  # RGB -> BGR

    return arr  # (448, 448, 3)
```

---

## 4. Exécution de la conversion HEF

### 4-1. Script de conversion

```python
# convert_wd_tagger.py
from hailo_sdk_client import ClientRunner
import numpy as np

ONNX_PATH = "model.onnx"
MODEL_NAME = "wd_swinv2_tagger_v3"
CALIBRATION_NPY = "calibration_data.npy"
HW_ARCH = "hailo10h"

# --- Étape 1: Parse ONNX → HAR ---
print("[1/4] Parsing ONNX model...")
runner = ClientRunner(hw_arch=HW_ARCH)
hn, npz = runner.translate_onnx_model(ONNX_PATH, MODEL_NAME)
print(f"  Parsed: {len(npz)} layers")

# --- Étape 2: Optimisation du modèle ---
print("[2/4] Optimizing model...")
runner.optimize(npz)

# --- Étape 3: Quantification INT8 ---
print("[3/4] Quantizing (INT8)...")
calib_data = np.load(CALIBRATION_NPY)
runner.quantize(calib_data)

# --- Étape 4: Compilation → HEF ---
print("[4/4] Compiling to HEF...")
hef = runner.compile()

hef_path = f"{MODEL_NAME}.hef"
with open(hef_path, "wb") as f:
    f.write(hef)
print(f"Done: {hef_path} ({len(hef) / 1024 / 1024:.1f} MB)")
```

### 4-2. Erreurs courantes et solutions

| Erreur | Cause | Solution |
|--------|------|------|
| `UnsupportedOp: <op_name>` | Opérateur ONNX non supporté par DFC | Vérifier la liste des opérateurs supportés Hailo |
| `Shape mismatch` | Shape d'entrée dynamique | Spécifier une shape fixe avec `net_input_shapes` |
| `Quantization error` / dégradation de précision | Données de calibration inappropriées | Augmenter le nombre d'images, utiliser des images représentatives |
| `Memory allocation failed` | Modèle trop grand pour la mémoire NPU | Fixer batch_size=1 ou envisager un modèle plus léger |

### 4-3. (Recommandé) Pré-traitement avec onnx-simplifier

```bash
uv pip install onnx-simplifier
python -m onnxsim model.onnx model_simplified.onnx
```

---

## 5. Vérification après conversion (sur serveur AI)

### 5-1. Vérification de la précision avec l'émulateur Hailo

```python
# verify_hef.py
import numpy as np
import onnxruntime as ort

# Inférence ONNX (float32, valeur de référence)
sess = ort.InferenceSession("model.onnx")
test_image = np.load("calibration_data.npy")[0:1]
input_name = sess.get_inputs()[0].name
onnx_output = sess.run(None, {input_name: test_image})[0][0]

# Inférence émulateur HEF
from hailo_sdk_client import ClientRunner

runner = ClientRunner(har="wd_swinv2_tagger_v3.har")
hef_output = runner.infer(test_image)[0]

# Comparaison
diff = np.abs(onnx_output - hef_output)
print(f"Max diff:  {diff.max():.6f}")
print(f"Mean diff: {diff.mean():.6f}")
print(f"Cosine similarity: {np.dot(onnx_output, hef_output) / (np.linalg.norm(onnx_output) * np.linalg.norm(hef_output)):.6f}")
```

**Critères d'évaluation** :
- Similarité cosinus > 0.95 : Bon
- Taux de correspondance des tags > 90% : Niveau utilisable
- Taux de correspondance des tags < 80% : Révision des données de calibration nécessaire

---

## 6. Transfert vers Pi et test sur machine réelle

### 6-1. Transfert du fichier HEF

```bash
scp ~/hailo_convert/wd_tagger/wd_swinv2_tagger_v3.hef pi@raspberrypi:~/hailo_models/
```

---

## 7. Préoccupations connues

### Convertibilité de l'architecture SwinV2

WD-Tagger v3 est basé sur **Swin Transformer V2**. Les opérateurs suivants peuvent ne pas être supportés par DFC :

- **Window Attention** (shifted window)
- Opération **Roll**
- **Biais de position relative**

Alternatives si SwinV2 ne peut pas être converti :
1. **wd-vit-tagger-v3** (basé sur Vision Transformer) — ViT de la même famille que CLIP avec des précédents de conversion Hailo
2. **wd-convnext-tagger-v3** (basé sur ConvNeXt) — Type CNN plus facile à convertir
3. **wd-eva02-large-tagger-v3** (basé sur EVA-02) — Modèle volumineux (300MB+), attention à la mémoire NPU

---

## Références

- [Documentation Hailo Dataflow Compiler](https://hailo.ai/developer-zone/documentation/dataflow-compiler/)
- [Hailo Model Zoo](https://github.com/hailo-ai/hailo_model_zoo)
- [Modèles WD-Tagger (HuggingFace)](https://huggingface.co/SmilingWolf)
- [ONNX Simplifier](https://github.com/daquexian/onnx-simplifier)
