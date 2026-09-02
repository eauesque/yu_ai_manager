# Extensions

YU AI Manager supports adding functionality through an Extension system.
It currently ships with 43 built-in Extensions, organized into 6 categories.

## Built-in Extension List

### Metadata Extraction (metadata)

| Extension | Description |
|-----------|-------------|
| builtin-a1111 | Automatic1111 / SD WebUI PNG/WebP/WebM metadata extraction |
| builtin-novelai-v3 | NovelAI V3 and earlier metadata extraction |
| builtin-novelai-v4 | NovelAI V4 metadata extraction (Character Prompts, Vibe Transfer) |
| builtin-comfyui | ComfyUI workflow JSON parsing |
| builtin-annotations | File annotation storage, search, and batch operations |
| builtin-ratings | Star rating system (1-5 stars) |
| builtin-tag-dictionary | Danbooru tag dictionary search, import, and splitting |

### Bridge Integration (bridge)

| Extension | Description |
|-----------|-------------|
| builtin-sd-webui-bridge | SD WebUI / Forge integration (image generation, model management) |
| builtin-nai-bridge | NovelAI API integration (image generation) |
| builtin-comfyui-bridge | ComfyUI integration (workflow execution) |

### Prompt (prompt)

| Extension | Description |
|-----------|-------------|
| builtin-prompt-library | Prompt library and organization |
| builtin-prompt-syntax | Prompt syntax highlighting and error detection (NAI/SD/DP) |
| builtin-prompt-simulator | Dynamic Prompts simulator, weight calculation, and conversion |
| builtin-sd-nai-convert | SD <-> NovelAI prompt bidirectional conversion |

### AI (ai)

| Extension | Description |
|-----------|-------------|
| builtin-analysis | AI image analysis (Claude, OpenAI, Ollama, Hailo VLM) |
| builtin-wd-tagger | WD-Tagger auto-tagging (ONNX + VLM engine) |
| builtin-ocr | VLM OCR -- text extraction, structured analysis, and translation |
| builtin-clip-search | CLIP semantic image search engine |
| builtin-clip-onnx | CLIP ONNX Runtime encoder backend |
| builtin-clip-coreml | CLIP Core ML encoder (Apple Neural Engine) |
| builtin-hailo-semantic-search | Hailo-10H semantic search |
| builtin-hailo-yolo-detect | Hailo-10H YOLO object detection |
| builtin-hailo-genai | Hailo-10H GenAI (LLM/VLM/S2T) |
| builtin-speech-to-text | Speech-to-text (Hailo NPU / CUDA / ROCm / CPU) |
| builtin-audio-analysis | Audio analysis (Whisper local / OpenAI API) |
| builtin-video-analysis | Video AI analysis (multi-keyframe + Gemini) |
| builtin-inference | ONNX Runtime provider detection and GPU acceleration |

### Library (library)

| Extension | Description |
|-----------|-------------|
| builtin-favorites-manager | Favorites and collection management |
| builtin-freeze-pullback | Freeze & Pull-back video generation (Ken Burns effect) |
| builtin-download | Batch ZIP download of selected images |
| builtin-chatlog | Chat log importer and viewer (Claude / ChatGPT) |
| builtin-md-viewer | Markdown file viewer (FTS5 full-text search) |
| builtin-cross-search | Cross-search (MD, chat logs, prompts, text) |
| builtin-lan-share | LAN collection sharing (time-limited token authentication) |
| builtin-stats | Statistical insights (timeline, milestones) |
| builtin-trophy | Trophy and achievement system |
| builtin-export | Export hooks (record transformation for CSV output) |

### System (system)

| Extension | Description |
|-----------|-------------|
| builtin-auto-scan-watcher | Automatic file change detection and incremental updates |
| builtin-mcp-client | External MCP server connection management |
| builtin-backup | DB backup, restore, and scheduler |
| builtin-sns-share | SNS sharing (Bluesky, X/Twitter) |
| builtin-webhook | Webhook dispatcher (event-driven HTTP delivery) |
| builtin-debug-check | Debug diagnostics CLI |
| builtin-github-integration | GitHub issue monitoring, triage, PR/Discussion/Release tracking |

## Managing Extensions

The following operations are available in the Settings > Extensions tab:

- **Enable/Disable**: Instantly toggle with a switch
- **Install New**: Install by specifying a Git repository URL
- **Marketplace**: Search and one-click install public Extensions
- **Update**: Update Git-based Extensions to the latest version
- **Uninstall**: Remove third-party Extensions

