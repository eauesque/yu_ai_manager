# Verteilter Inferenz-Server

**Status**: Implementiert (v4.53.2)
**Ziel**: `deploy/hailo_tagger_server.py`
**Zweck**: Verteilung von Inferenz (Tagging, CLIP, YOLO, Whisper) über mehrere Maschinen in einem LAN

---

## Übersicht

Ein eigenständiger HTTP-Server, der die Inferenz-Fähigkeiten von YU AI Manager über mehrere Maschinen in einem LAN verteilt. Die Hauptinstallation von YU AI Manager ist nicht erforderlich — es wird nur mit Python und seinen Abhängigkeiten ausgeführt.

```
┌─────────────────────────────┐
│   YU AI Manager (Haupt)     │
│   Inferenz-Server-Registry  │
│   Gemeinsame Warteschlange / Work-Stealing │
└──────────┬──────────────────┘
      ┌────┼────────────┐
 ┌────▼────┐ ┌─────▼─────┐ ┌────▼────┐
 │ Pi5 A   │ │ Windows B │ │ Pi5 C   │
 │Hailo NPU│ │CUDA GPU   │ │ONNX CPU │
 │:9090    │ │:9090      │ │:8080    │
 └─────────┘ └───────────┘ └─────────┘
```

### Unterstützte Inferenz-Modi

| Modus | Endpunkt | Beschreibung |
|------|----------|-------------|
| **Tagger** | `POST /tag` | WD-Tagger-Tagging (nur verfügbar, wenn `--model-dir` angegeben ist) |
| **CLIP** | `POST /clip-encode` | CLIP ViT-B/16 Bild-Codierung (für semantische Suche) |
| **YOLO** | `POST /yolo-detect` | YOLOv11n / YOLOv8n Objekterkennung |
| **Whisper** | `POST /whisper-transcribe` | Sprache-in-Text-Transkription |

Alle Modi verwenden verzögerte Initialisierung — Modelle werden beim ersten Request geladen. CLIP- und YOLO-ONNX-Modelle werden automatisch heruntergeladen, falls nicht vorhanden.

---

## Inferenz-Backends und Anbieter

### Backend-Priorität

Jeder Inferenz-Modus wählt ein Backend in der folgenden Prioritätsreihenfolge aus:

| Modus | 1. | 2. | 3. |
|------|-----|-----|-----|
| Tagger | Hailo NPU | ONNX | — |
| CLIP | Hailo NPU | ONNX (Auto-Download) | — |
| YOLO | Hailo NPU | ONNX (Auto-Download) | — |
| Whisper | Hailo GenAI SDK | faster-whisper | whisper.cpp |

### ONNX Runtime Anbieter-Automatische Auswahl

Das ONNX-Backend wählt automatisch den schnellsten Anbieter für Ihre Plattform aus:

| Priorität | Anbieter | Plattform |
|----------|----------|----------|
| 1 | TensorRT | NVIDIA GPU (schnellste, erfordert TensorRT SDK) |
| 2 | CUDA | NVIDIA GPU |
| 3 | ROCm | AMD GPU (Linux) |
| 4 | MIGraphX | AMD GPU (Linux) |
| 5 | DirectML | Windows GPU (NVIDIA/AMD/Intel) |
| 6 | OpenVINO | Intel GPU/NPU |
| 7 | QNN | Qualcomm NPU |
| 8 | CoreML | macOS Apple Silicon GPU/ANE |
| 9 | Azure | Copilot+ PC NPU |
| 10 | CPU | Fallback (immer verfügbar) |

Sie können auch manuell mit `--ort-provider cuda` angeben.

### Hailo Backend

Verfügbar auf Raspberry Pi 5 mit Hailo-10H NPU. YOLO und CLIP verwenden offizielle vorkompilierte HEFs. Das Tagger HEF ist derzeit nicht verfügbar (DFC unterstützt die WD-Tagger-Architektur nicht).

---

## Einrichtung

### Auto-venv Erkennung

Das Skript startet automatisch mit dem venv Python neu, wenn es außerhalb eines venv ausgeführt wird:

```bash
# Vergessen, venv zu aktivieren, ist OK
python deploy/hailo_tagger_server.py --port 9090
# → [auto-venv] Re-launching with .../venv/bin/python
```

Suchbereich: Skript-Verzeichnis → übergeordnetes Verzeichnis → aktuelles Verzeichnis

### 1. Abhängigkeiten

```bash
# Gemeinsam (erforderlich)
pip install numpy Pillow

# ONNX Backend
pip install onnxruntime           # Nur CPU
pip install onnxruntime-gpu       # NVIDIA CUDA

# Whisper Backend (optional, wählen Sie eins)
pip install faster-whisper        # faster-whisper (CUDA/CPU)
# pip install whisper-cpp-python  # whisper.cpp (CPU)

# Hailo Backend (Pi5 + Hailo-10H)
# hailo_platform von Hailo Developer Zone
```

### CUDA + cuDNN Setup (NVIDIA GPU)

ONNX Runtime GPU erfordert CUDA + cuDNN Runtime DLLs:

| ONNX Runtime Version | Erforderlich CUDA | Erforderlich cuDNN |
|----------------------|---------------|----------------|
| Stabil (1.x) | CUDA 12.x | cuDNN 9.x |
| nightly | CUDA 13.x | cuDNN 9.x |

**Auf Windows:**

1. Installieren Sie CUDA Toolkit
2. Installieren Sie cuDNN (DLLs sind in `C:\Program Files\NVIDIA\CUDNN\v9.x\bin\<version>\x64\`)
3. Fügen Sie das Verzeichnis mit `cudnn64_9.dll` zu PATH hinzu
4. **PowerShell neu starten** (erforderlich, um Umgebungsvariablenänderungen zu übernehmen)

Überprüfung:
```powershell
where.exe cudnn64_9.dll
# → Wenn ein Pfad angezeigt wird, sind Sie bereit
```

### 2. Modelldateien

| Modus | Modell | Ort | Notizen |
|------|-------|----------|-------|
| Tagger | WD-SwinV2 etc. | Angegeben über `--model-dir` | `model.onnx` + `selected_tags.csv` |
| CLIP | ViT-B/16 | `~/.cache/yu_ai_manager/clip_onnx/` | **Auto-Download** (329 MB) |
| YOLO | YOLOv11n | `~/.cache/yu_ai_manager/yolo_onnx/` | **Auto-Download** |
| Whisper | faster-whisper-base | HuggingFace Cache | **Auto-Download** |

### 3. Server starten

```bash
# Alle Modi (CLIP + YOLO + Whisper) — ohne Tagger
python deploy/hailo_tagger_server.py --port 9090

# Auch Tagger aktivieren
python deploy/hailo_tagger_server.py --port 9090 --model-dir ./models/wd-swinv2-tagger-v3

# Mit Auth-Token
python deploy/hailo_tagger_server.py --port 9090 --token "my-secret-token"

# Mit einer Konfigurationsdatei
python deploy/hailo_tagger_server.py --config tagger.json
```

### 4. In YU AI Manager registrieren

#### Als Inferenz-Server registrieren (YOLO, Whisper, CLIP)

Registrieren Sie sich in der WebUI unter **Einstellungen → Inferenz-Server**, oder über MCP-Tool:

```
inference_servers_add:
  name: "Windows ONNX"
  endpoint_url: "http://192.168.50.247:9090"
  inference_types: ["clip", "yolo", "whisper"]
  priority: 50
```

#### Als Tagger-Server registrieren

Registrieren Sie sich in der WebUI unter **Einstellungen → Tagger → Tagger-Server-Registry**.

---

## API-Endpunkte

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

**device-Werte:**

| Wert | Bedeutung |
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

Taggen Sie ein Bild. Nur verfügbar, wenn `--model-dir` angegeben ist.

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

Generieren Sie CLIP-Embedding-Vektoren für Bilder.

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

Erkennen Sie Objekte in Bildern.

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

Transkribieren Sie Sprache in Text.

```bash
# Raw WAV
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

## Konfigurationsdatei

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

## Beispiele für verteilte Konfiguration

### Beispiel 1: Pi5 (Hailo NPU) + Windows (CUDA GPU)

Eine verifizierte funktionierende Konfiguration:

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

### Beispiel 2: macOS (CoreML) + Linux (ROCm)

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

### Beispiel 3: Failover-Konfiguration

```
Server A (Priorität 10) -- normalerweise verwendet
Server B (Priorität 50) -- nur verwendet, wenn A ausfällt
```

Modus: `single` (nur höchste Priorität verwenden)

---

## Mit systemd Daemonisieren

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

## Fehlerbehebung

### ONNX Runtime fällt auf CPU zurück

```
[W] Failed to create CUDAExecutionProvider. Require cuDNN 9.* and CUDA 12/13.*
```

→ Überprüfen Sie das `device`-Feld in `/health`
→ Überprüfen Sie den Bibliotheksort mit `where.exe cudnn64_9.dll` (Windows) / `find / -name cudnn64_9.dll` (Linux)
→ Nach dem Hinzufügen zu PATH **Terminal neu starten** (erforderlich, um Umgebungsvariablenänderungen zu übernehmen)

### CLIP gibt 503 zurück

→ Beim ersten Request wird das Modell (329 MB) automatisch von HuggingFace heruntergeladen. Überprüfen Sie Ihre Netzwerkverbindung.
→ Überprüfen Sie, ob `CLIP ONNX: downloading ...` in den Protokollen angezeigt wird.

### auto-venv betritt eine Endlosschleife

→ Behoben in v4.53.2. Verwendet jetzt `sys.prefix != sys.base_prefix` für venv-Erkennung.

### Alte Python-Prozesse bleiben erhalten

→ Windows: Mit `tasklist | findstr python` überprüfen, alles mit `taskkill /F /IM python.exe` beenden
→ Linux: `pkill -f hailo_tagger_server`

### Hailo VDevice ausschließlicher Zugriffsfehler

→ Die Hailo NPU kann jeweils nur ein Modell ausführen. Stoppen Sie alle laufenden LLM, VLM oder S2T, bevor Sie erneut versuchen.
