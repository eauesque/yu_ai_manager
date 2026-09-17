# Get Started with YU AI Manager in 5 Minutes

## What is YU AI Manager?

YU AI Manager is a WebUI application for managing metadata of AI-generated images (Stable Diffusion, NovelAI, ComfyUI, etc.). It automatically extracts embedded prompts and model information, making tag-based searching, browsing, and organizing effortless.

---

## System Requirements

| Item | Requirement |
|------|-------------|
| Python | 3.11 or later (`start.sh` / `start.bat` installs automatically) |
| Node.js | 22 LTS (optional — automatic download is offered on first launch) |
| OS | Windows 10/11, macOS, Linux |
| Browser | Chrome / Firefox / Edge (latest version recommended) |

> **No manual installation required.** `start.sh` / `start.bat` automatically sets up all required tools under the project directory (no system-wide writes or administrator privileges needed).

---

## Installation & Launch

### 1. Clone the Repository

```bash
git clone https://github.com/eauesque/yu_ai_manager.git
cd yu_ai_manager
```

### 2. Run the Start Script

**macOS / Linux:**

```bash
./start.sh
```

**Windows:**

```bat
start.bat
```

### First-Launch Auto-Setup

On the first run, the following tools are installed as needed:

| Tool | How it is obtained |
|------|--------------------|
| `uv` | Auto-downloaded to `./bin/uv` |
| Python 3.11+ | Installed automatically by `uv` |
| Node.js 22 LTS | Optional — prompts to download to `./bin/node/` (~30 MB) |
| pnpm | Enabled via `corepack` once Node.js is available |
| ffmpeg | Optional — prompts to download to `./bin/ffmpeg/` (~80 MB) |

> **ffmpeg** is only required for advanced features such as video analysis, audio transcription, and OCR. It is not needed to run the application itself.  
> In non-interactive environments (e.g. CI), set `YU_AUTO_INSTALL=1` to skip prompts and install everything automatically.

From the second launch onward, a rebuild is triggered only when dependencies or TypeScript sources have changed.

### 3. Open in Your Browser

Once the server is running, open the following URL:

```
http://localhost:5000
```

---

## Getting Started

### Step 1: Register an Image Folder for Scanning

Register folders containing your AI-generated images so their metadata can be extracted.

1. Open **Settings** from the hamburger menu in the top-right corner
2. Select the **Scan** tab
3. Add the path to your target folder
4. Scanning starts automatically after the folder is added

A progress bar appears at the top of the screen during scanning. Large libraries may take a few minutes, but you can still search and browse while the scan is in progress.

### Step 2: Browse Images in the Thumbnail Grid

Once scanning is complete, the main page displays a thumbnail grid.

- **Scrolling**: Virtual scrolling ensures smooth performance even with massive libraries
- **Sorting**: Use the sort menu at the top to switch between date, rating, and other orderings
- **Right-click**: The context menu lets you add images to favorites or collections

### Step 3: Search by Tags

Enter tags separated by commas in the search bar to filter images.

```
1girl, blue_eyes, school_uniform
```

- **Autocomplete**: Matching tag suggestions appear as you type
- **Filters**: Narrow results by date range, file format, star rating, and more
- **Prompt search**: Full-text search across prompt content is also available

### Step 4: View Image Details

Click a thumbnail to open the detail modal.

- **Info tab**: View prompts, negative prompts, model names, and generation parameters
- **AI Analysis tab**: View WD-Tagger auto-tagging results (when configured)
- **Star rating**: Rate images from 1 to 5 stars
- **Favorites**: Click the heart icon to add to favorites
- **Tag editing**: Add or remove user tags
- **Keyboard navigation**: Use arrow keys to move between images

---

## Common Actions at a Glance

| Goal | How to |
|------|--------|
| Find an image | Enter tags in the search bar |
| View image details | Click a thumbnail |
| Add to favorites | Heart icon in the detail modal, or right-click menu |
| Rate an image | Star icons in the detail modal |
| Add to a collection | Right-click > Add to Collection |
| Select multiple images | Ctrl+Click (or Shift+Click for range selection) |
| Scan a new folder | Settings > Scan tab |

---

## Launch Options

Place a `launch-args.txt` file in the project root to set persistent options:

```
--db /path/to/tags.db
--port 5001
--lan
--pin 1234
```

| Option | Description |
|--------|-------------|
| `--db` | Path to the database file |
| `--port` | Change the port number (default: 5000) |
| `--lan` | Enable LAN access mode (allows other devices to connect) |
| `--pin` | Set a PIN code for authentication when LAN access is enabled |

---

## Next Steps

Once you're comfortable with the basics, explore these additional features.

### Settings

The Settings page lets you customize appearance, set your timezone, configure LAN access, and more.

### Bridge (Image Generation Tool Integration)

Connect with SD WebUI, ComfyUI, or the NovelAI API to send and receive prompts.
See the [Bridge Guide](bridges.md) for details.

### Extensions

A wide range of extensions are available, including WD-Tagger (auto-tagging), Prompt Library, and Chatlog Viewer. Manage them from Settings > Extensions tab.

### Semantic Search

Configure a CLIP model to search images using natural language queries like "a girl watching the sunset by the sea."
See the [Search Guide](search.md) for details.

### MCP Server

Control YU AI Manager from AI agents such as Claude Desktop.

---

## Troubleshooting

If you run into issues, see the [Troubleshooting Guide](troubleshooting.md).

Common issues:

- **`start.sh` cannot be executed (Linux/macOS)**: Run `chmod +x start.sh` to grant execute permission
- **Port 5000 is in use**: Add `--port 5001` to `launch-args.txt` and restart
- **Images not showing**: Verify that the scan folder path is correct and that the image files exist on disk
- **Want to skip the Node.js download**: Enter `n` at the prompt, or set `YU_AUTO_INSTALL=1` to skip — if a pre-built `dist/` directory exists the application will run without it
