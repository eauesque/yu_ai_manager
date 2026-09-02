# YU QR Protocol v1 — Unified Payload Specification

**Version:** 1.0
**Date:** 2026-02-23
**Target application:** YU AI Manager (TagDB)

---

## Overview

YU AI Manager supports prompt sharing and error diagnostics via QR codes.
This document provides a unified specification for the QR payload format.

### Libraries Used

| Purpose | Library | Version |
|------|-----------|-----------|
| QR generation | QRCode.js | 1.0.0 |
| QR reading | jsQR | 1.4.0 |

### QR Capacity Limits

- Maximum characters: **2,953** (error correction level M)
- Above 2,500 characters: the meta JSON is minified and retried
- Above 2,953 characters: error (`qr.info.too_long`)

---

## Payload Type 1 — Prompt Share

### Origin

- `GET /api/share/<file_id>` -> Python `build_share_data_payload()`
- `routes/share_ops/payload_build.py`

### JSON Schema

```json
{
  "v":   "1.0",
  "t":   "prompt",
  "p":   "<positive prompt>",
  "n":   "<negative prompt>",
  "src": "TagDB",
  "m":   "<model name>",
  "s":   "<seed>",
  "st":  "<steps>",
  "cfg": "<CFG scale>",
  "sa":  "<sampler>",
  "sz":  "<WxH>"
}
```

### Field Definitions

| Key | Type | Required | Description | Limit |
|------|-----|------|------|------|
| `v` | string | ✅ | Protocol version. Currently `"1.0"` | — |
| `t` | string | ✅ | Payload type. Currently always `"prompt"` | — |
| `p` | string | ✅ | Positive prompt | 2,000 chars |
| `n` | string | ✅ | Negative prompt | 1,000 chars |
| `src` | string | ✅ | Issuer identifier. Currently always `"TagDB"` | — |
| `m` | string | — | Model name | — |
| `s` | string | — | Seed value | — |
| `st` | string | — | Step count | — |
| `cfg` | string | — | CFG scale | — |
| `sa` | string | — | Sampler name | — |
| `sz` | string | — | Image size in `"WxH"` format | — |

---

## QR Modes — 4 Types

### `positive` Mode

```
qrText = shareData.p
```

- Content: Positive prompt text only
- Use case: Direct text sharing of prompts

### `negative` Mode

```
qrText = shareData.n
```

- Content: Negative prompt text only

### `meta` Mode

```
qrText = JSON.stringify(shareData, null, 0)
```

- Content: The entire Prompt Share JSON payload, compacted
- Falls back to pretty-printed `JSON.stringify` when the result exceeds 2,500 characters

### `url` Mode

```
encoded = btoa(unescape(encodeURIComponent(JSON.stringify(shareData))))
qrText  = "{origin}/share?data={encoded}"
```

- Content: A URL to the YU AI Manager share page
- Disabled on localhost (`localhost` / `127.0.0.1`)

---

## Payload Type 2 — Error Diagnostic

### Origin

- Generated on HTTP errors -> `_render_error_page()`
- `core/web/app_factory_handlers.py`

### JSON Schema

```json
{
  "s": "<HTTP status code>",
  "p": "<request path>",
  "v": "<APP_VERSION>"
}
```

### Field Definitions

| Key | Type | Description | Limit |
|------|-----|------|------|
| `s` | string | HTTP status code (`"404"`, `"500"`, etc.) | — |
| `p` | string | Request path | 80 chars |
| `v` | string | Application version (from the `APP_VERSION` file) | — |

---

## URL Share Decoding Procedure

Decoding on the share page (`/share?data=...`):

```javascript
const encoded = new URL(location).searchParams.get('data');
const json    = decodeURIComponent(escape(atob(encoded)));
const data    = JSON.parse(json);
```

---

## QR Generation Parameters

```javascript
new QRCode(container, {
  text:         qrText,
  width:        200,   // 180 on error pages
  height:       200,   // 180 on error pages
  colorDark:    '#000000',
  colorLight:   '#ffffff',
  correctLevel: QRCode.CorrectLevel.M,  // 15% error correction
});
```

---

## Future Extensions (v1.x)

| Feature | Status | Notes |
|------|------|------|
| Collection QR export (multiple images) | Not implemented | Planned as payload type 3 |
| `t: "collection"` type | Not defined | File ID list + collection name |
| Compression (gzip + Base64) | Not implemented | Alternative for prompts exceeding 2,953 characters |

---

## Implementation Files

| File | Role |
|----------|------|
| `routes/share.py` | Share API Blueprint |
| `routes/share_ops/payload_build.py` | Payload generation |
| `routes/share_ops/prompt_extract.py` | Prompt data extraction |
| `core/web/app_factory_handlers.py` | Error QR data generation |
| `static/js/runtime/tools/runtime-tools-qr-core.js` | QR build and rendering |
| `static/js/runtime/tools/runtime-tools-qr.js` | QR UI handlers |
| `static/js/share/share-qr.js` | QR image decoding |
| `static/js/share/share-page.js` | Share page display |
| `static/vendor/qrcode.min.js` | QRCode.js library |
| `static/vendor/jsQR.min.js` | jsQR library |
