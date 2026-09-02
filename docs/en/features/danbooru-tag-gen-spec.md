# Danbooru Auto-Tagging — Implementation Specification

**Status**: Implemented (Phase 1-5: v2.77.0)
**Target**: YU AI Manager
**Purpose**: Automatically assign Danbooru tags to AI images using a two-tier approach: WD-Tagger ONNX (CPU) + VLM (OpenAI-compatible API)
**Implementation**: `extensions/builtin_wd_tagger/core_impl/` (12 files), `routes/wd_tagger.py` (11 APIs)

---

## Implementation Status

| Phase | Status | Location |
|---|---|---|
| Phase 1: WD-Tagger ONNX | **Complete** | `extensions/builtin_wd_tagger/core_impl/engine_onnx.py` |
| Phase 2: VLM Engine (OpenAI-compatible) | **Complete** (v2.77.0) | `extensions/builtin_wd_tagger/core_impl/engine_vlm.py` + `engine_composite.py` |
| Phase 3: Tag Post-processing | **Complete** (v2.77.0) | `extensions/builtin_wd_tagger/core_impl/tag_postprocess.py` |
| Phase 4: Batch API | **Complete** | `extensions/builtin_wd_tagger/core_impl/batch_ops.py` + `routes/wd_tagger.py` |
| Phase 5: UI | **Complete** | Tools page + detail modal WD tag badges + XMP viewer |

### Phase 2/3 Implementation Overview (v2.77.0-v2.77.1)

- **VLM Engine** (`engine_vlm.py`): Auto-fallback between OpenAI-compatible API and Ollama native API
- **Composite Engine** (`engine_composite.py`): Two-tier ONNX + VLM pipeline (Mode B)
- **Tag Post-processing** (`tag_postprocess.py`): Normalization (lowercase, underscore, invalid character removal, deduplication) + NSFW filter (~30 tags)
- **Engine Factory**: Routing by `engine_type` ("onnx" / "vlm" / "both")
- **UI**: Engine type selection, VLM URL/model/timeout settings, connection test, NSFW filter
- **API**: `GET /api/wd-tagger/vlm/test`, `GET /api/wd-tagger/vlm/models`
- **MCP**: `wd_tagger_vlm_test`, `wd_tagger_vlm_models` tools
- **Tested**: Real image tagging confirmed with Ollama qwen2.5vl:7b, 23 unit tests passing

---

## Prior Art

### DeepDanbooru (KichangKim)
- **Approach**: Image classification model (TensorFlow) for direct tag prediction
- **Strengths**: Fast, tag-specialized, ONNX-convertible
- **Weaknesses**: Fixed tag set, cannot adapt to new tags
- **Reference**: Already integrated into A1111

### WD-Tagger (SmilingWolf) — Adopted in Phase 1
- **Approach**: Successor to DeepDanbooru. Four architectures: SwinV2/ViT/ConvNeXt/EVA02
- **Strengths**: Higher accuracy than DeepDanbooru, category classification included (general/character/copyright/rating)
- **ONNX**: Official ONNX models + `selected_tags.csv` distributed on HuggingFace
- **Input**: 448x448 RGB (aspect ratio preserved + white padding)

### DanTagGen / DTG (KohakuBlueleaf)
- **Approach**: LLaMA-based LLM (400M) for tag generation and completion
- **Strengths**: Context-aware tag completion
- **Weaknesses**: Slow due to LLM inference
- **HuggingFace**: `KBlueLeaf/DanTagGen-beta`

### Design Rationale
The system supports **both** WD-Tagger ONNX (fast, reliable) and Qwen2-VL via hailo-ollama (flexible, context-aware), so users can choose the right tool for the job.

---

## Architecture

