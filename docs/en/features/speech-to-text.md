# Speech-to-Text Extension

**Status**: Implemented (v3.28.0)
**Target**: `extensions/builtin_speech_to_text/`
**Purpose**: Transcribe video and audio files with automatic backend detection

---

## Overview

This Extension extracts audio from video and audio files and transcribes it using Whisper models.
It automatically selects the optimal backend based on available hardware and runs on GPU or CPU even without a Hailo NPU.

---

## Backend Priority

| Priority | Backend | Library | Target Hardware |
|--------|-------------|-----------|-----------------|
| P100 | `hailo` | `hailo_platform.genai` | Hailo-10H NPU |
| P70 | `torch-whisper-rocm` | `torch` (ROCm) + `transformers` | AMD GPU (ROCm/HIP) |
| P50 | `faster-whisper-cuda` | `faster-whisper` (CTranslate2) | NVIDIA GPU (CUDA) |
| P40 | `torch-whisper-cuda` | `torch` (CUDA) + `transformers` | NVIDIA GPU (CUDA) |
| P20 | `torch-whisper-cpu` | `torch` + `transformers` | CPU |
| P50 | `faster-whisper-cpu` | `faster-whisper` (CTranslate2) | CPU |
| P10 | `whisper-cpp` | `pywhispercpp` | CPU (lightest) |

In `auto` mode, the backend with the highest priority among those returning `is_available() == True` is selected.

---

## Environment-Specific Setup

### Common Requirements

- Python 3.11+
- ffmpeg (required for extracting audio from video)

### Hailo-10H NPU (Raspberry Pi AI HAT 2)

No additional packages are required (`hailo_platform` must already be installed).
The model (`whisper-base` etc.) must have been downloaded via the GenAI Extension.

```bash
# Download the model from the GenAI Extension UI if not already present
```

### NVIDIA GPU (CUDA)

```bash
# Recommended: faster-whisper (lightweight, no PyTorch required)
pip install faster-whisper

# GPU is used automatically when CUDA is detected (float16)
# Falls back to CPU automatically when CUDA is absent (int8)
```

### AMD GPU (ROCm)

```bash
# 1. Install PyTorch ROCm edition
#    Official: https://pytorch.org/get-started/locally/
#    Example (ROCm 6.x):
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/rocm6.2

# 2. Install HuggingFace transformers
pip install transformers

# 3. Set backend in config (auto-detected in "auto" mode)
#    In the Extension settings: backend: "rocm" or "auto"
```

**ROCm detection mechanism**: PyTorch exposes ROCm as CUDA via HIP.
The system identifies ROCm when `torch.version.hip` is not `None`.

**Memory requirements** (ROCm):

| Model | VRAM estimate |
|--------|----------|
| tiny | ~150 MB |
| base | ~300 MB |
| small | ~500 MB |
| medium | ~1.5 GB |

### CPU Only

```bash
# Option 1: faster-whisper (recommended, fast with int8 quantization)
pip install faster-whisper

# Option 2: whisper.cpp (lightest, no PyTorch required)
pip install pywhispercpp

# Option 3: torch + transformers (general purpose but heavy)
pip install torch transformers
```

**CPU performance estimates** (base model, 1 minute of audio):

| Backend | RPi 5 | x86 (4 core) |
|---|---|---|
| faster-whisper (int8) | ~30 sec | ~5 sec |
| whisper.cpp | ~40 sec | ~8 sec |
| torch (float32) | ~90 sec | ~15 sec |

---

## Configuration

Configure via the Extension settings page (`/ext/speech-to-text/`) or config.json:

| Item | Choices | Default | Description |
|------|--------|-----------|------|
| `backend` | auto / hailo / cuda / rocm / cpu | auto | Inference backend |
| `model_size` | tiny / base / small / medium | base | Whisper model size |
| `default_language` | BCP-47 code (ja, en, etc.) | ja | Default language |

---

## API Endpoints

All endpoints are under the `/ext/speech-to-text` prefix.

### POST `/api/s2t/transcribe`

Transcribes uploaded WAV audio.

- **Content-Type**: `multipart/form-data`
- **Parameters**: `audio` (file), `language` (optional)
- **Response**: `{ status, text, segments, language, sample_rate, backend }`

