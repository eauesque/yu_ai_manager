# Padrão: Gerenciador VDevice Compartilhado para Aplicações Hailo-10H Multi-Modelo

Padrão de implementação para fazer funcionar múltiplos modelos Hailo (YOLO / CLIP / LLM / VLM / Whisper, etc.) na NPU Hailo-10H no mesmo processo de uma aplicação Python.

**Público-alvo**: Desenvolvedores que desejam fazer coexistir múltiplos modelos em uma única aplicação no chip Hailo-10H.

---

## TL;DR

- O Hailo-10H tem **exatamente 1 dispositivo físico**.
- Criar `VDevice()` duas vezes no mesmo processo falha com:
  `HAILO_OUT_OF_PHYSICAL_DEVICES(74)`
- Causas comuns: release lazy ao trocar modelos, conflito de preloaders em background, verificação `is_available()` que constrói e destrói `VDevice`.
- Solução: Introduzir um **singleton `VDevice` para todo o processo**, e todos os modelos acessam através de um registro com chave de owner.
- Configurar `VDevice.create_params().group_id` permite que o mesmo dispositivo físico seja **compartilhado entre múltiplos processos** também (o scheduler HailoRT media o acesso por time-slicing).

---

## Sintomas

```
[HailoRT] [error] Failed to create vdevice. there are not enough free devices. requested: 1, found: 0
[HailoRT] [error] CHECK_SUCCESS failed with status=HAILO_OUT_OF_PHYSICAL_DEVICES(74)
hailo_platform.pyhailort.pyhailort.HailoRTStatusException: 74
```

O stack trace geralmente aponta para a inicialização de YOLO, CLIP ou LLM, mas a causa real é que **outro componente** adquiriu `VDevice` anteriormente e não o liberou.

---

## Cenários Típicos de Falha

### Cenário 1: Conflito de Preloader em Background

```
app startup
  └─ preloader thread
       ├─ CLIP init → VDevice() [A]
       └─ YOLO init → VDevice() [B]  ← [A] ainda mantém o dispositivo → falha
```

### Cenário 2: Verificação `is_available()` Destrutiva

```python
class YoloEngine:
    @staticmethod
    def is_available():
        try:
            vd = VDevice()   # adquirir para verificação
            del vd            # pode não ser liberado imediatamente (timing do GC)
            return True
        except Exception:
            return False

# Chamador
if YoloEngine.is_available():     # VDevice adquirido e descartado aqui
    engine = YoloEngine()          # Tenta adquirir novamente → pode falhar
```

### Cenário 3: Release Lazy ao Trocar Modelos

```python
# Apenas del não libera VDevice imediatamente
del self.vd                 # contagem de referência cai
self.vd = VDevice()         # VDevice anterior pode ainda estar esperando GC → falha
```

A correção é chamar `self.vd.release()` explicitamente antes de criar um novo.

### Cenário 4: Módulos Independentes Inicializam de Forma Independente

Quando múltiplos módulos funcionais (extensions, plugins, etc.) cada um chama `VDevice()` ao carregar, conflitos são quase certos.

---

## Anti-padrões

```python
# ❌ module_yolo.py
from hailo_platform import VDevice

class YoloEngine:
    def __init__(self):
        self.vd = VDevice()    # aquisição independente
        self.model = self.vd.create_infer_model("yolov8n.hef")
        self.configured = self.model.configure()

    @staticmethod
    def is_available():
        try:
            VDevice()              # health check destrutivo
            return True
        except Exception:
            return False


# ❌ module_clip.py
class ClipEngine:
    def __init__(self):
        self.vd = VDevice()    # conflita com YoloEngine
        ...
```

---

## Padrão Recomendado: Gerenciador Compartilhado com Chave de Owner

