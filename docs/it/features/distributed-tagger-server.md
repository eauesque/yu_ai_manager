# Server di Inferenza Distribuita

**Status**: Implementato (v4.53.2)
**Target**: `deploy/hailo_tagger_server.py`
**Scopo**: Distribuire l'inferenza (tagging, CLIP, YOLO, Whisper) su più macchine su una LAN

---

## Panoramica

Un server HTTP autonomo che distribuisce le capacità di inferenza di YU AI Manager su più macchine su una LAN.
L'installazione principale di YU AI Manager non è necessaria — viene eseguito con solo Python e le sue dipendenze.

```
┌─────────────────────────────┐
│   YU AI Manager (Main)      │
│   Inference Server Registry │
│   Shared Queue / Work-Stealing │
└──────────┬──────────────────┘
      ┌────┼────────────┐
 ┌────▼────┐ ┌─────▼─────┐ ┌────▼────┐
 │ Pi5 A   │ │ Windows B │ │ Pi5 C   │
 │Hailo NPU│ │CUDA GPU   │ │ONNX CPU │
 │:9090    │ │:9090      │ │:8080    │
 └─────────┘ └───────────┘ └─────────┘
```

### Modalità Inferenza Supportate

| Modalità | Endpoint | Descrizione |
|------|----------|-------------|
| **Tagger** | `POST /tag` | Tagging WD-Tagger (disponibile solo quando `--model-dir` è specificato) |
| **CLIP** | `POST /clip-encode` | Codifica immagine CLIP ViT-B/16 (per ricerca semantica) |
| **YOLO** | `POST /yolo-detect` | Rilevamento oggetti YOLOv11n / YOLOv8n |
| **Whisper** | `POST /whisper-transcribe` | Trascrizione da voce a testo |

Tutte le modalità utilizzano l'inizializzazione lazy — i modelli vengono caricati alla prima richiesta.
I modelli CLIP e YOLO ONNX vengono scaricati automaticamente se non presenti.

---

## Backend di Inferenza e Provider

### Priorità Backend

Ogni modalità di inferenza seleziona un backend nell'ordine prioritario seguente:

| Modalità | 1° | 2° | 3° |
|------|-----|-----|-----|
| Tagger | Hailo NPU | ONNX | — |
| CLIP | Hailo NPU | ONNX (auto-download) | — |
| YOLO | Hailo NPU | ONNX (auto-download) | — |
| Whisper | Hailo GenAI SDK | faster-whisper | whisper.cpp |

### Selezione Automatica Provider ONNX Runtime

Il backend ONNX seleziona automaticamente il provider più veloce per la tua piattaforma:

| Priorità | Provider | Piattaforma |
|----------|----------|----------|
| 1 | TensorRT | NVIDIA GPU (più veloce, richiede SDK TensorRT) |
| 2 | CUDA | NVIDIA GPU |
| 3 | ROCm | AMD GPU (Linux) |
| 4 | MIGraphX | AMD GPU (Linux) |
| 5 | DirectML | Windows GPU (NVIDIA/AMD/Intel) |
| 6 | OpenVINO | Intel GPU/NPU |
| 7 | QNN | Qualcomm NPU |
| 8 | CoreML | macOS Apple Silicon GPU/ANE |
| 9 | Azure | Copilot+ PC NPU |
| 10 | CPU | Fallback (sempre disponibile) |

Puoi anche specificare manualmente con `--ort-provider cuda`.

### Backend Hailo

