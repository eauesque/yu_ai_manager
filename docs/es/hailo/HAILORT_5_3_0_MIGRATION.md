# Notas de migración de HailoRT 5.2.0 → 5.3.0

Conocimientos adquiridos de la actualización de HailoRT 5.2.0 a 5.3.0 en Raspberry Pi 5 + AI HAT 2 (Hailo-10H). Basado en pruebas de implementación de extremo a extremo y análisis directo de git diff entre las etiquetas oficiales `v5.2.0` / `v5.3.0`.

**Audiencia objetivo**: Desarrolladores que ejecutan inferencia en la NPU Hailo-10H usando Python (`pyhailort`).

---

## TL;DR

- **Básicamente cero cambios disruptivos para aplicaciones típicas de inferencia Python**.
  Las cifras principales (688 archivos modificados, +12,035 / −8,987 líneas) son grandes, pero
  las superficies de `VDevice`, `InferModel` y GenAI (`LLM` / `VLM` / `Speech2Text`) son completamente
  compatibles hacia atrás.
- La mayor parte de los cambios son **eliminación de APIs de cámara / ISP / gestión de firmware de Hailo-8**
  y refactorización interna. No afectan a la inferencia NPU pura.
- **Los archivos `.hef` de la era v5.2.0 se cargan sin cambios en el runtime 5.3.0.**
  Verificado con cinco modelos (YOLOv8n, CLIP ViT-B/16, Qwen2.5-1.5B, Qwen2-VL-2B, Whisper-Base).
- El driver Linux cambió de `hailo_pci` a `hailo1x_pci`, y el nodo de dispositivo de
  `/dev/hailort0` a **`/dev/h1x-0`**. `pyhailort` resuelve internamente el nuevo nodo,
  por lo que el código Python que usa `VDevice()` no necesita cambios. **Solo se necesita actualizar el passthrough de dispositivo Docker.**
- `Speech2Text.SegmentInfo` expone atributos `text` / `start_sec` / `end_sec`
  (igual que v5.2.0). `start` o `start_time` no están expuestos, y el código defensivo
  que usa estos nombres devolverá 0.0 silenciosamente.

---

## 1. Alcance de los cambios

Diff directo entre las etiquetas `v5.2.0` y `v5.3.0` del repositorio oficial de GitHub de HailoRT:

| Alcance | Archivos | Adiciones | Eliminaciones |
|---|---:|---:|---:|
| Total | 688 | +12,035 | −8,987 |
| Encabezados C++ públicos (`include/hailo/`) | 27 | +205 | **−383** |
| Bindings Python (`bindings/python/`) | 35 | +306 | **−413** |
| Solo `pyhailort.py` | 1 | +98 | **−158** |

**Las eliminaciones superan a las adiciones.** Es una versión de "simplificación".
La mayor parte de lo eliminado no tiene relación con la ruta de inferencia NPU.

---

## 2. APIs eliminadas — Solo cámara / ISP / firmware de Hailo-8

`hailort/libhailort/include/hailo/device.hpp` perdió 169 líneas,
`platform.h` perdió 75 líneas. Todo lo eliminado es control de dispositivo de bajo nivel:

- `firmware_update()` / `second_stage_update()` (reescritura de firmware)
- `store_sensor_config()` / `store_isp_config()`
- `sensor_dump_config()` / `sensor_reset()`
- `sensor_load_and_start_config()`
- `sensor_set_i2c_bus_index()` / `sensor_set_generic_i2c_slave()`
- `sensor_get_sections_info()`
- `examine_user_config()` / `read_user_config()` /
  `write_user_config()` / `erase_user_config()`

Todas estas son APIs para **módulos de cámara AI Hailo-8** (placas estilo SoC donde el chip Hailo
controla directamente el ISP y el sensor de imagen).
No se invocan en el flujo típico `VDevice` → `InferModel` → `generate`
en la NPU Hailo-10H pura.

**Impacto**: Cero para aplicaciones de inferencia NPU pura. Solo las aplicaciones que controlan
módulos de cámara Hailo-8 necesitan auditar su uso.

---

## 3. Cambios en la firma Python

| API | v5.2.0 | v5.3.0 | Compatibilidad |
|---|---|---|---|
| `Speech2Text.generate_all_segments(timeout_ms=)` | Predeterminado `10000` | Predeterminado `600000` | ✅ Solo predeterminado, las llamadas existentes no cambian |
| `Speech2Text.generate_all_text(timeout_ms=)` | Igual | Igual | ✅ Igual |
| `LLM.read_all(timeout_ms=10000)` | Con predeterminado | Predeterminado **eliminado** (obligatorio) | ⚠️ `read_all()` sin argumento → `TypeError` |
| `DeviceArchitecture.__init__` | 9 args posicionales | +`chip_serial_number` (10) | ⚠️ La construcción directa falla |

