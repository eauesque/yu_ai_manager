# Performance Tuning Guide

This guide covers tuning tips for running YU AI Manager comfortably with 100,000+ files.
Many optimizations are enabled by default, but you can fine-tune them for your specific environment.

---

## 1. Recommended Hardware

| Component | Minimum | Recommended (100K+ files) |
|-----------|---------|---------------------------|
| CPU | 2 cores | 4+ cores (thumbnail generation is parallelized) |
| RAM | 4 GB | 8 GB or more |
| Storage | HDD | **SSD strongly recommended** — directly affects database responsiveness |
| Network | — | 1 Gbps or higher when accessing over LAN |

**Critical**: Always place the database file (`data/tags.db`) on an SSD.
Image files themselves can reside on an HDD, but having the DB on an HDD will noticeably degrade search and browsing performance.

---

## 2. Optimizing the Initial Scan

### Splitting Scan Roots

Scanning a large number of files at once takes time.
We recommend registering multiple scan roots in Settings > Scan Roots and scanning them incrementally.

- Scan your most frequently used folders first
- Add remaining folders to the scan queue (they will be processed automatically in order)
- Duplicate folder registrations are automatically detected and skipped

### Browsing During Scans

Search and thumbnail display work normally while a scan is in progress.
Internally, read-only database connections are used so that scan write operations never block browsing.

### Automatic Post-Scan Optimization

When a scan completes, database statistics are automatically updated (ANALYZE).
This optimizes query execution plans and speeds up subsequent searches.
No manual action is needed.

---

## 3. Improving Browsing Speed

### Service Worker Cache

The browser's Service Worker automatically caches the following content:

| Type | Cache Limit | Effect |
|------|-------------|--------|
| Thumbnails | 5,000 items | Instant grid display on revisits |
| Previews (1200px) | 200 items | Faster modal display |
| Full-size images | 50 items | Instant redisplay of recently viewed images |

The Service Worker is managed automatically by the browser — no configuration needed.
To clear the cache, use your browser's Developer Tools > Application > Storage.

### Enabling Virtual Scroll

When displaying thousands of search results, enabling virtual scroll significantly improves rendering performance.

**How to enable**: Settings > Appearance > Turn on "Virtual Scroll"

Virtual scroll renders only the cards visible on screen in the DOM, greatly reducing memory usage and rendering overhead.
Strongly recommended for libraries with tens of thousands of files.

### WebP Thumbnails

Thumbnails are generated in WebP format (30-40% smaller than JPEG).
This reduces transfer size, which is especially beneficial when accessing over LAN.
Applied automatically with no configuration needed.

---

## 4. Search Performance

### Index Effectiveness

The database automatically creates indexes optimized for common search patterns.
Date-based sorting, tag filtering, and path searches all run efficiently.

**Benchmarks**:
- Unfiltered search: Under 50ms response even with 280K files
- Tag-filtered search: Under 100ms
- Path search (FTS5): Under 50ms

### FTS5 Full-Text Search vs. LIKE Search

Path searches automatically use FTS5 (Full-Text Search) indexes.
This is 20-100x faster than traditional LIKE searches (`%keyword%`).

If FTS5 is unavailable (e.g., after upgrading from an older DB), it automatically falls back to LIKE search.
Running a scan once will build the FTS5 index.

**Note on CJK searches**: Searches containing kanji, hiragana, or katakana may internally use a LIKE fallback.
This is due to a limitation of SQLite's FTS5 tokenizer and is expected behavior.

---

## 5. Video Playback Optimization

### Faststart Cache

Faststart processing is automatically applied to MP4/MOV files to speed up video playback.
Videos with faststart applied begin streaming playback immediately.