```python
"""device_manager.py — owner do VDevice para todo o processo."""
import gc
import os
import threading
from typing import Callable, Dict, Optional, Tuple

_lock = threading.Lock()
_vdevice = None
_models: Dict[str, dict] = {}

# Usado para compartilhar o dispositivo físico com outros processos.
_GROUP_ID = os.environ.get("HAILO_VDEVICE_GROUP_ID", "MY_APP_SHARED")


def _ensure_vdevice():
    """Criação lazy de VDevice único (chamador deve manter _lock)."""
    global _vdevice
    if _vdevice is not None:
        return _vdevice
    from hailo_platform import VDevice
    params = VDevice.create_params()
    params.group_id = _GROUP_ID
    _vdevice = VDevice(params)
    return _vdevice


def acquire_infer_model(owner: str, hef_path: str) -> Tuple:
    """Adquirir (InferModel, ConfiguredInferModel) no VDevice compartilhado.

    Mesmo owner + mesmo HEF reutiliza sessão existente. Mesmo owner mas
    HEF diferente libera o antigo antes de adquirir o novo.
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
    """Adquirir modelo GenAI (LLM / VLM / Speech2Text).

    `factory` é `(vdevice, model_path) -> instância construída`.
    Ex: `lambda vd, p: LLM(vd, p)`
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
    """Liberar modelo mantido pelo `owner`. Mantém o VDevice vivo."""
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
    # InferModel apenas descarta referências Python
    gc.collect()
    return True


def shutdown() -> None:
    """Chamar ao sair do processo: liberar todos os modelos e VDevice."""
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
    """Verificação não destrutiva — não constrói VDevice."""
    try:
        import hailo_platform  # noqa: F401
        return True
    except ImportError:
        return False
```

---

## Exemplos de Uso

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
        return is_hailo_available()   # Não toca no VDevice
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

### Coexistência de YOLO + CLIP + LLM

Usando nomes de owner diferentes, você pode **carregar 2 InferModels e 1 modelo GenAI no mesmo VDevice simultaneamente**. O scheduler interno HailoRT (ROUND_ROBIN) faz time-slicing automático do acesso de hardware:

```python
yolo = YoloEngine("yolov8n.hef")           # owner="yolo"
clip = ClipEncoder("clip_vit_b_16.hef")    # owner="clip"
llm = MyLlm("Qwen2.5-1.5B-Instruct.hef")   # owner="llm"

# 3 modelos ativos no mesmo dispositivo físico
bbox = yolo.detect(image)
embedding = clip.encode(image)
text = llm.generate([{"role": "user", "content": "..."}])
```

---

## Pontos de Design Importantes

### 1. `is_available()` não deve ser Destrutivo

Health checks que constroem e destroem `VDevice` são a causa mais comum desse tipo de bug. Não faça isso.

Em vez disso, confirme que o import funciona:

```python
def is_hailo_available() -> bool:
    try:
        import hailo_platform  # noqa: F401
        return True
    except ImportError:
        return False
```

Se você quiser verificar a presença do hardware sem construir `VDevice` com propósito de destruição, verifique o sistema de arquivos em nível `/sys/class/hailo*` ou `/dev/h1x-*`.

### 2. Design de Namespace de Nomes de Owner

Componentes que devem compartilhar o mesmo HEF usam o **mesmo nome de owner**. Se múltiplos módulos usam o mesmo YOLOv8n, todos adquirindo com owner `"yolo"` compartilham automaticamente a sessão:

```python
# Módulo A
yolo_a = acquire_infer_model("yolo", "yolov8n.hef")

# Módulo B (mesmo HEF)
yolo_b = acquire_infer_model("yolo", "yolov8n.hef")
# → retorna o mesmo infer_model / configured, sem reload
```

Componentes com HEF único recebem nomes de owner únicos:

| Componente | Owner | Nota |
|---|---|---|
| YOLO genérico | `"yolo"` | Compartilhado |
| CLIP genérico | `"clip"` | Compartilhado |
| Tagger personalizado (HEF único) | `"my-tagger"` | Único |
| LLM | `"llm"` | GenAI |
| VLM | `"vlm"` | GenAI |
| Speech2Text | `"s2t"` | GenAI |

