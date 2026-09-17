# Servidor de Inferencia Distribuida

**Estado**: Implementado (v4.53.2)
**Objetivo**: `deploy/hailo_tagger_server.py`
**Propósito**: Distribuir inferencia (etiquetado, CLIP, YOLO, Whisper) en múltiples máquinas en una LAN

---

## Descripción General

Un servidor HTTP independiente que distribuye las capacidades de inferencia de YU AI Manager en múltiples máquinas en una LAN.
No se requiere la instalación completa de YU AI Manager — se ejecuta con solo Python y sus dependencias.

```
┌─────────────────────────────┐
│   YU AI Manager (Principal) │
│   Registro de Servidor de   │
│   Inferencia                │
│   Cola Compartida /         │
│   Robo de Trabajo           │
└──────────┬──────────────────┘
      ┌────┼────────────┐
 ┌────▼────┐ ┌─────▼─────┐ ┌────▼────┐
 │ Pi5 A   │ │ Windows B │ │ Pi5 C   │
 │Hailo NPU│ │CUDA GPU   │ │ONNX CPU │
 │:9090    │ │:9090      │ │:8080    │
 └─────────┘ └───────────┘ └─────────┘
```

### Modos de Inferencia Soportados

| Modo | Endpoint | Descripción |
|------|----------|-------------|
| **Tagger** | `POST /tag` | Etiquetado WD-Tagger (solo disponible cuando se especifica `--model-dir`) |
| **CLIP** | `POST /clip-encode` | Codificación de imágenes CLIP ViT-B/16 (para búsqueda semántica) |
| **YOLO** | `POST /yolo-detect` | Detección de objetos YOLOv11n / YOLOv8n |
| **Whisper** | `POST /whisper-transcribe` | Transcripción de voz a texto |

Todos los modos utilizan inicialización perezosa — los modelos se cargan en la primera solicitud.
Los modelos CLIP y YOLO ONNX se descargan automáticamente si no están presentes.

---

## Backends de Inferencia y Proveedores

### Prioridad de Backend

Cada modo de inferencia selecciona un backend en el siguiente orden de prioridad:

| Modo | 1º | 2º | 3º |
|------|-----|-----|-----|
| Tagger | Hailo NPU | ONNX | — |
| CLIP | Hailo NPU | ONNX (descarga automática) | — |
| YOLO | Hailo NPU | ONNX (descarga automática) | — |
| Whisper | Hailo GenAI SDK | faster-whisper | whisper.cpp |

### Selección Automática del Proveedor de ONNX Runtime

El backend ONNX selecciona automáticamente el proveedor más rápido para tu plataforma:

| Prioridad | Proveedor | Plataforma |
|----------|----------|----------|
| 1 | TensorRT | GPU NVIDIA (más rápido, requiere SDK TensorRT) |
| 2 | CUDA | GPU NVIDIA |
| 3 | ROCm | GPU AMD (Linux) |
| 4 | MIGraphX | GPU AMD (Linux) |
| 5 | DirectML | GPU Windows (NVIDIA/AMD/Intel) |
| 6 | OpenVINO | GPU/NPU Intel |
| 7 | QNN | NPU Qualcomm |
| 8 | CoreML | macOS Apple Silicon GPU/ANE |
| 9 | Azure | Copilot+ PC NPU |
| 10 | CPU | Alternancia (siempre disponible) |

También puedes especificar manualmente con `--ort-provider cuda`.

### Backend Hailo

Disponible en Raspberry Pi 5 con NPU Hailo-10H. YOLO y CLIP utilizan HEF precompilados oficiales.
El HEF de Tagger actualmente no está disponible (DFC no soporta la arquitectura WD-Tagger).

---

## Configuración

### Detección Automática de venv

El script se reinicia automáticamente con el Python venv si se ejecuta fuera de un venv:

```bash
# Olvidar activar venv está bien
python deploy/hailo_tagger_server.py --port 9090
# → [auto-venv] Re-launching with .../venv/bin/python
```

Orden de búsqueda: directorio de script → directorio padre → directorio actual

### 1. Dependencias

```bash
# Común (requerido)
pip install numpy Pillow

# Backend ONNX
pip install onnxruntime           # Solo CPU
pip install onnxruntime-gpu       # NVIDIA CUDA

# Backend Whisper (opcional, elige uno)
pip install faster-whisper        # faster-whisper (CUDA/CPU)
# pip install whisper-cpp-python  # whisper.cpp (CPU)

# Backend Hailo (Pi5 + Hailo-10H)
# hailo_platform from Hailo Developer Zone
```

### Configuración CUDA + cuDNN (GPU NVIDIA)

ONNX Runtime GPU requiere DLL de tiempo de ejecución CUDA + cuDNN:

