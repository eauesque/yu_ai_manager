# Bridge Integration

The Bridge feature lets you send prompts directly from YU AI Manager to various AI image generation tools.

## Supported Bridges

### SD WebUI Bridge
Integrates with Stable Diffusion WebUI (Automatic1111 / Forge).
- Send and receive prompts
- Transfer generation parameters

### NAI Bridge
Integrates with NovelAI.
- Automatic prompt syntax conversion (SD <-> NAI)
- Automatic quality tag insertion

#### Vibe Transfer (NovelAI Potion) and encode-vibe Cache

NAI V4+ models require reference images to be pre-encoded via `/ai/encode-vibe`
(**2 Anlas per call**) before they can be used in a generation request.

To avoid wasting Anlas when generating with the same image repeatedly, the
encoded results are cached locally at:

```
data/nai_vibe_cache/<sha256>__<model>__<info_extracted>.bin
```

- **Key**: SHA256 of the raw image + model name + information_extracted (0.01 steps)
- **Max size**: 500 MB by default. Change in Settings > NAI Bridge > "Vibe encode cache (MB)" (0 = disabled)
- **LRU eviction**: Files are removed oldest-first in a background thread when the limit is exceeded

### ComfyUI Bridge
Integrates with ComfyUI.
- Insert prompts into workflows
- Customize output format

## Batch Generation

All three Bridges support batch generation in the main generation path (A1111-compatible semantics).

### Batch count / Batch size

- **Batch count** — Number of sequential generation runs (time axis). The client calls the API once per iteration.
- **Batch size** — Number of images generated in parallel per API call (VRAM axis). Not shown in NAI Bridge.
- Total images = Batch count × Batch size

With a fixed seed, the seed is incremented as `base + i` on each loop iteration (same behavior as A1111). With `-1` (random), a new random seed is used each time.

### Stop buttons

| Bridge | Single run (count=1) | Loop (count>1) |
|---|---|---|
| NAI | No stop button | "Stop after current" only |
| SD WebUI | "Stop" (server cancel API) | "Stop after current" + "Stop" |
| ComfyUI | "Stop" (server cancel API) | "Stop after current" + "Stop" |

- **Stop (immediate)** — Aborts the in-progress API call and halts the loop. For SD WebUI / ComfyUI, the server cancel API is also called.
- **Stop after current** — Lets the current image finish, then skips the next iteration.

NAI Bridge shows no stop button for single-image generation because the NAI API charges Anlas (credits) the moment it accepts the fetch request. Cutting the HTTP connection does not stop the server-side generation or refund the charge, so a stop button would only cause confusion.

### VRAM note

Increasing Batch size raises GPU VRAM usage proportionally on the server. Running SDXL with Batch size 4 or more can cause OOM errors — start at 1 and increase gradually.

## Quality Presets

Use the "QP" button in each Bridge's toolbar to insert quality-boosting tags with one click.

Built-in presets:
- SD High Quality
- SD Realistic
- NAI Quality
- NAI Artistic
- Minimal

Custom presets can also be created.

## Resolution Presets

SD WebUI Bridge and ComfyUI Bridge show a "Resolution Preset" dropdown and ⇄ Swap button above the Width/Height inputs, letting you pick common sizes in one click.