### POST `/api/s2t/transcribe-video`

Transcribes a video/audio file registered in the DB. Results are saved as annotations.

- **Body**: `{ file_id: int, language?: string }`
- **Response**: `{ status, text, segments, language, backend }`
- **Annotation**: `source="s2t"`, keys: `transcript`, `transcript_segments`, `transcript_backend`

### POST `/api/s2t/batch-transcribe`

Batch transcription of multiple files (runs in background).

Choose **one** of three input methods (mutually exclusive):

#### Method 1: File ID List (Legacy)

```json
{
  "file_ids": [123, 456, 789],
  "language": "ja"
}
```

#### Method 2: Directory

Automatically detects video/audio files in the specified directory and processes only those registered in the DB.

```json
{
  "directory": "/path/to/videos/",
  "recursive": true,
  "language": "en"
}
```

- `recursive` (default: `true`): Recursively search subdirectories
- Target extensions: `.webm`, `.mp4`, `.avi`, `.mov`, `.mkv`, `.m4v`, `.ogv`, `.mp3`, `.wav`, `.ogg`, `.opus`, `.m4a`, `.aac`, `.flac`

#### Method 3: Text/CSV List

Specify a text file or CSV listing file paths.

```json
{
  "list_file": "/path/to/targets.txt",
  "language": "ja"
}
```

**Text file format** (`.txt` etc.):
```
# Comment lines (lines starting with # are ignored)
/mnt/videos/interview_01.mp4
/mnt/videos/interview_02.webm
/mnt/audio/podcast_03.mp3
```

**CSV format** (`.csv`):
```csv
/mnt/videos/interview_01.mp4
/mnt/videos/interview_02.webm
/mnt/audio/podcast_03.mp3
```
The first column is used as the file path. Lines starting with `#` are skipped.

#### Common Options

| Parameter | Type | Default | Description |
|-----------|---|-----------|------|
| `language` | string | Config value (typically `ja`) | Language code (see below) |
| `recursive` | bool | `true` | Directory method only: recursive subdirectory search |

#### Limits and Constraints

- Maximum target files: **500**
- Only files registered in the DB (`files` table) are processed
- Deleted files (`is_deleted=1`) are excluded

#### Response Example

```json
{
  "status": "started",
  "total": 15,
  "mode": "directory",
  "directory": "/mnt/videos/",
  "recursive": true,
  "files_found": 23,
  "matched_in_db": 15
}
```

- **SSE events**: `s2t.batch_start`, `s2t.batch_progress`, `s2t.batch_complete`

### GET `/api/s2t/transcript/<file_id>`

Retrieves saved transcription results. Both `source="s2t"` and `source="hailo:s2t"` are checked for backward compatibility.

### GET `/api/s2t/status`

Returns backend status and a list of available backends.

---

## MCP Tools

| Tool Name | Description |
|---------|------|
| `s2t_status` | Get backend status |
| `s2t_transcribe_video` | Transcribe a single video file |
| `s2t_batch_transcribe` | Start batch transcription (file_ids / directory / list_file) |
| `s2t_get_transcript` | Retrieve saved transcription |

### `s2t_batch_transcribe` Parameters

| Parameter | Type | Required | Description |
|-----------|---|------|------|
| `file_ids` | list[int] | *1 | File ID list (max 500) |
| `directory` | string | *1 | Directory path (auto-detects video/audio) |
| `list_file` | string | *1 | Text/CSV file path |
| `recursive` | bool | | Directory method only. Recursive subdirectory search (default true) |
| `language` | string | | Language code. Empty = config default |
| `expected_count` | int | | For detecting file_ids truncation |

*1: Specify exactly one of `file_ids`, `directory`, or `list_file` (mutually exclusive)

---

## File Structure

