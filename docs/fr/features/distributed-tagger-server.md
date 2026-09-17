# Serveur d'inférence distribué

**Statut** : Implémenté (v4.53.2)
**Cible** : `deploy/hailo_tagger_server.py`
**Objectif** : Distribuer l'inférence (marquage, CLIP, YOLO, Whisper) sur plusieurs machines sur un LAN

---

## Aperçu

Un serveur HTTP autonome qui distribue les capacités d'inférence de YU AI Manager sur plusieurs machines sur un LAN.
L'installation principale de YU AI Manager n'est pas requise — il fonctionne avec juste Python et ses dépendances.

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

### Modes d'inférence pris en charge

| Mode | Point de terminaison | Description |
|------|----------|-------------|
| **Tagger** | `POST /tag` | Marquage WD-Tagger (disponible uniquement quand `--model-dir` est spécifié) |
| **CLIP** | `POST /clip-encode` | Encodage d'image CLIP ViT-B/16 (pour la recherche sémantique) |
| **YOLO** | `POST /yolo-detect` | Détection d'objets YOLOv11n / YOLOv8n |
| **Whisper** | `POST /whisper-transcribe` | Transcription de parole en texte |

Tous les modes utilisent l'initialisation lazy — les modèles sont chargés à la première requête.
Les modèles ONNX CLIP et YOLO sont téléchargés automatiquement s'ils ne sont pas présents.

---

## Moteurs d'inférence et fournisseurs

### Priorité des moteurs

Chaque mode d'inférence sélectionne un moteur dans l'ordre de priorité suivant :

| Mode | 1er | 2e | 3e |
|------|-----|-----|-----|
| Tagger | Hailo NPU | ONNX | — |
| CLIP | Hailo NPU | ONNX (téléchargement auto) | — |
| YOLO | Hailo NPU | ONNX (téléchargement auto) | — |
| Whisper | Hailo GenAI SDK | faster-whisper | whisper.cpp |

### Sélection automatique du fournisseur ONNX Runtime

Le moteur ONNX sélectionne automatiquement le fournisseur le plus rapide pour votre plate-forme :

| Priorité | Fournisseur | Plate-forme |
|----------|----------|----------|
| 1 | TensorRT | GPU NVIDIA (le plus rapide, nécessite SDK TensorRT) |
| 2 | CUDA | GPU NVIDIA |
| 3 | ROCm | GPU AMD (Linux) |
| 4 | MIGraphX | GPU AMD (Linux) |
| 5 | DirectML | GPU Windows (NVIDIA/AMD/Intel) |
| 6 | OpenVINO | GPU/NPU Intel |
| 7 | QNN | NPU Qualcomm |
| 8 | CoreML | macOS Apple Silicon GPU/ANE |
| 9 | Azure | Copilot+ PC NPU |
| 10 | CPU | Fallback (toujours disponible) |

Vous pouvez également spécifier manuellement avec `--ort-provider cuda`.

### Moteur Hailo

Disponible sur Raspberry Pi 5 avec Hailo-10H NPU. YOLO et CLIP utilisent des HEF pré-compilés officiels.
Le HEF Tagger n'est actuellement pas disponible (DFC ne supporte pas l'architecture WD-Tagger).

---

## Configuration

### Détection automatique de venv

Le script se relance automatiquement avec le Python venv s'il est exécuté en dehors d'un venv :

```bash
# Oublier d'activer venv est OK
python deploy/hailo_tagger_server.py --port 9090
# → [auto-venv] Re-launching with .../venv/bin/python
```

Ordre de recherche : répertoire du script → répertoire parent → répertoire courant

### 1. Dépendances

```bash
# Commun (requis)
pip install numpy Pillow

# Moteur ONNX
pip install onnxruntime           # CPU uniquement
pip install onnxruntime-gpu       # NVIDIA CUDA

# Moteur Whisper (optionnel, choisir un)
pip install faster-whisper        # faster-whisper (CUDA/CPU)
# pip install whisper-cpp-python  # whisper.cpp (CPU)

# Moteur Hailo (Pi5 + Hailo-10H)
# hailo_platform from Hailo Developer Zone
```

### Configuration CUDA + cuDNN (GPU NVIDIA)

ONNX Runtime GPU nécessite les DLL CUDA + cuDNN runtime :

| Version ONNX Runtime | CUDA requis | cuDNN requis |
|----------------------|---------------|----------------|
| Stable (1.x) | CUDA 12.x | cuDNN 9.x |
| nightly | CUDA 13.x | cuDNN 9.x |

**Sous Windows :**