- **SD 1.5** — 5 common resolutions for SD 1.5 models (512 base)
- **SDXL Trained** — 9 official SDXL training buckets (quality first)
- **SDXL Cheat Sheet** — 12 cinema / photography aspect ratios approximated at multiples of 8 (composition first, from [Civitai](https://civitai.com/articles/2246/sdxl-image-size-cheat-sheet))

Selecting `Custom` keeps your existing W/H values. If you edit W or H manually after applying a preset, the dropdown reverts to `Custom`. The ⇄ button swaps Width and Height.

Cheat Sheet resolutions fall outside the official SDXL buckets, so some models may produce slightly off compositions.

> In ComfyUI Bridge, presets apply only to Simple mode. Raw JSON Workflow node values are not modified.


## Multi-Server Support

SD WebUI Bridge and ComfyUI Bridge can connect to multiple servers simultaneously. You can compare different models side-by-side, increase throughput with multiple GPUs, or run remote and local servers in parallel.

### Adding servers

Open the **Servers** section (collapsible) at the bottom of the Bridge page.

1. Click **Servers** to expand
2. Click **+ Add Backend**
3. Enter **Type** (`comfyui` or `sd_webui`), **URL** (`http://HOST:PORT`), and optionally a **Name**, then Save

Registered servers are listed with name, URL, and a status dot (🟢 running / 🔴 stopped / 🟡 unknown). Use the Delete button to remove a server.

#### URL format

| Format | Example |
|--------|---------|
| Local | `http://127.0.0.1:8188` |
| LAN remote | `http://192.168.1.10:7860` |
| HTTPS | `https://gpu.example.com` |

Path, query, and fragment are not allowed — use `http://host:port` only.

### Creating groups

A group bundles multiple servers together. When you select a group as the send target, the prompt is sent to **all servers in the group simultaneously** (fan-out).

1. In the **Groups** area of the **Servers** section, click **+ Add Group**
2. Enter a group name, check the member servers, and Save

> The maximum number of servers per group is 16. A confirmation dialog appears before sending to more than 8 servers.

### Selecting a send target

Clicking the **→ ComfyUI** or **→ SD** button in the image detail modal opens the **server selector**.

| Option | Behavior |
|--------|----------|
| **Default** | Send to the configured default server (falls back to the built-in URL if none set) |
| **Group name** (⚡) | Fan-out to all servers in the group in parallel |
| **Server name** (🟢/🟡) | Send to that specific server |

Stopped (🔴) servers are grayed out and cannot be selected.

#### Setting a default server

In the **Default Backends** area of the **Servers** section, you can set a default server per type. Once set, selecting "Default" always routes to that server.

### Viewing parallel results

After sending to multiple servers, the result panel switches to **swimlane** view.

- Each server's generation appears in its own independent lane
- When a group was selected, a collapsible group header groups the lanes
- A progress bar at the top of each lane shows generation progress
- Click **"Unified View"** (top-right) to switch to a combined filmstrip ordered by receive time

If any server encounters an error, the other servers continue generating — the error is shown inside that lane only.

## Cross-Bridge Transfer

Prompts can be transferred directly between Bridges. Syntax is automatically converted between SD and NAI formats.

## Send to Bridge

From the image detail modal toolbar, you can send the displayed image's prompt or the image itself directly to a generation Bridge.

- **Send prompt ▾** — Sends the displayed image's prompt to NAI Bridge, SD WebUI, or ComfyUI. Prompts written in NAI syntax are automatically converted to SD syntax when targeting SD/ComfyUI, and vice versa. NAI v4 character prompts (positive/negative) are kept structured when targeting NAI Bridge, and merged into the main prompt for all other targets.
- **Send image (img2img) ▾** — Sends the full-resolution image directly to the img2img slot of NAI Bridge, SD WebUI, or ComfyUI Bridge. ComfyUI img2img is supported from v4.121.0 (LoadImage + VAEEncode + KSampler with denoise 0.75 default; output size matches the source image).
- **Remix ▾** (from v4.121.3) — Sends the prompt **and** the image together in one click. Useful when you want to tweak the prompt and re-generate from the same source image. Targets: NAI / SD WebUI / ComfyUI.

When the buttons appear:
- Send prompt: when the image contains prompt metadata (positive/negative or character information)
- Send image: when the displayed media is an image (still image, animated image, or video). For video, the frame at the current playback position is captured and sent as PNG (v4.121.20+).
- Remix: only when both above conditions are met

Notes:
- "Send image" is not shown for PDF or audio files
- For video, only a single frame at the current playback position is sent — not the original video file
- If prompt syntax conversion fails, the prompt is sent in its original syntax and a warning toast is displayed in the destination Bridge
- Only the prompt/image is sent. Parameters such as sampler, steps, CFG, and seed are not restored at the destination (the Bridge's default or previously set values are used)
