# Управление устройством Hailo-10H

## Обзор

Hailo-10H NPU может **выполнять несколько моделей одновременно**.
Встроенный планировщик ROUND_ROBIN автоматически распределяет доступ к железу между моделями по времени.

В yu_ai_manager поддерживается единственный общий VDevice, что позволяет CLIP, YOLO, LLM, VLM и Speech2Text
одновременно загружаться и выполнять инференс. Совместное использование с внешними процессами (hailo-ollama)
поддерживается через `group_id`.

## Архитектура

```
┌─────────────────────────────────────────────┐
│              Shared VDevice                  │
│         (group_id = YU_SHARED)               │
│                                              │
│  ┌─────────┐ ┌─────────┐ ┌───────────────┐  │
│  │  CLIP   │ │  YOLO   │ │  LLM (GenAI)  │  │
│  │InferMdl │ │InferMdl │ │  VLM / S2T    │  │
│  └─────────┘ └─────────┘ └───────────────┘  │
│                                              │
│     HailoRT ROUND_ROBIN Scheduler            │
└─────────────────────────────────────────────┘
```

- InferModel API (CLIP, YOLO) и GenAI API (LLM, VLM, S2T) сосуществуют на одном VDevice
- Все модели должны создаваться на **одном экземпляре VDevice** (на разных не работает)

## Сравнение двух режимов

| | Python SDK (Hailo VLM) | hailo-ollama-vlm (OpenAI-совместимый) |
|---|---|---|
| Управление устройством | device_manager в yu | Внешний C++ сервер |
| Совместимость с CLIP Search | Да (одновременная работа) | Да (общий group_id, v5.3.0+) |
| Скорость инференса | Одинаковая | Одинаковая |
| Накладные расходы | ~15ms | ~200-400ms (base64+HTTP) |
| Несколько клиентов | Нет | Возможно |
| Flask-поток | Блокируется на время инференса | Только ожидание HTTP |

## Общий VDevice (group_id)

### Совместное использование внутри процесса

`device_manager.py` управляет автоматически. Все модели используют один VDevice.

Изменить group_id через переменную окружения:
```bash
export HAILO_VDEVICE_GROUP_ID=MY_GROUP
```

По умолчанию: `YU_SHARED`

### Совместное использование с hailo-ollama (v5.3.0+)

hailo-ollama v5.3.0 и выше поддерживает переменную окружения `HAILO_OLLAMA_VDEVICE_GROUP_ID`.
При установке того же group_id, что и у yu_ai_manager, оба процесса будут использовать устройство совместно:

```bash
# Сторона yu_ai_manager
export HAILO_VDEVICE_GROUP_ID=SHARED

# Сторона hailo-ollama
HAILO_OLLAMA_VDEVICE_GROUP_ID=SHARED hailo-ollama
```

**Примечание**: group_id работает в yu_ai_manager начиная с HailoRT 5.2.0.
hailo-ollama принимает group_id только начиная с v5.3.0.

## device_manager API

### Получение модели

```python
from core.hailo_device_core.device_manager import acquire_device, acquire_genai

# InferModel (CLIP, YOLO)
infer_model, configured, quant_params = acquire_device("clip", "/path/to.hef")

# GenAI (LLM, VLM, S2T)
llm = acquire_genai("llm", "/path/to.hef", lambda vd, p: LLM(vd, p))
```

- Тот же owner + тот же HEF → повторное использование существующей сессии
- Тот же owner + другой HEF → освобождение старой модели и создание новой
- Другой owner → **сосуществование** (старая модель не освобождается)

### Освобождение модели

```python
from core.hailo_device_core.device_manager import release_device, shutdown_all

release_device("clip")   # Освободить только CLIP, остальные продолжают работать
shutdown_all()            # Освободить все модели + VDevice (при завершении процесса)
```

### Проверка состояния

```python
from core.hailo_device_core.device_manager import (
    get_active_owners, is_model_active,
    is_hailo_available, is_genai_available,
)

get_active_owners()       # ["clip", "yolo", "llm"]
is_model_active("clip")   # True
```

## Устранение неполадок

### Ошибка создания VDevice

**Симптом**: `HAILO_OUT_OF_PHYSICAL_DEVICES(74)` или `Failed to create VDevice`

**Причина**: Другой процесс занимает устройство с другим group_id

**Решение**:
1. Проверить, запущен ли hailo-ollama:
   ```bash
   ps aux | grep hailo-ollama
   ```
2. Установить одинаковый group_id или остановить:
   ```bash
   sudo systemctl stop hailo-ollama
   ```

### Устройство не освобождается

**Решение**:
1. Перезапустить процесс yu
2. Проверить зомби-процессы:
   ```bash
   sudo lsof /dev/hailo* 2>/dev/null
   kill <PID>
   ```
3. Сбросить драйвер Hailo:
   ```bash
   sudo systemctl restart hailort.service
   ```

## Руководство по выбору API

| Структура модели | Рекомендуемый API | Причина |
|---|---|---|
| Простая (1 вход, YOLO и т.д.) | `InferModel` | Работает с `create_infer_model()` + `configure()` |
| Сложная (2+ входа, Whisper и т.д.) | `GenAI SDK` | InferModel возвращает `INVALID_ARGUMENT` |
| CLIP энкодер | `InferModel` | 1 вход, 1 выход — без проблем |
| LLM (qwen2.5 и т.д.) | `GenAI SDK` | Требует авторегрессивное декодирование |

## История

- **v4.61.0**: Переход на общий VDevice. Отказ от эксклюзивного acquire/release, поддержка одновременной работы CLIP + YOLO + LLM.
- **v4.60.1**: Всех потребителей унифицировали через device_manager (эксклюзивный режим).
- **v4.60.0 и ранее**: Каждый потребитель вызывал VDevice() отдельно, что вызывало частые ошибки конфликта.