```
[Image Input]
    |
[Engine Selection]  (engine_factory.py)
    |-- WD-Tagger ONNX (fast, fixed tag set ~10,000 tags)  [Phase 1: implemented]
    |       | Confidence scores + categorized tag list
    |-- Qwen2-VL via hailo-ollama (slow, flexible, context-aware)   [Phase 2]
    |       | JSON array -> tag parsing
    |-- Two-tier: ONNX -> Qwen2-VL complement                    [Phase 2 option]
    |       | Feed ONNX tags into prompt, let LLM generate additional tags
    |
[Post-processing: tag normalization, NSFW filtering]  [Phase 3]
    |
[DB: save to file_wd_tags table]  (store.py)
[XMP: embed in file (optional)]  (xmp_write.py)
```

---

## Phase 1: WD-Tagger ONNX Engine — Implemented

**Model**: SmilingWolf/wd-swinv2-tagger-v3 (recommended), ViT v3, ConvNeXt v3, EVA02-Large v3

**Implementation files** (`extensions/builtin_wd_tagger/core_impl/`):
| File | Lines | Role |
|---|---|---|
| `types.py` | ~60 | TagPrediction, WdTagResult, WdTaggerEngine ABC |
| `tag_csv.py` | ~70 | selected_tags.csv parsing, category mapping |
| `model_download.py` | ~120 | HuggingFace HTTP download |
| `engine_onnx.py` | ~150 | ONNX inference (448x448, BGR, threshold filtering) |
| `engine_factory.py` | ~50 | Engine cache + creation |
| `store.py` | ~130 | DB CRUD (file_wd_tags table) |
| `xmp_xml.py` | ~60 | XMP packet construction |
| `xmp_read.py` | ~90 | XMP reading |
| `xmp_write.py` | ~160 | XMP writing to PNG/JPEG/WebP |
| `config_ops.py` | ~70 | config.json read/write |
| `single_ops.py` | ~80 | Single-image tagging pipeline |
| `batch_ops.py` | ~120 | Batch processing (JobManager integration) |

**DB**: `file_wd_tags` table (schema v14)
```sql
CREATE TABLE file_wd_tags (
    id         INTEGER PRIMARY KEY,
    file_id    INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    tag_name   TEXT NOT NULL,
    confidence REAL NOT NULL,
    category   TEXT NOT NULL DEFAULT 'general',
    model      TEXT NOT NULL,
    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    UNIQUE(file_id, tag_name, model)
);
```

**API**: `routes/wd_tagger.py` — 11 endpoints

---

## Phase 2: VLM Engine (OpenAI-compatible API) — Implemented (v2.77.0)

**Purpose**: Supplement WD-Tagger ONNX with detailed descriptions and contextual tags that ONNX cannot capture
**Implementation**: `extensions/builtin_wd_tagger/core_impl/engine_vlm.py` (generic OpenAI-compatible VLM engine)
**Note**: The original spec planned a Hailo-specific `engine_hailo.py`, but the actual implementation uses a generic engine `engine_vlm.py` that handles Ollama, hailo-ollama, and other OpenAI-compatible servers uniformly. It supports automatic fallback between the OpenAI-compatible API (`/v1/chat/completions`) and Ollama native API (`/api/chat`).

### Hardware Configuration

| Item | Specification |
|---|---|
| **Device** | Raspberry Pi 5 + Hailo-10H AI accelerator |
| **Memory** | 8GB RAM |
| **VLM Model** | **Qwen2-VL-2B-Instruct** (only VLM in Hailo Model Zoo) |
| **Inference Framework** | hailo-ollama (OpenAI-compatible API) |
| **Endpoint** | `http://<pi-ip>:8000/v1/chat/completions` |

### Model Characteristics

- **Qwen2-VL-2B-Instruct**: A Vision-Language model from the Qwen family (2B parameters)
- It belongs to the Qwen family, not the llava family. Image understanding accuracy is generally higher than llava-based models
- At 2B parameters, it fits comfortably within the Hailo-10H 8GB RAM
- The text-only Qwen2 (1.5B) has been confirmed to work with hailo-ollama
- **Note**: As of 2026-02, this is the only VLM available for Hailo-10H

### Prompt Design

