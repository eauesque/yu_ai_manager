# Tag Database - Debug Checklist

**Debug list in priority order**
**Status**: Legacy (recorded during v2.5.x era; all items have been resolved)
**Last updated**: 2026-02-13

---

## P0 (Critical): Immediate Fix (Affects Usability)

### ✅ 1. UI Layout Misalignment Fix

**Problem:**
```
Search fields overflow when placed side by side,
causing buttons to shift out of position.
```

**How to verify:**
1. Launch the WebUI
2. Resize the browser to 1366x768
3. Check search field alignment

**Fix location:** `templates/index.html`
```html
<!-- Before -->
<div class="search-row">
  <div class="form-group">...</div>
  <div class="form-group">...</div>
  <div class="form-group">...</div>
  <div class="form-group">...</div>
  <div class="form-group">...</div>
  <div class="form-group">...</div>
</div>

<!-- After -->
<div class="search-row">
  <!-- Add flex-wrap: wrap -->
  <div class="form-group" style="flex: 1 1 200px;">...</div>
  ...
</div>
```

**Verification:**
- [ ] Displays correctly at 1920x1080
- [ ] Displays correctly at 1366x768
- [ ] Displays correctly at 768x1024 (tablet)

---

### ✅ 2. Tag Autocomplete Deduplication

**Problem:**
```
Autocomplete suggestions contain duplicates.

Example:
  sample_creator_a,sample_creator_b,sample_creator_c
  sample_creator_a, sample_creator_b, sample_creator_c
  ^ Differ only by spacing
```

**How to verify:**
1. Type "sample_creator" in the tag input field
2. Check autocomplete suggestions
3. Look for duplicates

**Fix location:** `static/js/main/main.js`
```javascript
// Inside initTagAutocomplete()
async function fetchSuggestions(q) {
  const response = await fetch(`/api/suggest?q=${encodeURIComponent(q)}`);
  const data = await response.json();

  // Normalize and deduplicate
  const normalized = new Map();

  for (const item of data) {
    const clean = item.tag
      .replace(/,(?!\s)/g, ', ')  // Add space after commas
      .replace(/\s+/g, ' ')        // Collapse multiple spaces
      .trim();

    if (!normalized.has(clean)) {
      normalized.set(clean, item.count);
    } else {
      // Merge counts
      normalized.set(clean, normalized.get(clean) + item.count);
    }
  }

  return Array.from(normalized.entries()).map(([tag, count]) => ({
    tag,
    count
  }));
}
```

**Verification:**
- [ ] No duplicates remain
- [ ] Counts are properly merged
- [ ] No performance issues

---

## P1 (High): Improvement (Affects Functionality)

### ✅ 3. Bracket Normalization in Search

**Problem:**
```
Verify that \(tag\) and (tag) are treated as equivalent.
```

**How to verify:**
1. Prepare an image with the tag `\(emphasis\)`
2. Search for `(emphasis)` in the search field
3. Check that the image appears in results

**Checkpoints:**
- [ ] Searching `(tag)` also matches `\(tag\)`
- [ ] Searching `\(tag\)` also matches `(tag)`
- [ ] Regex mode does not apply this normalization

**Related code:** `web_ui.py` - `normalize_tag_for_search()`

---

### ✅ 4. In-ZIP File Reading Test

**Problem:**
```
Verify that images inside ZIP archives display correctly
and that metadata is extracted properly.
```

**Test cases:**

#### Test 1: Basic Operation
```bash
# 1. Create a test ZIP
zip test.zip image1.png image2.png

# 2. Scan
python tagdb_tool.py scan --db test.db --root . --scan-zips

# 3. Verify
python tagdb_tool.py search --db test.db --q "*"
```

**Checks:**
- [ ] In-ZIP files are registered as `test.zip!image1.png`
- [ ] Metadata is extracted
- [ ] Thumbnails are displayed

#### Test 2: Extraction Feature
```
1. Open an in-ZIP file in the WebUI
2. Click the "Extract and Edit" button
3. Verify that the file manager opens
4. Verify that the extracted file exists
```

**Checks:**
- [ ] The extract button is visible
- [ ] Clicking it opens the file manager
- [ ] Files are extracted to the extracted/ directory
- [ ] The extracted file is registered in the DB

#### Test 3: Large ZIP
```bash
# 1) Create a 1.1 GB ZIP (Zip64)
mkdir -p /tmp/tagdb_largezip_test/input
python - <<'PY'
from pathlib import Path
import base64
Path('/tmp/tagdb_largezip_test/input/sample.png').write_bytes(
    base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+X2foAAAAASUVORK5CYII=')
)
PY
truncate -s 1100M /tmp/tagdb_largezip_test/input/payload.bin
python - <<'PY'
import zipfile
from pathlib import Path
root = Path('/tmp/tagdb_largezip_test')
with zipfile.ZipFile(root / 'large_1_1gb.zip', 'w', compression=zipfile.ZIP_STORED, allowZip64=True) as z:
    z.write(root / 'input' / 'sample.png', arcname='images/sample.png')
    z.write(root / 'input' / 'payload.bin', arcname='payload/payload.bin')
print((root / 'large_1_1gb.zip').stat().st_size)
PY

# 2) Scan the ZIP
/usr/bin/time -f 'elapsed=%E maxrss_kb=%M' \
  python tagdb_tool.py scan --db /tmp/tagdb_largezip_test/largezip.db \
  --root /tmp/tagdb_largezip_test --recursive --scan-zips
```

