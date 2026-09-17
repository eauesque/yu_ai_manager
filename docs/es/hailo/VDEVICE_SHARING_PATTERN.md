# Patrón: Gestor de VDevice compartido para aplicaciones Hailo-10H con múltiples modelos

Patrón de implementación para ejecutar múltiples modelos Hailo (YOLO / CLIP / LLM / VLM / Whisper, etc.) en la NPU Hailo-10H dentro del mismo proceso en una aplicación Python.

**Audiencia objetivo**: Desarrolladores que quieren hacer coexistir múltiples modelos en la NPU Hailo-10H dentro de una sola aplicación.

---

## TL;DR

- Hailo-10H tiene **exactamente 1 dispositivo físico**.
- Crear `VDevice()` dos veces en el mismo proceso falla con:
  `HAILO_OUT_OF_PHYSICAL_DEVICES(74)`
- Causas comunes: liberación lazy al cambiar modelos, conflictos con precargadores en segundo plano, verificaciones `is_available()` que construyen y destruyen `VDevice` internamente.
- Solución: Introducir un **singleton `VDevice` para todo el proceso**, con todos los modelos accediendo a través de un registro con claves de propietario.
- Configurar `VDevice.create_params().group_id` permite compartir el mismo dispositivo físico **incluso entre múltiples procesos** (el scheduler HailoRT medía el acceso con time-slicing).

---

## Síntoma

```
[HailoRT] [error] Failed to create vdevice. there are not enough free devices. requested: 1, found: 0
[HailoRT] [error] CHECK_SUCCESS failed with status=HAILO_OUT_OF_PHYSICAL_DEVICES(74)
hailo_platform.pyhailort.pyhailort.HailoRTStatusException: 74
```

El stack trace generalmente apunta a la inicialización de YOLO, CLIP o LLM, pero la verdadera causa es que **otro componente** adquirió `VDevice` anteriormente y no lo liberó.

---

## Escenarios típicos de fallo

### Escenario 1: Conflicto con precargador en segundo plano

```
app startup
  └─ preloader thread
       ├─ CLIP init → VDevice() [A]
       └─ YOLO init → VDevice() [B]  ← [A] sigue teniendo el dispositivo → Fallo
```

### Escenario 2: Verificación `is_available()` destructiva

```python
class YoloEngine:
    @staticmethod
    def is_available():
        try:
            vd = VDevice()   # Adquirir para verificar
            del vd            # Puede no liberarse inmediatamente (temporización GC)
            return True
        except Exception:
            return False

# Llamador
if YoloEngine.is_available():     # Aquí adquiere y destruye VDevice
    engine = YoloEngine()          # Intenta adquirir de nuevo → Posible fallo
```

### Escenario 3: Liberación lazy al cambiar modelos

```python
# del solo no libera VDevice inmediatamente
del self.vd                 # Baja el contador de referencias
self.vd = VDevice()         # El VDevice anterior puede estar esperando GC → Fallo
```

La corrección es llamar explícitamente a `self.vd.release()` antes de crear uno nuevo.

### Escenario 4: Inicialización independiente de módulos independientes

Si múltiples módulos de funciones (extensiones, plugins, etc.) llaman cada uno a `VDevice()` al cargarse, casi con seguridad colisionarán.

---

## Anti-patrón

```python
# modulo_yolo.py
from hailo_platform import VDevice

class YoloEngine:
    def __init__(self):
        self.vd = VDevice()    # Adquisición independiente
        self.model = self.vd.create_infer_model("yolov8n.hef")
        self.configured = self.model.configure()

    @staticmethod
    def is_available():
        try:
            VDevice()              # Verificación de salud destructiva
            return True
        except Exception:
            return False


# modulo_clip.py
class ClipEngine:
    def __init__(self):
        self.vd = VDevice()    # Colisión con YoloEngine
        ...
```

---

## Patrón recomendado: Gestor compartido con claves de propietario

