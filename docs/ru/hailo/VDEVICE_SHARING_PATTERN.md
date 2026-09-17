# Паттерн: Общий менеджер VDevice для Hailo-10H приложений с несколькими моделями

Паттерн реализации для совместной работы нескольких моделей Hailo (YOLO / CLIP / LLM / VLM / Whisper)
на Hailo-10H NPU в одном процессе.

**Целевая аудитория**: Разработчики, которым нужно сосуществование нескольких моделей
на одном чипе Hailo-10H в едином приложении.

---

## TL;DR

- Hailo-10H имеет **ровно одно физическое устройство**.
- Создание `VDevice()` дважды в одном процессе завершается ошибкой:
  `HAILO_OUT_OF_PHYSICAL_DEVICES(74)`
- Типичные причины: ленивое освобождение при смене модели, конфликт фонового предзагрузчика,
  проверки `is_available()`, которые создают и уничтожают `VDevice` внутри.
- Решение: **Синглтон `VDevice` для всего процесса** — все модели обращаются через реестр с ключом владельца.
- Установка `VDevice.create_params().group_id` позволяет **совместно использовать одно физическое устройство между процессами** (планировщик HailoRT управляет доступом через временное нарезание).

---

## Симптомы

```
[HailoRT] [error] Failed to create vdevice. there are not enough free devices. requested: 1, found: 0
[HailoRT] [error] CHECK_SUCCESS failed with status=HAILO_OUT_OF_PHYSICAL_DEVICES(74)
hailo_platform.pyhailort.pyhailort.HailoRTStatusException: 74
```

Стек вызовов обычно указывает на инициализацию YOLO, CLIP или LLM, но истинная причина —
**другой компонент** ранее получил `VDevice` и не освободил его.

---

## Типичные сценарии сбоев

### Сценарий 1: Конфликт фонового предзагрузчика

```
запуск приложения
  └─ поток предзагрузчика
       ├─ инит CLIP → VDevice() [A]
       └─ инит YOLO → VDevice() [B]  ← [A] удерживает устройство → сбой
```

### Сценарий 2: Деструктивная проверка `is_available()`

```python
class YoloEngine:
    @staticmethod
    def is_available():
        try:
            vd = VDevice()   # Получить для проверки
            del vd            # Может не освободиться немедленно (зависит от GC)
            return True
        except Exception:
            return False

# Вызывающий код
if YoloEngine.is_available():     # Здесь получает и уничтожает VDevice
    engine = YoloEngine()          # Пытается получить снова → возможный сбой
```

### Сценарий 3: Ленивое освобождение при смене модели

```python
# del не освобождает VDevice немедленно
del self.vd                 # Счётчик ссылок уменьшается
self.vd = VDevice()         # Предыдущий VDevice ещё ждёт GC → возможный сбой
```

Исправление — явно вызвать `self.vd.release()` перед созданием нового.

---

## Рекомендуемый паттерн: Общий менеджер с ключом владельца

```python
"""device_manager.py — Владелец VDevice Hailo для всего процесса."""
import gc
import os
import threading
from typing import Callable, Dict, Optional, Tuple

_lock = threading.Lock()
_vdevice = None
_models: Dict[str, dict] = {}

_GROUP_ID = os.environ.get("HAILO_VDEVICE_GROUP_ID", "MY_APP_SHARED")


def _ensure_vdevice():
    """Лениво создать единственный VDevice (вызывающий должен держать _lock)."""
    global _vdevice
    if _vdevice is not None:
        return _vdevice
    from hailo_platform import VDevice
    params = VDevice.create_params()
    params.group_id = _GROUP_ID
    _vdevice = VDevice(params)
    return _vdevice


def acquire_infer_model(owner: str, hef_path: str) -> Tuple:
    """Получить (InferModel, ConfiguredInferModel) на общем VDevice."""
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


def acquire_genai(owner: str, model_path: str, factory: Callable) -> object:
    """Получить GenAI-модель (LLM / VLM / Speech2Text)."""
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
    """Освободить модель `owner`. VDevice остаётся живым."""
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
    gc.collect()
    return True


def shutdown() -> None:
    """Вызывать при завершении процесса: освободить все модели и VDevice."""
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
    """Неразрушающая проверка — не создаёт VDevice."""
    try:
        import hailo_platform  # noqa: F401
        return True
    except ImportError:
        return False
```

---

## Ключевые принципы проектирования

### 1. `is_available()` не должен быть деструктивным

Создание и уничтожение `VDevice` в «проверке работоспособности» — наиболее распространённая причина этого бага.
Вместо этого проверяйте доступность импорта:

```python
def is_hailo_available() -> bool:
    try:
        import hailo_platform  # noqa: F401
        return True
    except ImportError:
        return False
```

### 2. Дизайн пространства имён ключей владельцев

Компоненты, использующие один и тот же HEF, используют **одно имя владельца** — они автоматически разделяют сессию.
Компоненты с уникальными HEF получают уникальные имена владельцев:

| Компонент | Владелец | Примечание |
|-----------|----------|-----------|
| Общий YOLO | `"yolo"` | Общий |
| Общий CLIP | `"clip"` | Общий |
| Кастомный тэггер (уникальный HEF) | `"my-tagger"` | Уникальный |
| LLM | `"llm"` | GenAI |
| VLM | `"vlm"` | GenAI |
| Speech2Text | `"s2t"` | GenAI |

### 3. Использовать `group_id` для межпроцессного совместного использования

```python
params = VDevice.create_params()
params.group_id = "MY_APP_SHARED"
vd = VDevice(params)
```

### 4. Хуки завершения обязательны

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

Восстановление при проблемах:

```bash
# Найти процесс, удерживающий устройство
lsof /dev/h1x-0        # hailort 5.3.0+

# Принудительно завершить
kill -9 <PID>
```

### 5. Одновременное использование InferModel и GenAI на одном VDevice

Проверено на HailoRT 5.2.0 и 5.3.0: **несколько InferModel (YOLO + CLIP) и несколько GenAI-моделей
(LLM, VLM, Speech2Text) могут сосуществовать на одном `VDevice` одновременно.**

### 6. Охлаждение при сбое инициализации

```python
import time
from typing import Optional

_init_failed_at: Optional[float] = None
_INIT_COOLDOWN_SEC = 60.0

def try_initialize():
    global _init_failed_at
    now = time.time()
    if _init_failed_at and (now - _init_failed_at) < _INIT_COOLDOWN_SEC:
        return None  # Ещё в периоде охлаждения
    try:
        return acquire_infer_model("yolo", "yolov8n.hef")
    except Exception:
        _init_failed_at = now
        raise
```

---

## Проверено на HailoRT 5.2.0 и 5.3.0

Паттерн проверен на Raspberry Pi 5 + AI HAT 2 при следующих конфигурациях:

- 2× InferModel (YOLOv8n + CLIP ViT-B/16) + 1× GenAI LLM (Qwen2.5-1.5B) одновременно
- 2× InferModel + 1× GenAI VLM (Qwen2-VL-2B) одновременно
- 2× InferModel + 1× GenAI Speech2Text (Whisper-Base) одновременно
