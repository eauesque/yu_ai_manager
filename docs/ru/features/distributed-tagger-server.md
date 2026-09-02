# Сервер распределённого умозаключения

**Статус**: Реализовано (v4.53.2)
**Цель**: `deploy/hailo_tagger_server.py`
**Назначение**: Распределить умозаключение (теггирование, CLIP, YOLO, Whisper) на нескольких машинах на LAN

---

## Обзор

Автономный HTTP сервер, который распределяет возможности умозаключения YU AI Manager на нескольких машинах на LAN.
Основная установка YU AI Manager не требуется — она работает с просто Python и его зависимостями.

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

### Поддерживаемые режимы умозаключения

| Режим | Конечная точка | Описание |
|------|----------|-------------|
| **Tagger** | `POST /tag` | Теггирование WD-Tagger (доступно только когда `--model-dir` указан) |
| **CLIP** | `POST /clip-encode` | Кодирование изображения CLIP ViT-B/16 (для семантического поиска) |
| **YOLO** | `POST /yolo-detect` | Обнаружение объектов YOLOv11n / YOLOv8n |
| **Whisper** | `POST /whisper-transcribe` | Транскрипция речи в текст |

Все режимы используют ленивую инициализацию — модели загружаются при первом запросе.
Модели CLIP и YOLO ONNX автоматически загружаются, если отсутствуют.

---

## Backends умозаключения и провайдеры

### Приоритет Backend

Каждый режим умозаключения выбирает backend в следующем порядке приоритета:

| Режим | 1-й | 2-й | 3-й |
|------|-----|-----|-----|
| Tagger | Hailo NPU | ONNX | — |
| CLIP | Hailo NPU | ONNX (автозагрузка) | — |
| YOLO | Hailo NPU | ONNX (автозагрузка) | — |
| Whisper | Hailo GenAI SDK | faster-whisper | whisper.cpp |

### Автоматический выбор провайдера ONNX Runtime

ONNX backend автоматически выбирает самый быстрый провайдер для вашей платформы:

| Приоритет | Провайдер | Платформа |
|----------|----------|----------|
| 1 | TensorRT | NVIDIA GPU (самый быстрый, требуется TensorRT SDK) |
| 2 | CUDA | NVIDIA GPU |
| 3 | ROCm | AMD GPU (Linux) |
| 4 | MIGraphX | AMD GPU (Linux) |
| 5 | DirectML | Windows GPU (NVIDIA/AMD/Intel) |
| 6 | OpenVINO | Intel GPU/NPU |
| 7 | QNN | Qualcomm NPU |
| 8 | CoreML | macOS Apple Silicon GPU/ANE |
| 9 | Azure | Copilot+ PC NPU |
| 10 | CPU | Резервный вариант (всегда доступен) |

Вы также можете указать вручную с `--ort-provider cuda`.

### Hailo Backend

Доступен на Raspberry Pi 5 с Hailo-10H NPU. YOLO и CLIP используют официально предкомпилированные HEFs.
Tagger HEF в настоящее время недоступен (DFC не поддерживает архитектуру WD-Tagger).

---

## Установка

### Автоматическое обнаружение venv

Скрипт автоматически перезапускается с Python venv при запуске вне venv:

```bash
# Забыть активировать venv нормально
python deploy/hailo_tagger_server.py --port 9090
# → [auto-venv] Re-launching with .../venv/bin/python
```

Порядок поиска: директория скрипта → родительская директория → текущая директория

### 1. Зависимости

```bash
# Общие (требуется)
pip install numpy Pillow

# ONNX backend
pip install onnxruntime           # Только CPU
pip install onnxruntime-gpu       # NVIDIA CUDA

# Whisper backend (опционально, выберите один)
pip install faster-whisper        # faster-whisper (CUDA/CPU)
# pip install whisper-cpp-python  # whisper.cpp (CPU)

# Hailo backend (Pi5 + Hailo-10H)
# hailo_platform из Hailo Developer Zone
```

### CUDA + cuDNN Setup (NVIDIA GPU)

ONNX Runtime GPU требует CUDA + cuDNN runtime DLLs:

| ONNX Runtime Version | Требуемая CUDA | Требуемая cuDNN |
|----------------------|---------------|----------------|
| Stable (1.x) | CUDA 12.x | cuDNN 9.x |
| nightly | CUDA 13.x | cuDNN 9.x |

