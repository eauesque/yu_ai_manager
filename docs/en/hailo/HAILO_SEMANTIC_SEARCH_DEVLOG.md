# Hailo-10H Semantic Search — Development Log

**Project**: YU AI Manager — Hailo-10H CLIP Semantic Image Search
**Goal**: Implement CLIP-based natural language image search on Raspberry Pi 5 + AI HAT 2 (Hailo-10H)
**Start Date**: 2026-03-01
**Status**: Phase 1-8 complete, Phase 9-12 (VLM caption integration, video S2T, LLM multi-turn, OpenAI-compatible API) complete

---

## Why This Project Matters

Hailo-10H (AI HAT 2) is a relatively new edge AI accelerator released in late 2025,
installed in the Raspberry Pi 5's M.2 slot. It delivers 40 TOPS inference performance, but
**practical application examples are still extremely scarce**.

This project implements semantic search (natural language image search) across a library of
200K images using Hailo-10H — likely the first practical software to do so.

---

## Phase 1: Feasibility Study (2026-03-01)

### Environment

| Item | Value |
|------|-------|
| Hardware | Raspberry Pi 5 (8GB) + AI HAT 2 (Hailo-10H) |
| OS | Raspberry Pi OS Trixie (Linux 6.12.62+rpt-rpi-2712) |
| Python | 3.13.5 |
| HailoRT Driver | 5.2.0 (hailort-pcie-driver) |
| HailoRT Library | 5.2.0 (hailort deb) |
| HailoRT Python | 5.2.0 (**source build**) |

### Step 1-1: Device Recognition — OK

```bash
$ hailortcli fw-control identify
Firmware Version: 5.2.0 (release,app)
Device Architecture: HAILO10H
```

Device was recognized without issues. PCIe connection and driver loading both normal.

### Step 1-2: HEF Download — OK

Direct download from the Hailo Model Zoo v5.2.0 S3 bucket was possible (no authentication required).

```
~/hailo_models/clip_vit_b_16_image_encoder.hef  (76 MB)
~/hailo_models/clip_vit_b_16_text_encoder.hef   (77 MB)
```

URL pattern:
```
https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/<model>.hef
```

### Step 1-3: Python Bindings — Source Build Required

#### Problem: Package Version Mismatch

The Raspberry Pi OS repository contains two separate package lineages:

| Package Lineage | Version | Notes |
|-----------------|---------|-------|
| `hailort` + `hailort-pcie-driver` | 5.2.0 | Official Hailo deb. No Python bindings |
| `h10-hailort` + `python3-h10-hailort` | 5.1.1 | Provided by Raspberry Pi team. Includes Python |

**Problem**: The two lineages have `Conflicts` declarations and cannot coexist. Installing `h10-hailort` (5.1.1) also downgrades the driver to 5.1.1, but hailo-ollama requires 5.2.0.

#### Solution: Source-Build the hailort 5.2.0 Python Wheel

**No wheel on PyPI**. The Hailo Developer Zone download page also has
**no aarch64 wheel** (x86_64 only).

Resolved by source-building from the GitHub repository:

```bash
git clone --depth 1 --branch v5.2.0 https://github.com/hailo-ai/hailort.git ~/hailort

# Build dependencies
sudo apt install -y swig build-essential
pip install pybind11 setuptools wheel

# Build (~2 minutes)
cd ~/hailort/hailort/libhailort/bindings/python/platform
HAILORT_INCLUDE_DIR=/usr/include/hailo \
LIBHAILORT_PATH=/usr/lib/libhailort.so.5.2.0 \
PYBIND11_PYTHON_VERSION=3.13 \
python3 setup.py bdist_wheel --plat-name linux_aarch64

# Install
pip install dist/hailort-5.2.0-cp313-cp313-linux_aarch64.whl
```

**Notes**:
- `--plat-name linux_aarch64` is required. Omitting it causes a
  `ValueError: not enough values to unpack` due to a `LIBHAILORT_PATH` directory name parsing bug (setup.py line 163)
- The `hailort` deb (C library) must be installed beforehand
- `h10-hailort` and `hailort` have `Conflicts` declarations and cannot coexist,
  so `h10-hailort` must be removed before installing `hailort` 5.2.0

### Step 1-4: Inference Test — Successful (API Change Required)

#### Critical Discovery: Hailo-10H Does Not Support the Legacy VStreams API

The `InferVStreams` + `ConfigureParams.create_from_hef()` code described in the spec
**does not work on Hailo-10H**. `VDevice.configure()` returns `HAILO_NOT_IMPLEMENTED (error 7)`.

This is a **fundamental API difference between Hailo-8/8L and Hailo-10H**,
and is not clearly documented in the official documentation — a critical finding.

