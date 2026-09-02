# Hailo Semantic Search Extension — Implementation Specification

**Status**: Implemented — The Hailo-specific version has been superseded by CLIP ONNX (v2.95.0)
**Target**: YU AI Manager Extension
**Purpose**: Semantic image search using CLIP/SigLIP on Hailo-10H (AI HAT 2)
**Implementation**: `extensions/builtin_clip_search/core_impl/` (shared layer) + `extensions/builtin_clip_onnx/core_impl/` (ONNX implementation)
**Note**: This specification describes the initial Hailo-only design. The current implementation uses a unified ONNX multi-backend architecture

---

## Overview

This Extension adds the ability to search images using natural language text.
Examples: "blue sky and ocean", "girl smiling", "night cityscape" — all return visually similar images.

It is required to work **in parallel** with the existing FTS5 tag search and pHash similarity search.
The Extension simply disables itself in environments where no Hailo device is present.

---

## Architecture

```
[During image scan]
Image file -> CLIP Image Encoder (Hailo HEF) -> 512-dim vector -> DB storage

[During search]
Text input -> CLIP Text Encoder (CPU / Hailo HEF) -> 512-dim vector
           -> Cosine similarity search -> file_id list -> Merge with existing search results
```

**Both CLIP and SigLIP are supported**, switchable via configuration.
SigLIP offers higher accuracy, but CLIP has a stronger track record and more community resources.
The recommended approach is to start with CLIP and add SigLIP later.

---

## Phase Breakdown

### Phase 1: Feasibility Verification (Do This First)

After moving to the Pi5 environment, have Claude Code execute the following steps **in order from top to bottom**.
Stop at any step that fails and address the issue before continuing.

#### Step 1-1: Verify HailoRT Runtime

```bash
# Check device recognition
hailortcli fw-control identify

# Check Python bindings
python3 -c "import hailo_platform; print('HailoRT version:', hailo_platform.__version__)"
```

- **Device not visible**: Check driver status with `dmesg | grep hailo`. Verify AI HAT 2 PCIe connection
- **Import fails**: Install via `pip install hailort` or from the Hailo APT repository (`python3-hailort`)

#### Step 1-2: Download CLIP HEF Files

```bash
mkdir -p ~/hailo_models && cd ~/hailo_models

# Image encoder
wget https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/clip_vit_b_16_image_encoder.hef

# Text encoder
wget https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/clip_vit_b_16_text_encoder.hef
```

