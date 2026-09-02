# SVG Rasterization API

API for converting SVG vector images to PNG/WebP bitmaps.
Designed for img2img pipeline integration — the returned base64 image data can be passed directly to NovelAI Bridge or SD WebUI Bridge.

## GET /api/svg/info

Check SVG rasterization availability.

- **Rate limit**: None (GET)

### Response

```json
{
  "available": true,
  "backend": "resvg"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `available` | bool | Whether rasterization is available |
| `backend` | string \| null | Active backend (`"resvg"` or `null`) |

---

## POST /api/svg/rasterize

Rasterize an SVG to a PNG/WebP bitmap.

- **Rate limit**: HEAVY

### Request Body

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_id` | int | *1 | SVG file ID from the database |
| `svg_path` | string | *1 | Absolute path to an SVG file |
| `svg_data` | string | *1 | Inline SVG XML string |
| `width` | int | No | Output width (default: 1024) |
| `height` | int | No | Output height (default: 1024) |
| `format` | string | No | `"png"` or `"webp"` (default: `"png"`) |
| `background` | string | No | Background colour (e.g. `"#ffffff"`). Transparent if omitted |

> *1: Provide exactly one of `file_id`, `svg_path`, or `svg_data`.

### Request Example

```json
{
  "file_id": 123,
  "width": 832,
  "height": 1216,
  "format": "png",
  "background": "#ffffff"
}
```

### Response

```json
{
  "ok": true,
  "base64": "iVBORw0KGgo...",
  "width": 832,
  "height": 1216,
  "format": "png",
  "size_bytes": 45678
}
```

| Field | Type | Description |
|-------|------|-------------|
| `ok` | bool | Success flag |
| `base64` | string | Base64-encoded PNG/WebP data |
| `width` | int | Actual output width |
| `height` | int | Actual output height |
| `format` | string | Output format |
| `size_bytes` | int | Binary size in bytes |

### Error Response

```json
{
  "ok": false,
  "error": "resvg is not installed (pip install resvg)"
}
```

---

## MCP Integration

Use Claude Desktop to build an SVG → img2img pipeline:

```
# Step 1: Rasterize the SVG
svg_rasterize(file_id=123, width=832, height=1216, background="#ffffff")

# Step 2: Pass the returned base64 to img2img
nai_generate(prompt="icon, detailed illustration, ...", image=<base64>, strength=0.7)
```

### MCP Tools

| Tool | Description |
|------|-------------|
| `svg_info` | Check rasterization availability |
| `svg_rasterize` | Rasterize SVG to PNG/WebP |

---

## Dependencies

| Package | License | Purpose |
|---------|---------|---------|
| `resvg` | MIT | Rust-based SVG renderer (cross-platform) |

If `resvg` is not installed, thumbnails show a placeholder and the API returns HTTP 501.

```bash
pip install resvg
```