#### Correct API: InferModel

On Hailo-10H, use `VDevice.create_infer_model()`:

```python
from hailo_platform import VDevice
import numpy as np

hef_path = "~/.hailo_models/clip_vit_b_16_image_encoder.hef"

with VDevice() as vdevice:
    infer_model = vdevice.create_infer_model(hef_path)

    # inputs/outputs are properties (not callable)
    inp_info = infer_model.inputs[0]   # NOT inputs()
    out_info = infer_model.outputs[0]

    configured = infer_model.configure()
    bindings = configured.create_bindings()

    # Input: uint8 image
    dummy = np.random.randint(0, 255, inp_info.shape, dtype=np.uint8)
    bindings.input().set_buffer(dummy)

    # Output: explicitly allocate uint8 buffer
    output_buf = np.empty(out_info.shape, dtype=np.uint8)
    bindings.output().set_buffer(output_buf)

    configured.run([bindings], timeout=10000)

    vec = output_buf.flatten()  # (512,) uint8
```

#### Stumbling Points and Resolutions

| Problem | Error | Resolution |
|---------|-------|------------|
| `infer_model.inputs()` raises TypeError | `'list' object is not callable` | It is a property, use `inputs[0]` (no parentheses) |
| Output buffer not set | `not configured as view` | Explicitly allocate with `bindings.output().set_buffer(buf)` |
| Output buffer allocated as float32 | `buffer size 2048 != expected 512` | Allocate as **uint8** (512 bytes). float32 would be 2048 bytes |
| Error on VDevice teardown | `Lost communication with server` | VDevice cleanup ordering issue. **Does not affect inference results** |

### Inference Performance

| Item | Value |
|------|-------|
| Model | CLIP ViT-B/16 Image Encoder |
| Input | (224, 224, 3) uint8 |
| Output | (1, 1, 512) uint8 (quantized) |
| Inference Time | **~20 ms** |
| Theoretical Throughput | **~50 images/sec** |

Index construction for 200K images: inference alone takes approximately 67 minutes. Including preprocessing, expected to complete within a few hours.

### Phase 1 Verdict

| Criterion | Result |
|-----------|--------|
| 512-dimensional vector output | **OK** (uint8 quantized, dequantization required) |
| Inference speed | **Excellent** (20ms/image) |
| API compatibility | Uses InferModel API (VStreams API from the spec is not supported) |
| Verdict | **Proceed to Phase 2** |

### Handoff Items for Next Phase

1. **Dequantization**: uint8 output must be converted to float32.
   The HEF should contain quantization parameters (scale/zero_point).
   `hailo_platform.pyhailort._pyhailort.dequantize_output_buffer` may be usable.
2. **Text Encoder**: HEF exists but untested. Need to verify whether the same InferModel API works.
   CPU implementation (sentence-transformers) as outlined in the spec may be safer.
3. **Coexistence with hailo-ollama**: VDevice uses the device exclusively.
   hailo-ollama must be stopped during index construction.
4. **VDevice Cleanup**: The teardown error message is harmless, but
   watch for resource leaks in long-running server processes.

---

## Phase 2: DB Schema Extension (2026-03-01)

### Implementation

Added `file_vectors` table as Migration 25.

```sql
CREATE TABLE file_vectors (
    file_id     INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
    model       TEXT NOT NULL DEFAULT 'clip_vit_b_16',
    vector      BLOB NOT NULL,        -- float32 numpy array tobytes() (512*4=2048 bytes)
    created_at  INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);
CREATE INDEX idx_file_vectors_model ON file_vectors(model);
```

**Design Decisions**:
- `vector` stores dequantized float32 BLOBs. Storing as uint8 would degrade precision
- `file_id` is the PRIMARY KEY (one vector per file). Future multi-model support would require changing to UNIQUE(file_id, model)
- `ON DELETE CASCADE` auto-deletes when files are deleted

**Testing**: Applied migration to in-memory DB, verified table/index existence — OK

### Files

- `core/schema_core/schema_migrate_steps_25.py` (new)
- `core/schema_core/schema_migrate.py` (added import + `if current_version < 25` block)
- `core/schema_core/schema_constants.py` (`CURRENT_SCHEMA_VERSION = 25`)
- `core/hailo_clip_core/vector_store.py` (new - DB vector CRUD)  *(now at `extensions/builtin_hailo_semantic_search/core_impl/`)*

---

## Phase 3: Hailo Inference Core (2026-03-01)

### Implementation

Created new `core/hailo_clip_core/` package *(now at `extensions/builtin_hailo_semantic_search/core_impl/`)*:

| File | Responsibility |
|------|----------------|
| `hailo_inference.py` | HailoClipEncoder singleton. InferModel API wrapper |
| `image_preprocess.py` | Resize to 224x224 + BGR-to-RGB conversion using cv2 |
| `dequantize.py` | uint8-to-float32 dequantization + L2 normalization + quant_params extraction |
| `text_encoder.py` | CPU CLIP text encoder (`openai/clip-vit-base-patch16`) |

**Design Decisions**:
- Image preprocessing passes uint8 directly to Hailo (normalization happens inside the HEF)
- Text encoder uses `transformers` CLIPModel (not `sentence-transformers`).
  Reason: `openai/clip-vit-base-patch16` is the same model as the Hailo HEF's CLIP ViT-B/16,
  ensuring matching vector spaces
- Dequantization parameters are retrieved from `infer_model.outputs[0].quant_infos[0]`;
  falls back to scale=1.0, zero_point=0.0 on failure

**Dependencies**: `opencv-python-headless`, `numpy` (required), `transformers`, `torch` (for text search)

---

## Phase 4: Indexer + Extension (2026-03-01)

### Implementation

| File | Responsibility |
|------|----------------|
| `core/hailo_clip_core/indexer.py` *(now at `extensions/builtin_clip_search/core_impl/`)* | Background thread batch index construction |
| `core/hailo_clip_core/event_handler.py` *(now at `extensions/builtin_clip_search/core_impl/`)* | Auto-index on scan.complete event |
| `extensions/builtin_hailo_semantic_search/extension.json` | Extension manifest |
| `extensions/builtin_hailo_semantic_search/hailo_semantic_search.py` | Blueprint with 5 APIs |

**API Endpoints**:
- `GET /ext/hailo-semantic/api/status` — Device and index status
- `POST /ext/hailo-semantic/api/index/start` — Start index construction
- `GET /ext/hailo-semantic/api/index/status` — Progress
- `POST /ext/hailo-semantic/api/index/stop` — Stop
- `GET /ext/hailo-semantic/api/search` — Semantic search
- `POST /ext/hailo-semantic/api/index/clear` — Clear index

**Events**: Added `semantic_index.start/progress/complete` to event_bus

---

## Phase 5: Semantic Search Engine (2026-03-01)

### Implementation

`core/hailo_clip_core/search.py` *(now at `extensions/builtin_clip_search/core_impl/search.py`)* — Cosine similarity search with memory cache

**Algorithm**:
1. Bulk-load all vectors from DB into memory cache
2. Pre-normalize vectors with L2
3. Query text → CLIP text encoder → 512-dimensional vector
4. Matrix multiplication (dot product) for batch cosine similarity computation
5. Sort results above threshold → return results

**Memory Estimate**: 200K x 512 x 4 bytes = ~400 MB (acceptable for Pi5 8GB RAM)

**Response Format**:
```json
{
    "status": "ok",
    "total": 25,
    "results": [{"file_id": 123, "score": 0.82, "path": "..."}],
    "query": "blue sky",
    "indexed_count": 200000,
    "threshold": 0.2,
    "timing": {"encode_ms": 150.3, "search_ms": 12.5}
}
```

---

## Phase 6: UI Integration (2026-03-01)

### Search Page

- Added semantic search toggle (brain icon, `regex-pill` style) next to the search bar
- Shown only when Hailo is available and index has been built
- When toggle is ON: intercepts search form submission → semantic search API → displays results in existing grid
- Placeholder text changed to English text examples

### Tools Page

- Added semantic search section to the Search & Analysis tab
- Displays device status and index status
- Batch size slider + auto-index checkbox
- Build Index / Stop / Clear buttons + progress bar (2-second polling)

---

## Technical Notes

### Key Differences: Hailo-10H vs Hailo-8/8L (Developer Perspective)

| Item | Hailo-8/8L | Hailo-10H |
|------|-----------|-----------|
| VStreams API | Supported | **Not supported** (NOT_IMPLEMENTED) |
| InferModel API | Supported | Supported |
| ConfigureParams | create_from_hef(hef, interface) | Not needed (create_infer_model replaces it) |
| Output format | float32 or uint8 selectable | uint8 only (dequantization required) |
| Python package | PyPI wheel available | **None** (source build required) |
| APT package | `hailort` integrated | `h10-hailort` separate lineage (5.1.1 only) |

### Pre-Built Wheel Storage

```
~/hailort/hailort/libhailort/bindings/python/platform/dist/
  hailort-5.2.0-cp313-cp313-linux_aarch64.whl
```

This wheel can be copied and installed on other Pi5 environments
(requires libhailort.so.5.2.0 and hailort-pcie-driver 5.2.0).