**La corrección de `read_all()` es un cambio de una línea**:

```python
# Antes (estilo v5.2.0, predeterminado de 10 segundos)
text = generator.read_all()

# Después (v5.3.0 requiere timeout explícito)
text = generator.read_all(timeout_ms=600000)  # 10 minutos
```

`DeviceArchitecture` rara vez se construye directamente en el código del usuario,
por lo que el cambio de su firma tiene poco impacto.

---

## 4. Cambios en nombres de encabezados C++ (transparente a través de Python)

Disruptivos para aplicaciones que usan HailoRT directamente desde C++:

- **`Speech2Text::DEFAULT_OPERATION_TIMEOUT`** (10 segundos) →
  **`DEFAULT_GENERATE_ALL_TIMEOUT`** (10 minutos), renombrado y extendido
- **`LLM::DEFAULT_READ_ALL_TIMEOUT`** añadido, también 10 minutos
- Se añaden 4 sobrecargas de `generate_from_embeddings()` a `vlm.hpp`

Estos cambios de nombre no se propagan a través de los bindings Python.

---

## 5. Corrección de coordenadas de bounding box NMS (cambio de comportamiento)

Corrección de lógica en el postprocesamiento NMS de `pyhailort.py`:

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

Mejoras:

- Clipping de límites de imagen añadido `max(0, …)` / `min(image_width, …)`
- `ceil` → `floor` (prevención de sobredisparo)
- `bbox_width` recalculado desde `x_max - x_min` recortado

**Diferencia de comportamiento**: Con el mismo modelo y la misma imagen, la salida NMS puede desplazarse ±1 píxel cerca de los límites. Las aplicaciones que escriben su propio postprocesamiento NMS no se ven afectadas. Las aplicaciones que llaman a los helpers `_output_raw_buffer_to_nms_with_byte_mask_*` de pyhailort pueden ver cambios de forma en bounding boxes cerca de los bordes de la imagen.

---

## 6. Nuevas APIs (aditivas)

- **`VDevice::create_session(uint16_t port)`** — Nueva API de sesión de inferencia basada en red
- **`VLM::generate_from_embeddings()`** — 4 sobrecargas. Acepta embeddings de imagen/video precomputados como entrada `MemoryView`.
  Permite computar embeddings de imagen una vez y reutilizarlos en múltiples llamadas VLM.
- **`InferModel::set_nms_classes_filter_mask(vector<bool>)`** — Filtrado a nivel de clase para salida NMS (en el chip)
- **`Device::query_performance_stats(sampling_period_ms)`** —
  Período de muestreo configurable
- **`Device::get_current_limit()`** — Consultar límite de corriente
- **`DeviceArchitecture.chip_serial_number`** — Leer el número de serie del chip

Todas son aditivas, por lo que el código existente no se rompe. Adoptar según sea necesario.

---

## 7. Cambios de entorno

### 7.1 Nuevo driver Linux PCI

| Elemento | Antiguo | Nuevo |
|---|---|---|
| Módulo del kernel | `hailo_pci` | `hailo1x_pci` |
| Nodo de dispositivo | `/dev/hailort0` (o `/dev/hailo0`) | `/dev/h1x-0` |

```bash
lsmod | grep hailo        # → hailo1x_pci
ls /dev/h1x-*             # → /dev/h1x-0
```

**`pyhailort` resuelve internamente el nuevo nodo de dispositivo**,
por lo que el código Python que usa `VDevice()` continúa funcionando sin cambios.
Solo el código que abre directamente `/dev/hailo*` o `/dev/hailort0` necesita actualización.

#### Passthrough Docker / Podman

Actualizar la declaración de passthrough del dispositivo:

```yaml
# docker-compose.yml
services:
  my-app:
    devices:
      - /dev/h1x-0:/dev/h1x-0   # era: /dev/hailort0:/dev/hailort0
```

También actualizar las líneas `DeviceAllow=` de las unidades systemd y las reglas udev.

### 7.2 Restricción de numpy relajada

- `setup.py` de v5.2.0: `numpy<2` (fijo)
- `setup.py` de v5.3.0: `numpy` (sin límite superior)

