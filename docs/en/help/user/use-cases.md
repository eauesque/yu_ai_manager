# Use Cases

A collection of common scenarios showing how to get the most out of YU AI Manager.

---

## 1. Organizing a Large Collection of AI Images

You have thousands of images generated with NovelAI or Stable Diffusion scattered across folders, and finding anything has become a chore.

### Steps

1. Go to **Settings > Scan** tab and register your image folders (multiple folders supported)
2. Scanning starts automatically after adding a folder. ZIP/7z archives are also scanned
3. Once scanning is complete, use tag search (e.g., `1girl, blue_eyes`) or sorting on the main page to find images
4. Select your favorites, then right-click > **Add to Collection** to organize them into groups
5. Access your collections anytime from the collection sidebar

### Tips

- You can search and browse while scanning is in progress (read-only DB connections prevent lock contention)
- Enable the Auto Scan Watcher extension to automatically detect newly added files
- Libraries with over 1 million files remain fast thanks to Keyset Pagination

---

## 2. Finding Images by Prompt Content

You can't quite remember the prompt you used for that perfect composition.

### Steps

1. Switch the search target to **in_prompt** in the search bar
2. Enter any keywords you recall (e.g., `cherry blossom`)
3. Use regular expressions for more precise matching (e.g., `masterpiece.*cherry`)

### Tips

- When FTS (full-text search) is enabled, even massive prompt libraries are searched quickly
- Combine with date range or file format filters for better results
- Set the sort order to `random` to rediscover forgotten gems

---

## 3. Finding Visually Similar Images

You have an image and want to find others with a similar look or feel.

### Approach A: pHash Similarity Search (Composition & Color)

1. Open the image in the detail modal
2. Click the **Find Similar Images** button
3. Images with similar compositions are displayed in a side panel, ranked by pHash (perceptual hash) similarity

### Approach B: CLIP Semantic Search (Meaning & Concept)

1. Click the **Semantic Search** button next to the search bar
2. Enter a natural language description (e.g., "a girl standing by the sea" or "a sunset cityscape")
3. CLIP understands the image content and returns results ranked by semantic similarity

### Tips

- Semantic search requires a pre-configured CLIP model (ONNX or Hailo-10H)
- For large libraries (100K+ images), installing `faiss-cpu` dramatically improves search speed
- pHash excels at matching compositions, while CLIP matches by meaning — try both for the best results

---

## 4. Managing Favorite Images

You want to quickly revisit your best work from a large library.

### Steps

1. Click the **heart button** on an image card or in the detail modal to mark it as a favorite
2. Set a **star rating** (1–5) in the detail modal to evaluate quality
3. Add **annotations** with free-form notes (e.g., "candidate for rework" or "posted to SNS")
4. Use search filters to show only favorites or images rated 4 stars and above

### Tips

- Sort by rating (`rating_desc`) to browse your top-rated images together
- Favorites and ratings can also be managed from the context menu (right-click)

---

## 5. Sending Prompts to Another Generation Tool

You want to reuse a prompt from a past image to create variations in a different tool.

### Steps

1. Open the detail modal and review the prompt information
2. Click **Send to SD WebUI** / **Send to ComfyUI** / **Send to NAI**
3. The Bridge page opens with the prompt pre-filled
4. Edit the prompt as needed and run generation in the target tool

### Tips

- Weight syntax (`()` vs `{}`) is automatically converted between SD and NAI formats
- Use the **QP** button in the Bridge toolbar to insert quality presets with one click
- Prompts can also be sent to any Bridge from the Prompt Converter or Prompt Simulator

---

## 6. Browsing Images Inside ZIP/7z Archives

You've downloaded image sets packaged as ZIP files and want to browse them without extracting.

### Steps

1. In Settings > Scan, register the folder containing your ZIP/7z files
2. Enable the **ZIP/7z scanning** option in the scan settings
3. After scanning, archived images appear on the main page just like regular images
4. The detail modal shows the archive name and the path within the archive

### Tips

- Videos inside archives are extracted to a temporary cache (LRU, 2 GB) for smooth repeated playback
- Nested archives (ZIP-in-ZIP) are supported
- Use the batch download feature to repackage archived images into a new ZIP

---

## 7. Sharing Images with Your Team or Family

You want other devices on the same Wi-Fi network (phones, tablets, etc.) to browse your library.

### Steps

1. In **Settings > Server** tab, turn on "LAN Access"
2. Set a **PIN code** (required for LAN access)
3. Restart the server
4. Access `http://<server-IP>:5000` from another device on the LAN
5. Enter the PIN to log in

### Tips

- Issue a **LAN Share token** (`/s/` path) to create a guest access link that doesn't require a PIN
- A QR code is displayed on the server screen — just scan it with your phone's camera to connect
- Trusted Proxy authentication via a reverse proxy is also supported

---

## 8. Auto-Tagging Images with AI

Tagging by hand is tedious, and you'd rather let AI analyze and tag your images automatically.

### Approach A: WD-Tagger (Fast, Tag-Focused)

1. Download a WD-Tagger ONNX model from **Settings**
2. Click **Run WD-Tagger** from the Tools page or the detail modal
3. Danbooru-style tags are automatically assigned

### Approach B: AI Analysis (Natural Language, High Accuracy)

1. Add an Ollama or OpenAI-compatible server in **Settings > AI Analysis**
2. Run the analysis from the **AI Analysis tab** in the detail modal
3. A natural language description of the image is generated

### Tips

