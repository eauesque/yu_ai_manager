# Servidor de Inferência Distribuída

**Status**: Implementado (v4.53.2)
**Alvo**: `deploy/hailo_tagger_server.py`
**Propósito**: Distribuir inferência (tagging, CLIP, YOLO, Whisper) em várias máquinas em uma LAN

---

## Visão Geral

Um servidor HTTP independente que distribui as capacidades de inferência do YU AI Manager em várias máquinas em uma LAN.
A instalação principal do YU AI Manager não é necessária — é executado apenas com Python e suas dependências.

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

### Modos de Inferência Suportados

| Modo | Endpoint | Descrição |
|------|----------|-------------|
| **Tagger** | `POST /tag` | Tagging WD-Tagger (disponível apenas quando `--model-dir` é especificado) |
| **CLIP** | `POST /clip-encode` | Codificação de imagem CLIP ViT-B/16 (para pesquisa semântica) |
| **YOLO** | `POST /yolo-detect` | Detecção de objeto YOLOv11n / YOLOv8n |
| **Whisper** | `POST /whisper-transcribe` | Transcrição de fala para texto |

Todos os modos usam inicialização lazy — modelos são carregados na primeira requisição.
Os modelos ONNX CLIP e YOLO são automaticamente baixados se não estiverem presentes.

---

## Backends de Inferência e Provedores

### Prioridade de Backend

Cada modo de inferência seleciona um backend na seguinte ordem de prioridade:

| Modo | 1º | 2º | 3º |
|------|-----|-----|-----|
| Tagger | Hailo NPU | ONNX | — |
| CLIP | Hailo NPU | ONNX (auto-download) | — |
| YOLO | Hailo NPU | ONNX (auto-download) | — |
| Whisper | Hailo GenAI SDK | faster-whisper | whisper.cpp |

### Seleção Automática de Provedor ONNX Runtime

O backend ONNX seleciona automaticamente o provedor mais rápido para sua plataforma:

| Prioridade | Provedor | Plataforma |
|----------|----------|----------|
| 1 | TensorRT | NVIDIA GPU (mais rápido, requer SDK TensorRT) |
| 2 | CUDA | NVIDIA GPU |
| 3 | ROCm | AMD GPU (Linux) |
| 4 | MIGraphX | AMD GPU (Linux) |
| 5 | DirectML | Windows GPU (NVIDIA/AMD/Intel) |
| 6 | OpenVINO | Intel GPU/NPU |
| 7 | QNN | Qualcomm NPU |
| 8 | CoreML | macOS Apple Silicon GPU/ANE |
| 9 | Azure | Copilot+ PC NPU |
| 10 | CPU | Fallback (sempre disponível) |

Você também pode especificar manualmente com `--ort-provider cuda`.

### Backend Hailo

Disponível em Raspberry Pi 5 com Hailo-10H NPU. YOLO e CLIP usam HEFs pré-compilados oficiais.
O HEF do Tagger não está disponível atualmente (DFC não suporta a arquitetura WD-Tagger).

---

## Configuração

### Detecção Automática de venv

O script relança automaticamente com o Python venv se executado fora de um venv:

```bash
# Esquecer de ativar venv está OK
python deploy/hailo_tagger_server.py --port 9090
# → [auto-venv] Re-launching with .../venv/bin/python
```

Ordem de pesquisa: diretório de script → diretório pai → diretório atual

### 1. Dependências

```bash
# Comum (necessário)
pip install numpy Pillow

# Backend ONNX
pip install onnxruntime           # Apenas CPU
pip install onnxruntime-gpu       # NVIDIA CUDA

# Backend Whisper (opcional, escolha um)
pip install faster-whisper        # faster-whisper (CUDA/CPU)
# pip install whisper-cpp-python  # whisper.cpp (CPU)

# Backend Hailo (Pi5 + Hailo-10H)
# hailo_platform do Hailo Developer Zone
```

### Configuração CUDA + cuDNN (NVIDIA GPU)

ONNX Runtime GPU requer DLLs de runtime CUDA + cuDNN:

| Versão ONNX Runtime | CUDA Necessário | cuDNN Necessário |
|----------------------|---------------|----------------|
| Estável (1.x) | CUDA 12.x | cuDNN 9.x |
| nightly | CUDA 13.x | cuDNN 9.x |