1. Installer CUDA Toolkit
2. Installer cuDNN (les DLL se trouvent dans `C:\Program Files\NVIDIA\CUDNN\v9.x\bin\<version>\x64\`)
3. Ajouter le répertoire contenant `cudnn64_9.dll` à PATH
4. **Redémarrer PowerShell** (requis pour prendre en compte les changements de variable d'environnement)

Vérifier :
```powershell
where.exe cudnn64_9.dll
# → Si un chemin est affiché, c'est bon
```

### 2. Fichiers de modèle

| Mode | Modèle | Localisation | Remarques |
|------|-------|----------|-------|
| Tagger | WD-SwinV2 etc. | Spécifié via `--model-dir` | `model.onnx` + `selected_tags.csv` |
| CLIP | ViT-B/16 | `~/.cache/yu_ai_manager/clip_onnx/` | **Téléchargement auto** (329 MB) |
| YOLO | YOLOv11n | `~/.cache/yu_ai_manager/yolo_onnx/` | **Téléchargement auto** |
| Whisper | faster-whisper-base | Cache HuggingFace | **Téléchargement auto** |

### 3. Démarrer le serveur

```bash
# Tous les modes (CLIP + YOLO + Whisper) — sans Tagger
python deploy/hailo_tagger_server.py --port 9090

# Activer aussi Tagger
python deploy/hailo_tagger_server.py --port 9090 --model-dir ./models/wd-swinv2-tagger-v3

# Avec token d'authentification
python deploy/hailo_tagger_server.py --port 9090 --token "my-secret-token"

# Utiliser un fichier de configuration
python deploy/hailo_tagger_server.py --config tagger.json
```

### 4. Enregistrer dans YU AI Manager

#### Enregistrer en tant que serveur d'inférence (YOLO, Whisper, CLIP)

Enregistrer dans l'interface WebUI sous **Paramètres → Serveurs d'inférence**, ou via un outil MCP :

```
inference_servers_add:
  name: "Windows ONNX"
  endpoint_url: "http://192.168.50.247:9090"
  inference_types: ["clip", "yolo", "whisper"]
  priority: 50
```

#### Enregistrer en tant que serveur Tagger

Enregistrer dans l'interface WebUI sous **Paramètres → Tagger → Registre des serveurs Tagger**.

---

## Points de terminaison API

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

**Valeurs device :**

| Valeur | Signification |
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

Marquer une image. Disponible uniquement quand `--model-dir` est spécifié.

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

Générer des vecteurs d'intégration CLIP pour les images.

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

Détecter des objets dans les images.

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

Transcrire la parole en texte.

```bash
# WAV brut
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

## Fichier de configuration

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

## Exemples de configuration distribuée

### Exemple 1 : Pi5 (Hailo NPU) + Windows (CUDA GPU)

Une configuration vérifiée et fonctionnelle :

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

### Exemple 2 : macOS (CoreML) + Linux (ROCm)

```
Mac (192.168.1.10:9090)
  ├── CLIP: ONNX CoreMLExecutionProvider (Apple Silicon ANE)
  ├── YOLO: ONNX CoreMLExecutionProvider
  └── Whisper: faster-whisper CPU

Linux (192.168.1.20:9090)
  ├── CLIP: ONNX ROCMExecutionProvider (GPU AMD)
  ├── YOLO: ONNX ROCMExecutionProvider
  └── Whisper: faster-whisper ROCm
```

### Exemple 3 : Configuration de basculement

```
Server A (priority 10) -- utilisé normalement
Server B (priority 50) -- utilisé uniquement quand A est down
```

Mode : `single` (utiliser uniquement la priorité la plus élevée)

---

## Daemoniser avec systemd

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

## Dépannage

### ONNX Runtime bascule au CPU

```
[W] Failed to create CUDAExecutionProvider. Require cuDNN 9.* and CUDA 12/13.*
```

→ Vérifier le champ `device` dans `/health`
→ Vérifier la localisation de la bibliothèque avec `where.exe cudnn64_9.dll` (Windows) / `find / -name cudnn64_9.dll` (Linux)
→ Après avoir ajouté à PATH, **redémarrer votre terminal** (requis pour prendre en compte les changements de variable d'environnement)

### CLIP retourne 503

→ À la première requête, le modèle (329 MB) est automatiquement téléchargé à partir de HuggingFace. Vérifier votre connexion réseau.
→ Vérifier que "CLIP ONNX: downloading ..." apparaît dans les logs.

### auto-venv entre dans une boucle infinie

→ Corrigé dans v4.53.2. Utilise désormais `sys.prefix != sys.base_prefix` pour la détection venv.

### Les anciens processus Python subsistent

→ Windows : Vérifier avec `tasklist | findstr python`, terminer tous avec `taskkill /F /IM python.exe`
→ Linux : `pkill -f hailo_tagger_server`

### Erreur d'accès exclusif VDevice Hailo

→ Le NPU Hailo ne peut exécuter qu'un seul modèle à la fois. Arrêter tout LLM, VLM ou S2T en cours avant de réessayer.