```
extensions/builtin_speech_to_text/
  extension.json                      # Manifest
  speech_to_text_ext.py               # Entry point (Blueprint)
  s2t_routes.py                       # Single-file API routes
  s2t_batch_routes.py                 # Batch API routes
  core_impl/
    base.py                           # S2TBackend abstract base class
    backend_hailo.py                  # Hailo-10H NPU
    backend_faster_whisper.py         # faster-whisper (CUDA/CPU)
    backend_torch_whisper.py          # PyTorch transformers (ROCm/CUDA/CPU)
    backend_whisper_cpp.py            # whisper.cpp (CPU)
    backend_registry.py               # Auto-detection + singleton management
  templates/speech_to_text/
    s2t.html                          # UI page
mcp_server/
  s2t_tools.py                        # MCP tool definitions
```

---

## Supported Language Codes

Major language codes (BCP-47) supported by Whisper:

| Code | Language | Code | Language |
|--------|------|--------|------|
| `ja` | Japanese | `en` | English |
| `zh` | Chinese | `ko` | Korean |
| `de` | German | `fr` | French |
| `es` | Spanish | `it` | Italian |
| `pt` | Portuguese | `ru` | Russian |
| `ar` | Arabic | `hi` | Hindi |
| `th` | Thai | `vi` | Vietnamese |
| `nl` | Dutch | `tr` | Turkish |
| `pl` | Polish | `uk` | Ukrainian |
| `id` | Indonesian | `sv` | Swedish |

Other Whisper-supported languages can also be specified. An empty string triggers automatic detection.
The default language can be changed via the Extension setting `default_language` (initial value: `ja`).

---

## Known Limitations

- **First-load delay**: transformers / faster-whisper downloads models from HuggingFace Hub (base: ~150MB). The first run may take several minutes
- **Hailo HEF models**: Must be downloaded via the GenAI Extension. The S2T Extension itself has no download functionality
- **Memory**: The medium model may cause out-of-memory errors on RPi 5 (8GB). The base model is recommended
- **Concurrency**: Backends are managed as singletons. Requests arriving during batch processing share the same instance
- **Input format**: WAV (PCM s16le, mono, 16kHz) is assumed. Video files are automatically converted via ffmpeg
- **Batch input**: The directory / list_file methods only process DB-registered files. Unscanned files must first be registered via `start_scan`

---

## Real-time Streaming Transcription

Transcribe audio from internet radio, RTSP streams, and video files in real time and display subtitles in the WebUI.

### Two Modes

- **Chunk mode** (default): Splits audio into chunks using RMS-based silence detection. Compatible with all backends (Hailo/CUDA/CPU). Results are displayed after each utterance ends.
- **Live mode**: Performs incremental transcription using faster-whisper's Silero VAD. Displays interim results while speech is still ongoing. Requires an ONNX/faster-whisper backend.

### Supported Input Sources

- HTTP/HTTPS streams (internet radio, etc.)
- RTSP cameras
- RTMP streams

### API Endpoints

| Endpoint | Method | Function |
|---|---|---|
| `/api/s2t/stream/start` | POST | Start streaming (`source_url`, `language`, `mode`) |
| `/api/s2t/stream/stop` | POST | Stop streaming |
| `/api/s2t/stream/status` | GET | Get status |
| `/api/s2t/stream/transcript` | GET | Get full transcript |
| `/api/s2t/stream/export/txt` | GET | Export as text |
| `/api/s2t/stream/export/srt` | GET | Export as SRT subtitles |

### SSE Events

| Event | Description |
|---|---|
| `s2t.stream_chunk` | Finalized text |
| `s2t.stream_interim` | Interim text (Live mode only) |
| `s2t.stream_complete` | Streaming complete |

### MCP Tools

| Tool | Description |
|---|---|
| `s2t_stream_start(source_url, language)` | Start streaming |
| `s2t_stream_stop()` | Stop streaming |
| `s2t_stream_status()` | Get status |
| `s2t_stream_transcript()` | Get full transcript |

### Streaming Configuration

Configurable items in `extension.json`:

| Item | Description | Default |
|---|---|---|
| `stream_chunk_min_sec` | Minimum chunk length in Chunk mode (seconds) | — |
| `stream_chunk_max_sec` | Maximum chunk length in Chunk mode (seconds) | — |
| `stream_silence_threshold` | RMS threshold for silence detection | — |
| `stream_silence_ms` | Silence duration for detection (milliseconds) | — |
| `live_interval_sec` | Transcription interval in Live mode (seconds) | — |
