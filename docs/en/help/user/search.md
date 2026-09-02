# Search

## Basic Search

Enter tags separated by commas in the search bar.

```
1girl, blue_eyes, school_uniform
```

## Search Filters

| Filter | Description |
|--------|-------------|
| Date range | Filter by start and end date |
| File format | PNG / WebP / JPG / GIF |
| Rating | Filter by 1–5 stars |
| Favorites | Show only favorited images |
| Collection | Show only images in a specific collection |

## Prompt Search

Use the "in_prompt" field to perform a full-text search within image prompt text.
When FTS (Full-Text Search) is enabled, searches are significantly faster.

## Sort Order

| Sort | Description |
|------|-------------|
| date | Registration date (newest first) |
| date_old | Registration date (oldest first) |
| folder | By folder |
| path | By path |
| random | Random |
| rating_desc | Rating (highest first) |
| rating_asc | Rating (lowest first) |

## Semantic Search

If a Hailo-10H or ONNX CLIP model is configured, you can search for images using natural language.
Use the semantic search button to the right of the search bar.

### Acceleration with FAISS (Recommended)

Semantic search uses NumPy brute-force search by default, but
**installing FAISS provides a significant speedup**.

| Library size | NumPy (default) | FAISS (recommended) |
|-------------|-----------------|---------------------|
| Under 10K | Tens of ms | A few ms |
| 100K | 1–3 seconds | Tens of ms |
| 1M+ | 10+ seconds | Under 100ms |

FAISS automatically selects the optimal index type based on the library size:
- **Under 50K**: IndexFlatIP (exact search, fast enough)
- **50K and above**: IndexIVFFlat (approximate nearest neighbor, fast at scale)

#### Installation

```bash
# Activate venv before installing
source venv/bin/activate

# x86_64 (Intel/AMD) — direct pip install
uv pip install faiss-cpu

# Raspberry Pi 5 (aarch64) — if pip install fails
# Option 1: via conda
conda install -c conda-forge faiss-cpu

# Option 2: build from source
# https://github.com/facebookresearch/faiss/blob/main/INSTALL.md
```

After installation, simply restart the server — FAISS will be auto-detected.
If the following message appears in the startup log, FAISS is active:

```
FAISS x.x.x detected — using accelerated vector search
```

If FAISS is not installed, the system will continue to work using NumPy as before.