```python
"""device_manager.py — Propietario de VDevice para todo el proceso."""
import gc
import os
import threading
from typing import Callable, Dict, Optional, Tuple

_lock = threading.Lock()
_vdevice = None
_models: Dict[str, dict] = {}

# Usado para compartir el dispositivo físico con otros procesos.
_GROUP_ID = os.environ.get("HAILO_VDEVICE_GROUP_ID", "MY_APP_SHARED")


def _ensure_vdevice():
    """Crear lazily un único VDevice (el llamador debe mantener _lock)."""
    global _vdevice
    if _vdevice is not None:
        return _vdevice
    from hailo_platform import VDevice
    params = VDevice.create_params()
    params.group_id = _GROUP_ID
    _vdevice = VDevice(params)
    return _vdevice


def acquire_infer_model(owner: str, hef_path: str) -> Tuple:
    """Obtener (InferModel, ConfiguredInferModel) en el VDevice compartido.

    El mismo propietario + el mismo HEF reutiliza la sesión existente. El mismo
    propietario pero HEF diferente: libera el antiguo antes de adquirir el nuevo.
    """
    with _lock:
        existing = _models.get(owner)
        if existing and existing["hef"] == hef_path:
            return existing["infer_model"], existing["configured"]

        if existing:
            _release_internal(owner)

        vd = _ensure_vdevice()
        infer_model = vd.create_infer_model(hef_path)
        configured = infer_model.configure()

        _models[owner] = {
            "type": "infer",
            "infer_model": infer_model,
            "configured": configured,
            "hef": hef_path,
        }
        return infer_model, configured


def acquire_genai(
    owner: str,
    model_path: str,
    factory: Callable,
) -> object:
    """Obtener modelo GenAI (LLM / VLM / Speech2Text).

    `factory` es `(vdevice, model_path) -> instancia construida`.
    Ejemplo: `lambda vd, p: LLM(vd, p)`
    """
    with _lock:
        existing = _models.get(owner)
        if existing and existing["hef"] == model_path:
            return existing["instance"]

        if existing:
            _release_internal(owner)

        vd = _ensure_vdevice()
        instance = factory(vd, model_path)

        _models[owner] = {
            "type": "genai",
            "instance": instance,
            "hef": model_path,
        }
        return instance


def release(owner: str) -> bool:
    """Liberar el modelo retenido por `owner`. El VDevice en sí se mantiene vivo."""
    with _lock:
        return _release_internal(owner)


def _release_internal(owner: str) -> bool:
    entry = _models.pop(owner, None)
    if entry is None:
        return False
    if entry["type"] == "genai":
        try:
            entry["instance"].release()
        except Exception:
            pass
    # InferModel solo necesita soltar las referencias Python
    gc.collect()
    return True


def shutdown() -> None:
    """Llamar al terminar el proceso: libera todos los modelos y VDevice."""
    global _vdevice
    with _lock:
        for owner in list(_models.keys()):
            _release_internal(owner)
        if _vdevice is not None:
            try:
                _vdevice.release()
            except Exception:
                pass
            _vdevice = None
        gc.collect()


def is_hailo_available() -> bool:
    """Verificación no destructiva — no construye VDevice."""
    try:
        import hailo_platform  # noqa: F401
        return True
    except ImportError:
        return False
```

---

## Ejemplos de uso

### YOLO (InferModel)

```python
from device_manager import acquire_infer_model, release, is_hailo_available
import numpy as np

class YoloEngine:
    def __init__(self, hef_path: str):
        self.infer_model, self.configured = acquire_infer_model("yolo", hef_path)
        self.input_shape = tuple(self.infer_model.inputs[0].shape)

    def detect(self, image_uint8: np.ndarray):
        bindings = self.configured.create_bindings()
        bindings.input().set_buffer(image_uint8)
        for out in self.infer_model.outputs:
            fmt = str(getattr(out.format, "type", "")).lower()
            dtype = np.float32 if "float" in fmt else np.uint8
            buf = np.zeros(tuple(out.shape), dtype=dtype)
            bindings.output(out.name).set_buffer(buf)
        self.configured.run([bindings], timeout=10000)
        return bindings

    def close(self):
        release("yolo")

    @staticmethod
    def is_available() -> bool:
        return is_hailo_available()   # No toca VDevice
```

### LLM (GenAI)

```python
from hailo_platform.genai import LLM
from device_manager import acquire_genai, release

class MyLlm:
    def __init__(self, hef_path: str):
        self.llm = acquire_genai(
            "llm", hef_path,
            lambda vd, p: LLM(vd, p),
        )

    def generate(self, prompt: list, **kwargs) -> str:
        return self.llm.generate_all(prompt=prompt, **kwargs)

    def close(self):
        release("llm")
```

### Coexistencia de YOLO + CLIP + LLM

Usando diferentes nombres de propietario, se pueden **cargar simultáneamente 2 InferModel y 1 modelo GenAI en el mismo VDevice**. El scheduler interno de HailoRT (ROUND_ROBIN) divide automáticamente el tiempo el acceso al hardware:

```python
yolo = YoloEngine("yolov8n.hef")           # owner="yolo"
clip = ClipEncoder("clip_vit_b_16.hef")    # owner="clip"
llm = MyLlm("Qwen2.5-1.5B-Instruct.hef")   # owner="llm"

# 3 modelos activos en 1 dispositivo físico
bbox = yolo.detect(image)
embedding = clip.encode(image)
text = llm.generate([{"role": "user", "content": "..."}])
```

---

## Puntos clave de diseño

### 1. `is_available()` no debe ser destructiva

Los "verificaciones de salud" que construyen y destruyen `VDevice` son la causa más común de este tipo de bugs. No hacer esto.

En su lugar, verificar que la importación funciona:

```python
def is_hailo_available() -> bool:
    try:
        import hailo_platform  # noqa: F401
        return True
    except ImportError:
        return False
```

Si se quiere verificar la presencia del hardware sin construir `VDevice` solo para destruirlo, verificar a nivel del sistema de archivos `/sys/class/hailo*` o `/dev/h1x-*`.

### 2. Diseño del espacio de nombres de propietario