---

## Post-Implementation Bug Fix Log for Phase 2-6 (2026-03-01)

### 1. Text Encoder `get_text_features` Compatibility Issue

**Problem**: `CLIPModel.get_text_features(**inputs)` in newer versions of transformers
returns a `BaseModelOutputWithPooling` object instead of `torch.Tensor`.
This caused an `AttributeError` on `.squeeze()`, making semantic search return a `Search failed` error.

**Symptom**: `curl /ext/hailo-semantic/api/search?q=girl` → `{"message":"Search failed","status":"error"}`

**Root Cause**: The return value of `_model.get_text_features()` depends on the transformers version.
In newer versions, the full model output object is returned, requiring manual extraction via `.pooler_output` etc.

**Fix**: Changed `text_encoder.py` to explicitly use a two-stage `text_model()` → `text_projection()` approach:

```python
# Before (broken)
text_features = _model.get_text_features(**inputs)
vec = text_features.squeeze().numpy()

# After (fixed)
text_out = _model.text_model(**inputs)
text_features = _model.text_projection(text_out.pooler_output)
vec = text_features.squeeze().numpy()
```

**Performance**:
- First query (including model loading): ~6 seconds
- Subsequent queries: ~100-170ms (CPU inference only)
- Vector search: <1ms (51 items, memory cache)

### 2. Infinite Retry Loop During Index Construction

**Problem**: Files that failed to decode (non-image files, corrupted files, etc.) were not tracked in `failed_ids`,
causing `get_unindexed_file_ids()` to return the same failing files every time, pushing the error count above 3 million.

**Fix**: Added `failed_ids: set` to `indexer.py`. Records failed file_ids and excludes them from subsequent batches.

### 3. Image Loading Failure for Archive Files

**Problem**: `cv2.imread('test.7z!image.png')` cannot parse archive member paths.

**Fix**: In `image_preprocess.py`, detect archive paths using `is_archive_member()` and
switch to the `read_bytes_from_zip` / `read_bytes_from_7z` + `cv2.imdecode()` pattern.

### 4. SSE Real-Time Progress Updates

**Problem**: 2-second polling produced choppy progress updates with poor UX.

**Fix**: Switched to `EventSource` SSE connection. Real-time updates via `semantic_index.progress` events.
On `visibilitychange`, disconnect SSE when tab is hidden and reconnect on tab return.

---

## Phase 7: YOLO Object Detection (2026-03-02)

### Overview

Following CLIP semantic search, implemented YOLO object detection on the same Hailo-10H.
Performs 80-class COCO object detection on images and videos, storing results in the `file_annotations` table.

### Architecture Design

#### VDevice Sharing Problem

Hailo-10H only supports a single VDevice per process, and InferModel is exclusive.
CLIP and YOLO cannot run simultaneously.

**Solution**: Created `core/hailo_device_core/device_manager.py`.
- `acquire_device(owner, hef_path)` — If another owner holds the device, auto-releases and switches
- Same owner + same HEF reuses the existing instance (avoiding reinitialization)
- Thread-safe via `threading.Lock`
- Refactored CLIP's `hailo_inference.py` to delegate to device_manager

#### YOLO Output Tensor Handling

CLIP has a single output tensor, but YOLO has multiple output tensors (one per stride head).
`device_manager` collects quantization parameters for all outputs and returns them.

#### Post-Processing Pipeline

YOLO post-processing consists of the following steps:
1. uint8 → float32 dequantization (using per-output scale/zero_point)
2. Grid cell → pixel coordinate decoding (sigmoid + grid offset + stride)
3. Confidence filtering
4. Per-class NMS (pure numpy)
5. Letterbox coordinates → original image normalized coordinates (0-1) conversion

#### Video Support

Extract frames with ffmpeg → detect each frame independently → aggregate by class.
Retain maximum confidence and frame count for each class.

### New Module Structure

| Module | Role |
|--------|------|
| `core/hailo_device_core/device_manager.py` | Shared VDevice lifecycle management |
| `core/hailo_yolo_core/hailo_yolo_inference.py` | YOLODetector singleton |
| `core/hailo_yolo_core/yolo_postprocess.py` | NMS, box decode, dequantize |
| `core/hailo_yolo_core/yolo_labels.py` | COCO 80-class labels |
| `core/hailo_yolo_core/yolo_preprocess.py` | 640x640 letterbox resize |
| `core/hailo_yolo_core/yolo_video.py` | Video frame extraction + aggregation |
| `core/hailo_yolo_core/yolo_indexer.py` | Background batch detection |
| `core/hailo_yolo_core/model_download.py` | HEF download |
| `core/hailo_yolo_core/event_handler.py` | scan.complete handler |
| `extensions/builtin_hailo_yolo_detect/` | Extension + Blueprint API + UI |