### Management via API

```bash
# List extensions
curl -H "Authorization: Bearer sk_xxx" \
     http://localhost:5000/api/extensions

# Toggle enable/disable
curl -X POST -H "Authorization: Bearer sk_xxx" \
     http://localhost:5000/api/extensions/builtin_wd_tagger/toggle

# Install from Git
curl -X POST -H "Authorization: Bearer sk_xxx" \
     -H "Content-Type: application/json" \
     -d '{"url": "https://github.com/user/my-extension.git"}' \
     http://localhost:5000/api/extensions/install
```

## Extension Sandbox

Third-party Extensions are protected by a sandbox.

### Trust Levels

| Level | Target | Restrictions |
|-------|--------|--------------|
| L0 (TRUSTED) | `builtin-*` | No restrictions |
| L2 (UNTRUSTED) | Others | DB/FS/network restrictions apply |

### Sandbox Phases

1. **Capability Token**: Permission management via HMAC-SHA256 signed tokens. 24-hour expiry
2. **SandboxedDB / SandboxedFS**: Extensions with `db:read` only are limited to SELECT queries. File access is controlled by path-based rules
3. **SandboxedHTTPClient / ImportGuard**: SSRF prevention, runtime import monitoring, SHA-256 tamper detection
4. **Process Isolation (Linux)**: L2 Extensions run in separate processes. Unix socket JSON-RPC 2.0 IPC

### OS-Level Isolation (Optional)

- **Linux**: Auto-generated AppArmor profiles
- **macOS**: sandbox-exec (experimental)
- **Windows**: Restricted Token + Job Object

> **Tip**: For details on Extension development, see the "Extension Development" section.

## Directory Structure

```
extensions/builtin_<name>/
  extension.json            # Manifest (name, version, permissions, etc.)
  <name>_ext.py             # Entry point (exposes get_blueprint())
  templates/<name>/          # Jinja2 templates
  core_impl/                 # Business logic (optional)
```

### Required Fields in extension.json

```json
{
  "name": "my-extension",
  "version": "1.0.0",
  "entrypoint": "my_extension_ext.py",
  "has_blueprint": true,
  "category": "library"
}
```

Categories are one of 6 types: `metadata`, `bridge`, `prompt`, `ai`, `library`, `system`.

## Extension Module API v2 (ES Module Support)

Starting from v4.29.0, Extensions can use `<script type="module">` with Import Maps for clean ES Module imports.

### Enabling

Add `"script_type": "module"` to your `extension.json`:

```json
{
  "name": "my-extension",
  "version": "1.0.0",
  "entry": "my_extension_ext.py",
  "has_blueprint": true,
  "category": "library",
  "script_type": "module"
}
```

### Usage

Change your template's `<script>` to `<script type="module">` and import from `yu-api`:

```html
<script nonce="{{ csp_nonce }}" type="module">
import { showToast, sseSubscribe, tr, apiFetch, escapeHtml } from 'yu-api';

// Toast notification
showToast('Saved successfully');

// SSE event subscription
sseSubscribe('scan.progress', (data) => {
  console.log('Progress:', data);
});

// i18n translation
const label = tr('my_ext.title', 'My Extension');

// API call (CSRF header auto-injected)
const res = await apiFetch('/ext/my-extension/api/data');
const json = await res.json();
</script>
```

### Available API

| Function | Description |
|---|---|
| `showToast(message, isError?)` | Show a toast notification |
| `sseSubscribe(eventType, handler)` | Subscribe to SSE events |
| `sseUnsubscribe(eventType, handler)` | Unsubscribe from SSE events |
| `tr(path, a?, b?)` | Resolve an i18n translation key |
| `apiFetch(path, opts?)` | Fetch wrapper with CSRF header |
| `apiUrl(path)` | Build an API URL |
| `escapeHtml(text)` | Escape HTML special characters |

### TypeScript Type Definitions

Copy `src/ts/extension-api/extension-api.d.ts` into your Extension project to enable IDE autocompletion and type checking.

### Legacy Compatibility

Extensions with `"script_type": "classic"` (the default) continue to use `window.showToast()` and other globals as before. No changes are required for existing Extensions.

## Development Documentation

Development insights on Extension development, internal design decisions, known caveats, and debugging tips can be viewed in the [MD Viewer](/ext/md-viewer/). The `docs/development/development_docs/` directory is registered and supports FTS5 full-text search.
