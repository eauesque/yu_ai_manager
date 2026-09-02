# Guía de conversión ONNX → HEF

**Propósito**: Convertir modelos ONNX como WD-Tagger al formato HEF de Hailo para habilitar la inferencia en la NPU Hailo-10H
**Entorno de ejecución**: Linux x86_64 (servidor AI) — El Hailo Dataflow Compiler solo funciona en x86
**Entorno de inferencia**: Raspberry Pi 5 + AI HAT 2 (Hailo-10H)

---

## Conocimiento previo

### Por qué es necesaria la conversión

| Elemento | ONNX Runtime (situación actual) | Hailo HEF (objetivo) |
|------|---------------------|-------------------|
| Destino de ejecución | CPU | NPU Hailo-10H (40 TOPS) |
| Cuantización | float32 | INT8 (uint8) |
| Velocidad de inferencia | ~500ms/imagen (CPU Pi5) | ~20ms/imagen (estimado, basado en rendimiento CLIP) |
| Memoria | ~200MB (carga del modelo) | ~Decenas de MB (HEF) |

### Resumen del pipeline de conversión

```
model.onnx (float32)
  |
  | [1] Parser del Model Zoo de Hailo (ONNX → HAR)
  v
model.har (Hailo Archive, float32)
  |
  | [2] Optimización (fusión de capas, disposición de memoria)
  v
model_optimized.har
  |
  | [3] Cuantización (float32 → INT8, usando imágenes de calibración)
  v
model_quantized.har
  |
  | [4] Compilación (conversión a instrucciones HW)
  v
model.hef (Hailo Executable Format)
```

---

## 1. Configuración del entorno en el servidor AI

### 1-1. Instalación del Hailo Dataflow Compiler

