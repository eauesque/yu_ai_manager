# YU AI Manager

AI-generated image metadata management WebUI.

- [English](README.en.md)
- [日本語](README.ja.md)
- [繁體中文](README.zh-tw.md)
- [简体中文](README.zh-cn.md)
- [한국어](README.ko.md)
- [Deutsch](README.de.md)
- [Español](README.es.md)
- [Français](README.fr.md)
- [Italiano](README.it.md)
- [Português](README.pt.md)
- [Русский](README.ru.md)

---

**Supported sources**: Stable Diffusion (A1111/Forge), NovelAI V3/V4, ComfyUI

**Languages**: English / 日本語 / 繁體中文 / 简体中文 / 한국어 / Deutsch / Español / Français / Italiano / Português / Русский

**License**: MIT

## Quick Start

```bash
git clone https://github.com/eauesque/yu_ai_manager.git
cd yu_ai_manager

# Windows
start.bat

# macOS / Linux
./start.sh
```

**No manual setup needed.** Use `start.sh` / `start.bat` as the normal entry point. The launcher keeps setup project-local, starts the Python app through `uv`, and rebuilds the Web UI bundle when the generated `dist` files are missing or stale.

| Tool | How it's installed |
| --- | --- |
| `uv` | Auto-downloaded to `./bin/uv` |
| Python 3.11+ | Managed by `uv` automatically |
| Node.js 22 LTS | Uses system Node if present, otherwise prompts to download to `./bin/node/` (~30 MB) |
| pnpm / npm | Used by the launcher to rebuild the frontend bundle when needed |
| ffmpeg | Optional; prompts to download to `./bin/ffmpeg/` on Windows/macOS, prints distro-specific `apt`/`dnf`/`pacman` hint on Linux |

### What the launcher does

1. Downloads `uv` into `./bin/uv` if needed.
2. Selects the ONNX Runtime variant (`cpu`, `gpu`, `directml`, or `rocm`) and caches it in `.onnx_extra`.
3. Finds or offers to install project-local Node.js for frontend builds.
4. Finds or offers to install ffmpeg for video / speech-to-text / OCR extensions.
5. Starts `web_ui.py` through `uv run`.
6. If the Web UI bundle is stale, rebuilds it once with `pnpm run build` or `npm run build`, then restarts the server.

`ui/default/static/dist/` is treated as generated output. It is not the source of truth and does not need to be manually edited or committed; `start.sh` / `start.bat` will regenerate it from the frontend sources when required.

Useful environment variables:

| Variable | Effect |
| --- | --- |
| `YU_AUTO_INSTALL=1` | Accepts optional launcher installs in non-interactive environments |
| `YU_AUTO_INSTALL_NODE=1` | Auto-installs project-local Node.js when missing |
| `YU_AUTO_INSTALL_FFMPEG=1` | Auto-installs ffmpeg where the bootstrap supports it |
| `YU_SKIP_DIST_CHECK=1` | Bypasses stale `dist` detection in the app |

ffmpeg is only required by video / speech-to-text / OCR extensions. The core app starts without it.

## Documentation

- [Development Guide](DEVELOPMENT.en.md)
- [FAQ](docs/en/FAQ.md)
- [API Reference](docs/en/api/README.md)
- [All Documents](docs/en/README.md)

## Bug Reports

[GitHub Issues](https://github.com/eauesque/yu_ai_manager/issues)