### Technical Notes

- **Multi-output tensors**: YOLO HEFs have multiple output tensors (one per stride head).
  Must iterate `infer_model.outputs` to collect all shapes and quant_params
- **Output buffers**: Allocate individual uint8 buffers for each output tensor,
  binding by name with `bindings.output(out.name).set_buffer(buf)`
- **Tensor layout**: Shape is typically `(1, H, W, C)`. C contains bbox (4) + class scores (80)
- **HEF download**: Direct download from Hailo Model Zoo v5.2.0. Must set `_USER_AGENT` as
  Cloudflare blocks requests without a User-Agent
- **Detection result storage**: Stored as a JSON array in the `file_annotations` table with
  `source='hailo:<model>'`, `key='detections'`. Leverages the existing annotation CRUD API

---

## Phase 8: GenAI (LLM / VLM / Speech2Text) Integration (2026-03-02)

### Goal

Integrate the Hailo-10H `hailo_platform.genai` module (LLM, VLM, Speech2Text) into
device_manager, enabling text generation, image understanding, and speech transcription from the WebUI.

### device_manager Extension

- **Problem**: The existing device_manager only supported InferModel API (CLIP/YOLO).
  GenAI classes operate in a different mode, taking a VDevice directly rather than using InferModel
- **Solution**: Introduced a `_mode` variable (`"infer"` | `"genai"`) to distinguish modes.
  Added `acquire_genai(owner, model_path, genai_factory)`, using the factory pattern
  to instantiate LLM/VLM/S2T instances
- **Release behavior differences**:
  - InferModel: `del configured` → `del infer_model` → `del vdevice`
  - GenAI: `instance.release()` → `vdevice.release()` (explicit release method)

### GenAI API Discoveries

- **Message format**: OpenAI-compatible role/content structure. Content is an array with `{"type": "text", "text": "..."}` format
- **VLM image input**: 336x336 RGB uint8 numpy array. Passed as a list via `frames=[image]`.
  Place an `{"type": "image"}` placeholder in the prompt
- **S2T input**: Little-endian float32 (`<f4`), mono, 16kHz. int16-to-float32 normalization is required
- **S2T segments**: `generate_all_segments()` returns a list of `SegmentInfo` objects.
  Has `.text`, `.start`, `.end` attributes
- **Context management**: LLM/VLM manage the context window via `get_context_usage_size()`, `max_context_capacity()`,
  `clear_context()`
- **Streaming**: `generate()` returns an iterator, yielding per token

### Model HEF Download URLs

- Pattern: `https://dev-public.hailo.ai/v{hailort_version}/blob/{ModelName}.hef`
- HailoRT 5.2.0 → `v5.2.0`
- Model names are CamelCase (e.g., `Qwen2.5-1.5B-Instruct.hef`, `Whisper-Base.hef`)
- Can be verified via the `gen-ai-mz` source type in `hailo-apps-infra`'s `download_resources.py`

### New Files

| File | Description |
|------|-------------|
| `core/hailo_genai_core/__init__.py` | Package init |
| `core/hailo_genai_core/genai_types.py` | GenAIModelType enum + GenAIModelInfo dataclass |
| `core/hailo_genai_core/model_download.py` | Download management for 7 model HEFs |
| `core/hailo_genai_core/llm_inference.py` | HailoLLM wrapper (singleton, streaming) |
| `core/hailo_genai_core/vlm_inference.py` | HailoVLM wrapper (singleton, image preprocessing) |
| `core/hailo_genai_core/s2t_inference.py` | HailoS2T wrapper (singleton, segment support) |
| `extensions/builtin_hailo_genai/extension.json` | Extension manifest |
| `extensions/builtin_hailo_genai/hailo_genai_ext.py` | Blueprint with 8 APIs (SSE streaming) |
| `extensions/.../templates/hailo_genai/_genai_ui.html` | Tools page UI (4 panels) |

### Technical Notes

- **VDevice.create_params()**: In GenAI mode, create parameters with `VDevice.create_params()`
  and instantiate with `VDevice(params)`. This differs from the InferModel mode's `VDevice()` (no arguments)
- **SSE streaming**: Uses Flask's `Response(generator(), mimetype='text/event-stream')` to
  send `data: {"token": "..."}\n\n` per token. Sends `data: {"done": true}\n\n` on completion
- **VLM FormData submission**: Since image files and text prompts must be sent together,
  the VLM API uses `multipart/form-data` instead of JSON
- **S2T WAV reading**: Server-side reads uploaded WAV byte streams directly using
  the `wave` module + `io.BytesIO`

