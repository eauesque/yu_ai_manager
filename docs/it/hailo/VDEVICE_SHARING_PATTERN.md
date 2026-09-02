# Pattern: VDevice Manager Condiviso per Applicazioni Hailo-10H con Modelli Multipli

Pattern di implementazione per eseguire più modelli Hailo (YOLO / CLIP / LLM / VLM / Whisper ecc.) sullo stesso processo sulla NPU Hailo-10H.

**Destinatari**: Sviluppatori che vogliono far coesistere più modelli all'interno di una singola applicazione sul chip Hailo-10H.

---

## TL;DR

- Hailo-10H ha **esattamente 1 dispositivo fisico**.
- Creare `VDevice()` due volte nello stesso processo fallisce con: `HAILO_OUT_OF_PHYSICAL_DEVICES(74)`
- Cause comuni: rilascio lazy al cambio modello, conflitto preloader in background, controllo `is_available()` che costruisce e distrugge `VDevice` internamente.
- Soluzione: Introdurre un **singleton `VDevice` per l'intero processo**, con tutti i modelli che accedono tramite un registro con chiave owner.
- Impostando `VDevice.create_params().group_id` è possibile **condividere lo stesso dispositivo fisico tra più processi** (lo scheduler HailoRT fa da mediatore tramite time-slicing).

---

## Sintomi

```
[HailoRT] [error] Failed to create vdevice. there are not enough free devices. requested: 1, found: 0
[HailoRT] [error] CHECK_SUCCESS failed with status=HAILO_OUT_OF_PHYSICAL_DEVICES(74)
hailo_platform.pyhailort.pyhailort.HailoRTStatusException: 74
```

Lo stack trace punta generalmente all'inizializzazione di YOLO, CLIP o LLM, ma la vera causa è che **un altro componente** ha acquisito `VDevice` in precedenza senza rilasciarlo.

---

## Scenari di Fallimento Tipici

### Scenario 1: Conflitto Preloader in Background

```
avvio app
  └─ thread preloader
       ├─ init CLIP → VDevice() [A]
       └─ init YOLO → VDevice() [B]  ← [A] mantiene il dispositivo → fallisce
```

### Scenario 2: Controllo `is_available()` Distruttivo

```python
class YoloEngine:
    @staticmethod
    def is_available():
        try:
            vd = VDevice()   # Acquisizione per il controllo
            del vd            # Potrebbe non essere rilasciato immediatamente (timing GC)
            return True
        except Exception:
            return False

# Chiamante
if YoloEngine.is_available():     # Acquisisce e distrugge VDevice qui
    engine = YoloEngine()          # Tenta di acquisire di nuovo → potenziale fallimento
```

### Scenario 3: Rilascio Lazy al Cambio Modello

```python
# del da solo non rilascia immediatamente VDevice
del self.vd                 # Il conteggio dei riferimenti scende
self.vd = VDevice()         # Il VDevice precedente potrebbe ancora essere in attesa del GC → fallisce
```

La correzione è chiamare esplicitamente `self.vd.release()` prima di crearne uno nuovo.

### Scenario 4: Moduli Indipendenti che si Inizializzano Indipendentemente

Più moduli funzionali (extension, plugin ecc.) che chiamano `VDevice()` al caricamento si scontrano quasi certamente.

---

## Anti-pattern

```python
# ❌ module_yolo.py
from hailo_platform import VDevice

class YoloEngine:
    def __init__(self):
        self.vd = VDevice()    # Acquisizione indipendente
        self.model = self.vd.create_infer_model("yolov8n.hef")
        self.configured = self.model.configure()

    @staticmethod
    def is_available():
        try:
            VDevice()              # Health check distruttivo
            return True
        except Exception:
            return False


# ❌ module_clip.py
class ClipEngine:
    def __init__(self):
        self.vd = VDevice()    # Conflitto con YoloEngine
        ...
```

---

## Pattern Consigliato: Manager Condiviso con Chiave Owner

```python
"""device_manager.py — Owner VDevice Hailo per l'intero processo."""
import gc
import os
import threading
from typing import Callable, Dict, Optional, Tuple

_lock = threading.Lock()
_vdevice = None
_models: Dict[str, dict] = {}

# Usato per condividere il dispositivo fisico con altri processi.
_GROUP_ID = os.environ.get("HAILO_VDEVICE_GROUP_ID", "MY_APP_SHARED")


def _ensure_vdevice():
    """Creazione lazy del singolo VDevice (il chiamante deve mantenere _lock)."""
    global _vdevice
    if _vdevice is not None:
        return _vdevice
    from hailo_platform import VDevice
    params = VDevice.create_params()
    params.group_id = _GROUP_ID
    _vdevice = VDevice(params)
    return _vdevice


def acquire_infer_model(owner: str, hef_path: str) -> Tuple:
    """Acquisisce (InferModel, ConfiguredInferModel) sul VDevice condiviso.

    Stesso owner + stesso HEF → riutilizza sessione esistente. Stesso owner ma
    HEF diverso → rilascia il vecchio e acquisisce il nuovo.
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
    """Acquisisce un modello GenAI (LLM / VLM / Speech2Text).

    `factory` è `(vdevice, model_path) -> istanza costruita`.
    Esempio: `lambda vd, p: LLM(vd, p)`
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
    """Rilascia il modello detenuto da `owner`. Il VDevice stesso rimane attivo."""
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
    # Per InferModel, basta eliminare i riferimenti Python
    gc.collect()
    return True


def shutdown() -> None:
    """Da chiamare alla chiusura del processo: rilascia tutti i modelli e VDevice."""
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
    """Controllo non distruttivo — non costruisce VDevice."""
    try:
        import hailo_platform  # noqa: F401
        return True
    except ImportError:
        return False
```