**No Windows:**

1. Instale CUDA Toolkit
2. Instale cuDNN (DLLs estão em `C:\Program Files\NVIDIA\CUDNN\v9.x\bin\<version>\x64\`)
3. Adicione o diretório contendo `cudnn64_9.dll` ao PATH
4. **Reinicie PowerShell** (necessário para pegar mudanças de variável de ambiente)

Verifique:
```powershell
where.exe cudnn64_9.dll
# → Se um caminho for mostrado, você está bom
```

### 2. Arquivos de Modelo

| Modo | Modelo | Localização | Notas |
|------|-------|----------|-------|
| Tagger | WD-SwinV2 etc. | Especificado via `--model-dir` | `model.onnx` + `selected_tags.csv` |
| CLIP | ViT-B/16 | `~/.cache/yu_ai_manager/clip_onnx/` | **Auto-download** (329 MB) |
| YOLO | YOLOv11n | `~/.cache/yu_ai_manager/yolo_onnx/` | **Auto-download** |
| Whisper | faster-whisper-base | Cache do HuggingFace | **Auto-download** |

### 3. Iniciar o Servidor

```bash
# Todos os modos (CLIP + YOLO + Whisper) — sem Tagger
python deploy/hailo_tagger_server.py --port 9090

# Também ativar Tagger
python deploy/hailo_tagger_server.py --port 9090 --model-dir ./models/wd-swinv2-tagger-v3

# Com token de autenticação
python deploy/hailo_tagger_server.py --port 9090 --token "my-secret-token"

# Usando um arquivo de configuração
python deploy/hailo_tagger_server.py --config tagger.json
```

### 4. Registrar em YU AI Manager

#### Registrar como Servidor de Inferência (YOLO, Whisper, CLIP)

Registre na WebUI em **Settings → Inference Servers**, ou via ferramenta MCP:

```
inference_servers_add:
  name: "Windows ONNX"
  endpoint_url: "http://192.168.50.247:9090"
  inference_types: ["clip", "yolo", "whisper"]
  priority: 50
```

#### Registrar como Servidor de Tagger

Registre na WebUI em **Settings → Tagger → Tagger Server Registry**.

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

Marcar uma imagem. Disponível apenas quando `--model-dir` é especificado.

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

Gerar vetores de embedding CLIP para imagens.

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

Detectar objetos em imagens.

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

Transcrever fala para texto.

```bash
# WAV bruto
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

## Arquivo de Configuração

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

## Exemplos de Configuração Distribuída

### Exemplo 1: Pi5 (Hailo NPU) + Windows (CUDA GPU)

Uma configuração verificada e funcional:

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

### Exemplo 2: macOS (CoreML) + Linux (ROCm)

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

### Exemplo 3: Configuração de Failover

```
Servidor A (prioridade 10) -- normalmente utilizado
Servidor B (prioridade 50) -- utilizado apenas quando A está inativo
```

Modo: `single` (usar apenas prioridade mais alta)

---

## Daemonizar com systemd

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

## Solução de Problemas

### ONNX Runtime cai de volta para CPU

```
[W] Failed to create CUDAExecutionProvider. Require cuDNN 9.* and CUDA 12/13.*
```

→ Verificar o campo `device` em `/health`
→ Verificar localização de biblioteca com `where.exe cudnn64_9.dll` (Windows) / `find / -name cudnn64_9.dll` (Linux)
→ Depois de adicionar ao PATH, **reinicie seu terminal** (necessário para pegar mudanças de variável de ambiente)

### CLIP retorna 503

→ Na primeira requisição, o modelo (329 MB) é automaticamente baixado do HuggingFace. Verifique sua conexão de rede.
→ Verifique que "CLIP ONNX: downloading ..." aparece nos logs.

### auto-venv entra em loop infinito

→ Corrigido em v4.53.2. Agora usa `sys.prefix != sys.base_prefix` para detecção de venv.

### Processos Python antigos permanecem

→ Windows: Verifique com `tasklist | findstr python`, encerre todos com `taskkill /F /IM python.exe`
→ Linux: `pkill -f hailo_tagger_server`

### Erro de acesso exclusivo do VDevice do Hailo

→ O NPU Hailo pode executar apenas um modelo por vez. Pare qualquer LLM, VLM ou S2T em execução antes de tentar novamente.