**Checks:**
- [x] Memory usage stays within normal bounds
- [x] Scan completes within an acceptable time (under 5 minutes)
- [x] No errors

**Measured results (2026-02-17):**
- ZIP size: `1,153,433,914 bytes` (approx. 1.1 GB)
- Elapsed time: `elapsed=0:00.14`
- Peak RSS: `maxrss_kb=23864`
- DB records: `zip_members=1` (`large_1_1gb.zip!images/sample.png`)

---

### ✅ 5. Checkpoint Search Test

**Problem:**
```
Verify that model names are correctly extracted and searchable.
```

**Test cases:**

#### Test 1: Model Name Extraction
```python
# Verify extraction across each format

# NovelAI
metadata = {"model": "nai-diffusion-3"}
→ model_name: "nai-diffusion-3"

# SD
metadata = {"Model": "animagine-xl-3.1", "Model hash": "abc123"}
→ model_name: "animagine-xl-3.1", model_hash: "abc123"

# ComfyUI
metadata = {"checkpoint": "ponyDiffusionV6XL.safetensors"}
→ model_name: "ponyDiffusionV6XL"
```

**Checks:**
- [ ] Extraction works for NovelAI format
- [ ] Extraction works for SD format
- [ ] Extraction works for ComfyUI format

#### Test 2: Search Functionality
```
1. Click the checkpoint input field in the WebUI
2. Verify that autocomplete appears
3. Search for "animagine"
4. Verify that only images from that model are displayed
```

**Checks:**
- [ ] Autocomplete works
- [ ] Partial matching works
- [ ] Results are sorted by usage frequency

---

## P2 (Medium): Future Work (Performance Improvements)

### ✅ 6. Thumbnail Cache Implementation

**Problem:**
```
Thumbnails for in-ZIP files are regenerated on every request.
This is slow.
```

**Proposed implementation:**
```python
# web_ui.py
import hashlib

CACHE_DIR = Path("cache/thumbnails")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

@app.route("/api/thumbnail/<int:file_id>")
def api_thumbnail(file_id):
    # Generate cache path
    cache_key = hashlib.md5(f"{file_id}".encode()).hexdigest()
    cache_path = CACHE_DIR / f"{cache_key}.jpg"

    # Return cached version if available
    if cache_path.exists():
        return send_file(cache_path, mimetype='image/jpeg')

    # Otherwise generate
    thumbnail = generate_thumbnail(...)

    # Save to cache
    thumbnail.save(cache_path, 'JPEG', quality=85)

    return send_file(cache_path, mimetype='image/jpeg')
```

**Verification:**
- [ ] Second access is noticeably faster
- [ ] Disk usage remains acceptable
- [ ] Cache clearing works

---

### ✅ 7. Performance Measurement at Scale

**Test cases:**

#### Test 1: 100,000 Files
```bash
# Measure scan time
time python tagdb_tool.py scan --db large.db --root /path/to/100k --recursive

# Measure search time
time python tagdb_tool.py search --db large.db --q "1girl"
```

**Targets:**
- [ ] Scan: at least 50,000 files/hour
- [ ] Search: under 1 second (among 100,000 files)

#### Test 2: WebUI Responsiveness
```
1. Launch the WebUI with a 100,000-file DB
2. Run a search
3. Scroll through results
```

**Checks:**
- [ ] Search results appear within 3 seconds
- [ ] Scrolling is smooth
- [ ] The browser does not freeze

---

## Test Execution Checklist

### Environment Setup
- [ ] Python 3.8+ installed
- [ ] Dependencies installed
- [ ] Test data prepared (images in each format)

### Functional Tests
- [ ] ZIP reading
- [ ] Multi-directory scanning
- [ ] Tag normalization
- [ ] Checkpoint search
- [ ] Model filtering

### UI/UX Tests
- [ ] Layout (multiple resolutions)
- [ ] Dark mode
- [ ] Keyboard shortcuts
- [ ] Autocomplete

### Performance Tests
- [ ] 10,000 files
- [ ] 50,000 files
- [ ] 100,000 files
- [ ] Large ZIP (500 MB+)

### Browser Compatibility
- [ ] Chrome/Edge
- [ ] Firefox
- [ ] Safari

### OS Compatibility
- [ ] Windows 10/11
- [ ] macOS
- [ ] Linux (Ubuntu)

---

## Debug Tools

### Enable Logging
```bash
# Add to the top of tagdb_tool.py
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Performance Measurement
```python
import time

start = time.time()
# ... processing ...
print(f"Time: {time.time() - start:.2f}s")
```

### Memory Usage Check
```python
import tracemalloc

tracemalloc.start()
# ... processing ...
current, peak = tracemalloc.get_traced_memory()
print(f"Memory: {peak / 1024 / 1024:.2f} MB")
tracemalloc.stop()
```

---

**Created:** 2026-02-13
**Priority order:** P0 then P1 then P2
**Note:** This checklist was created during the v2.5.x era. All listed items have been resolved.