Las aplicaciones anteriormente fijadas a numpy 1.x pueden actualizar a numpy 2.x junto con el bump de HailoRT.

### 7.3 Compatibilidad binaria HEF

**Los archivos `.hef` descargados desde el bucket de v5.2.0 se cargan y ejecutan sin cambios en el runtime 5.3.0.**
Verificado con cinco modelos (Raspberry Pi 5 + AI HAT 2):

| Modelo | Archivo | Resultado |
|---|---|---|
| YOLOv8n | `yolov8n.hef` | ✅ `create_infer_model()` + `.run()` |
| Codificador de imagen CLIP ViT-B/16 | `clip_vit_b_16_image_encoder.hef` | ✅ Salida de 512 dimensiones |
| Qwen2.5-1.5B Instruct | `Qwen2.5-1.5B-Instruct.hef` | ✅ `LLM.generate_all()` devuelve texto válido |
| Qwen2-VL-2B Instruct | `Qwen2-VL-2B-Instruct.hef` | ✅ `VLM.generate_all(frames=[…])` devuelve texto válido |
| Whisper-Base | `Whisper-Base.hef` | ✅ `Speech2Text.generate_all_segments()` devuelve `SegmentInfo` |

El formato binario HEF puede romperse teóricamente entre grandes actualizaciones del runtime, pero **no ocurrió entre 5.2.0 y 5.3.0**.

### 7.4 Bucket de URLs de descarga HEF

Hailo Developer Zone (`dev-public.hailo.ai`) hospeda los buckets v5.2.0 y v5.3.0 en paralelo:

```
https://dev-public.hailo.ai/v5.2.0/blob/<model>.hef
https://dev-public.hailo.ai/v5.3.0/blob/<model>.hef
```

Estado del bucket v5.3.0 a 2026-04-06:

| Modelo | Bucket v5.3.0 |
|---|---|
| Qwen2.5-1.5B-Instruct | ✅ 200 |
| DeepSeek-R1-Distill-Qwen-1.5B | ✅ 200 |
| Qwen2.5-Coder-1.5B-Instruct | ✅ 200 |
| Qwen2-VL-2B-Instruct | ✅ 200 |
| Whisper-Base / Whisper-Small | ✅ 200 |
| **Llama-3.2-1B-Instruct** | ❌ **404** |

→ Las aplicaciones que necesiten Llama-3.2-1B deben continuar obteniéndolo desde el bucket v5.2.0 por ahora. Los HEF v5.2.0 se cargan correctamente en el runtime 5.3.0.

---

## 8. Nombres de atributos de `Speech2Text.SegmentInfo`

En v5.2.0 y v5.3.0, `Speech2Text.generate_all_segments()` devuelve objetos `SegmentInfo` con estos atributos públicos:

```python
seg.text        # str
seg.start_sec   # float (segundos)
seg.end_sec     # float (segundos)
```

**`seg.start` y `seg.start_time` no existen.** La documentación antigua y el código de ejemplo puede referirse a estos nombres, pero causarán `AttributeError` o, peor aún, devolverán 0.0 silenciosamente si están envueltos en código defensivo como `getattr(seg, "start", 0.0) or getattr(seg, "start_time", 0.0)`.

Para verificar los nombres reales de atributos en el runtime:

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

## 9. Script de prueba de humo

Script mínimo para verificar que el entorno realmente funciona después de actualizar a 5.3.0:

```python
"""Prueba de humo de HailoRT 5.3.0 — VDevice / InferModel / LLM / Speech2Text."""
import numpy as np
from hailo_platform import VDevice

# 1. Crear VDevice
params = VDevice.create_params()
params.group_id = "SMOKE_TEST"
vd = VDevice(params)
print("1. VDevice OK")

# 2. Ruta InferModel (YOLOv8n o cualquier HEF existente)
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

# 3. Ruta GenAI LLM
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

# 4. Ruta Speech2Text
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

## 10. Lista de verificación de actualización

Puntos para auditar en el código antes o durante la actualización 5.2.0 → 5.3.0:

- [ ] `VDevice()` / `create_infer_model()` / `InferModel.configure()` —
      **No necesita cambios**
- [ ] Constructores `LLM(vd, path)` / `VLM(vd, path)` / `Speech2Text(vd, path)`
      — **No necesita cambios**
- [ ] Argumentos de `LLM.generate()` / `.generate_all()` / `VLM.generate(frames=…)` /
      `.generate_all()` — **No necesita cambios**
- [ ] `Speech2Text.generate_all_segments(audio_data=, task=, language=,
      timeout_ms=)` — **No necesita cambios** (si se pasa `timeout_ms` explícitamente)
- [ ] Verificar si `LLM.read_all()` se llama sin argumento `timeout_ms` →
      si es así, agregar timeout explícito
- [ ] Verificar si `DeviceArchitecture` se construye directamente → si es así,
      agregar `chip_serial_number`
- [ ] Grep para apertura directa de `/dev/hailo*` o `/dev/hailort0` →
      si existe, reemplazar con `/dev/h1x-0` (o mejor, usar pyhailort)
- [ ] Actualizar secciones `devices:` de Docker / Podman a `/dev/h1x-0`
- [ ] Actualizar líneas `DeviceAllow=` de unidades systemd y reglas udev
- [ ] Grep para acceso a atributos de `SegmentInfo` usando `.start` o `.start_time` →
      cambiar a `.start_sec` / `.end_sec`. Verificar que los timestamps de Whisper
      no devuelvan 0.0 silenciosamente en la aplicación
- [ ] Si numpy estaba fijado a 1.x (por `numpy<2` de v5.2.0), ahora se puede quitar el pin
- [ ] **No es necesario** volver a descargar los archivos `.hef` existentes
- [ ] Si los URLs de descarga HEF tienen hardcodeado el bucket `v5.2.0`, actualizar a
      `v5.3.0` (mantener `v5.2.0` para Llama-3.2-1B)
- [ ] Si se depende del postprocesamiento NMS integrado de pyhailort,
      tener en cuenta que los bounding boxes cerca de los bordes de la imagen pueden
      desplazarse ±1 píxel

---

## 11. Comandos usados en la investigación

Asumiendo que el repositorio oficial de HailoRT está clonado:

```bash
cd ~/hailort

# Tamaño total del diff
git diff --stat v5.2.0 v5.3.0 | tail

# Diff de encabezados C++ públicos
git diff --stat v5.2.0 v5.3.0 -- 'hailort/libhailort/include/hailo/'

# Diff de bindings Python
git diff --stat v5.2.0 v5.3.0 -- 'hailort/libhailort/bindings/python/'

# Diff completo de pyhailort.py
git diff v5.2.0 v5.3.0 -- \
  'hailort/libhailort/bindings/python/platform/hailo_platform/pyhailort/pyhailort.py'

# Diff de API pública de encabezado específico (solo firmas de funciones)
git diff v5.2.0 v5.3.0 -- 'hailort/libhailort/include/hailo/genai/llm/llm.hpp' \
  | grep -E '^[+-]' | grep -E 'Expected|hailo_status|void|static'

# APIs eliminadas de device.hpp
git diff v5.2.0 v5.3.0 -- 'hailort/libhailort/include/hailo/device.hpp' \
  | grep '^-' | grep 'virtual'
```

Los encabezados C++ contienen la mayor información por línea para el análisis de API —
los bindings Python son casi todos boilerplate de pybind11, por lo que un diff de líneas ingenuo es engañoso. Grep por símbolos públicos en su lugar.

---

## 12. Conclusión

El titular "688 archivos modificados" está lejos del impacto real.
En una aplicación típica de inferencia NPU con Hailo-10H:

- **Las APIs core de inferencia NPU (`VDevice` / `InferModel` / GenAI) son
  totalmente compatibles hacia atrás**
- Todas las APIs eliminadas pertenecen a la superficie de cámara / sensor / ISP /
  gestión de firmware de Hailo-8, sin relación con el uso solo de NPU
- **Todos los archivos `.hef` existentes se cargan sin necesidad de volver a descargar**
- El único cambio obligatorio a nivel de entorno es actualizar el passthrough
  del dispositivo Docker a `/dev/h1x-0`

Principales mejoras de calidad de vida después de la actualización:

- Los timeouts predeterminados se han extendido significativamente (10 segundos → 10 minutos),
  reduciendo los timeouts falsos en generación de texto largo
- `FormatType.FLOAT32` está disponible (en v5.2.0 era obligatoria la cuantización/descuantización manual)
- Corrección del bug de clipping de coordenadas NMS
- Ruta de actualización de numpy 2.x abierta
- `VLM.generate_from_embeddings()` permite reutilizar embeddings de imagen precomputados
  en múltiples llamadas VLM

Si mantienes una aplicación Python Hailo-10H fijada a 5.2.0 y has estado aplazando la actualización, este documento debería confirmar que la migración es esencialmente una no-operación (no hay nada que hacer).