Descargar desde Hailo Developer Zone (https://hailo.ai/developer-zone/).
Se requiere registro de cuenta.

```bash
# Se recomienda Python 3.10 o 3.11 (posible falta de soporte para 3.12+)
python3 --version

# Crear venv
python3 -m venv ~/hailo_env
source ~/hailo_env/bin/activate

# Instalación del Hailo Dataflow Compiler (DFC)
# Especificar el .whl descargado desde Developer Zone
uv pip install hailo_dataflow_compiler-3.29.0-py3-none-linux_x86_64.whl

# Paquetes dependientes
uv pip install numpy pillow onnx onnxruntime
```

**Verificación**:
```bash
python -c "from hailo_sdk_client import ClientRunner; print('DFC OK')"
```

### 1-2. Hailo Model Zoo (opcional pero recomendado)

```bash
git clone https://github.com/hailo-ai/hailo_model_zoo.git ~/hailo_model_zoo
uv pip install -e ~/hailo_model_zoo
```

El Model Zoo contiene la configuración de conversión (YAML) de muchos modelos, lo que sirve de referencia.

---

## 2. Preparación del modelo objetivo

### 2-1. Modelos WD-Tagger

Modelos actualmente en uso:
- **Repositorio**: `SmilingWolf/wd-swinv2-tagger-v3` etc. en HuggingFace
- **Archivo**: `model.onnx` (~110MB, float32)
- **Entrada**: `(1, 448, 448, 3)` float32, BGR, sin normalización [0, 255]
- **Salida**: `(1, num_tags)` float32, probabilidades con sigmoid aplicado

```bash
# Descargar desde HuggingFace
mkdir -p ~/hailo_convert/wd_tagger
cd ~/hailo_convert/wd_tagger

# Obtener model.onnx y selected_tags.csv
wget https://huggingface.co/SmilingWolf/wd-swinv2-tagger-v3/resolve/main/model.onnx
wget https://huggingface.co/SmilingWolf/wd-swinv2-tagger-v3/resolve/main/selected_tags.csv
```

### 2-2. Verificar E/S del modelo ONNX

```python
import onnx

model = onnx.load("model.onnx")

print("=== Entradas ===")
for inp in model.graph.input:
    shape = [d.dim_value for d in inp.type.tensor_type.shape.dim]
    print(f"  {inp.name}: {shape}")

print("=== Salidas ===")
for out in model.graph.output:
    shape = [d.dim_value for d in out.type.tensor_type.shape.dim]
    print(f"  {out.name}: {shape}")
```

Anotar el shape y el nombre de E/S. Serán necesarios durante la conversión.

---

## 3. Preparación de imágenes de calibración

La cuantización INT8 requiere un conjunto representativo de imágenes (datos de calibración).
Se usan para determinar los parámetros de cuantización (scale/zero_point).

```bash
mkdir -p ~/hailo_convert/calibration_images
```

### Requisitos

- **Cantidad**: Aproximadamente 100〜1000 imágenes (más imágenes = mayor estabilidad de precisión, pero más tiempo)
- **Contenido**: Muestras representativas de las imágenes que se inferirán en la práctica (variaciones de imágenes generadas por IA)
- **Formato**: JPEG/PNG
- **Tamaño**: Cualquiera (el script de preprocesamiento redimensionará)

```bash
# Ejemplo de copia aleatoria de 500 imágenes desde la biblioteca de yu_ai_manager
# (transferir desde Pi al servidor AI con scp, etc.)
scp pi@raspberrypi:/path/to/images/*.png ~/hailo_convert/calibration_images/
```

### Script de preprocesamiento de calibración

Es necesario aplicar el mismo procesamiento que el preprocesamiento de WD-Tagger:

```python
# calibration_preprocess.py
"""Preprocesar imágenes de calibración en formato WD-Tagger."""
import numpy as np
from PIL import Image
from pathlib import Path

INPUT_SIZE = 448

def preprocess(image_path: str) -> np.ndarray:
    """Mismo preprocesamiento que engine_onnx.py de yu_ai_manager."""
    with Image.open(image_path) as raw:
        img = raw.convert("RGBA")

    # Composición sobre fondo blanco (soporte de transparencia)
    canvas = Image.new("RGBA", img.size, (255, 255, 255, 255))
    canvas.alpha_composite(img)
    img = canvas.convert("RGB")

    # Redimensionar manteniendo la relación de aspecto
    old_w, old_h = img.size
    scale = INPUT_SIZE / max(old_w, old_h)
    new_w = int(old_w * scale)
    new_h = int(old_h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)

    # Rellenar con blanco para forma cuadrada
    padded = Image.new("RGB", (INPUT_SIZE, INPUT_SIZE), (255, 255, 255))
    padded.paste(img, ((INPUT_SIZE - new_w) // 2, (INPUT_SIZE - new_h) // 2))

    # HWC, float32, RGB -> BGR
    arr = np.array(padded, dtype=np.float32)
    arr = arr[:, :, ::-1]  # RGB -> BGR

    return arr  # (448, 448, 3)


def load_calibration_set(image_dir: str, max_images: int = 500) -> np.ndarray:
    """Devuelve imágenes de calibración como tensor de lote."""
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

## 4. Ejecución de la conversión HEF

### 4-1. Script de conversión

```python
# convert_wd_tagger.py
"""Script de conversión WD-Tagger ONNX → Hailo HEF."""
from hailo_sdk_client import ClientRunner
import numpy as np

# ========== Configuración ==========
ONNX_PATH = "model.onnx"
MODEL_NAME = "wd_swinv2_tagger_v3"
CALIBRATION_NPY = "calibration_data.npy"
HW_ARCH = "hailo10h"  # Para Hailo-10H
# ==========================

# --- Paso 1: Análisis ONNX → HAR ---
print("[1/4] Parsing ONNX model...")
runner = ClientRunner(hw_arch=HW_ARCH)

# start_node / end_node son los nombres de los nodos de E/S del modelo
# (especificar los nombres confirmados en el Paso 2-2)
hn, npz = runner.translate_onnx_model(
    ONNX_PATH,
    MODEL_NAME,
    # net_input_shapes={"input": [1, 448, 448, 3]},  # Especificar si es necesario
)
print(f"  Parsed: {len(npz)} layers")

# --- Paso 2: Optimización del modelo ---
print("[2/4] Optimizing model...")
runner.optimize(npz)

# --- Paso 3: Cuantización INT8 ---
print("[3/4] Quantizing (INT8)...")
calib_data = np.load(CALIBRATION_NPY)
print(f"  Calibration set: {calib_data.shape}")

runner.quantize(calib_data)

# --- Paso 4: Compilación → HEF ---
print("[4/4] Compiling to HEF...")
hef = runner.compile()

hef_path = f"{MODEL_NAME}.hef"
with open(hef_path, "wb") as f:
    f.write(hef)
print(f"Done: {hef_path} ({len(hef) / 1024 / 1024:.1f} MB)")

# También guardar HAR (archivo intermedio) para depuración
har_path = f"{MODEL_NAME}.har"
runner.save_har(har_path)
print(f"HAR saved: {har_path}")
```

### 4-2. Ejecución

```bash
source ~/hailo_env/bin/activate
cd ~/hailo_convert/wd_tagger

# Preprocesamiento de imágenes de calibración
python calibration_preprocess.py

# Conversión HEF
python convert_wd_tagger.py
```

**Tiempo estimado**: Depende del tamaño del modelo y el número de imágenes de calibración, pero puede tomar decenas de minutos a varias horas.

### 4-3. Errores comunes y soluciones

| Error | Causa | Solución |
|--------|------|------|
| `UnsupportedOp: <op_name>` | Operador ONNX no compatible con DFC | Verificar la lista de operadores compatibles de Hailo. Eliminar los ops no compatibles con modificación del modelo u `onnx-simplifier` |
| `Shape mismatch` | Shape de entrada dinámico | Especificar shape fijo con `net_input_shapes` |
| `Quantization error` / degradación de precisión | Datos de calibración inadecuados | Aumentar el número de imágenes, usar las imágenes de operación real |
| `Memory allocation failed` | Modelo demasiado grande para la memoria de la NPU | Fijar batch_size=1, o considerar un modelo más ligero |
| `hailo_sdk_client not found` | DFC no instalado | Verificar el Paso 1-1 |

### 4-4. (Recomendado) Preprocesamiento con onnx-simplifier

Simplificar el modelo ONNX antes de la conversión aumenta la tasa de éxito:

```bash
uv pip install onnx-simplifier
python -m onnxsim model.onnx model_simplified.onnx
```

---

## 5. Verificación después de la conversión (en el servidor AI)

### 5-1. Verificación de precisión con el emulador Hailo

Se puede verificar la precisión del modelo convertido a HEF sin hardware real:

```python
# verify_hef.py
"""Comparar la salida del HEF con la salida ONNX para verificar la degradación de precisión."""
import numpy as np
import onnxruntime as ort

# Inferencia ONNX (float32, valor de referencia)
sess = ort.InferenceSession("model.onnx")
test_image = np.load("calibration_data.npy")[0:1]  # Tomar 1 imagen
input_name = sess.get_inputs()[0].name
onnx_output = sess.run(None, {input_name: test_image})[0][0]

# Inferencia del emulador HEF
from hailo_sdk_client import ClientRunner

runner = ClientRunner(har="wd_swinv2_tagger_v3.har")
hef_output = runner.infer(test_image)[0]

# Comparación
diff = np.abs(onnx_output - hef_output)
print(f"Max diff:  {diff.max():.6f}")
print(f"Mean diff: {diff.mean():.6f}")
print(f"Cosine similarity: {np.dot(onnx_output, hef_output) / (np.linalg.norm(onnx_output) * np.linalg.norm(hef_output)):.6f}")

# Tasa de coincidencia de etiquetas (coincidencia con umbral 0.35)
threshold = 0.35
onnx_tags = set(np.where(onnx_output > threshold)[0])
hef_tags = set(np.where(hef_output > threshold)[0])
overlap = len(onnx_tags & hef_tags)
print(f"Tag match: {overlap}/{len(onnx_tags)} ({overlap/max(len(onnx_tags),1)*100:.1f}%)")
```

**Criterios de evaluación**:
- Similitud coseno > 0.95: Bueno
- Tasa de coincidencia de etiquetas > 90%: Nivel práctico
- Tasa de coincidencia de etiquetas < 80%: Necesario revisar los datos de calibración

---

## 6. Transferencia al Pi y prueba en hardware real

### 6-1. Transferencia del archivo HEF

```bash
scp ~/hailo_convert/wd_tagger/wd_swinv2_tagger_v3.hef pi@raspberrypi:~/hailo_models/
```

### 6-2. Prueba de inferencia en hardware real

```python
# test_wd_tagger_hef.py (ejecutar en Pi5)
"""Prueba de inferencia en hardware real del WD-Tagger convertido a HEF."""
import numpy as np
from hailo_platform import VDevice
from PIL import Image
import time

HEF_PATH = "~/.hailo_models/wd_swinv2_tagger_v3.hef"
INPUT_SIZE = 448

def preprocess(image_path: str) -> np.ndarray:
    """Mismo preprocesamiento que engine_onnx.py (pero con salida uint8)."""
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

# Imagen de prueba
test_img = preprocess("/path/to/test/image.png")

with VDevice() as vdevice:
    infer_model = vdevice.create_infer_model(HEF_PATH)
    configured = infer_model.configure()
    bindings = configured.create_bindings()

    # Entrada
    bindings.input().set_buffer(test_img)

    # Buffer de salida (uint8)
    out_info = infer_model.outputs[0]
    output_buf = np.empty(out_info.shape, dtype=np.uint8)
    bindings.output().set_buffer(output_buf)

    # Inferencia
    t0 = time.perf_counter()
    configured.run([bindings], timeout=10000)
    elapsed = (time.perf_counter() - t0) * 1000

    print(f"Inference: {elapsed:.1f} ms")
    print(f"Output shape: {output_buf.shape}")
    print(f"Output range: [{output_buf.min()}, {output_buf.max()}]")

    # Descuantización
    try:
        qi = out_info.quant_infos[0]
        scale = qi.qp_scale
        zp = qi.qp_zp
    except Exception:
        scale, zp = 1.0 / 255.0, 0.0

    probs = (output_buf.astype(np.float32) - zp) * scale
    print(f"Dequantized range: [{probs.min():.4f}, {probs.max():.4f}]")
```

### 6-3. Comparación de precisión (ONNX vs HEF)

Inferir la misma imagen con ONNX Runtime y Hailo HEF y comparar las salidas de etiquetas:

```bash
# Ejecutar en Pi
python test_wd_tagger_hef.py
python -c "
from extensions.builtin_wd_tagger.core_impl.engine_onnx import OnnxWdTaggerEngine
e = OnnxWdTaggerEngine(Path('cache/wd_tagger/...'))
r = e.tag_image('/path/to/test/image.png')
for t in r.tags[:20]: print(f'{t.tag}: {t.confidence}')
"
```

---

## 7. Problemas conocidos

### Posibilidad de conversión de la arquitectura SwinV2

WD-Tagger v3 está basado en **Swin Transformer V2**. Los siguientes ops pueden no ser compatibles con DFC:

- **Window Attention** (ventana desplazada)
- Operación **Roll**
- **Sesgo de posición relativa**

Alternativas si SwinV2 no puede convertirse:
1. **wd-vit-tagger-v3** (basado en Vision Transformer) — ViT es de la misma familia que CLIP y hay precedentes de conversión con Hailo
2. **wd-convnext-tagger-v3** (basado en ConvNeXt) — Serie CNN, más fácil de convertir
3. **wd-eva02-large-tagger-v3** (basado en EVA-02) — El modelo es grande (300MB+), precaución con la memoria de la NPU

### Diferencias de preprocesamiento

- **Versión ONNX**: Entrada float32 (rango 0-255, sin normalización)
- **Versión HEF**: Entrada uint8 (la normalización se realiza dentro del HEF)

Al convertir a HEF, puede ocurrir que el preprocesamiento quede incorporado en el HEF.
Verificar el manejo del preprocesamiento al ejecutar `translate_onnx_model()` de DFC.

### Parámetros de descuantización

La salida es cuantizada como uint8. Para restaurar correctamente las probabilidades de etiquetas (0.0-1.0),
es indispensable la descuantización usando los parámetros de cuantización del HEF (scale/zero_point).
Consultar el precedente de CLIP (`extensions/builtin_hailo_semantic_search/core_impl/dequantize.py`).

---

## 8. Plantilla de instrucciones para Claude

Ejemplo de prompt para solicitar a Claude que realice el trabajo de conversión en el servidor AI:

```
Por favor realice la conversión del modelo ONNX de WD-Tagger a Hailo HEF siguiendo estos pasos.

1. Activar ~/hailo_env
2. Descargar model.onnx a ~/hailo_convert/wd_tagger/
3. Crear datos de calibración con las imágenes de muestra preparadas en calibration_images/
4. Ejecutar convert_wd_tagger.py para convertir a HEF
5. Ejecutar verify_hef.py para comparar la precisión con ONNX
6. Por favor informe los resultados

Si la conversión falla:
- Reportar el mensaje de error
- Intentar con onnx-simplifier
- Si SwinV2 no es compatible, reintentar con wd-vit-tagger-v3

Modelo objetivo: SmilingWolf/wd-swinv2-tagger-v3
Hardware objetivo: hailo10h
```

---

## Referencias

- [Documentación de Hailo Dataflow Compiler](https://hailo.ai/developer-zone/documentation/dataflow-compiler/)
- [Hailo Model Zoo](https://github.com/hailo-ai/hailo_model_zoo)
- [Modelos WD-Tagger (HuggingFace)](https://huggingface.co/SmilingWolf)
- [ONNX Simplifier](https://github.com/daquexian/onnx-simplifier)
