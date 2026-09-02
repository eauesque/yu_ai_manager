# Muster: Geteilter VDevice-Manager für Multi-Modell-Hailo-10H-Anwendungen

Implementierungsmuster für den Betrieb mehrerer Hailo-Modelle (YOLO / CLIP / LLM / VLM / Whisper usw.) auf der Hailo-10H NPU im selben Prozess.

**Zielgruppe**: Entwickler, die mehrere Modelle auf einem Hailo-10H-Chip in einer einzigen Anwendung koexistieren lassen möchten.

---

## TL;DR

- Hailo-10H hat **genau ein physisches Gerät**.
- Das zweimalige Erstellen von `VDevice()` im selben Prozess schlägt fehl:
  `HAILO_OUT_OF_PHYSICAL_DEVICES(74)`
- Häufige Ursachen: Lazy-Release beim Modellwechsel, Preloader-Konflikte im Hintergrund, destruktive `is_available()`-Checks, die intern `VDevice` bauen und verwerfen.
- Lösung: **Prozessweiter `VDevice`-Singleton** mit Owner-Key-Registry, über die alle Modelle zugreifen.
- `VDevice.create_params().group_id` setzen ermöglicht das **Teilen des physischen Geräts auch zwischen mehreren Prozessen** (HailoRT-Scheduler vermittelt den Zugriff per Time-Slicing).

---

## Symptome

```
[HailoRT] [error] Failed to create vdevice. there are not enough free devices. requested: 1, found: 0
[HailoRT] [error] CHECK_SUCCESS failed with status=HAILO_OUT_OF_PHYSICAL_DEVICES(74)
hailo_platform.pyhailort.pyhailort.HailoRTStatusException: 74
```

Der Stack-Trace zeigt meist auf YOLO-, CLIP- oder LLM-Initialisierung, aber die eigentliche Ursache ist meist, dass **eine andere Komponente** zuvor `VDevice` akquiriert und nicht freigegeben hat.

---

## Typische Fehlerszenarien

### Szenario 1: Preloader-Konflikt im Hintergrund

```
App-Start
  └─ Preloader-Thread
       ├─ CLIP-Init → VDevice() [A]
       └─ YOLO-Init → VDevice() [B]  ← [A] hält Gerät noch → Fehler
```

### Szenario 2: Destruktiver `is_available()`-Check

```python
class YoloEngine:
    @staticmethod
    def is_available():
        try:
            vd = VDevice()   # Gerät zum Prüfen akquirieren
            del vd            # Kann nicht sofort freigegeben werden (GC-Timing)
            return True
        except Exception:
            return False

# Aufrufer
if YoloEngine.is_available():     # Hier VDevice akquiriert und verworfen
    engine = YoloEngine()          # Nochmal akquirieren → kann fehlschlagen
```

### Szenario 3: Lazy-Release beim Modellwechsel

```python
# del gibt VDevice nicht sofort frei
del self.vd                 # Referenzzähler sinkt
self.vd = VDevice()         # Vorheriger VDevice wartet möglicherweise noch auf GC → Fehler
```

Fix: Explizit `self.vd.release()` aufrufen, bevor ein neues erstellt wird.

### Szenario 4: Unabhängige Modulinitialisierung

Mehrere Feature-Module (Extensions, Plugins usw.), die beim Laden je `VDevice()` aufrufen, führen fast sicher zu Konflikten.

---

## Anti-Muster

```python
# Anti-Muster: Jedes Modul erstellt seinen eigenen VDevice

# module_yolo.py
class YoloEngine:
    def __init__(self):
        self.vd = VDevice()    # Unabhängige Akquisition
        self.model = self.vd.create_infer_model("yolov8n.hef")
        self.configured = self.model.configure()

    @staticmethod
    def is_available():
        try:
            VDevice()              # Destruktiver Health-Check
            return True
        except Exception:
            return False

# module_clip.py
class ClipEngine:
    def __init__(self):
        self.vd = VDevice()    # Kollidiert mit YoloEngine
        ...
```