- **403 / Access denied**: Registration on Hailo Developer Zone (https://hailo.ai/developer-zone/) is required.
  After registration, try downloading via Model Zoo CLI (`hailo_model_zoo`)
- **Size check**: Each file should be tens to ~100 MB. An unusually small file indicates a download failure

#### Step 1-3: Install Python Dependencies

```bash
# Required for image preprocessing (used in Phase 1)
pip install opencv-python-headless numpy

# Verify
python3 -c "import cv2; import numpy; print('cv2:', cv2.__version__, 'numpy:', numpy.__version__)"
```

#### Step 1-4: Minimal Inference Test

```python
from hailo_platform import HEF, VDevice, HailoStreamInterface, InferVStreams, ConfigureParams
import numpy as np

hef_path = "/home/<user>/hailo_models/clip_vit_b_16_image_encoder.hef"
hef = HEF(hef_path)

# Check HEF input/output layer info (layer names vary by model)
print("Input layers:", [l.name for l in hef.get_input_vstream_infos()])
print("Output layers:", [l.name for l in hef.get_output_vstream_infos()])

with VDevice() as target:
    configure_params = ConfigureParams.create_from_hef(hef, interface=HailoStreamInterface.PCIe)
    network_groups = target.configure(hef, configure_params)
    network_group = network_groups[0]

    input_info = hef.get_input_vstream_infos()[0]
    input_name = input_info.name
    input_shape = input_info.shape  # Expected: (224, 224, 3) etc.
    print(f"Input: name={input_name}, shape={input_shape}")

    # Inference test with a dummy image
    dummy = np.random.randint(0, 255, (1, *input_shape), dtype=np.uint8)
    with InferVStreams(network_group, {}) as pipeline:
        result = pipeline.infer({input_name: dummy})
        for name, data in result.items():
            print(f"Output: name={name}, shape={data.shape}, dtype={data.dtype}")
            # Success if a 512-dim vector is output
```

- **VDevice error (`not enough free devices`)**: hailo-ollama may be running. Stop it with `systemctl stop hailo-ollama` and retry
- **Inference succeeds but output is not 512-dim**: Verify the HEF version and model variant

#### Step 1-5: Decision Criteria

| Result | Next Action |
|------|----------------|
| 512-dim vector output | Proceed to Phase 2 and beyond |
| HEF loads successfully but output dimensions differ | Try a different model variant (clip_resnet_50 etc.) |
| Cannot download HEF | Register on Developer Zone -> download via Model Zoo CLI |
| Cannot import hailo_platform | Reinstall HailoRT. Fall back to CPU CLIP if unresolved |
| Device not recognized | Hardware connection / driver issue. Pause this Extension development |

Proceed with the full implementation if Phase 1 succeeds. Consider CPU CLIP as an alternative if it does not.

---

### Phase 2: DB Schema Extension

Add to the existing DB migration:

```sql
-- migration 14: semantic search vectors
CREATE TABLE IF NOT EXISTS file_vectors (
    file_id     INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
    model       TEXT NOT NULL DEFAULT 'clip',   -- 'clip' | 'siglip'
    vector      BLOB NOT NULL,                  -- float32 numpy array -> bytes
    created_at  INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);

CREATE INDEX IF NOT EXISTS idx_file_vectors_model ON file_vectors(model);
```

Storage: `numpy.ndarray.tobytes()` -> BLOB
Loading: `numpy.frombuffer(blob, dtype=numpy.float32)`

**Note**: SQLite has no ANN (Approximate Nearest Neighbor) index, so all 200,000 records require full cosine similarity computation. Batch computation with numpy should keep this within acceptable limits on Pi5 (measurement required). Consider the `sqlite-vec` extension if the record count grows significantly.

---

### Phase 3: Hailo Inference Core

**File structure**:
```
extensions/hailo_semantic_search/
├── __init__.py
├── extension.py          # Extension entry point
├── core/
│   ├── hailo_clip.py     # Hailo CLIP inference wrapper
│   ├── cpu_clip.py       # CPU fallback for non-Hailo environments (optional)
│   └── vector_store.py   # DB vector CRUD
├── routes/
│   └── semantic_search.py  # API endpoints
└── templates/
    └── _semantic_search_ui.html
```

**Responsibilities of `hailo_clip.py`**:
- HEF loading and VDevice initialization (singleton, once at startup)
- Image -> preprocessing (224x224 resize, normalization) -> HEF inference -> 512-dim vector
- Text -> tokenization -> HEF inference -> 512-dim vector
  * Use the text encoder HEF if available for Hailo-10H; otherwise use CPU (transformers library)

**Preprocessing**:
```python
import cv2
import numpy as np

def preprocess_image(path: str) -> np.ndarray:
    img = cv2.imread(path)
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    img = cv2.resize(img, (224, 224))
    img = img.astype(np.float32) / 255.0
    mean = np.array([0.48145466, 0.4578275, 0.40821073])
    std  = np.array([0.26862954, 0.26130258, 0.27577711])
    img = (img - mean) / std
    return img[np.newaxis, ...]  # (1, 224, 224, 3)
```

---

### Phase 4: Index Building API

**Endpoint**:
```
POST /api/extensions/hailo-semantic/index
```
- Processes unindexed images sequentially in a background thread
- Sends progress via SSE as `semantic_index.progress` events
- Optionally hooks into the existing `scan.complete` event for automatic execution

**Batch size**: 32 images per batch (balancing memory and speed)

```
GET /api/extensions/hailo-semantic/index/status
-> { "total": 200000, "indexed": 12500, "running": true }
```

---

### Phase 5: Semantic Search API

```
GET /api/extensions/hailo-semantic/search?q=blue sky&limit=50&threshold=0.25
```

**Processing flow**:
1. Convert text `q` to a vector
2. Load all vectors from `file_vectors` (numpy)
3. Compute cosine similarity in batch
4. Sort results above `threshold` by descending similarity
5. Return the `file_id` list in the existing `/api/search` format

**Cosine similarity computation**:
```python
def cosine_similarity_batch(query_vec: np.ndarray, stored_vecs: np.ndarray) -> np.ndarray:
    # query_vec: (512,), stored_vecs: (N, 512)
    query_norm = query_vec / np.linalg.norm(query_vec)
    stored_norm = stored_vecs / np.linalg.norm(stored_vecs, axis=1, keepdims=True)
    return stored_norm @ query_norm  # (N,)
```

**Performance target**: Under 1 second for 200,000 records (achievable with numpy batch computation, even on Pi5)

---

### Phase 6: UI Integration

Add a "Semantic Search" tab to the existing search UI.
It can be a standalone UI independent of the existing condition-builder (integration is for the future).

```html
<!-- Add toggle button next to search bar -->
<button id="semantic-search-toggle" class="btn-secondary">
  🔍 Semantic Search (Hailo)
</button>
```

- Hide or gray out the button when no Hailo device is detected
- Reuse the existing grid for search results
- Show a prompt to build the index when no index exists

---

## Configuration (config.json addition)

```json
{
  "hailo_semantic_search": {
    "enabled": true,
    "model": "clip",           // "clip" | "siglip"
    "device": "auto",          // "auto" | "hailo" | "cpu"
    "batch_size": 32,
    "similarity_threshold": 0.25,
    "auto_index_on_scan": false,
    "hef_dir": "~/.local/share/hailo-ollama/models"
  }
}
```

---

## Verified Facts (as of 2026-02-27)

The following information has been confirmed through prior research. Use it as reference during Phase 1 execution.

### CLIP HEF Availability

Hailo Model Zoo v5.2.0 contains **both image and text encoder** HEFs for Hailo-10H across CLIP/SigLIP variants:

| Model | Image Encoder HEF | Text Encoder HEF |
|--------|-------------------|-------------------|
| clip_vit_b_16 | Available | Available |
| clip_vit_b_32 | Available | Available |
| clip_vit_l_14 | Available | Available |
| clip_resnet_50 | Available | Available |
| siglip_b_16 | Available | Available |
| siglip_l_16_256 | Available | Available |
| siglip2_b_32_256 | Available | Available |
| TinyCLIP variants | Available | Available |

S3 URL pattern: `https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/<model>.hef`

### Text Encoder Status

- The official `hailo-CLIP` app runs **the text encoder on CPU (PyTorch)**
- Text Encoder HEFs for Hailo-10H exist in Model Zoo, but **no published application uses them**
- Recommended approach: **Implement the text encoder on CPU (`sentence-transformers`)**. It runs only once per search query, so speed is not a concern
- The image encoder is where Hailo acceleration provides real value (batch indexing of 200K images)

### Coexistence with hailo-ollama

- Device sharing via `SHARED_VDEVICE_GROUP_ID` is officially supported
- However, **the hailo-ollama binary does not participate in this sharing** (it exclusively occupies the device)
- Community example: A custom device manager was built to run 6 services simultaneously
- **Practical approach**: Stop hailo-ollama during index building and time-share the device
  - `systemctl stop hailo-ollama` -> Build index -> `systemctl start hailo-ollama`

### Vector Search Estimates for 200,000 Records

- 200K x 512 float32 = approximately 400MB — fits within Pi5 (8GB) RAM
- numpy batch cosine similarity should complete within 1 second on the Pi5 Cortex-A76

### FAISS Acceleration for Large-Scale Vector Search (v3.26.0)

FAISS (Facebook AI Similarity Search) support was added in v3.26.0. The system auto-detects `faiss-cpu` when installed and uses approximate nearest neighbor search instead of NumPy brute force.

| Scale | NumPy (O(N)) | FAISS IndexFlatIP | FAISS IndexIVFFlat |
|------|-------------|-------------------|-------------------|
| 10K | ~10ms | ~2ms | - |
| 100K | ~100ms | ~20ms | ~5ms |
| 500K | ~500ms | ~100ms | ~10ms |
| 1.5M | ~1.5s | ~300ms | ~20ms |

- **< 50K**: IndexFlatIP (exact inner product search) is auto-selected
- **>= 50K**: IndexIVFFlat (IVF clustering) is auto-selected, nprobe = nlist/10
- Falls back to NumPy when FAISS is not installed (no impact)

**Installation**:
```bash
source venv/bin/activate
uv pip install faiss-cpu  # Direct pip install works on x86_64
# On aarch64 (RPi): conda install -c conda-forge faiss-cpu or build from source
```

The startup log shows `FAISS x.x.x detected — using accelerated vector search` when active.

### Notes on the hailo-CLIP App

- `hailo-ai/hailo-CLIP` targets **Hailo-8/8L**. Hailo-10H is not supported
- It is designed for real-time zero-shot classification, not image search pipelines
- It serves as reference material but cannot be used directly. A custom pipeline must be built using the HailoRT API

---

## Alternative (When Hailo Is Unavailable)

`sentence-transformers` with `clip-ViT-B-32` provides CPU-only CLIP support.
It is slower but allows the same Extension to run in environments without Hailo.

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('clip-ViT-B-32')
image_embedding = model.encode(Image.open(path))
text_embedding  = model.encode("blue sky")
```

Setting `"device": "cpu"` in the Extension configuration enables CPU mode. This dual-architecture approach maximizes portability.

---

## Implementation Priority

```
Phase 1 (Verification)   -> Required, do this first
Phase 2 (DB)             -> After Phase 1 success
Phase 3 (Inference core) -> After Phase 2
Phase 4 (Indexing)       -> After Phase 3
Phase 5 (Search API)     -> After Phase 4
Phase 6 (UI)             -> After Phase 5, last
```

Switch the entire approach to CPU CLIP if Phase 1 fails.

---

## Reference Repositories

- `hailo-ai/hailo-apps`: CLIP zero-shot classification samples
- `hailo-ai/hailort`: pyHailoRT API reference
- `hailo-ai/Hailo-Application-Code-Examples`: Python inference samples
- `hailo-ai/hailo_model_zoo`: CLIP/SigLIP HEF download source

---

*Created: 2026-02-27*
*Research addendum: 2026-02-27 — Phase 1 procedure details, HEF availability confirmation, hailo-ollama coexistence analysis*
