# Control de Dispositivos Hailo-10H

## Resumen

La NPU Hailo-10H puede **ejecutar múltiples modelos simultáneamente**.
El scheduler ROUND_ROBIN incorporado divide automáticamente el tiempo de acceso al hardware entre los modelos.

En yu_ai_manager se mantiene un único VDevice compartido, lo que permite que CLIP, YOLO, LLM, VLM y Speech2Text se carguen e infieran simultáneamente. El compartido con procesos externos (hailo-ollama) también se gestiona con `group_id`.

## Arquitectura

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

- La API InferModel (CLIP, YOLO) y la API GenAI (LLM, VLM, S2T) coexisten en el mismo VDevice
- Todos los modelos deben crearse en la **misma instancia VDevice** (no funciona con instancias separadas)

## Comparación de los dos modos

| | Python SDK (Hailo VLM) | hailo-ollama-vlm (compatible con OpenAI) |
|---|---|---|
| Gestión de dispositivos | device_manager de yu | Servidor C++ externo |
| Coexistencia con búsqueda CLIP | Posible (funcionamiento simultáneo) | Posible (compartición group_id, v5.3.0+) |
| Velocidad de inferencia | Igual | Igual |
| Overhead | ~15ms | ~200-400ms (base64+HTTP) |
| Múltiples clientes | No posible | Posible |
| Hilos Flask | Bloqueante durante inferencia | Solo espera HTTP |

## Compartición VDevice (group_id)

### Compartición dentro del proceso

`device_manager.py` gestiona automáticamente. Todos los modelos comparten el mismo VDevice.

Se puede cambiar el group_id con variable de entorno:
```bash
export HAILO_VDEVICE_GROUP_ID=MY_GROUP
```

Predeterminado: `YU_SHARED`

### Coexistencia con hailo-ollama (v5.3.0+)

hailo-ollama v5.3.0 y posteriores soportan la variable de entorno `HAILO_OLLAMA_VDEVICE_GROUP_ID`.
Configurando el mismo group_id que yu_ai_manager, ambos procesos pueden compartir el dispositivo:

```bash
# Lado de yu_ai_manager
export HAILO_VDEVICE_GROUP_ID=SHARED

# Lado de hailo-ollama
HAILO_OLLAMA_VDEVICE_GROUP_ID=SHARED hailo-ollama
```

**Nota**: group_id funciona en yu_ai_manager con HailoRT 5.2.0 o posterior.
hailo-ollama solo acepta group_id con v5.3.0 o posterior.

## API de device_manager

### Obtener modelo

```python
from core.hailo_device_core.device_manager import acquire_device, acquire_genai

# InferModel (CLIP, YOLO)
infer_model, configured, quant_params = acquire_device("clip", "/path/to.hef")

# GenAI (LLM, VLM, S2T)
llm = acquire_genai("llm", "/path/to.hef", lambda vd, p: LLM(vd, p))
```

- Mismo propietario + mismo HEF → Reutilizar sesión existente
- Mismo propietario + HEF diferente → Liberar modelo antiguo y crear nuevo
- Propietario diferente → **Coexistencia** (el modelo antiguo no se libera)

### Liberar modelo

```python
from core.hailo_device_core.device_manager import release_device, shutdown_all

release_device("clip")   # Solo libera CLIP, el resto continúa
shutdown_all()            # Libera todos los modelos + VDevice (al terminar el proceso)
```

### Verificar estado

```python
from core.hailo_device_core.device_manager import (
    get_active_owners, is_model_active,
    is_hailo_available, is_genai_available,
)

get_active_owners()       # ["clip", "yolo", "llm"]
is_model_active("clip")   # True
```

## Solución de problemas

### Error al crear VDevice

**Síntoma**: `HAILO_OUT_OF_PHYSICAL_DEVICES(74)` o `Failed to create VDevice`

**Causa**: Otro proceso ocupa el dispositivo con un group_id diferente

**Solución**:
1. Verificar si hailo-ollama está en ejecución:
   ```bash
   ps aux | grep hailo-ollama
   ```
2. Hacer coincidir el group_id o detenerlo:
   ```bash
   sudo systemctl stop hailo-ollama
   ```

### El dispositivo no se libera

**Solución**:
1. Reiniciar el proceso de yu
2. Verificar procesos zombi:
   ```bash
   sudo lsof /dev/hailo* 2>/dev/null
   kill <PID>
   ```
3. Reiniciar el driver Hailo:
   ```bash
   sudo systemctl restart hailort.service
   ```

## Guía de elección de API

| Estructura del modelo | API recomendada | Razón |
|---|---|---|
| Simple (1 entrada, YOLO, etc.) | `InferModel` | Funciona con `create_infer_model()` + `configure()` |
| Complejo (2+ entradas, Whisper, etc.) | `GenAI SDK` | InferModel devuelve `INVALID_ARGUMENT` |
| Codificador CLIP | `InferModel` | Sin problemas con 1 entrada, 1 salida |
| LLM (qwen2.5, etc.) | `GenAI SDK` | Requiere decodificación autoregresiva |

## Historial

- **v4.61.0**: Migración al método VDevice compartido. Se eliminó la exclusión acquire/release y se habilitó el funcionamiento simultáneo de CLIP + YOLO + LLM.
- **v4.60.1**: Unificación de todos los consumidores a través de device_manager (método exclusivo).
- **Anterior a v4.60.0**: Cada consumidor llamaba a VDevice() individualmente, con frecuentes errores de conflicto.