---

## Esempi d'Uso

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
        return is_hailo_available()   # Non tocca VDevice
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

### Coesistenza YOLO + CLIP + LLM

Usando nomi owner diversi, è possibile **caricare simultaneamente 2 InferModel e 1 modello GenAI sullo stesso VDevice**. Lo scheduler HailoRT interno (ROUND_ROBIN) fa automaticamente il time-slicing dell'accesso hardware:

```python
yolo = YoloEngine("yolov8n.hef")           # owner="yolo"
clip = ClipEncoder("clip_vit_b_16.hef")    # owner="clip"
llm = MyLlm("Qwen2.5-1.5B-Instruct.hef")   # owner="llm"

# 3 modelli attivi su 1 dispositivo fisico
bbox = yolo.detect(image)
embedding = clip.encode(image)
text = llm.generate([{"role": "user", "content": "..."}])
```

---

## Punti Chiave del Design

### 1. `is_available()` Non Deve Essere Distruttivo

Il "health check" che costruisce e distrugge `VDevice` è la causa più comune di questo tipo di bug.

```python
def is_hailo_available() -> bool:
    try:
        import hailo_platform  # noqa: F401
        return True
    except ImportError:
        return False
```

Per verificare la presenza hardware senza costruire `VDevice`, controllare a livello filesystem `/sys/class/hailo*` o `/dev/h1x-*`.

### 2. Design del Namespace dei Nomi Owner

I componenti che dovrebbero condividere lo stesso HEF usano lo **stesso nome owner**:

```python
# Modulo A
yolo_a = acquire_infer_model("yolo", "yolov8n.hef")

# Modulo B (stesso HEF)
yolo_b = acquire_infer_model("yolo", "yolov8n.hef")
# → Restituisce lo stesso infer_model / configured, nessun reload
```

| Componente | Owner | Note |
|------------|-------|------|
| YOLO generico | `"yolo"` | Condiviso |
| CLIP generico | `"clip"` | Condiviso |
| Tagger custom (HEF unico) | `"my-tagger"` | Unico |
| LLM | `"llm"` | GenAI |
| VLM | `"vlm"` | GenAI |
| Speech2Text | `"s2t"` | GenAI |

### 3. Usare `group_id` per la Condivisione Cross-Process

Impostando `VDevice.create_params().group_id`, **processi diversi** possono condividere lo stesso dispositivo fisico:

```python
params = VDevice.create_params()
params.group_id = "MY_APP_SHARED"
vd = VDevice(params)
```

### 4. I Hook di Shutdown Sono Obbligatori

Se il processo crasha, `VDevice` non viene rilasciato e `/dev/h1x-0` rimane detenuto. I successivi avvii otterranno `HAILO_OUT_OF_PHYSICAL_DEVICES(74)` finché non si uccide il processo. Installare hook di shutdown:

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

Recupero in caso di problemi:

```bash
# Trovare il processo che mantiene il dispositivo
lsof /dev/h1x-0        # hailort 5.3.0+
lsof /dev/hailort0     # hailort 5.2.0 e precedenti

# Forzarne la terminazione
kill -9 <PID>
```

### 5. Mix di InferModel e GenAI sullo Stesso VDevice

Verificato su HailoRT 5.2.0 e 5.3.0: **è possibile far coesistere simultaneamente più InferModel (es. YOLO + CLIP) e più modelli GenAI (LLM, VLM, Speech2Text) sullo stesso `VDevice`.**

### 6. Cooldown al Fallimento dell'Inizializzazione

L'inizializzazione Hailo è costosa (~1 secondo). Ritentativi immediati dopo un fallimento portano spesso ad ulteriori fallimenti. Introdurre un breve cooldown (es. 60 secondi):

```python
import time
from typing import Optional

_init_failed_at: Optional[float] = None
_INIT_COOLDOWN_SEC = 60.0

def try_initialize():
    global _init_failed_at
    now = time.time()
    if _init_failed_at and (now - _init_failed_at) < _INIT_COOLDOWN_SEC:
        return None  # Ancora in cooldown
    try:
        return acquire_infer_model("yolo", "yolov8n.hef")
    except Exception:
        _init_failed_at = now
        raise
```

---

## Verificato su HailoRT 5.2.0 e 5.3.0

Questo pattern è stato verificato su Raspberry Pi 5 + AI HAT 2 negli ambienti seguenti:

- HailoRT 5.2.0 e 5.3.0
- 2× InferModel (YOLOv8n + CLIP ViT-B/16) + 1× GenAI LLM (Qwen2.5-1.5B) simultaneamente
- 2× InferModel + 1× GenAI VLM (Qwen2-VL-2B) simultaneamente
- 2× InferModel + 1× GenAI Speech2Text (Whisper-Base) simultaneamente

---

## Riferimenti Correlati

- Note di migrazione HailoRT 5.2.0 → 5.3.0 (`HAILORT_5_3_0_MIGRATION.md`)
- Con il nuovo driver `hailo1x_pci` di 5.3.0, il nodo dispositivo è stato rinominato da `/dev/hailort0` a `/dev/h1x-0`