| Setting | Value |
|---------|-------|
| Cache location | `cache/faststart/` |
| Size limit | 4 GB (managed automatically via LRU) |
| Per-file limit | 500 MB |
| Supported formats | MP4, MOV (WebM is skipped as it doesn't need it) |

**Expected improvements**:

| File size | Without faststart | With faststart |
|-----------|-------------------|----------------|
| 5-50 MB | 2-10 second wait | ~200ms to start playback |
| 50-200 MB | 10-60 second wait | ~500ms to start playback |
| 200-500 MB | Minutes of waiting | ~1 second to start playback |

### Verifying FFmpeg

Faststart processing requires FFmpeg. If it is not installed, videos will play only after being fully downloaded.

```bash
ffmpeg -version
```

If FFmpeg is not found in your PATH, install it from the [official site](https://ffmpeg.org/download.html).

---

## 6. Managing Memory Usage

### SQLite mmap

For large databases (100K+ files), SQLite's mmap (memory-mapped I/O) is automatically set to 1 GB.
This accelerates read queries by leveraging the OS page cache.

**Environments with 4 GB or less RAM**: mmap may put pressure on available memory.
In that case, monitor free memory and close other applications if excessive swapping occurs.

### Browser Tab Management

YU AI Manager communicates with each tab in real time via SSE (Server-Sent Events).

- Maximum 10 simultaneous SSE connections per IP
- Closing unused tabs frees connection resources
- Opening many tabs also increases browser memory usage

**Recommendation**: Keep no more than 3-4 tabs open simultaneously.

---

## 7. Troubleshooting — Checklist When Things Feel Slow

### Basic Checks

- [ ] **Using an SSD?**: All operations will be slow if `data/tags.db` is on an HDD
- [ ] **Is FFmpeg installed?**: Required for fast video playback
- [ ] **Number of browser tabs**: Check if you have 5 or more open

### Slow Browsing

- [ ] **Enable virtual scroll**: Settings > Appearance > Virtual Scroll
- [ ] **Don't clear browser cache**: The Service Worker cache is helping performance
- [ ] **Check if scanning is active**: Browsing works during scans, but initial thumbnail generation takes time

### Slow Search

- [ ] **Complete the scan first**: ANALYZE runs at scan completion, optimizing searches
- [ ] **Over 100K results**: Add filters (tags, dates, paths, etc.) to narrow down results

### Slow Video Playback

- [ ] **Check FFmpeg availability**: Run `ffmpeg -version` to verify
- [ ] **Faststart cache size**: Check whether `cache/faststart/` exceeds 4 GB (managed automatically, but verifiable)
- [ ] **File size**: Videos over 500 MB are not cached by faststart. They play via Range delivery, which may be slightly slower initially

### Overall Server Sluggishness

- [ ] **Concurrent connections**: Check if SSE connections exceed 10 per IP
- [ ] **Active uploads**: A file near the 100 MB upload limit may be in transit
- [ ] **Settings > Logs tab**: Check server logs for errors or warnings

---

## 8. Performance Benchmarks

The following are expected response times in a properly optimized environment.

| Operation | ~280K files | ~100K files |
|-----------|------------|------------|
| Grid display (first load) | 200-500ms | 100-300ms |
| Grid display (cached) | Under 50ms | Under 50ms |
| Tag search | Under 100ms | Under 50ms |
| Path search (FTS5) | Under 50ms | Under 30ms |
| Thumbnail (cache hit) | Under 5ms | Under 5ms |
| Video playback start (faststart applied) | 200ms | 200ms |

If your response times significantly exceed these values, review the checklist above.

---

## Fast mode (Rust server)

On supported platforms, startup switches automatically to the Rust server
(`yu-server`). There is nothing to configure. When it cannot be used, the app
starts on Python instead -- **a failure here breaks nothing**.

### Some features stop working

While fast mode is active, these 7 routes return **503**. They only work on
the Python server.

- Hailo GenAI LLM generation, VLM generation, and context clearing
- Hailo GenAI model unload
- OpenAI-compatible chat completions and embeddings
- Hailo GenAI chat send

**Model status and model download still work in fast mode** -- those are
implemented natively in Rust.

### When you need those features

Set an environment variable to force the Python server:

```bash
YU_SKIP_FAST_MODE=1 ./start.sh
```

Windows (PowerShell):

```powershell
$env:YU_SKIP_FAST_MODE = "1"; .\start.ps1
```

The startup log tells you which one ran. On the Python path you will see
`[fast-mode] Python で起動します: <reason>`.

### Building it yourself

Pick one under Settings -> "Server" -> "Fast Mode" -> **how to obtain the Rust server**:

- **Download the published binary** (default) -- never builds
- **Build on this machine** -- never downloads
- **Download, and build if that fails**

Building needs 8GB+ free disk and uses a lot of CPU and memory. **On low-memory machines
(a Raspberry Pi, say) it can exhaust swap and take the whole system down.** All features
stay usable while it compiles. Building on Windows also needs the Visual Studio build
tools (the linker).

Progress appears on the same screen: elapsed time while compiling, cargo's most recent
line, success or failure, and whether the build stopped partway. The raw log is at
`bin/fast-mode-build.log`.

### When nothing is obtained at all

When fast mode is refused because of **this checkout's own state** (a stale web bundle, an
extension outside the bundled roster), fetching a binary cannot change the answer, so
neither a download nor a build is attempted. That reason is shown on the same screen.