```python
SYSTEM_PROMPT = """You are a Danbooru image tagging assistant.
Analyze the image and output ONLY Danbooru-style tags as a JSON array.
Rules:
- Use underscores instead of spaces (e.g., long_hair, blue_eyes)
- Output ONLY the JSON array, no other text
- Include tags for: character count, gender, hair, eyes, clothing, pose, background, art style
- Do NOT include copyright or character name tags unless clearly identifiable
- Maximum 40 tags
Example output: ["1girl", "solo", "long_hair", "blue_eyes", "smile"]"""

USER_PROMPT = "Tag this image with Danbooru tags."
```

### Implementation Design (`extensions/builtin_wd_tagger/core_impl/engine_hailo.py` — ~100 lines)

```python
import base64
import json
import logging
import urllib.request
from pathlib import Path

from .types import TagPrediction, WdTagResult, WdTaggerEngine

logger = logging.getLogger(__name__)

_USER_AGENT = "YU-AI-Manager/2.0 (WD-Tagger Qwen2-VL)"

class HailoQwen2VLEngine(WdTaggerEngine):
    """Qwen2-VL-2B-Instruct via hailo-ollama (OpenAI-compatible API)."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        model: str = "qwen2-vl:2b",
        timeout: int = 60,
    ):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    def tag_image(self, image_path: str) -> WdTagResult:
        with open(image_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode()

        # MIME type inference
        suffix = Path(image_path).suffix.lower()
        mime = {"png": "image/png", "webp": "image/webp"}.get(
            suffix.lstrip("."), "image/jpeg"
        )

        payload = json.dumps({
            "model": self._model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {
                            "url": f"data:{mime};base64,{image_b64}"
                        }},
                        {"type": "text", "text": USER_PROMPT},
                    ],
                },
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": 512,
            "temperature": 0.3,
        }).encode()

        req = urllib.request.Request(
            f"{self._base_url}/v1/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": _USER_AGENT,
            },
        )

        resp = urllib.request.urlopen(req, timeout=self._timeout)
        data = json.loads(resp.read())
        content = data["choices"][0]["message"]["content"]
        raw_tags = json.loads(content)

        # Response format: list or {"tags": [...]}
        if isinstance(raw_tags, dict) and "tags" in raw_tags:
            raw_tags = raw_tags["tags"]
        if not isinstance(raw_tags, list):
            raw_tags = []

        tags = []
        for t in raw_tags:
            name = str(t).strip().lower().replace(" ", "_")
            if name:
                tags.append(TagPrediction(
                    tag=name,
                    confidence=0.5,  # LLMs do not return confidence scores
                    category="general",
                ))

        return WdTagResult(tags=tags, model=self._model)

    def get_name(self) -> str:
        return f"Qwen2-VL ({self._model})"

    def is_available(self) -> bool:
        """Check connectivity to the hailo-ollama server."""
        try:
            req = urllib.request.Request(
                f"{self._base_url}/v1/models",
                headers={"User-Agent": _USER_AGENT},
            )
            resp = urllib.request.urlopen(req, timeout=5)
            return resp.status == 200
        except Exception:
            return False
```

### Operating Modes

**Mode A: Qwen2-VL Standalone**
```
Image -> Qwen2-VL -> JSON tag array -> Normalization -> DB save
```
- The LLM directly analyzes the image and generates tags
- No confidence scores (uniformly set to 0.5)
- Flexible tagging without a fixed tag set
- Speed: ~3-10 seconds per image (estimated on Hailo-10H)

**Mode B: WD-Tagger ONNX -> Qwen2-VL Complement (Two-tier)**
```
Image -> WD-Tagger ONNX -> High-confidence tags (>=0.7)
                              |
                              v
    Qwen2-VL: "These tags describe the image. Suggest additional tags."
                              |
                              v
    ONNX tags + LLM complement tags -> Merge -> Normalization -> DB save
```
- Combines reliable ONNX tags with the LLM's contextual understanding
- Including ONNX tags in the prompt should improve LLM accuracy
- Speed: ONNX (~0.5s) + LLM (~3-10s) = ~4-11 seconds per image