- WD-Tagger also supports a composite mode with VLM engines (OpenAI API-compatible)
- Post-processing such as NSFW filtering and tag normalization is applied automatically
- Tags can be written to XMP metadata for easy interoperability with other tools

---

## 9. Viewing Statistics and Reports

You want to understand the trends and growth of your image library.

### Steps

1. Open the **Stats** page from the navigation bar to see overall statistics
2. Visit the **Monthly Report** page for detailed monthly breakdowns:
   - Monthly file count and month-over-month change, top 20 tags, new tags, source distribution, daily counts
3. Check the **Trophies** section for your achievement badges

### Tips

- Trophies span 6 categories (milestone / streak / diversity / source / hidden) and 4 tiers (bronze through platinum), unlocked progressively
- Set your timezone correctly in Settings > Appearance to ensure accurate daily statistics

---

## 10. Integrating with AI Agents via MCP

You want to interact with your image library from Claude Desktop or other MCP-compatible AI tools.

### Steps

1. Register YU AI Manager's MCP server in your MCP client (e.g., Claude Desktop):
   ```json
   {
     "command": "python",
     "args": ["-m", "mcp_server"],
     "env": { "YU_DB": "./tags.db" }
   }
   ```
2. Give natural language instructions to the AI, such as "search for images" or "add this to favorites"
3. Over 60 tools are available, including `search_images`, `add_favorite`, and `trigger_scan`

### Tips

- The MCP Client extension can also connect to external MCP servers (stdio / SSE / Streamable HTTP)
- With API Key authentication configured, external tools can call the REST API directly without CSRF headers
- The Hailo GenAI extension enables integration via an OpenAI SDK-compatible endpoint

---

## 11. Using Hailo-10H as an OpenAI-Compatible Server

If you have a Hailo-10H NPU, you can use it as a local AI server with full OpenAI SDK compatibility. External tools like Open WebUI, Continue.dev, and custom scripts can access Hailo's LLM, VLM, speech-to-text, and CLIP embeddings directly.

### Supported Endpoints

| Endpoint | Function | OpenAI API Equivalent |
|---|---|---|
| `GET /ext/hailo-genai/v1/models` | List downloaded models | List Models |
| `POST /ext/hailo-genai/v1/chat/completions` | Text generation & image understanding (VLM) | Chat Completions |
| `POST /ext/hailo-genai/v1/audio/transcriptions` | Speech-to-text | Audio Transcriptions |
| `POST /ext/hailo-genai/v1/embeddings` | Text-to-vector (CLIP) | Embeddings |

### Steps

1. Confirm the Hailo GenAI extension is enabled under **Extensions > GenAI**
2. Download the models you need (LLM: `qwen2.5-1.5b-chat`, VLM: `llava-v1.6-vicuna-7b`, etc.)
3. Set the **Base URL** in your external tool's connection settings:
   ```
   http://localhost:5000/ext/hailo-genai/v1
   ```
   (Adjust the port number to match your YU AI Manager configuration)
4. No API key is needed for local access. If the tool requires one, enter a dummy value (e.g., `dummy`)

### Connecting External Tools

#### Open WebUI

In Settings > Connections > OpenAI API, add:
- **URL**: `http://localhost:5000/ext/hailo-genai/v1`
- **API Key**: `dummy`

#### Continue.dev (VS Code AI Assistant)

Add to `~/.continue/config.json`:
```json
{
  "models": [{
    "title": "Hailo Qwen2.5",
    "provider": "openai",
    "model": "qwen2.5-1.5b-chat",
    "apiBase": "http://localhost:5000/ext/hailo-genai/v1",
    "apiKey": "dummy"
  }]
}
```

#### Python (OpenAI SDK)

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:5000/ext/hailo-genai/v1",
    api_key="dummy",
)

# Text generation
res = client.chat.completions.create(
    model="qwen2.5-1.5b-chat",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(res.choices[0].message.content)

# Image understanding (VLM) — attach a base64 image
import base64
with open("image.png", "rb") as f:
    b64 = base64.b64encode(f.read()).decode()

res = client.chat.completions.create(
    model="llava-v1.6-vicuna-7b",
    messages=[{
        "role": "user",
        "content": [
            {"type": "text", "text": "Describe this image."},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
        ],
    }],
)

# Speech-to-text
res = client.audio.transcriptions.create(
    model="whisper-1",
    file=open("audio.wav", "rb"),
)

# Text embeddings (CLIP)
res = client.embeddings.create(
    model="clip",
    input="a girl standing by the sea",
)
print(len(res.data[0].embedding))  # 512
```

### Supported Parameters

- **Chat Completions**: `model`, `messages`, `stream`, `temperature` (0–2), `max_tokens` (64–2048)
- **Audio Transcriptions**: `model`, `file`, `language`, `response_format` (json / text / verbose_json)
- **Embeddings**: `model`, `input` (string or array of strings)
- **Model aliases**: `whisper-1` → whisper-base, `clip` / `text-embedding-clip` → clip-vit-b-16

### Important Notes

- **Device exclusivity**: The Hailo-10H can only load one GenAI model (LLM, VLM, or S2T) at a time. Switch modes from the GenAI page
- **Image URL restriction**: For security, `http://` image URLs are blocked. Use `data:image/...;base64,...` format or YU AI Manager's `file_id:` extension instead
- **CLIP embeddings**: Only text-to-vector is supported. For image-to-vector, use the `/api/semantic/` endpoint
- **Audio formats**: Non-WAV formats (MP3, M4A, OGG, etc.) require ffmpeg to be installed
- **`usage` field**: Token counts always return 0 (Hailo NPU limitation)
