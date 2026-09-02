# Drag & Drop File Registration

Drag and drop image/video files onto the main library page (`/`) to save them
into a configured **Drop Inbox** directory and automatically register them in
the library. The normal scan path (`scan_one`) is used, so metadata extraction,
thumbnail generation, and tagging all run as they would for a normal scan.

## Behavior

1. With the main page open, drag files from the file explorer or another browser
2. An overlay appears on the window showing the target (Drop Inbox) path
3. On drop, each file is copied into the Drop Inbox and registered
4. A toast shows the number of successes and failures

## Drop Inbox Resolution

The Drop Inbox is resolved in this priority:

1. `drop_inbox_dir` from `config.json` (explicit setting)
2. If unset: the first enabled scan root is used as-is

**Constraint**: `drop_inbox_dir` **must** live inside one of the `scan_roots`
entries. Any path outside scan roots is rejected with HTTP 400. This preserves
the invariant that scan roots are the single source of truth for library files.

## Configuration Example

```json
{
  "scan_roots": [
    { "path": "D:/Pictures/AI", "enabled": true, "recursive": true }
  ],
  "drop_inbox_dir": "D:/Pictures/AI/inbox"
}
```

The `drop_inbox_dir` is created if it does not exist (its parent must still be
inside `scan_roots`).

## Name Collision Handling

If a file with the same name already exists in the inbox, suffixes `_1`, `_2`,
... are automatically appended. Existing files are never overwritten.

## Allowed Extensions

| Category | Extensions |
|---|---|
| Images | `.png` `.jpg` `.jpeg` `.webp` `.gif` `.bmp` `.tiff` `.tif` `.svg` |
| Videos | `.mp4` `.webm` `.mov` `.avi` `.mkv` `.m4v` |

Archives (`.zip` / `.7z` / `.rar`) are **not supported** via drag & drop. Place
archive files directly into a scan root and run a regular scan instead.

## Limitations

- The total request size is capped at `MAX_CONTENT_LENGTH` (default **100 MB**)
- Filenames containing path traversal (`..`) are rejected
- Dropping an entire directory is not currently supported (individual files only)

## HTTP API

### `POST /api/dnd-upload`

Accepts multipart file uploads, saves them into the Drop Inbox, and registers
them in the library.

Response:

```json
{
  "ok": true,
  "total": 3,
  "success": 2,
  "results": [
    { "ok": true, "status": "added", "file_id": 12345, "path": "...", "filename": "a.png" },
    { "ok": true, "status": "skipped", "path": "...", "filename": "b.png" },
    { "ok": false, "code": "unsupported_type", "error": "...", "filename": "c.xyz" }
  ]
}
```

### `GET /api/dnd-inbox`

Returns the currently resolved Drop Inbox for the UI overlay to display.

```json
{ "ok": true, "inbox": "D:/Pictures/AI/inbox", "explicit": true }
```

### `POST /api/files/register-path`

Registers an already-on-disk file by path (no upload). The path must be inside
`scan_roots`. Used by the `register_file` MCP tool.

```json
{ "path": "D:/Pictures/AI/inbox/a.png" }
```

## MCP Tools

| Tool | Description |
|---|---|
| `register_file(path)` | Register a file at an absolute path into the library |
| `drop_inbox_info()` | Return the currently resolved Drop Inbox directory |