**Mode B Prompt**:
```python
补完_SYSTEM_PROMPT = """You are a Danbooru image tagging assistant.
The image already has these tags from automated classification: {existing_tags}
Analyze the image and suggest ADDITIONAL Danbooru-style tags not in the list above.
Output ONLY a JSON array of new tags. Use underscores instead of spaces.
Focus on: composition, mood, background details, specific clothing items, art style.
Maximum 20 additional tags.
Example: ["looking_at_viewer", "outdoors", "cloudy_sky", "pleated_skirt"]"""
```

### Addition to engine_factory.py

```python
# Addition to get_engine() in engine_factory.py

engine_type = config.get("engine_type", "onnx")  # "onnx" | "hailo" | "both"

if engine_type == "hailo":
    from .engine_hailo import HailoQwen2VLEngine
    engine = HailoQwen2VLEngine(
        base_url=config.get("hailo_url", "http://localhost:8000"),
        model=config.get("hailo_model", "qwen2-vl:2b"),
        timeout=config.get("hailo_timeout", 60),
    )
elif engine_type == "both":
    # Two-tier: ONNX -> Hailo complement (Phase 2 option)
    ...
```

### config.json Entries

```json
{
  "wd_tagger": {
    "model": "SmilingWolf/wd-swinv2-tagger-v3",
    "general_threshold": 0.35,
    "character_threshold": 0.85,
    "write_xmp": true,
    "auto_download": true,
    "engine_type": "onnx",
    "hailo_url": "http://localhost:8000",
    "hailo_model": "qwen2-vl:2b",
    "hailo_timeout": 60
  }
}
```

### Pre-implementation Verification (Pi Hardware Testing)

1. **Confirm that Qwen2-VL-2B-Instruct launches on hailo-ollama**
   ```bash
   # On the Pi
   hailo-ollama run qwen2-vl:2b
   ```

2. **Confirm that vision requests work through the OpenAI-compatible API**
   ```bash
   curl -X POST http://localhost:8000/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{
       "model": "qwen2-vl:2b",
       "messages": [{"role": "user", "content": [
         {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,/9j/..."}},
         {"type": "text", "text": "What is in this image?"}
       ]}],
       "max_tokens": 256
     }'
   ```

3. **Confirm that Danbooru-format JSON output is stable**
   - Check that hailo-ollama supports `response_format: json_object`
   - A regex-based JSON extraction fallback from text output is needed if unsupported

4. **Measure actual inference speed** — seconds per image (required for batch size calculation)

---

## Phase 3: Tag Post-processing — Implemented (v2.77.0)

**Implementation**: `extensions/builtin_wd_tagger/core_impl/tag_postprocess.py`
**Integration**: Automatically applied after inference in `single_ops.py` / `batch_ops.py`

```python
class TagPostProcessor:
    INVALID_CHARS = set('[](){}"\'/\\')
    MAX_TAG_LEN = 100

    def normalize(self, tags: list[str]) -> list[str]:
        result = []
        for tag in tags:
            tag = tag.strip().lower()
            tag = tag.replace(" ", "_")
            # Remove invalid characters
            tag = "".join(c for c in tag if c not in self.INVALID_CHARS)
            if 1 <= len(tag) <= self.MAX_TAG_LEN:
                result.append(tag)
        # Deduplicate and sort
        return sorted(set(result))

    def filter_nsfw(self, tags: list[str], allow_nsfw: bool) -> list[str]:
        # NSFW tag list (managed in a separate file)
        if allow_nsfw:
            return tags
        return [t for t in tags if t not in NSFW_TAG_SET]
```

**Integration with Phase 1**:
- WD-Tagger ONNX already separates rating tags using category 9 (rating)
- The NSFW filter uses rating tags (`explicit`, `questionable`) plus an additional NSFW list
- Implementation: `extensions/builtin_wd_tagger/core_impl/tag_postprocess.py` (~80 lines)

---

## Phase 4: Batch Processing API — Implemented

