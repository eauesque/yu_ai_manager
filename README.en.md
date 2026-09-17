# YU AI Manager

AI-generated image metadata management WebUI.

## Overview

A WebUI tool that extracts, searches, and manages metadata (prompts, models, seeds, etc.) embedded in AI-generated images.

**What you can do:**

- Scan entire folders or ZIP archives to auto-register images
- Cross-search and filter by prompts, tags, model names, seed values, etc.
- Instantly send favorite images to SD / ComfyUI / NovelAI for regeneration
- Auto-tag with WD-Tagger, analyze content with Ollama/OpenAI
- Access from other devices (smartphones, etc.) on the LAN via QR code

**Supported sources**: Stable Diffusion (A1111/Forge), NovelAI V3/V4, ComfyUI

## System Requirements

- Windows / Linux / macOS

> **No manual installation needed.** `start.sh` / `start.bat` bootstraps all necessary tools under the project directory (no system writes or admin privileges required).

## Setup & Launch

```bash
git clone https://github.com/eauesque/yu_ai_manager.git
cd yu_ai_manager

# Windows
start.bat

# macOS / Linux
./start.sh
```

Auto-setup on first launch:

| Tool | How to get |
| --- | --- |
| `uv` | Auto-downloaded to `./bin/uv` |
| Python 3.11+ | Auto-installed by `uv` |
| Node.js 22 LTS | Optional — confirm auto-download to `./bin/node/` (approximately 30 MB) |
| pnpm | Enabled via `corepack` once Node.js is installed |
| ffmpeg | Optional — Windows/macOS: confirm auto-download to `./bin/ffmpeg/` (approximately 80 MB), Linux: see instructions for distro `apt`/`dnf`/`pacman` commands |

Set `YU_AUTO_INSTALL=1` to skip prompts and fully automate installation even in non-interactive environments (CI, etc.). ffmpeg is optional and only used for extended features like video analysis, S2T, and OCR—not required for core startup.

On subsequent launches, reinstallation and rebuild occur only if dependencies or TypeScript sources have changed.

Persistent settings can be configured by writing `--db`, `--port`, `--lan`, `--pin`, etc. in `launch-args.txt`.

## Major Features

### Scan & Register
- Auto-extraction of metadata from PNG / WebP / JPEG
- Transparent scanning of ZIP / 7z archives without extraction
- Add files via drag-and-drop

### Search & Browse
- Full-text search by prompts, tags, model names, seed values
- Regex search, combined filtering
- pHash similarity search, CLIP semantic search

### Organize & Manage
- Favorites, star ratings (1–5), notes (annotations)
- Collections (grouping)
- Statistics dashboard, monthly reports, trophy system

### Generation Tool Integration (Bridge)
- Instant prompt sending to SD WebUI / Forge / ComfyUI / NovelAI
- Also supports clipboard-based sending

### AI Assistance
- Auto-tagging with WD-Tagger
- Image content analysis using Ollama / OpenAI
- Speech-to-text (S2T)

### Networking & Sharing
- LAN sharing mode (access from smartphone via QR code)
- MCP server (control from AI agents)
- Fleet management (centralized multi-instance administration)

### Customization
- Custom UI & extension system
- Theme support (light / dark)
- Tauri desktop app (launch without browser)

## Multilingual Support

English / 日本語 / 繁體中文 / 简体中文 / 한국어

## Documentation

- [Quick Start](docs/en/help/user/quickstart.md)
- [Use Cases](docs/en/help/user/use-cases.md)
- [API Reference](docs/en/api/README.md)
- [Performance Tuning](docs/en/help/user/performance-tuning.md)
- [Deployment](docs/en/help/user/deployment.md)
- [Extension Development](docs/en/plugin-development/getting-started.md)
- [Custom UI](docs/en/custom-ui/README.md)
- [MCP Tools Reference](docs/en/api/MCP_TOOLS_REFERENCE.md)
- [All Documentation](docs/en/README.md)

## Development & Customization

See [DEVELOPMENT.en.md](DEVELOPMENT.en.md) ([日本語](DEVELOPMENT.ja.md))

## Ask AI for Help

### If it won't launch

Tell an AI agent (like Claude Code Desktop) with this project folder as the working directory:

> `start.bat` (or `start.sh`) starts but then stops. Please investigate.

> **Note**: With Claude Code Desktop, you need to specify the project folder before starting the conversation.

### Issues, settings, or usage after launch

**Step 1 — Get context**

Open the help page (`/help`) and click the **"Copy AI Context"** button.
It fetches `GET /api/ai-context` using your logged-in browser session and copies the JSON to clipboard (works even in http:// LAN environments).

> **Note (if you have an API key)**: With an admin-scoped API key, you can directly call `GET /api/ai-context` with the `Authorization: Bearer <key>` header.

**Step 2 — Share with AI**

Paste the copied JSON into your AI chat, then ask your question:

> [Pasted JSON]
> Based on this, please resolve [problem description].

`/api/ai-context` includes the current version, enabled features, configuration hints, API list, and CSRF rules—everything AI needs for accurate assistance.

## FAQ

[docs/en/FAQ.md](docs/en/FAQ.md) ([日本語](docs/ja/FAQ.md))

## Bug Reports

[GitHub Issues](https://github.com/eauesque/yu_ai_manager/issues)

## License

MIT License — [LICENSE](LICENSE) / [English](docs/en/LICENSE.md) ([日本語](docs/ja/LICENSE.md))
