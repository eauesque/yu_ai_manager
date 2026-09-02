# CJK / Double-Byte Encoding Pitfalls and Solutions

This document catalogs bugs specific to double-byte character environments -- primarily Japanese (CP932/Shift-JIS) -- along with the solutions adopted in this project. It is intended as a reference for developers and AI agents who encounter similar issues.

---

## 1. Windows Console cp932 Crash

### Symptoms

The default output encoding on Windows `cmd.exe` / PowerShell / Git Bash is **cp932 (Shift-JIS)**. A `print()` call that outputs a Unicode character absent from cp932 immediately crashes with a `UnicodeEncodeError`.

```
UnicodeEncodeError: 'charmap' codec can't encode character '\u2014' in position 12
```

### Characters That Triggered This

| Character | Name | Context |
|-----------|------|---------|
| `—` (U+2014) | em dash | Log output separator |
| `–` (U+2013) | en dash | Progress display |
| `✓ ✗ ✅ ❌ ⚠️` | Check marks / emoji | Success/failure indicators |
| `🧹 📦 📁 🔍 🔧` | Emoji | Operation labels |
| `█ ░` | Block characters | Progress bars |

### Solution

- **Use only ASCII-safe characters in `print()`**: `[OK]`, `[NG]`, `[!]`, `--`, `#`, `-`, etc.
- The same applies to `logging` handlers. A handler whose encoding is cp932 will hit the same issue.
- It is possible to work around the problem by setting `PYTHONIOENCODING=utf-8`, but relying on user environment is fragile. Defensive use of ASCII is safer.

### Scope of Impact

This project required a bulk fix across **19 files** (v2.28.0). AI code generators (Claude/GPT) use emoji and em dashes at a high rate. **This is one of the most important items to check when reviewing AI-generated code.**

---

## 2. ZIP Filename Mojibake (CP437)

### Symptoms

ZIP files created on older Windows systems (95/98/XP era) store filenames in **Shift-JIS (CP932)**, but the ZIP specification carries no encoding metadata. Python's `zipfile` module decodes filenames as **CP437** when the UTF-8 flag (bit 11) is not set. This turns Japanese filenames into garbled text like `âwâCâèâb`.

### Solution: 10-Stage Fallback Chain

`core/infra_core/encoding.py` defines a prioritized list of CJK encodings:

```
UTF-8 (tried first by zipfile) → CP932 → EUC-JP → ISO-2022-JP
→ EUC-KR → CP949 → GB2312 → GBK → Big5 → CP950
```

- `chardet` / `cchardet` are **not used**: short filenames (10--30 bytes) produce too many false detections.
- A fixed-priority approach offers better reproducibility and simpler debugging.

### The `metadata_encoding` Parameter in Python 3.11+

```python
# Python 3.11+ allows direct specification via metadata_encoding
zf = zipfile.ZipFile(path, metadata_encoding='cp932')
```

This does not handle ZIP files encoded in something other than CP932. On failure, the code reopens the archive without `metadata_encoding` and attempts recovery via `repair_cp437_name()`.

### 7z Archives

7-Zip has its own filename handling. CP437 mojibake can occur through the 7z CLI; `repair_cp437_name()` applies the same recovery logic.

---

## 3. ZIP/7z Scan Hangs on Double-Byte Filenames

### Symptoms

`zipfile.ZipFile()` can enter blocking I/O and hang when it reads the central directory of an old ZIP whose filenames are Shift-JIS encoded. Archives with a large number of files are especially prone to this.

### Solution

1. **Timeout protection**: A `run_with_timeout()` daemon-thread helper was introduced.
   - File listing: 30 seconds
   - Scan I/O: 60 seconds
2. **scan_errors table** (migration v24): Timeouts and encoding errors are persisted in the DB.
   - Error type categories: `encoding` / `timeout` / `scan` / `archive_scan` / `archive_timeout` / `filesystem`

---

## 4. SQLite FTS5 tokenchars Quoting Issue

### Symptoms

It is possible to trigger a parse error in the SQLite FTS5 `tokenize` directive depending on the combination of quotation marks used with the `tokenchars` option.

```sql
-- NG: Outer single quotes + inner double quotes → parse error
tokenize='unicode61 tokenchars "_:."'

-- OK: Outer double quotes + inner single quotes
tokenize="unicode61 tokenchars '_:.'"
```

### Cause

The FTS5 tokenizer parser fails to parse double quotes nested inside single quotes correctly. There may also be version-specific behavior differences (confirmed on SQLite 3.45.1).

### Solution

Use Python triple-quote strings to accommodate both SQL quote types:

```python
# OK: Python ''' wraps both SQL " and '
con.execute('''
    CREATE VIRTUAL TABLE fts USING fts5(
        col1,
        tokenize="unicode61 tokenchars '_:.'"
    )
''')
```

### Discovery Context

This issue surfaced during migration 29, which rebuilds FTS5 tables. AI-generated code used the single-quote-outer syntax. The server crashed on startup under SQLite 3.45.1 (fixed in v2.70.1).

---

## 5. WebP EXIF with UTF-16 Encoding

### Symptoms

Some image generation tools (notably NAI-family tools) store WebP EXIF metadata in **UTF-16 (with BOM)**. Standard UTF-8 decoding produces garbled text.

### Solution

- Detect the BOM (Byte Order Mark) to determine UTF-16 BE/LE.
- Use heuristics to guess BE/LE when no BOM is present.
- Fall back through UTF-8 then latin-1.

---

## 6. PNG tEXt Chunk Encoding

### Symptoms

The PNG specification defines tEXt chunks as **Latin-1 (ISO-8859-1)**, but most AI image generation tools write UTF-8 encoded strings directly. Decoding as `latin-1` garbles Japanese text.

### Solution

Decode as UTF-8 first, falling back to latin-1 on failure:

```python
try:
    text = raw_bytes.decode('utf-8')
except UnicodeDecodeError:
    text = raw_bytes.decode('latin-1')
```

---

## 7. Windows Path Backslashes in config.json

### Symptoms

Windows file paths contain backslashes (`\`). Manually entering a path in a JSON file creates invalid escape sequences.

```json
{"scan_roots": ["C:\Users\test"]}  // \U and \t become escape sequences
```

### Solution

- `_repair_json_backslashes()` auto-repairs paths at server startup.
- Paths are normalized internally before saving.

---

## 8. pathlib and WSL UNC Paths

### Symptoms

`pathlib.Path.exists()` can return incorrect results for UNC paths (`\\server\share\...`) when running under WSL (Windows Subsystem for Linux).

### Solution

- Use `os.path.exists()` for UNC path existence checks.
- `pathlib` is convenient but unreliable with network paths.

---

## 9. UTF-8 BOM in CSV Export

### Symptoms

Excel garbles UTF-8 CSV files that lack a BOM. Excel interprets BOM-less UTF-8 as ANSI (CP932 in Japanese environments).

### Solution

```python
buf.write("\ufeff")  # UTF-8 BOM for Excel compatibility
```

Prepend a BOM (`\ufeff`) to the CSV output. This ensures Excel recognizes the file as UTF-8.

---

## 10. `ensure_ascii=False` in JSON Output

### Symptoms

Python's `json.dumps()` escapes non-ASCII characters as `\uXXXX` by default. MCP tool responses that contain Japanese tag names or file paths appear as `\u30bf\u30b0`, making it harder for AI agents to understand the content.

### Solution

```python
json.dumps(data, ensure_ascii=False, indent=2)
```

This project uses this setting consistently across all MCP tool modules (10 files).

---

## 11. Folder Selection Dialog Output Decoding

### Symptoms

The PowerShell folder-selection dialog on Windows returns `subprocess` output encoded in CP932. The default UTF-8 decode raises a `UnicodeDecodeError`.

### Solution

```python
result = subprocess.run(..., capture_output=True)
path = result.stdout.decode('cp932', errors='replace').strip()
```

The `errors='replace'` flag ensures safe handling even when decoding fails.

---

## Notes for AI Agents

Many of the issues above are **patterns that AI code generators tend to overlook**:

1. **Do not use emoji or decorative characters in `print()`** -- AI generators use them frequently for visual appeal.
2. **Do not assume filename encoding** -- code written with a UTF-8 assumption breaks in CP932 environments.
3. **Test SQLite quoting on the actual runtime** -- documentation-conforming syntax can still fail in practice.
4. **Always pass `ensure_ascii=False` to `json.dumps()`** -- this is essential when handling Japanese data.
5. **Decode subprocess output using the environment's encoding** -- Windows typically uses CP932.
6. **Include a BOM in CSV output** -- this is required for Excel compatibility.

---

## Reference: Related Files in This Project

| File | Description |
|------|-------------|
| `core/infra_core/encoding.py` | CJK fallback chain, CP437 mojibake repair |
| `core/schema_core/schema_migrate_steps_29.py` | Correct FTS5 tokenchars quoting |
| `core/tools/fs_dialog.py` | Folder-selection dialog CP932 decoding |
| `core/configuration/json_rw.py` | config.json backslash repair |
| `routes/collections.py` | CSV export BOM insertion |
| `CLAUDE.md` | "Windows Environment Notes > Console Output" section |