**API** (`routes/wd_tagger.py`):

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/wd-tagger/batch` | Start batch (file_ids, limit, force) |
| POST | `/api/wd-tagger/tag/<file_id>` | Tag a single image |
| GET | `/api/wd-tagger/tags/<file_id>` | Retrieve tags |
| DELETE | `/api/wd-tagger/tags/<file_id>` | Delete tags |
| GET | `/api/wd-tagger/stats` | Statistics |
| GET | `/api/wd-tagger/untagged` | List untagged files |
| GET/POST | `/api/wd-tagger/config` | Settings CRUD |
| POST | `/api/wd-tagger/model/download` | Model download |
| GET | `/api/wd-tagger/model/status` | Model status |
| GET | `/api/wd-tagger/xmp/<file_id>` | XMP reading |

**Processing flow** (`batch_ops.py`):
1. Process files in `file_ids` sequentially (defaults to untagged files with `meta_source=unknown` when unspecified)
2. Run inference through the engine
3. UPSERT into the `file_wd_tags` table (engine identified by the model column)
4. Embed XMP in the file (optional)
5. Track progress and support cancellation via JobManager

---

## Phase 5: UI — Implemented

**Tools page** (`templates/tools/content/primary/_wd_tagger.html`):
- Model selection (4 models), threshold sliders (general/character)
- XMP write toggle, model download button
- Batch execution button + progress bar
- Statistics display (tag count, per-category breakdown, untagged count)

**Detail modal**:
- WD tag badges (general=blue, character=green, copyright=orange, rating=red)
- XMP viewer button (dc:subject + wdtag namespace + raw XML)
- Tag click triggers search

---

## File Structure (Current)

```
extensions/builtin_wd_tagger/core_impl/
├── __init__.py              # Module initialization
├── types.py                 # TagPrediction, WdTagResult, WdTaggerEngine ABC
├── tag_csv.py               # selected_tags.csv parsing
├── model_download.py        # HuggingFace model download
├── engine_onnx.py           # WD-Tagger ONNX inference [Phase 1]
├── engine_vlm.py            # VLM engine (OpenAI-compatible) [Phase 2: complete]
├── engine_composite.py      # ONNX + VLM two-tier [Phase 2: complete]
├── engine_factory.py        # Engine creation + cache
├── store.py                 # DB CRUD (file_wd_tags)
├── xmp_xml.py               # XMP packet construction
├── xmp_read.py              # XMP reading
├── xmp_write.py             # XMP writing (PNG/JPEG/WebP)
├── config_ops.py            # config.json read/write
├── single_ops.py            # Single-image tagging pipeline
├── batch_ops.py             # Batch processing (JobManager)
├── batch_processors.py      # Batch processing internal logic
└── tag_postprocess.py       # Tag normalization, NSFW filter [Phase 3: complete]

routes/wd_tagger.py          # API endpoints (11 total)

src/ts/tools-page/wd-tagger/
├── core.ts                  # Settings CRUD, batch, model download
└── render.ts                # DOM rendering

src/ts/runtime-tools-ui/tools/
└── wd-tags.ts               # Detail modal WD tags + XMP viewer
```

---

## Implementation Priority (Updated)

```
Phase 1 (WD-Tagger ONNX)        -> Complete
Phase 4 (Batch API)              -> Complete
Phase 5 (UI)                     -> Complete
Phase 3 (Post-processing/NSFW)   -> Next (~80 additional lines)
Phase 2 (Qwen2-VL hailo-ollama) -> After Pi hardware testing (~100 additional lines + factory changes)
```

---

## References

- WD-Tagger (SmilingWolf): https://huggingface.co/SmilingWolf/wd-swinv2-tagger-v3
- DeepDanbooru: https://github.com/KichangKim/DeepDanbooru
- DanTagGen: https://huggingface.co/KBlueLeaf/DanTagGen-beta
- Hailo Model Zoo VLM: Qwen2-VL-2B-Instruct (hailo.ai Model Explorer)
- hailo-ollama API specification: Refer to the modified fork source

---

*Created: 2026-02-27 / Updated: 2026-02-27 (Phase 1 implementation complete, Phase 2 revised to Qwen2-VL base)*