### 3. Usar `group_id` para Compartilhamento Entre Processos

Configurar `VDevice.create_params().group_id` permite que **processos diferentes** compartilhem o mesmo dispositivo físico:

```python
params = VDevice.create_params()
params.group_id = "MY_APP_SHARED"   # Alinhar via env vars, config, etc.
vd = VDevice(params)
```

Outro processo que chama `VDevice(params)` com o mesmo `group_id` terá seus requests paralelizados por time-slicing pelo scheduler HailoRT. É assim que ferramentas externas como `hailo-ollama` funcionam em paralelo com processos de inferência próprios.

### 4. Hooks de Shutdown São Obrigatórios

Quando o processo trava, o `VDevice` não é liberado e `/dev/h1x-0` permanece mantido por file descriptors zumbis. A inicialização subsequente receberá `HAILO_OUT_OF_PHYSICAL_DEVICES(74)` até matar `/dev/h1x-0`. Instale hooks de shutdown:

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

Recuperação quando problemas ocorrem:

```bash
# Encontrar processo mantendo o dispositivo
lsof /dev/h1x-0        # hailort 5.3.0+
lsof /dev/hailort0     # anterior ao hailort 5.2.0

# Forçar matar
kill -9 <PID>
```

### 5. Misturando InferModel e GenAI no Mesmo VDevice

Verificado com HailoRT 5.2.0 e 5.3.0: **Você pode fazer coexistir múltiplos InferModels (ex: YOLO + CLIP) e múltiplos modelos GenAI (LLM, VLM, Speech2Text) no mesmo `VDevice` simultaneamente.**

Ressalvas:

- Após criar o `VDevice`, você pode chamar tanto `create_infer_model()` quanto `LLM(vd, path)` na mesma instância.
- No entanto, a instância `VDevice` em si deve ser o **mesmo objeto Python**. Tentar criar um segundo `VDevice()` com o mesmo `group_id` e reutilizar sessões de outra variável Python causará falhas em `InferModel.run()`.

### 6. Cooldown Após Falha de Inicialização

A inicialização do Hailo é cara (~1 segundo). Tentativas imediatas após falha frequentemente causam mais falhas. Introduza um curto cooldown (ex: 60 segundos) para suprimir tempestades de retry:

```python
import time
from typing import Optional

_init_failed_at: Optional[float] = None
_INIT_COOLDOWN_SEC = 60.0

def try_initialize():
    global _init_failed_at
    now = time.time()
    if _init_failed_at and (now - _init_failed_at) < _INIT_COOLDOWN_SEC:
        return None  # ainda em cooldown
    try:
        return acquire_infer_model("yolo", "yolov8n.hef")
    except Exception:
        _init_failed_at = now
        raise
```

---

## Verificado com HailoRT 5.2.0 e 5.3.0

Este padrão foi verificado no Raspberry Pi 5 + AI HAT 2 nos seguintes ambientes:

- HailoRT 5.2.0 e 5.3.0
- 2× InferModel (YOLOv8n + CLIP ViT-B/16) + 1× GenAI LLM (Qwen2.5-1.5B) simultaneamente
- 2× InferModel + 1× GenAI VLM (Qwen2-VL-2B) simultaneamente
- 2× InferModel + 1× GenAI Speech2Text (Whisper-Base) simultaneamente

A restrição física (1 dispositivo físico por processo) não muda no 5.3.0. O compartilhamento baseado em `group_id` e o scheduler ROUND_ROBIN interno continuam suportados.

---

## Relacionado

- Notas de migração HailoRT 5.2.0 → 5.3.0 (`HAILORT_5_3_0_MIGRATION.md`)
- No novo driver `hailo1x_pci` do 5.3.0, o nó de dispositivo foi renomeado de `/dev/hailort0` para `/dev/h1x-0`