---

## Phase 9: Semantic Search + VLM Caption Integration (2026-03-03)

### Goal

Batch-generate VLM (Qwen2-VL) captions for CLIP search result images and
store them in `file_annotations`.

### Implementation

- **`core/hailo_clip_core/caption_runner.py`** *(now at `extensions/builtin_hailo_semantic_search/core_impl/caption_runner.py`)* (~150 lines): Runs VLM caption generation in batch on a background thread. Follows the `indexer.py` pattern of `_state_lock` + `_stop_requested` + `_progress`. SSE events: `vlm_caption.start/progress/complete`
- **Blueprint extension**: Added 3 endpoints to `hailo_semantic_search.py`: `/api/caption/start`, `/api/caption/status`, `/api/caption/stop`
- **UI**: Added "VLM Caption Generation" panel to the Semantic Search section on the Tools page. Prompt input, SSE progress bar, auto-linked search result file_ids

### VDevice Exclusive Access

- Acquires VLM via `acquire_genai("vlm", ...)`. If the CLIP indexer is running, device_manager's existing behavior auto-releases it
- After caption completion, VLM continues to hold the device, so resuming CLIP indexing requires model unloading

### Annotation Storage Convention

- `source="hailo:vlm"`, `key="caption"`, `value=<caption text>`

---

## Phase 10: Video Audio Transcription — S2T Pipeline (2026-03-03)

### Goal

Extract audio from video files with ffmpeg → transcribe with Whisper (S2T) → store in `file_annotations`.

### Implementation

- **`core/files_core/video_audio.py`** (~80 lines): `extract_audio_wav()` extracts audio via ffmpeg (mono PCM s16le 16kHz). Dynamic timeout calculation based on video duration (max 120 seconds). `check_ffmpeg()` reused from `media_video.py`
- **Blueprint extension**: Added 3 endpoints to `hailo_genai_ext.py`:
  - `POST /api/s2t/transcribe-video`: Single video transcription (file_id, language)
  - `POST /api/s2t/batch-transcribe`: Batch transcription for multiple videos (file_ids, language), background thread + SSE progress (`video_s2t.*`)
  - `GET /api/s2t/transcript/<file_id>`: Retrieve saved transcription
- **UI**: Added "Video Transcription" subsection within the S2T panel. file_id input, language selection (ja/en), retrieve saved transcript button

### Annotation Storage Convention

- `source="hailo:s2t"`, `key="transcript"`, `value=<full text>`
- `source="hailo:s2t"`, `key="transcript_segments"`, `value=<JSON [{text, start, end}, ...]>`

### Notes

- Temporary WAV files are created with `tempfile.NamedTemporaryFile`, always deleted in finally block
- S2T and LLM/VLM are device-exclusive (cannot be used simultaneously)

---

## Phase 11: LLM Multi-Turn Conversation UI Improvements (2026-03-03)

### Goal

Extend single-shot prompts to support conversation history. Context continuation, reset, and bubble-style UI.

### Implementation

- **API modification**: `api_llm_generate()` can now accept a `messages` array. Backward compatible: when only `prompt` is provided, converts to system + user messages as before. `generate_stream()` already supported multi-turn (via `_normalise_prompt()`)
- **Bubble-style chat UI**: `hg-chat-container` + `hg-bubble` (user = right-aligned purple, AI = left-aligned gray). CSS classes: `hg-bubble-user`, `hg-bubble-ai`, `hg-bubble-label`
- **Conversation history management**: JS-side `_chatHistory = []` array accumulates `{role, content}`. On API submission, passes `messages: [systemMsg, ..._chatHistory]`. `hgLlmClear()` resets the array + clears HailoRT context
- **Streaming**: AI bubble is inserted into DOM first, SSE tokens appended incrementally

### Bug Fix: Multi-Turn Conversation System Role Error (2026-03-03)

Discovered via MCP debug queries + hailort logs. The following error occurred on `generate()` calls from the 2nd turn onward:

```
[HailoRT] [error] CHECK failed - System role messages can only be provided on the first prompt
[HailoRT] [error] CHECK_SUCCESS failed with status=HAILO_INVALID_OPERATION(6)
```

**Root Cause**: The UI template was prepending `[systemMsg].concat(_chatHistory)` with the system role on every submission. HailoRT's LLM API does not accept system role when context already exists (2nd turn onward).

**Fix**:
1. Added `_prepare_prompt()` method to `llm_inference.py`: When `get_context_usage_size() > 0`, automatically strips system role messages
2. UI template (`_genai_ui.html`): Only includes system when `_chatHistory.length <= 1` (first user message only)

