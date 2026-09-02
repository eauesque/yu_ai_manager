# Hailo-10H Setup

Host-side setup required to use a Raspberry Pi 5 + Hailo AI Hat+ (Hailo-10H NPU) with YU AI Manager. The Python wheel is not on PyPI, so a few manual steps are needed beyond `uv sync`.

> **Audience**: machines that have the Hailo-10H hardware and want to enable the Hailo extensions (GenAI chat / Semantic Search / YOLO Detect / Tagger / Whisper). If you have no Hailo HW, you can ignore this page entirely.

---

## 1. Prerequisites

- Raspberry Pi 5 (8 GB strongly recommended — the 4 GB model is tight under the CMA constraint when loading multiple models)
- Hailo AI Hat+ (Hailo-10H)
- Raspberry Pi OS Bookworm 64-bit (aarch64)
- Python 3.13.x (`pyproject.toml` pins `<3.14`; `uv` will pick 3.13 automatically)

---

## 2. Install the PCIe driver

Hailo-10H uses the `hailo1x_pci` kernel module (renamed from `hailo_pci` in HailoRT 5.3.0).

```bash
sudo apt update
sudo apt install hailo-all
sudo reboot
```

Verify after reboot:

```bash
lsmod | grep hailo1x
ls /dev/h1x-0
dmesg | grep -i hailo | tail -20
```

You should see `hailo1x_pci` loaded, the device node `/dev/h1x-0` (note: **not** `/dev/hailo0` — that path is obsolete since HailoRT 5.3.0), and a `Firmware loaded` / `Device created at /dev/h1x-0` line in dmesg.

The app accepts both old and new device paths (`core/llm_router/hailo_detect.py`), so the rename is transparent.

---

## 3. Install HailoRT (system-side)

Provides the `hailortcli` binary and `libhailort.so`. `hailo-all` already includes this; install a newer `.deb` from the Hailo Developer Zone only if you specifically need a newer revision.

Verify:

```bash
hailortcli fw-control identify
# Device Architecture: HAILO10H
# Firmware Version: 5.3.0 (release,app)
```

---

## 4. Prepare the Python wheel (`hailort-*.whl`)

**The aarch64 Hailo Python wheel is not distributed via PyPI or via the Hailo Developer Zone — you have to build it yourself.**

### 4.1 Build from source

```bash
cd ~
git clone --branch v5.3.0 https://github.com/hailo-ai/hailort.git
cd hailort
./build.sh -aarch64
# produces e.g. hailort-5.3.0-cp313-cp313-linux_aarch64.whl
```

See the official Hailo README for full build prerequisites.

### 4.2 Stage the wheel under $HOME

Drop the wheel in **any** of the following locations and it will be auto-detected at startup:

| Search path (priority order) | Notes |
|---|---|
| `$HAILORT_WHEEL` environment variable | Absolute path override (highest priority) |
| `$HOME/share/` | **Recommended** location |
| `$HOME/hailort/` | If you keep the build tree as-is |
| `$HOME/Downloads/` | Temporary parking spot |
| `$HOME/` (directly) | Last-resort search |

Recommended placement:

```bash
mkdir -p ~/share
cp ~/hailort/hailort-5.3.0-cp313-cp313-linux_aarch64.whl ~/share/
```

### 4.3 How auto-install works

`./start.sh` runs `scripts/install_hailo.py` at every launch:

1. Tries `import hailo_platform` inside the venv.
2. If that fails, scans the locations above for a wheel matching the current Python version (cp313) and machine arch (aarch64).
3. If found, `uv pip install`s the newest match.
4. If nothing is found, or `hailo_platform` is already installed, it silently does nothing.

No manual `uv pip install` is required — staging the wheel under `$HOME` is enough.

---

## 4.4 HEF model files

Each Hailo extension needs a pre-compiled HEF model file in `~/hailo_models/`.

| File | Used by | Approx. size |
|---|---|---:|
| `yolov8n.hef` | YOLO object detection | 7 MB |
| `clip_vit_b_16_image_encoder.hef` | **Semantic Search (CLIP image)** | 76 MB |
| `clip_vit_b_16_text_encoder.hef` | Semantic Search (CLIP text, optional) | 77 MB |
| `Whisper-{Tiny,Base,Small}.hef` | Speech-to-Text | 75-405 MB |
| `Qwen3-1.7B-Instruct.hef` | LLM chat | 2.9 GB |
| `Qwen3-VL-2B-Instruct.hef` | VLM (image + text) | 3.2 GB |

The Hailo Model Zoo S3 bucket allows direct downloads without authentication:

```
https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/<model>.hef
```

Example (CLIP image encoder):

```bash
mkdir -p ~/hailo_models
curl -L -o ~/hailo_models/clip_vit_b_16_image_encoder.hef \
  https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/clip_vit_b_16_image_encoder.hef
```

