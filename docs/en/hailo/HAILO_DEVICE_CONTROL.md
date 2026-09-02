# Hailo-10H Device Control

## Overview

The Hailo-10H NPU can **execute multiple models concurrently**.
The built-in ROUND_ROBIN scheduler automatically time-slices hardware access among models.

yu_ai_manager maintains a single shared VDevice, allowing CLIP, YOLO, LLM, VLM, and Speech2Text
to be loaded and run inference simultaneously. Sharing with external processes (hailo-ollama) is supported via `group_id`.

## Architecture

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

- The InferModel API (CLIP, YOLO) and GenAI API (LLM, VLM, S2T) coexist on the same VDevice
- All models must be created on **the same VDevice instance** (they will not work on separate instances)

## Comparison of the Two Modes

| | Python SDK (Hailo VLM) | hailo-ollama-vlm (OpenAI-compatible) |
|---|---|---|
| Device management | yu's device_manager | External C++ server |
| Coexistence with CLIP search | Yes (concurrent operation) | Yes (group_id sharing, v5.3.0+) |
| Inference speed | Same | Same |
| Overhead | ~15ms | ~200-400ms (base64+HTTP) |
| Multiple clients | No | Yes |
| Flask thread | Blocked during inference | HTTP wait only |

## VDevice Sharing (group_id)

### In-Process Sharing

`device_manager.py` manages this automatically. All models share the same VDevice.

The group_id can be changed via an environment variable:
```bash
export HAILO_VDEVICE_GROUP_ID=MY_GROUP
```

Default: `YU_SHARED`

### Coexistence with hailo-ollama (v5.3.0+)

hailo-ollama v5.3.0 and later supports the `HAILO_OLLAMA_VDEVICE_GROUP_ID` environment variable.
Setting the same group_id as yu_ai_manager allows both processes to share the device:

```bash
# yu_ai_manager side
export HAILO_VDEVICE_GROUP_ID=SHARED

# hailo-ollama side
HAILO_OLLAMA_VDEVICE_GROUP_ID=SHARED hailo-ollama
```

**Note**: yu_ai_manager requires HailoRT 5.2.0 or later for group_id to work.
hailo-ollama requires v5.3.0 or later to accept group_id.

## device_manager API

### Acquiring Models

```python
from core.hailo_device_core.device_manager import acquire_device, acquire_genai

# InferModel (CLIP, YOLO)
infer_model, configured, quant_params = acquire_device("clip", "/path/to.hef")

# GenAI (LLM, VLM, S2T)
llm = acquire_genai("llm", "/path/to.hef", lambda vd, p: LLM(vd, p))
```

- Same owner + same HEF -> reuses the existing session
- Same owner + different HEF -> releases the old model and creates a new one
- Different owner -> **coexists** (the old model is not released)

### Releasing Models

```python
from core.hailo_device_core.device_manager import release_device, shutdown_all

release_device("clip")   # Release CLIP only, others continue
shutdown_all()            # Release all models + VDevice (at process exit)
```

### Checking Status

```python
from core.hailo_device_core.device_manager import (
    get_active_owners, is_model_active,
    is_hailo_available, is_genai_available,
)

get_active_owners()       # ["clip", "yolo", "llm"]
is_model_active("clip")   # True
```

## Troubleshooting

### VDevice Creation Error

**Symptom**: `HAILO_OUT_OF_PHYSICAL_DEVICES(74)` or `Failed to create VDevice`

**Cause**: Another process is occupying the device with a different group_id

**Resolution**:
1. Check if hailo-ollama is running:
   ```bash
   ps aux | grep hailo-ollama
   ```
2. Either align the group_id or stop the process:
   ```bash
   sudo systemctl stop hailo-ollama
   ```

### Device Not Released

**Resolution**:
1. Restart the yu process
2. Check for zombie processes:
   ```bash
   sudo lsof /dev/hailo* 2>/dev/null
   kill <PID>
   ```
3. Reset the Hailo driver:
   ```bash
   sudo systemctl restart hailort.service
   ```

## API Selection Guide

| Model Structure | Recommended API | Reason |
|---|---|---|
| Simple (1 input, YOLO, etc.) | `InferModel` | Works with `create_infer_model()` + `configure()` |
| Complex (2+ inputs, Whisper, etc.) | `GenAI SDK` | InferModel returns `INVALID_ARGUMENT` |
| CLIP encoder | `InferModel` | Single input, single output, no issues |
| LLM (qwen2.5, etc.) | `GenAI SDK` | Requires autoregressive decoding |

## History

- **v4.61.0**: Migrated to shared VDevice approach. Removed exclusive acquire/release in favor of concurrent CLIP + YOLO + LLM operation.
- **v4.60.1**: Unified all consumers to go through device_manager (exclusive mode).
- **v4.60.0 and earlier**: Each consumer called VDevice() individually, causing frequent conflict errors.