**Technical Note**: As a HailoRT constraint, `LLM.generate()` only processes system role on the first invocation. This differs from OpenAI API behavior and requires attention when implementing multi-turn conversations

---

## WD-Tagger VLM x Hailo-10H Live Device Testing (2026-03-03)

### Test Environment
- Raspberry Pi 5 + Hailo AI HAT 2 (Hailo-10H)
- HailoRT FW 5.2.0, hailo_platform Python 5.2.0
- hailo-ollama v0.5.1 (built from source)
- Qwen2-VL-2B-Instruct.hef (3.0 GB)

### Critical Discovery: hailo-ollama Does Not Support VLM

Explicitly stated in hailo-ollama's official documentation (USAGE.rst):
> "The Hailo-Ollama API is currently limited to language models (LLMs) and cannot be used for VLMs."

In the MODELS table, the Inference API column for `Qwen2-VL-2B-Instruct` shows only "C++, Python" and does not include "Hailo-Ollama".

Model list returned by `/hailo/v1/list`:
```
deepseek_r1:1.5b, llama3.2:1b, qwen2.5-coder:1.5b, qwen2.5:1.5b, qwen2:1.5b
```
`qwen2-vl` is not included.

### hailo-ollama Test Results

**Config note**: The built-from-source binary uses the `NLOHMANN_DEFINE_TYPE_NON_INTRUSIVE` macro, which requires a `limits` key in the config JSON. This is not included in the official config template, so the following must be added:
```json
"limits": {"max_in_flight": 4, "max_queue": 10, "retry_after_sec": 1}
```

- **LLM text generation (qwen2.5:1.5b)**: Both OpenAI and Ollama native APIs work, 6.5 TPS
- **OpenAI API vision request**: 500 error (`Node is NOT a STRING`)
- **Ollama native API + images**: Accepted but LLM cannot process images
- **VlmWdTaggerEngine fallback**: OpenAI 500 → auto-switch to Ollama native OK
- **response_format: json_object**: Accepted but JSON output is not enforced

### Hailo Python SDK VLM Direct Test Results

VLM requires `{"type": "image"}` in the message format:
```python
messages = [
    {"role": "user", "content": [
        {"type": "image"},
        {"type": "text", "text": "Tag this image."}
    ]}
]
vlm.generate_all(messages, frames=[frame_336x336_rgb_uint8])
```

- **Model load**: 33 seconds (initial cold start. Discrepancy from the stated 6.2s is dominated by disk I/O)
- **Inference speed**: ~5.1 TPS (128 tokens / 20 seconds). Discrepancy from stated 6.73 TPS includes TTFT
- **Image recognition accuracy**: Correctly understands image content (accurately described "two women holding hands in a snowy landscape")
- **JSON output quality**: Low. The 2B model produces unreliable structured JSON (missing commas, markdown code fence contamination)

### Bugs Found

1. **`engines_hailo_vlm.py` prompt format**: Was passing text-only messages to VLM → Fixed to list format including `{"type": "image"}`
2. **`vlm_inference.py` frames argument**: VLM's `generate_all()` requires `frames` but it was declared as Optional → Fixed to required

### Technical Notes

- **VDevice exclusive constraint**: While hailo-ollama is running, `hailo_platform.VDevice()` cannot be acquired. hailo-ollama must be stopped for direct VLM inference
- **VLM.generate_all() requires frames**: Text-only inference results in `HAILO_INVALID_OPERATION` error. LLM and VLM have different API preconditions
- **Qwen2-VL prompt template**: Uses a Jinja2 template to insert `<|vision_start|><|image_pad|><|vision_end|>`. Including `{"type": "image"}` in the message format causes the SDK to handle this automatically

---

## Phase 12: OpenAI-Compatible API + Device Switching Bug Fix (2026-03-14)

### Goal

1. Provide an OpenAI-compatible API enabling external tools such as OpenAI SDK / LiteLLM / Continue.dev / Open WebUI to use Hailo GenAI directly
2. Fix Quart async compatibility issues
3. Add MCP tool support for SSE endpoints

### Implementation: OpenAI-Compatible API (`hailo_openai_routes.py`)

Created new file `extensions/builtin_hailo_genai/hailo_openai_routes.py`. Implemented 4 endpoints:

| Endpoint | Functionality | Supported Models |
|----------|--------------|------------------|
| `GET /v1/models` | List available models | All models + CLIP |
| `POST /v1/chat/completions` | Text/image chat (streaming supported) | LLM + VLM |
| `POST /v1/audio/transcriptions` | Audio transcription | Whisper |
| `POST /v1/embeddings` | Text → CLIP vector | CLIP ViT-B/16 |

#### Design Decisions