> **Missing HEF files surface as "unavailable" in the corresponding extension**. For example, the Semantic Search status panel shows `hailo-10h (CLIP HEF not staged)` when `clip_vit_b_16_image_encoder.hef` is absent from `~/hailo_models/`. The status payload breaks the check into three flags (`runtime_ok` / `hardware_ok` / `hef_ok`) so it is easy to tell which layer is missing. Hover the status badge for the full reason string.

You can override the directory by setting `HAILO_HEF_DIR=/some/other/path`.

---

## 5. Kernel parameter (CMA)

Hailo GenAI models (LLM / VLM / Whisper) need CMA (Contiguous Memory Allocator) memory for DMA.

Append to `/boot/firmware/cmdline.txt`:

```
cma=256M
```

> **`cma=1G` and `cma=512M` silently fail on the Pi 5 (8 GB)**. The default kernel applies `numa=fake=8`, so CMA must fit within a single 1 GB NUMA node — anything above `256M` ends up as `CmaTotal=0` with no kernel panic. See [`docs/en/hailo/PI5_NUMA_CMA_CONSTRAINTS.md`](../../hailo/PI5_NUMA_CMA_CONSTRAINTS.md) (Japanese reference).

After reboot:

```bash
grep CmaTotal /proc/meminfo
# CmaTotal:         262144 kB  ← 256 MB → success
```

A reading of `0 kB` means your value was rejected — lower it.

---

## 6. Coexistence with hailo-ollama (optional)

Running `hailo-ollama` (Ollama with Hailo NPU support) on the same device:

- **HailoRT 5.3.0+**: launch as `HAILO_OLLAMA_VDEVICE_GROUP_ID=YU_SHARED hailo-ollama` to share the physical device with yu_ai_manager (which uses `group_id="YU_SHARED"`). The HailoRT scheduler time-slices in ROUND_ROBIN fashion.
- **5.2.0 and earlier**: hailo-ollama does not accept the group_id flag — `sudo systemctl stop hailo-ollama` before launching yu_ai_manager.

---

## 7. Verification

After `./start.sh`, the WebUI's **Settings → Extensions** page should list these as enabled:

- `builtin_hailo_genai` (Hailo chat / LLM / VLM / Speech2Text)
- `builtin_hailo_semantic_search` (CLIP semantic search)
- `builtin_hailo_yolo_detect` (YOLO object detection)

Or check directly from the CLI:

```bash
uv run python -c "
from hailo_platform import VDevice
v = VDevice()
print('VDevice OK')
v.release()
"
```

---

## 8. Troubleshooting

### All Hailo extensions show "failed to load"

Most likely the Python wheel is not installed:

```bash
uv run python -c "import hailo_platform; print(hailo_platform.__file__)"
```

If you get `ModuleNotFoundError`, stage the wheel under `$HOME` and restart `./start.sh` (see §4.2).

### `hailortcli fw-control identify` fails with `HAILO_OPEN_FILE_FAILURE`

Driver or device-node problem. Check `lsmod | grep hailo1x` and `ls /dev/h1x-0`. If both are missing, redo §2 and reboot.

### LLM/VLM load fails with `HAILO_OUT_OF_HOST_MEMORY` or the Pi locks up

CMA exhaustion. Confirm `grep CmaTotal /proc/meminfo` shows 256 MB (§5). Note that `VDevice.release()` does **not** return CMA to the OS — after many model switches you may need to restart the process.

### `HAILO_OUT_OF_PHYSICAL_DEVICES(74)`

Another process is holding the VDevice. Find it via `lsof /dev/h1x-0` (typically `hailo-ollama`, or a previous run that did not exit cleanly) and `kill` it before relaunching.

### Python is 3.14 and the wheel is incompatible

This repo pins `requires-python = ">=3.13,<3.14"` in `pyproject.toml`, so a fresh `uv sync` always selects 3.13.x. If you manually wrote `.python-version` with `3.14`, revert it.

---

## 9. Related docs

- [`docs/ja/hailo/README.md`](../../../ja/hailo/README.md) — Hailo-10H developer-doc index (Japanese)
- [`docs/ja/hailo/HAILORT_5_3_0_MIGRATION.md`](../../../ja/hailo/HAILORT_5_3_0_MIGRATION.md) — HailoRT 5.2.0 → 5.3.0 migration notes
- [`docs/ja/hailo/PI5_NUMA_CMA_CONSTRAINTS.md`](../../../ja/hailo/PI5_NUMA_CMA_CONSTRAINTS.md) — CMA constraint deep-dive
- [`scripts/install_hailo.py`](../../../../scripts/install_hailo.py) — the wheel auto-detect script