**На Windows:**

1. Установить CUDA Toolkit
2. Установить cuDNN (DLLs в `C:\Program Files\NVIDIA\CUDNN\v9.x\bin\<version>\x64\`)
3. Добавить директорию содержащую `cudnn64_9.dll` в PATH
4. **Перезагрузить PowerShell** (требуется для внесения изменений в переменные окружения)

Проверка:
```powershell
where.exe cudnn64_9.dll
# → Если показан путь, всё хорошо
```

### 2. Файлы модели

| Режим | Модель | Расположение | Примечания |
|------|-------|----------|-------|
| Tagger | WD-SwinV2 и т.д. | Указано через `--model-dir` | `model.onnx` + `selected_tags.csv` |
| CLIP | ViT-B/16 | `~/.cache/yu_ai_manager/clip_onnx/` | **Автозагрузка** (329 MB) |
| YOLO | YOLOv11n | `~/.cache/yu_ai_manager/yolo_onnx/` | **Автозагрузка** |
| Whisper | faster-whisper-base | Кэш HuggingFace | **Автозагрузка** |

### 3. Запустить сервер

```bash
# Все режимы (CLIP + YOLO + Whisper) — без Tagger
python deploy/hailo_tagger_server.py --port 9090

# Также включить Tagger
python deploy/hailo_tagger_server.py --port 9090 --model-dir ./models/wd-swinv2-tagger-v3

# С токеном аутентификации
python deploy/hailo_tagger_server.py --port 9090 --token "my-secret-token"

# Используя файл конфигурации
python deploy/hailo_tagger_server.py --config tagger.json
```

### 4. Зарегистрировать в YU AI Manager

#### Зарегистрировать как Inference Server (YOLO, Whisper, CLIP)

Зарегистрировать в WebUI под **Settings → Inference Servers**, или через MCP инструмент:

```
inference_servers_add:
  name: "Windows ONNX"
  endpoint_url: "http://192.168.50.247:9090"
  inference_types: ["clip", "yolo", "whisper"]
  priority: 50
```

#### Зарегистрировать как Tagger Server

Зарегистрировать в WebUI под **Settings → Tagger → Tagger Server Registry**.

---

## API Конечные точки

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

**Значения device:**

| Значение | Значение |
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

Теггировать изображение. Доступно только когда `--model-dir` указан.

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

Генерировать CLIP вектор встраивания для изображений.

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

Обнаружить объекты на изображениях.

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

Транскрибировать речь в текст.

```bash
# Сырой WAV
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

## Файл конфигурации

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

## Примеры распределённой конфигурации

### Пример 1: Pi5 (Hailo NPU) + Windows (CUDA GPU)

Проверенная рабочая конфигурация:

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

### Пример 2: macOS (CoreML) + Linux (ROCm)

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

### Пример 3: Конфигурация отказоустойчивости

```
Сервер A (приоритет 10) -- обычно используется
Сервер B (приоритет 50) -- используется только когда A недоступен
```

Режим: `single` (использовать только самый высокий приоритет)

---

## Daemonize с systemd

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

## Устранение неполадок

### ONNX Runtime возвращается к CPU

```
[W] Failed to create CUDAExecutionProvider. Require cuDNN 9.* and CUDA 12/13.*
```

→ Проверить поле `device` в `/health`
→ Проверить расположение библиотеки с `where.exe cudnn64_9.dll` (Windows) / `find / -name cudnn64_9.dll` (Linux)
→ После добавления в PATH, **перезагрузить терминал** (требуется для внесения изменений в переменные окружения)

### CLIP возвращает 503

→ При первом запросе модель (329 MB) автоматически загружается с HuggingFace. Проверить соединение.
→ Проверить что `CLIP ONNX: downloading ...` появляется в логах.

### auto-venv входит в бесконечный цикл

→ Исправлено в v4.53.2. Теперь использует `sys.prefix != sys.base_prefix` для обнаружения venv.

### Старые процессы Python остаются

→ Windows: Проверить с `tasklist | findstr python`, завершить все с `taskkill /F /IM python.exe`
→ Linux: `pkill -f hailo_tagger_server`

### Ошибка эксклюзивного доступа Hailo VDevice

→ Hailo NPU может запускать только одну модель одновременно. Остановить любой работающий LLM, VLM или S2T перед повторной попыткой.