- **Vision support**: Accepts the OpenAI Vision API format (`image_url` with `data:` base64) as-is. Additionally supports `file_id:123` format to directly reference images from the YU library
- **HTTP URL not supported**: `http://` / `https://` in `image_url` are rejected to prevent SSRF
- **Model aliases**: `whisper-1` → `whisper-base`, `clip` → `clip-vit-b-16`, and other OpenAI-compatible aliases defined
- **Non-WAV audio**: Automatically converted via ffmpeg (16kHz mono PCM16)
- **Usage field**: Hailo SDK does not return token counts, so `0` is used as a constant. Room for future improvement

#### MCP Tools

- `hailo_genai_openai_info`: Helper tool that returns endpoint list and usage instructions (generated locally without calling the API)

### Fix: Quart Async SSE Generators

All route files had async compatibility issues in their SSE generators:

| File | Problem | Fix |
|------|---------|-----|
| `hailo_llm_routes.py` | `def generate_sse()` was a synchronous function | Changed to `async def`, moved `get_llm()` and `next(it)` to `asyncio.to_thread` |
| `hailo_vlm_routes.py` | Same + synchronous DB access | Same + wrapped with `run_db_sync` |
| `hailo_s2t_routes.py` | Synchronous transcribe + synchronous DB | `asyncio.to_thread` + `run_db_sync` wrapping |
| `hailo_chat_routes.py` | Same (both LLM/VLM) | All blocking calls converted to async |

In Quart (ASGI), generators that are not `async def` block the event loop, preventing other requests from being processed during SSE delivery.

### Bug Found: Singleton Inconsistency During Device Switching

#### Symptom

Calling LLM after VLM usage produces `'NoneType' object has no attribute 'get_context_usage_size'` error. Also reproducible in the reverse direction (LLM → VLM → LLM).

#### Root Cause Analysis

Hailo-10H can only hold one VDevice, so `device_manager.py` manages exclusive access. The flow during model switching:

1. VLM's `get_vlm()` → `acquire_genai("vlm", ...)` → internally `_release_internal()` releases LLM's VDevice
2. VLM usage completes
3. LLM's `get_llm()` → `_instance` still exists + `model_name` matches → **reuses existing instance**
4. `_instance._llm`'s underlying VDevice is already released → `get_context_usage_size()` is called on `None` → crash

Root problem: Even though the singleton `_instance` persists, the internal Hailo SDK object (`self._llm`) points to a VDevice that was `.release()`d by `device_manager`'s `_release_internal()`. Python's reference counting keeps `_instance._llm` alive, but the native resources on the Hailo SDK side are freed.

#### Fix

Added `device_manager.get_current_owner()` check to the singleton reuse logic in `get_llm()` / `get_vlm()` / `get_s2t()`:

```python
def get_llm(model_name="qwen2.5-1.5b-chat"):
    global _instance
    with _lock:
        if _instance is not None and _instance.model_name == model_name:
            from core.hailo_device_core.device_manager import get_current_owner
            if get_current_owner() == "llm":
                return _instance  # Device still held → safe to reuse
            # Device was claimed by another model → recreate
            _instance = None
        ...
```

Applied the same fix to all three singletons: LLM, VLM, and S2T.

#### Verification

Confirmed normal operation across 4 consecutive switches: LLM → VLM → LLM → VLM.

### Other Fixes

- **MCP `post_sse` method**: Added `post_sse()` method to `mcp_server/client.py` that consumes an SSE stream and returns the final text as JSON. Used by `hailo_llm_generate` and `hailo_vlm_generate` tools
- **MCP `yolo_search` parameter**: Renamed `labels` → `class_name` (matching the API-side parameter name)
- **Circuit Breaker**: Added `_READ_SUFFIXES` (`_status`, `_info`, `_list`, `_stats`). Status tools like `hailo_genai_status` are now permitted in half_open state
- **Semantic Search async**: Wrapped `get_encoder_info()` and `semantic_search()` with `run_db_sync` (preventing Quart event loop blocking)

### Technical Notes

- **VDevice exclusive constraint is at the SDK level**: Even if Python holds an object reference, the resource becomes unusable once the Hailo SDK's native side releases it. When using the singleton pattern, native resource validity must be checked separately
- **Quart + synchronous generators**: Passing synchronous generators to Quart's SSE responses works, but processing between `yield`s blocks the event loop. Heavy operations like Hailo inference must be offloaded to a separate thread via `asyncio.to_thread`
- **OpenAI Vision API and VLM integration**: The OpenAI Vision API receives images via the `image_url` field, but Hailo VLM receives `frames` (numpy array). The conversion layer performs base64 decode → OpenCV decode → 336x336 RGB resize