| Versión de ONNX Runtime | CUDA Requerido | cuDNN Requerido |
|----------------------|---------------|----------------|
| Estable (1.x) | CUDA 12.x | cuDNN 9.x |
| nightly | CUDA 13.x | cuDNN 9.x |

**En Windows:**

1. Instalar CUDA Toolkit
2. Instalar cuDNN (los DLL están en `C:\Program Files\NVIDIA\CUDNN\v9.x\bin\<version>\x64\`)
3. Añadir el directorio que contiene `cudnn64_9.dll` a PATH
4. **Reiniciar PowerShell** (requerido para recoger cambios de variable de entorno)

Verificar:
```powershell
where.exe cudnn64_9.dll
# → Si se muestra una ruta, estás bien
```

### 2. Archivos de Modelo

| Modo | Modelo | Ubicación | Notas |
|------|-------|----------|-------|
| Tagger | WD-SwinV2 etc. | Especificado vía `--model-dir` | `model.onnx` + `selected_tags.csv` |
| CLIP | ViT-B/16 | `~/.cache/yu_ai_manager/clip_onnx/` | **Descarga automática** (329 MB) |
| YOLO | YOLOv11n | `~/.cache/yu_ai_manager/yolo_onnx/` | **Descarga automática** |
| Whisper | faster-whisper-base | Caché de HuggingFace | **Descarga automática** |

### 3. Iniciar el Servidor

```bash
# Todos los modos (CLIP + YOLO + Whisper) — sin Tagger
python deploy/hailo_tagger_server.py --port 9090

# También habilitar Tagger
python deploy/hailo_tagger_server.py --port 9090 --model-dir ./models/wd-swinv2-tagger-v3

# Con token de autenticación
python deploy/hailo_tagger_server.py --port 9090 --token "my-secret-token"

# Usando archivo de configuración
python deploy/hailo_tagger_server.py --config tagger.json
```

### 4. Registrar en YU AI Manager

#### Registrar como Servidor de Inferencia (YOLO, Whisper, CLIP)

Registrar en la WebUI en **Configuración → Servidores de Inferencia**, o vía herramienta MCP:

```
inference_servers_add:
  name: "Windows ONNX"
  endpoint_url: "http://192.168.50.247:9090"
  inference_types: ["clip", "yolo", "whisper"]
  priority: 50
```

#### Registrar como Servidor Tagger

Registrar en la WebUI en **Configuración → Tagger → Registro de Servidor Tagger**.

---

## Endpoints de API

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

**Valores de device:**

| Valor | Significado |
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

Etiquetar una imagen. Solo disponible cuando se especifica `--model-dir`.

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

Generar vectores de incrustación CLIP para imágenes.

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

Detectar objetos en imágenes.

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

Transcribir voz a texto.

```bash
# WAV sin formato
curl -X POST -H "Content-Type: application/octet-stream" \
  --data-binary @audio.wav "http://host:9090/whisper-transcribe?language=ja"

# Multiparte
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

## Archivo de Configuración

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

## Ejemplos de Configuración Distribuida

### Ejemplo 1: Pi5 (Hailo NPU) + Windows (CUDA GPU)

Una configuración verificada que funciona:

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

### Ejemplo 2: macOS (CoreML) + Linux (ROCm)

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

### Ejemplo 3: Configuración de Conmutación por Error

```
Servidor A (prioridad 10) -- normalmente usado
Servidor B (prioridad 50) -- usado solo cuando A está inactivo
```

Modo: `single` (usar solo la prioridad más alta)

---

## Daemonizar con systemd

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

## Solución de Problemas

### ONNX Runtime se retrocede a CPU

```
[W] Failed to create CUDAExecutionProvider. Require cuDNN 9.* and CUDA 12/13.*
```

→ Verificar el campo `device` en `/health`
→ Verificar ubicación de la biblioteca con `where.exe cudnn64_9.dll` (Windows) / `find / -name cudnn64_9.dll` (Linux)
→ Después de añadir a PATH, **reiniciar tu terminal** (requerido para recoger cambios de variable de entorno)

### CLIP devuelve 503

→ En la primera solicitud, el modelo (329 MB) se descarga automáticamente de HuggingFace Hub. Verifica tu conexión de red.
→ Verifica que aparezca "CLIP ONNX: downloading ..." en los registros.

### auto-venv entra en bucle infinito

→ Corregido en v4.53.2. Ahora utiliza `sys.prefix != sys.base_prefix` para detección de venv.

### Los procesos Python antiguos permanecen

→ Windows: Verificar con `tasklist | findstr python`, terminar todos con `taskkill /F /IM python.exe`
→ Linux: `pkill -f hailo_tagger_server`

### Error de acceso exclusivo de Hailo VDevice

→ El NPU Hailo solo puede ejecutar un modelo a la vez. Detener cualquier LLM, VLM o S2T en ejecución antes de reintentar.
