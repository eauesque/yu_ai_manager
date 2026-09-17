# Pattern : Gestionnaire VDevice partagé pour applications Hailo-10H multi-modèles

Pattern d'implémentation pour faire fonctionner plusieurs modèles Hailo (YOLO / CLIP / LLM / VLM / Whisper, etc.) dans le même processus sur le NPU Hailo-10H d'une application Python.

**Public cible** : Développeurs souhaitant faire coexister plusieurs modèles dans une seule application sur le chip Hailo-10H.

---

## TL;DR

- Le Hailo-10H a **exactement 1 périphérique physique**.
- Créer `VDevice()` deux fois dans le même processus échoue avec :
  `HAILO_OUT_OF_PHYSICAL_DEVICES(74)`
- Causes courantes : libération lazy lors de la commutation de modèles, conflit de préchargeur en arrière-plan, vérifications `is_available()` qui construisent et détruisent `VDevice` en interne.
- Solution : Introduire un **singleton `VDevice` à l'échelle du processus** et permettre à tous les modèles d'y accéder via un registre avec clé de propriétaire.
- Configurer `VDevice.create_params().group_id` permet de **partager le même périphérique physique entre plusieurs processus** (le planificateur HailoRT médiatise l'accès par time-slicing).

---

## Symptômes

```
[HailoRT] [error] Failed to create vdevice. there are not enough free devices. requested: 1, found: 0
[HailoRT] [error] CHECK_SUCCESS failed with status=HAILO_OUT_OF_PHYSICAL_DEVICES(74)
hailo_platform.pyhailort.pyhailort.HailoRTStatusException: 74
```

---

## Scénarios d'échec typiques

### Scénario 1 : Conflit de préchargeur en arrière-plan

```
app startup
  └─ preloader thread
       ├─ CLIP init → VDevice() [A]
       └─ YOLO init → VDevice() [B]  ← [A] détient encore le périphérique → échec
```

### Scénario 2 : Vérification `is_available()` destructive

```python
class YoloEngine:
    @staticmethod
    def is_available():
        try:
            vd = VDevice()   # Acquisition pour vérification
            del vd            # Peut ne pas être libéré immédiatement (timing GC)
            return True
        except Exception:
            return False
```

### Scénario 3 : Libération lazy lors de la commutation de modèles

```python
# del seul ne libère pas VDevice immédiatement
del self.vd                 # Le compteur de références diminue
self.vd = VDevice()         # L'ancien VDevice peut encore être en attente de GC → peut échouer
```

La correction est d'appeler explicitement `self.vd.release()` avant d'en créer un nouveau.

---

## Anti-patterns

```python
# MAUVAIS module_yolo.py
from hailo_platform import VDevice

class YoloEngine:
    def __init__(self):
        self.vd = VDevice()    # Acquisition indépendante
        ...

    @staticmethod
    def is_available():
        try:
            VDevice()              # Vérification de santé destructive
            return True
        except Exception:
            return False


# MAUVAIS module_clip.py
class ClipEngine:
    def __init__(self):
        self.vd = VDevice()    # Entre en conflit avec YoloEngine
        ...
```

---

## Pattern recommandé : Gestionnaire partagé avec clé de propriétaire

```python
"""device_manager.py — Propriétaire VDevice Hailo à l'échelle du processus."""
import gc
import os
import threading
from typing import Callable, Dict, Optional, Tuple

_lock = threading.Lock()
_vdevice = None
_models: Dict[str, dict] = {}

# Utilisé pour le partage du périphérique physique avec d'autres processus.
_GROUP_ID = os.environ.get("HAILO_VDEVICE_GROUP_ID", "MY_APP_SHARED")


def _ensure_vdevice():
    """Création lazy du VDevice unique (l'appelant doit détenir _lock)."""
    global _vdevice
    if _vdevice is not None:
        return _vdevice
    from hailo_platform import VDevice
    params = VDevice.create_params()
    params.group_id = _GROUP_ID
    _vdevice = VDevice(params)
    return _vdevice


def acquire_infer_model(owner: str, hef_path: str) -> Tuple:
    """Acquérir (InferModel, ConfiguredInferModel) sur le VDevice partagé."""
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
    """Acquérir un modèle GenAI (LLM / VLM / Speech2Text).

    `factory` est `(vdevice, model_path) -> instance construite`.
    Exemple : `lambda vd, p: LLM(vd, p)`
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
    """Libérer le modèle détenu par `owner`. VDevice lui-même reste en vie."""
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
    # InferModel : juste supprimer la référence Python
    gc.collect()
    return True


def shutdown() -> None:
    """Appeler à la fin du processus : libérer tous les modèles et VDevice."""
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
    """Vérification non destructive — ne construit pas VDevice."""
    try:
        import hailo_platform  # noqa: F401
        return True
    except ImportError:
        return False
```

---

## Exemples d'utilisation

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
        return is_hailo_available()   # Ne touche pas VDevice
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

### Coexistence YOLO + CLIP + LLM

En utilisant des noms de propriétaires différents, il est possible de **charger simultanément 2 InferModel et 1 modèle GenAI sur le même VDevice**. Le planificateur HailoRT interne (ROUND_ROBIN) gère automatiquement le time-slicing de l'accès matériel :

```python
yolo = YoloEngine("yolov8n.hef")           # owner="yolo"
clip = ClipEncoder("clip_vit_b_16.hef")    # owner="clip"
llm = MyLlm("Qwen2.5-1.5B-Instruct.hef")   # owner="llm"

# 3 modèles actifs sur 1 périphérique physique
bbox = yolo.detect(image)
embedding = clip.encode(image)
text = llm.generate([{"role": "user", "content": "..."}])
```

---

## Points de conception importants

### 1. `is_available()` ne doit pas être destructif

Construire et détruire `VDevice` pour un "health check" est la cause la plus courante de ce type de bug. Ne pas faire cela.

Vérifier plutôt que l'import fonctionne :

```python
def is_hailo_available() -> bool:
    try:
        import hailo_platform  # noqa: F401
        return True
    except ImportError:
        return False
```

### 2. Conception de l'espace de noms des noms de propriétaires

Les composants partageant le même HEF utilisent le **même nom de propriétaire**. Ils partagent automatiquement la session :

```python
# Module A
yolo_a = acquire_infer_model("yolo", "yolov8n.hef")

# Module B (même HEF)
yolo_b = acquire_infer_model("yolo", "yolov8n.hef")
# → Retourne le même infer_model / configured, pas de rechargement
```

### 3. Utiliser `group_id` pour le partage inter-processus

`VDevice.create_params().group_id` permet à **différents processus** de partager le même périphérique physique :

```python
params = VDevice.create_params()
params.group_id = "MY_APP_SHARED"
vd = VDevice(params)
```

### 4. Les hooks d'arrêt sont obligatoires

Si le processus crash, `VDevice` n'est pas libéré et `/dev/h1x-0` est retenu par des file descriptors zombies. Installer des hooks d'arrêt :

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

Récupération en cas de problème :

```bash
# Trouver le processus qui détient le périphérique
lsof /dev/h1x-0        # hailort 5.3.0+
lsof /dev/hailort0     # hailort 5.2.0 et antérieur

# Forcer la terminaison
kill -9 <PID>
```

### 5. Mélange InferModel et GenAI sur le même VDevice

Vérifié sur HailoRT 5.2.0 et 5.3.0 : **Plusieurs InferModel (YOLO + CLIP) et plusieurs modèles GenAI (LLM, VLM, Speech2Text) peuvent coexister simultanément sur le même `VDevice`.**

Note :
- Après avoir créé `VDevice`, vous pouvez appeler `create_infer_model()` et `LLM(vd, path)` sur la même instance.
- Cependant, l'instance `VDevice` elle-même doit être le **même objet Python**. Créer un deuxième `VDevice()` avec le même `group_id` et essayer de réutiliser la session depuis une variable Python différente fera échouer `InferModel.run()`.

### 6. Délai de refroidissement lors des échecs d'initialisation

L'initialisation Hailo est coûteuse (~1 seconde). Un réessai immédiat après un échec conduit souvent à d'autres échecs. Introduire un court délai de refroidissement (ex: 60 secondes) :

```python
import time
from typing import Optional

_init_failed_at: Optional[float] = None
_INIT_COOLDOWN_SEC = 60.0

def try_initialize():
    global _init_failed_at
    now = time.time()
    if _init_failed_at and (now - _init_failed_at) < _INIT_COOLDOWN_SEC:
        return None  # Encore en refroidissement
    try:
        return acquire_infer_model("yolo", "yolov8n.hef")
    except Exception:
        _init_failed_at = now
        raise
```

---

## Vérifié sur HailoRT 5.2.0 et 5.3.0

Ce pattern a été vérifié sur Raspberry Pi 5 + AI HAT 2 avec :

- HailoRT 5.2.0 et 5.3.0
- 2× InferModel (YOLOv8n + CLIP ViT-B/16) + 1× GenAI LLM (Qwen2.5-1.5B) simultanément
- 2× InferModel + 1× GenAI VLM (Qwen2-VL-2B) simultanément
- 2× InferModel + 1× GenAI Speech2Text (Whisper-Base) simultanément

La contrainte physique (1 périphérique physique par processus) reste inchangée dans 5.3.0. Le partage basé sur `group_id` et le planificateur ROUND_ROBIN interne continuent d'être supportés.
