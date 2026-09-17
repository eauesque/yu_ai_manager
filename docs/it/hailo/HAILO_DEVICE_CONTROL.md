# Controllo Dispositivo Hailo-10H

## Panoramica

L'NPU Hailo-10H può **eseguire più modelli contemporaneamente**.
Lo scheduler ROUND_ROBIN integrato divide automaticamente l'accesso hardware tra i modelli in time-sharing.

In yu_ai_manager viene mantenuto un singolo VDevice condiviso, e CLIP, YOLO, LLM, VLM, Speech2Text possono essere caricati e inferire contemporaneamente. La condivisione con processi esterni (hailo-ollama) è gestita tramite `group_id`.

## Architettura

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

- Le API InferModel (CLIP, YOLO) e GenAI API (LLM, VLM, S2T) coesistono sullo stesso VDevice
- Tutti i modelli devono essere creati sulla **stessa istanza VDevice** (non funziona con istanze separate)

## Confronto tra due Modalità

| | Python SDK (Hailo VLM) | hailo-ollama-vlm (compatibile OpenAI) |
|---|---|---|
| Gestione dispositivo | device_manager di yu | Server C++ esterno |
| Coesistenza con CLIP | Possibile (funzionamento simultaneo) | Possibile (condivisione group_id, v5.3.0+) |
| Velocità inferenza | Uguale | Uguale |
| Overhead | ~15ms | ~200-400ms (base64+HTTP) |
| Client multipli | Non possibile | Possibile |
| Thread Flask | Blocca durante inferenza | Solo attesa HTTP |

## Condivisione VDevice (group_id)

### Condivisione all'interno del Processo

`device_manager.py` gestisce automaticamente. Tutti i modelli condividono lo stesso VDevice.

È possibile cambiare group_id tramite variabile d'ambiente:
```bash
export HAILO_VDEVICE_GROUP_ID=MY_GROUP
```

Default: `YU_SHARED`

### Coesistenza con hailo-ollama (v5.3.0+)

hailo-ollama versione 5.3.0 e successive supportano la variabile d'ambiente `HAILO_OLLAMA_VDEVICE_GROUP_ID`.
Impostando lo stesso group_id di yu_ai_manager, entrambi i processi possono condividere il dispositivo:

```bash
# Lato yu_ai_manager
export HAILO_VDEVICE_GROUP_ID=SHARED

# Lato hailo-ollama
HAILO_OLLAMA_VDEVICE_GROUP_ID=SHARED hailo-ollama
```

**Nota**: In yu_ai_manager il group_id funziona a partire da HailoRT 5.2.0.
hailo-ollama non accetta group_id prima della v5.3.0.

## API device_manager

### Acquisizione del Modello

```python
from core.hailo_device_core.device_manager import acquire_device, acquire_genai

# InferModel (CLIP, YOLO)
infer_model, configured, quant_params = acquire_device("clip", "/path/to.hef")

# GenAI (LLM, VLM, S2T)
llm = acquire_genai("llm", "/path/to.hef", lambda vd, p: LLM(vd, p))
```

- Stesso owner + stesso HEF → riutilizzo sessione esistente
- Stesso owner + HEF diverso → rilascio vecchio modello e creazione nuovo
- Owner diverso → **coesistenza** (il vecchio modello non viene rilasciato)

### Rilascio del Modello

```python
from core.hailo_device_core.device_manager import release_device, shutdown_all

release_device("clip")   # Rilascia solo CLIP, gli altri continuano
shutdown_all()            # Rilascia tutti i modelli + VDevice (alla chiusura del processo)
```

### Verifica Stato

```python
from core.hailo_device_core.device_manager import (
    get_active_owners, is_model_active,
    is_hailo_available, is_genai_available,
)

get_active_owners()       # ["clip", "yolo", "llm"]
is_model_active("clip")   # True
```

## Risoluzione dei Problemi

### Errore di Creazione VDevice

**Sintomo**: `HAILO_OUT_OF_PHYSICAL_DEVICES(74)` o `Failed to create VDevice`

**Causa**: Un altro processo occupa il dispositivo con un group_id diverso

**Soluzione**:
1. Verificare se hailo-ollama è in esecuzione:
   ```bash
   ps aux | grep hailo-ollama
   ```
2. Allineare i group_id o fermare il processo:
   ```bash
   sudo systemctl stop hailo-ollama
   ```

### Dispositivo Non Rilasciato

**Soluzione**:
1. Riavviare il processo yu
2. Verificare processi zombie:
   ```bash
   sudo lsof /dev/hailo* 2>/dev/null
   kill <PID>
   ```
3. Resettare il driver Hailo:
   ```bash
   sudo systemctl restart hailort.service
   ```

## Guida alla Scelta dell'API

| Struttura Modello | API Consigliata | Motivo |
|---|---|---|
| Semplice (1 input, YOLO ecc.) | `InferModel` | Funziona con `create_infer_model()` + `configure()` |
| Complessa (2+ input, Whisper ecc.) | `GenAI SDK` | InferModel restituisce `INVALID_ARGUMENT` |
| Encoder CLIP | `InferModel` | 1 input 1 output, nessun problema |
| LLM (qwen2.5 ecc.) | `GenAI SDK` | Richiede decodifica autoregressiva |

## Cronologia

- **v4.61.0**: Migrazione al metodo VDevice condiviso. Abolizione di acquire/release esclusivi, supporto al funzionamento simultaneo di CLIP + YOLO + LLM.
- **v4.60.1**: Unificazione di tutti i consumer attraverso device_manager (metodo esclusivo).
- **v4.60.0 e precedenti**: Ogni consumer chiamava VDevice() individualmente, con frequenti errori di conflitto.