Disponibile su Raspberry Pi 5 con Hailo-10H NPU. YOLO e CLIP utilizzano HEF pre-compilati ufficiali.
Il Tagger HEF è attualmente non disponibile (DFC non supporta l'architettura WD-Tagger).

---

## Configurazione

### Rilevamento Auto-venv

Lo script si rilancia automaticamente con il Python venv se eseguito al di fuori di un venv:

```bash
# Dimenticare di attivare venv va bene
python deploy/hailo_tagger_server.py --port 9090
# → [auto-venv] Re-launching with .../venv/bin/python
```

Ordine di ricerca: directory script → directory padre → directory corrente

### 1. Dipendenze

```bash
# Comune (richiesto)
pip install numpy Pillow

# Backend ONNX
pip install onnxruntime           # Solo CPU
pip install onnxruntime-gpu       # NVIDIA CUDA

# Backend Whisper (opzionale, scegliere uno)
pip install faster-whisper        # faster-whisper (CUDA/CPU)
# pip install whisper-cpp-python  # whisper.cpp (CPU)

# Backend Hailo (Pi5 + Hailo-10H)
# hailo_platform dal Hailo Developer Zone
```

### Configurazione CUDA + cuDNN (NVIDIA GPU)

ONNX Runtime GPU richiede DLL di runtime CUDA + cuDNN:

| Versione ONNX Runtime | CUDA Richiesto | cuDNN Richiesto |
|----------------------|---------------|----------------|
| Stable (1.x) | CUDA 12.x | cuDNN 9.x |
| nightly | CUDA 13.x | cuDNN 9.x |

**Su Windows:**

1. Installa CUDA Toolkit
2. Installa cuDNN (le DLL sono in `C:\Program Files\NVIDIA\CUDNN\v9.x\bin\<version>\x64\`)
3. Aggiungi la directory contenente `cudnn64_9.dll` a PATH
4. **Riavvia PowerShell** (necessario per applicare le modifiche delle variabili d'ambiente)

Verifica:
```powershell
where.exe cudnn64_9.dll
# → Se viene mostrato un percorso, sei a posto
```

### 2. File Modello

| Modalità | Modello | Posizione | Note |
|------|-------|----------|-------|
| Tagger | WD-SwinV2 ecc. | Specificato via `--model-dir` | `model.onnx` + `selected_tags.csv` |
| CLIP | ViT-B/16 | `~/.cache/yu_ai_manager/clip_onnx/` | **Auto-download** (329 MB) |
| YOLO | YOLOv11n | `~/.cache/yu_ai_manager/yolo_onnx/` | **Auto-download** |
| Whisper | faster-whisper-base | Cache HuggingFace | **Auto-download** |

### 3. Avvia il Server

```bash
# Tutte le modalità (CLIP + YOLO + Whisper) — senza Tagger
python deploy/hailo_tagger_server.py --port 9090

# Abilita anche Tagger
python deploy/hailo_tagger_server.py --port 9090 --model-dir ./models/wd-swinv2-tagger-v3

# Con token di autenticazione
python deploy/hailo_tagger_server.py --port 9090 --token "my-secret-token"

# Usando un file di configurazione
python deploy/hailo_tagger_server.py --config tagger.json
```

### 4. Registra in YU AI Manager

#### Registra come Server di Inferenza (YOLO, Whisper, CLIP)

Registra nell'interfaccia Web in **Impostazioni → Server di Inferenza**, oppure via strumento MCP:

```
inference_servers_add:
  name: "Windows ONNX"
  endpoint_url: "http://192.168.50.247:9090"
  inference_types: ["clip", "yolo", "whisper"]
  priority: 50
```

#### Registra come Server Tagger

Registra nell'interfaccia Web in **Impostazioni → Tagger → Tagger Server Registry**.

---

## Endpoint API

### GET /health

```json
{
  "status": "idle",
  "queue_depth": 0,
  "model": "wd-swinv2-tagger-v3",
  "backend": "onnx",
  "device": "onnx-cuda",
  "auth_required": false,
  "inference_types": ["clip", "yolo", "whisper"]
}
```

**Valori device:**

| Valore | Significato |
|-------|---------|
| `hailo-10h` | Hailo-10H NPU |
| `onnx-cuda` | ONNX Runtime CUDA |
| `onnx-tensorrt` | ONNX Runtime TensorRT |
| `onnx-rocm` | ONNX Runtime ROCm |
| `onnx-migraphx` | ONNX Runtime MIGraphX |
| `onnx-directml` | ONNX Runtime DirectML |
| `onnx-openvino` | ONNX Runtime OpenVINO |
| `onnx-qnn` | ONNX Runtime QNN |
| `onnx-coreml` | ONNX Runtime CoreML |
| `onnx-azure` | ONNX Runtime Azure NPU |
| `onnx-cpu` | ONNX Runtime CPU |

### POST /tag

Etichetta un'immagine. Disponibile solo quando `--model-dir` è specificato.

```bash
curl -X POST -F "image=@test.png" http://host:9090/tag
```

```json
{
  "tags": [
    {"tag": "1girl", "confidence": 0.97, "category": "general"},
    {"tag": "hatsune_miku", "confidence": 0.88, "category": "character"}
  ],
  "model": "wd-swinv2-tagger-v3",
  "elapsed_ms": 145
}
```

### POST /clip-encode

Genera vettori di incorporamento CLIP per immagini.

```bash
curl -X POST -F "images=@test.png" http://host:9090/clip-encode
```

```json
{
  "vectors": ["<base64-encoded float32 array>"],
  "model": "clip_vit_b_16",
  "count": 1
}
```

### POST /yolo-detect

Rileva oggetti nelle immagini.

```bash
curl -X POST -F "images=@test.png" http://host:9090/yolo-detect
```

```json
{
  "detections": [[
    {"class": "person", "confidence": 0.92, "bbox": [100, 50, 300, 400]}
  ]],
  "model": "yolov11n",
  "count": 1
}
```

### POST /whisper-transcribe

Trascrive il discorso in testo.

```bash
# WAV grezzo
curl -X POST -H "Content-Type: application/octet-stream" \
  --data-binary @audio.wav "http://host:9090/whisper-transcribe?language=ja"

# Multipart
curl -X POST -F "image=@audio.wav" "http://host:9090/whisper-transcribe?language=ja"
```

```json
{
  "status": "ok",
  "text": "こんにちは世界",
  "segments": [
    {"text": "こんにちは世界", "start": 0.0, "end": 1.5}
  ],
  "language": "ja",
  "backend": "faster-whisper-cuda"
}
```

---

## File di Configurazione

```json
{
  "port": 9090,
  "host": "0.0.0.0",
  "backend": "auto",
  "model": "wd-swinv2-tagger-v3",
  "model_dir": "./models/wd-swinv2-tagger-v3",
  "ort_provider": "",
  "general_threshold": 0.35,
  "character_threshold": 0.85,
  "bearer_token": ""
}
```

---

## Esempi di Configurazione Distribuita

### Esempio 1: Pi5 (Hailo NPU) + Windows (CUDA GPU)

Una configurazione verificata come funzionante:

```
Pi5 (192.168.50.4:9090)
  ├── Tagger: Hailo NPU
  ├── CLIP: Hailo NPU
  ├── YOLO: Hailo NPU
  └── Whisper: Hailo GenAI SDK (NPU)

Windows (192.168.50.247:9090)
  ├── CLIP: ONNX CUDAExecutionProvider
  ├── YOLO: ONNX CUDAExecutionProvider
  └── Whisper: faster-whisper CUDA
```

### Esempio 2: macOS (CoreML) + Linux (ROCm)

```
Mac (192.168.1.10:9090)
  ├── CLIP: ONNX CoreMLExecutionProvider (Apple Silicon ANE)
  ├── YOLO: ONNX CoreMLExecutionProvider
  └── Whisper: faster-whisper CPU

Linux (192.168.1.20:9090)
  ├── CLIP: ONNX ROCMExecutionProvider (AMD GPU)
  ├── YOLO: ONNX ROCMExecutionProvider
  └── Whisper: faster-whisper ROCm
```

### Esempio 3: Configurazione Failover

```
Server A (priorità 10) -- normalmente utilizzato
Server B (priorità 50) -- utilizzato solo quando A è inattivo
```

Modalità: `single` (utilizza solo il più alto prioritario)

---

## Daemonizza con systemd

```ini
# /etc/systemd/system/inference-server.service
[Unit]
Description=YU AI Manager Inference Server
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/yu_ai_manager
ExecStart=/home/pi/yu_ai_manager/venv/bin/python deploy/hailo_tagger_server.py \
  --config /home/pi/tagger.json
Restart=on-failure
RestartSec=5
Environment=TAGGER_BEARER_TOKEN=my-secret-token

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now inference-server
```

---

## Risoluzione dei Problemi

### ONNX Runtime ricade su CPU

```
[W] Failed to create CUDAExecutionProvider. Require cuDNN 9.* and CUDA 12/13.*
```

→ Controlla il campo `device` in `/health`
→ Verifica la posizione della libreria con `where.exe cudnn64_9.dll` (Windows) / `find / -name cudnn64_9.dll` (Linux)
→ Dopo aver aggiunto a PATH, **riavvia il tuo terminale** (necessario per applicare le modifiche della variabile d'ambiente)

### CLIP restituisce 503

→ Alla prima richiesta, il modello (329 MB) viene scaricato automaticamente da HuggingFace. Controlla la connessione di rete.
→ Verifica che "CLIP ONNX: downloading ..." appaia nei log.

### auto-venv entra in un ciclo infinito

→ Corretto in v4.53.2. Ora utilizza `sys.prefix != sys.base_prefix` per il rilevamento venv.

### Rimangono processi Python vecchi

→ Windows: Controlla con `tasklist | findstr python`, termina tutti con `taskkill /F /IM python.exe`
→ Linux: `pkill -f hailo_tagger_server`

### Errore accesso esclusivo VDevice Hailo

→ L'NPU Hailo può eseguire un modello solo alla volta. Ferma qualsiasi LLM, VLM o S2T in esecuzione prima di ritentare.