Los componentes que deben compartir el mismo HEF usan el **mismo nombre de propietario**. Si múltiples módulos usan el mismo YOLOv8n, todos adquieren con el propietario `"yolo"` y comparten automáticamente la sesión:

```python
# Módulo A
yolo_a = acquire_infer_model("yolo", "yolov8n.hef")

# Módulo B (mismo HEF)
yolo_b = acquire_infer_model("yolo", "yolov8n.hef")
# → Devuelve el mismo infer_model / configured, sin recarga
```

Los componentes con HEF único obtienen un nombre de propietario único:

| Componente | Propietario | Notas |
|---|---|---|
| YOLO genérico | `"yolo"` | Compartido |
| CLIP genérico | `"clip"` | Compartido |
| Etiquetador personalizado (HEF único) | `"my-tagger"` | Único |
| LLM | `"llm"` | GenAI |
| VLM | `"vlm"` | GenAI |
| Speech2Text | `"s2t"` | GenAI |

### 3. Usar `group_id` para compartición entre procesos

Configurar `VDevice.create_params().group_id` permite que **diferentes procesos** compartan el mismo dispositivo físico:

```python
params = VDevice.create_params()
params.group_id = "MY_APP_SHARED"   # Unificar con variable de entorno, configuración, etc.
vd = VDevice(params)
```

Otro proceso que llame a `VDevice(params)` con el mismo `group_id` tendrá sus solicitudes paralelas divididas en el tiempo por el scheduler HailoRT. Así es como herramientas externas como `hailo-ollama` pueden funcionar en paralelo con el proceso de inferencia propio.

### 4. Los hooks de apagado son obligatorios

Si el proceso se bloquea, `VDevice` no se libera y `/dev/h1x-0` queda retenido por descriptores de archivo zombi. Los inicios posteriores obtienen `HAILO_OUT_OF_PHYSICAL_DEVICES(74)` hasta que se elimine `/dev/h1x-0`. Instalar un hook de apagado:

```python
import atexit
import signal
from device_manager import shutdown

atexit.register(shutdown)

def _signal_handler(signum, frame):
    shutdown()
    raise KeyboardInterrupt

signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)
```

Recuperación cuando hay problemas:

```bash
# Encontrar el proceso que retiene el dispositivo
lsof /dev/h1x-0        # hailort 5.3.0+
lsof /dev/hailort0     # hailort 5.2.0 y anteriores

# Forzar la eliminación
kill -9 <PID>
```

### 5. Mezclar InferModel y GenAI en el mismo VDevice

Verificado con HailoRT 5.2.0 y 5.3.0: **se pueden hacer coexistir simultáneamente múltiples InferModel (p.ej., YOLO + CLIP) y múltiples modelos GenAI (LLM, VLM, Speech2Text) en el mismo `VDevice`.**

Notas:

- Después de crear `VDevice`, se puede llamar tanto a `create_infer_model()` como a `LLM(vd, path)` en la misma instancia.
- Sin embargo, la propia instancia de `VDevice` debe ser el **mismo objeto Python**. Intentar reutilizar sesiones desde diferentes variables de Python creando un segundo `VDevice()` con el mismo `group_id` hará que `InferModel.run()` falle.

### 6. Tiempo de espera al fallar la inicialización

La inicialización de Hailo es costosa (~1 segundo). Los reintentos inmediatos justo después de un fallo a menudo provocan más fallos. Introducir un breve tiempo de espera (p.ej., 60 segundos) para suprimir las tormentas de reintentos:

```python
import time
from typing import Optional

_init_failed_at: Optional[float] = None
_INIT_COOLDOWN_SEC = 60.0

def try_initialize():
    global _init_failed_at
    now = time.time()
    if _init_failed_at and (now - _init_failed_at) < _INIT_COOLDOWN_SEC:
        return None  # Aún en período de espera
    try:
        return acquire_infer_model("yolo", "yolov8n.hef")
    except Exception:
        _init_failed_at = now
        raise
```

---

## Verificado con HailoRT 5.2.0 y 5.3.0

Este patrón ha sido verificado en Raspberry Pi 5 + AI HAT 2 con los siguientes entornos:

- HailoRT 5.2.0 y 5.3.0
- 2× InferModel (YOLOv8n + CLIP ViT-B/16) + 1× GenAI LLM (Qwen2.5-1.5B) simultáneamente
- 2× InferModel + 1× GenAI VLM (Qwen2-VL-2B) simultáneamente
- 2× InferModel + 1× GenAI Speech2Text (Whisper-Base) simultáneamente

La restricción física (1 dispositivo físico por proceso) no ha cambiado en 5.3.0. El compartido basado en `group_id` y el scheduler interno ROUND_ROBIN continúan siendo compatibles.

---

## Relacionado

- Notas de migración de HailoRT 5.2.0 → 5.3.0 (`HAILORT_5_3_0_MIGRATION.md`)
- Con el nuevo driver `hailo1x_pci` de 5.3.0, el nodo del dispositivo pasó de `/dev/hailort0` a `/dev/h1x-0`
