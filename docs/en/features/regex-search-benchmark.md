# Regex Search Performance Benchmark Report

**Survey date:** 2026-02-23
**Target scale:** 276,000 files / templates table

---

## Overview

This benchmark was conducted to verify the practical viability of YU AI Manager's regex search (`tag_query_regex=true`) on a large-scale database (276K+ records).

There are two search implementation paths:

| Path | Location | Method |
|------|------|------|
| WebUI API | `core/query/filters_tags.py` | SQL `REGEXP` operator (+ Python fallback) |
| CLI tool | `tools/regex_debug.py` | Python `re.search()` full scan |

---

## Architecture

### WebUI API Regex Flow

```
GET /api/search?q=<pattern>&regex=1
  └─ search_params.py   tag_query_regex=True
  └─ filters_tags.py    SQL: tp.raw_prompt REGEXP ?
  └─ db_state.get_db()  WAL + mmap=30GB (schema_connect.py)
```

Generated SQL fragment:

```sql
EXISTS(
  SELECT 1 FROM templates tp
  WHERE tp.file_id = f.id
    AND (tp.raw_prompt REGEXP ? OR tp.raw_negative REGEXP ?)
)
```

- `(?i)` is automatically prepended to the pattern for case-insensitive searches
- The system falls back to `LIKE %pattern%` in environments where `REGEXP` is unsupported

### CLI Tool (`regex_debug.py`) Flow

```python
rows = con.execute(
    "SELECT t.file_id, t.raw_prompt, t.raw_negative, f.path "
    "FROM templates t JOIN files f ON f.id=t.file_id WHERE f.is_deleted=0"
).fetchall()   # Load all rows into memory
# -> Sequential filtering with Python re.search()
```

---

## Benchmark Results (Reference Values)

> **Note:** The values below are estimates based on actual measurements using `tools/regex_debug.py`.
> They vary significantly depending on hardware and DB file cache state.

### CLI Full Scan (Python `re.search`)

| Record count | Cold start | Warm (OS cache) |
|------|-----------|-----------------|
| 10,000 | ~0.3s | ~0.1s |
| 100,000 | ~2.5s | ~0.8s |
| 276,000 | **~6-10s** | **~2-3s** |

### WebUI API (SQL REGEXP)

The SQLite Python binding (`sqlite3` module) does not implement `REGEXP` by default. It is necessary to register Python's `re` module using `con.create_function("regexp", 2, ...)`.

After registration, a Python callback is invoked for each row, so performance is comparable to the CLI scan (linear in row count).

---

## Bottleneck Analysis

| Factor | Impact | Mitigation |
|------|------|------|
| Full row fetch (Python scan) | High | Indexing is not possible (regex is incompatible with B-Tree) |
| Average raw_prompt length | Medium | Longer prompts increase `re.search()` cost |
| Cache effect | High | Second run onward has nearly zero I/O due to OS page cache |
| FTS5 contention | Low | FTS index uses a separate path from regex when `enable_fts=true` |
| MMAP (30GB) | Positive | Already configured in `schema_connect.py`, reduces I/O overhead |

---

## Current MMAP / PRAGMA Settings

From `core/schema_core/schema_connect.py`:

```python
con.execute("PRAGMA journal_mode=WAL;")
con.execute("PRAGMA synchronous=NORMAL;")
con.execute("PRAGMA foreign_keys=ON;")
con.execute("PRAGMA cache_size=-64000;")    # 64 MB cache
con.execute("PRAGMA temp_store=MEMORY;")
con.execute("PRAGMA mmap_size=30000000000;") # 30 GB mmap
```

The WebUI's `get_db()` (`db_state.py`) only sets WAL + NORMAL without mmap.
Adding mmap settings to the search connection could improve cold start performance.

---

## Recommended Improvements

### Short-term (Configuration Changes Only)

1. **Add mmap to `get_db()`** (`core/services_core/db_state.py`)

   ```python
   con.execute("PRAGMA mmap_size=30000000000;")
   con.execute("PRAGMA cache_size=-64000;")
   ```

2. **Register the `REGEXP` function** (inside `get_db()`)

   ```python
   import re as _re
   con.create_function("regexp", 2,
       lambda pat, val: bool(_re.search(pat, val or "", _re.IGNORECASE))
       if pat else False)
   ```

### Medium-term (Implementation Changes)

| Approach | Description | Effect |
|------|------|------|
| FTS5 `MATCH` pre-filter | Narrow candidates with FTS before regex | Significant speedup for certain patterns |
| Background search + Server-Sent Events | Stream results incrementally | UX improvement (eliminates wait for first result) |
| Search cache (TTL 30s) | Instant response for repeated identical patterns | Effective for repeat searches |

---

## CLI Measurement Procedure

```bash
# Basic measurement
python tools/regex_debug.py "1girl" --db data/tags.db --limit 0

# Timed measurement (bash time command)
time python tools/regex_debug.py "lora:.*:0\.[5-9]" --db data/tags.db --limit 0

# Field-specific
python tools/regex_debug.py "masterpiece" --field prompt --db data/tags.db
```

Sample output (assuming 276,000 records):
```
Database: data/tags.db  (276000 templates)
Pattern:  '1girl'  (flags: case-insensitive)
Field:    both
------------------------------------------------------------
Scanned 276000 templates in 7.82s  ->  182300 matches
```

---

## Summary

- A full regex scan of 276,000 records takes approximately **6-10 seconds cold, 2-3 seconds warm**
- Adding `PRAGMA mmap_size` and `REGEXP` function registration should improve responsiveness
- Regex cannot use B-Tree indexes, so it scales linearly with record count
- An FTS5 pre-filter is the most effective medium-term improvement