---

## Empfohlenes Muster: Geteilter Manager mit Owner-Key

```python
"""device_manager.py — Prozessweiter Hailo VDevice-Eigentümer."""
import gc
import os
import threading
from typing import Callable, Dict, Optional, Tuple

_lock = threading.Lock()
_vdevice = None
_models: Dict[str, dict] = {}

# Für physisches Geräte-Sharing mit anderen Prozessen.
_GROUP_ID = os.environ.get("HAILO_VDEVICE_GROUP_ID", "MY_APP_SHARED")


def _ensure_vdevice():
    """Einzelnen VDevice lazy erstellen (Aufrufer muss _lock halten)."""
    global _vdevice
    if _vdevice is not None:
        return _vdevice
    from hailo_platform import VDevice
    params = VDevice.create_params()
    params.group_id = _GROUP_ID
    _vdevice = VDevice(params)
    return _vdevice


def acquire_infer_model(owner: str, hef_path: str) -> Tuple:
    """(InferModel, ConfiguredInferModel) auf dem geteilten VDevice akquirieren.

    Gleicher Eigentümer + gleiche HEF: Bestehende Session wiederverwenden.
    Gleicher Eigentümer, aber andere HEF: Alte freigeben und neue akquirieren.
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
    """GenAI-Modell (LLM / VLM / Speech2Text) akquirieren.

    `factory` ist `(vdevice, model_path) -> erstellte Instanz`.
    Beispiel: `lambda vd, p: LLM(vd, p)`
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
    """Von `owner` gehaltenes Modell freigeben. VDevice selbst bleibt am Leben."""
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
    # InferModel: nur Python-Referenzen fallen lassen
    gc.collect()
    return True


def shutdown() -> None:
    """Beim Prozessende aufrufen: Alle Modelle und VDevice freigeben."""
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
    """Nicht-destruktiver Check — erstellt keinen VDevice."""
    try:
        import hailo_platform  # noqa: F401
        return True
    except ImportError:
        return False
```

---

## Verwendungsbeispiele

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
        return is_hailo_available()   # Kein Gerätekontakt
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

### YOLO + CLIP + LLM koexistieren

Mit unterschiedlichen Owner-Namen können **zwei InferModelle und ein GenAI-Modell gleichzeitig auf demselben VDevice geladen werden**. Der interne HailoRT-Scheduler (ROUND_ROBIN) teilt den Hardware-Zugriff automatisch per Time-Slicing:

```python
yolo = YoloEngine("yolov8n.hef")           # owner="yolo"
clip = ClipEncoder("clip_vit_b_16.hef")    # owner="clip"
llm = MyLlm("Qwen2.5-1.5B-Instruct.hef")   # owner="llm"

# 3 Modelle aktiv auf einem physischen Gerät
bbox = yolo.detect(image)
embedding = clip.encode(image)
text = llm.generate([{"role": "user", "content": "..."}])
```

---

## Wichtige Designpunkte

### 1. `is_available()` darf nicht destruktiv sein

"Health-Checks", die `VDevice` bauen und verwerfen, sind die häufigste Ursache dieser Art von Bugs. Das darf nicht gemacht werden.

Stattdessen prüfen, ob der Import funktioniert:

```python
def is_hailo_available() -> bool:
    try:
        import hailo_platform  # noqa: F401
        return True
    except ImportError:
        return False
```

Für Hardware-Präsenzprüfung ohne `VDevice`-Erstellung: `/sys/class/hailo*` oder `/dev/h1x-*` auf Dateisystem-Ebene prüfen.

### 2. Owner-Name Namensraum-Design

Komponenten, die dieselbe HEF teilen, verwenden **denselben Owner-Namen**. Wenn mehrere Module alle dasselbe YOLOv8n nutzen, teilen sie durch Verwendung von `"yolo"` als Owner automatisch die Session:

```python
# Modul A
yolo_a = acquire_infer_model("yolo", "yolov8n.hef")

# Modul B (gleiche HEF)
yolo_b = acquire_infer_model("yolo", "yolov8n.hef")
# → Gibt gleichen infer_model / configured zurück, kein Neuladen
```

### 3. `group_id` für Cross-Prozess-Sharing verwenden

`VDevice.create_params().group_id` ermöglicht **verschiedenen Prozessen**, dasselbe physische Gerät zu teilen:

```python
params = VDevice.create_params()
params.group_id = "MY_APP_SHARED"   # Über env-Variablen, Konfiguration usw. angleichen
vd = VDevice(params)
```

### 4. Shutdown-Hooks sind unerlässlich

Wenn der Prozess crasht, wird `VDevice` nicht freigegeben und `/dev/h1x-0` wird durch Zombie-File-Descriptors gehalten. Spätere Starts erhalten `HAILO_OUT_OF_PHYSICAL_DEVICES(74)` bis der Prozess beendet wird:

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

Recovery bei Problemen:

```bash
# Prozess finden, der das Gerät hält
lsof /dev/h1x-0        # hailort 5.3.0+
lsof /dev/hailort0     # hailort 5.2.0 und früher

# Erzwungen beenden
kill -9 <PID>
```

### 5. InferModel und GenAI auf demselben VDevice mischen

Verifiziert auf HailoRT 5.2.0 und 5.3.0: **Mehrere InferModelle (z.B. YOLO + CLIP) und mehrere GenAI-Modelle (LLM, VLM, Speech2Text) können auf demselben `VDevice` gleichzeitig koexistieren.**

Hinweis: Der `VDevice`-Instanz selbst muss das **gleiche Python-Objekt** sein. Ein zweites `VDevice()` mit derselben `group_id` aus einer anderen Python-Variablen zu erstellen und Sessions wiederzu­verwenden, führt zu Fehlern bei `InferModel.run()`.

### 6. Cooldown bei Initialisierungsfehlern

Hailo-Initialisierung ist teuer (~1 Sek.). Sofortiges Retry nach einem Fehler führt meist zu weiteren Fehlern. Kurzen Cooldown einführen (z.B. 60 Sek.):

```python
import time
from typing import Optional

_init_failed_at: Optional[float] = None
_INIT_COOLDOWN_SEC = 60.0

def try_initialize():
    global _init_failed_at
    now = time.time()
    if _init_failed_at and (now - _init_failed_at) < _INIT_COOLDOWN_SEC:
        return None  # Noch im Cooldown
    try:
        return acquire_infer_model("yolo", "yolov8n.hef")
    except Exception:
        _init_failed_at = now
        raise
```

---

## Verifiziert auf HailoRT 5.2.0 und 5.3.0

Dieses Muster wurde auf Raspberry Pi 5 + AI HAT 2 in folgenden Umgebungen verifiziert:

- HailoRT 5.2.0 und 5.3.0
- 2× InferModel (YOLOv8n + CLIP ViT-B/16) + 1× GenAI LLM (Qwen2.5-1.5B) gleichzeitig
- 2× InferModel + 1× GenAI VLM (Qwen2-VL-2B) gleichzeitig
- 2× InferModel + 1× GenAI Speech2Text (Whisper-Base) gleichzeitig

Die physische Einschränkung (1 physisches Gerät pro Prozess) gilt auch in 5.3.0 weiterhin. `group_id`-basiertes Sharing und interner ROUND_ROBIN-Scheduler werden weiterhin unterstützt.

---

## Verwandte Dokumente

- HailoRT 5.2.0 → 5.3.0 Migrationshinweise (`HAILORT_5_3_0_MIGRATION.md`)
- Unter dem neuen `hailo1x_pci`-Treiber in 5.3.0 wurde der Device-Node von `/dev/hailort0` zu `/dev/h1x-0` umbenannt
