# Hailo-10H 设置

在 Raspberry Pi 5 + Hailo AI Hat+ (Hailo-10H NPU) 上从 YU AI Manager 使用的主机端设置步骤。硬件和 OS 相关部分不能通过 PyPI 完成，因此需要进行一些手动准备。

> **目标**：仅当在搭载 Hailo-10H 硬件的 Raspberry Pi 5 (建议 8 GB) 上启用 Hailo 相关扩展 (GenAI 聊天 / Semantic Search / YOLO Detect / Tagger / Whisper) 时。如果没有 Hailo HW，则不需要执行此页面的任何操作。

---

## 1. 先决条件

- Raspberry Pi 5 (强烈建议 8 GB。由于 CMA 限制，4 GB 在同时加载多个模型时会很困难)
- Hailo AI Hat+ (Hailo-10H)
- Raspberry Pi OS Bookworm 64-bit (aarch64)
- Python 3.13.x (已在 `pyproject.toml` 的 `requires-python` 中固定为 `<3.14`。`uv` 会自动选择 3.13)

---

## 2. PCIe 驱动程序安装

Hailo-10H 使用专用内核模块 `hailo1x_pci` (从 HailoRT 5.3.0 起从旧 `hailo_pci` 改名)。

```bash
sudo apt update
sudo apt install hailo-all
sudo reboot
```

重新启动后确认：

```bash
lsmod | grep hailo1x
ls /dev/h1x-0
dmesg | grep -i hailo | tail -20
```

预期结果：

- `hailo1x_pci` 已加载
- 存在 `/dev/h1x-0` 设备节点 (不是旧的 `/dev/hailo0`)
- `dmesg` 中有 `Firmware loaded in NNNN ms` `Device created at /dev/h1x-0` 的行

> **即使看起来没有 `/dev/hailo0` 也没关系**。HailoRT 5.3.0 之后 `/dev/h1x-0` 是默认的，本应用程序可识别两者 (`core/llm_router/hailo_detect.py`)。

---

## 3. HailoRT (系统端) 安装

`hailortcli` 二进制文件和 `libhailort.so` 共享库。虽然 `hailo-all` 包中包含了它们，但如果需要最新版本，可以从 Hailo Developer Zone 获取 `.deb` 进行覆盖安装。

确认：

```bash
hailortcli fw-control identify
```

预期输出 (要点)：

```
Device Architecture: HAILO10H
Firmware Version: 5.3.0 (release,app)
```

---

## 4. Python wheel (`hailort-*.whl`) 准备

这是 PyPI 不提供的部分。**aarch64 的 Hailo Python wheel 也不在 Hailo Developer Zone，因此需要自行构建。**

### 4.1 从源代码构建

```bash
cd ~
git clone --branch v5.3.0 https://github.com/hailo-ai/hailort.git
cd hailort
./build.sh -aarch64
# 完成后，构建树内会生成 hailort-5.3.0-cp313-cp313-linux_aarch64.whl
```

(构建步骤的详细信息和依赖包请参考 Hailo 官方 README。)

### 4.2 将 wheel 放在主目录

将构建的 wheel 复制到以下 **任何位置**，本应用程序在启动时会自动检测：

| 探索位置 (优先顺序) | 用途 |
|---|---|
| `$HAILORT_WHEEL` 环境变量 | 任意完整路径指定 (最优先) |
| `$HOME/share/` | **建议位置** |
| `$HOME/hailort/` | 在源代码位置保留构建树的情况 |
| `$HOME/Downloads/` | 下载后的临时位置 |
| `$HOME/` (直下) | 最后的备用 |

建议位置：

```bash
mkdir -p ~/share
cp ~/hailort/hailort-5.3.0-cp313-cp313-linux_aarch64.whl ~/share/
```

### 4.3 自动安装机制

执行 `./start.sh` 时，`scripts/install_hailo.py` 会运行，

1. 检查 venv 内 `import hailo_platform` 是否成功
2. 失败时，从上述探索位置搜索 **符合现有 Python 版本 (cp313) + 架构 (aarch64) 的** wheel
3. 找到最新的 wheel 后使用 `uv pip install` 进行安装
4. 如果没有 wheel 或已安装，则不执行任何操作 (无声无操作)

也就是说，不需要手动 `uv pip install`。将 wheel 放在主目录并重新启动 `./start.sh` 即可恢复。

---

## 4.4 HEF 模型文件放置

将各扩展功能使用的 HEF 文件 (为 NPU 编译的模型) 放在 `~/hailo_models/` 中。

| 文件 | 用途 | 大小目安 |
|---|---|---:|
| `yolov8n.hef` | YOLO 物体检测 | 7 MB |
| `clip_vit_b_16_image_encoder.hef` | **语义搜索 (CLIP 图像)** | 76 MB |
| `clip_vit_b_16_text_encoder.hef` | 语义搜索 (CLIP 文字，可选) | 77 MB |
| `Whisper-{Tiny,Base,Small}.hef` | 语音识别 | 75-405 MB |
| `Qwen3-1.7B-Instruct.hef` | LLM 聊天 | 2.9 GB |
| `Qwen3-VL-2B-Instruct.hef` | VLM (图像+文字) | 3.2 GB |

可以从 Hailo Model Zoo 的 S3 bucket 无需认证直接下载 (URL 格式)：

```
https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/<model>.hef
```

示例 (CLIP 图像编码器)：

```bash
mkdir -p ~/hailo_models
curl -L -o ~/hailo_models/clip_vit_b_16_image_encoder.hef \
  https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/clip_vit_b_16_image_encoder.hef
```

> **如果 HEF 文件不足，扩展功能将显示 `无法使用`**。例如，如果语义搜索状态显示 `hailo-10h (CLIP HEF 未配置)`，表示 `clip_vit_b_16_image_encoder.hef` 不在 `~/hailo_models/` 中。为了易于区分硬件或 Python 运行时问题，`runtime_ok` / `hardware_ok` / `hef_ok` 这 3 阶段的原因包含在响应中 (将鼠标悬停在状态文字上以查看详细信息)。

也可以用 `HAILO_HEF_DIR` 环境变量指定别的目录。

---

## 5. 内核参数 (CMA)

Hailo 的 GenAI 模型 (LLM/VLM/Whisper) 需要 CMA (Contiguous Memory Allocator) 用于 DMA。

在 `/boot/firmware/cmdline.txt` 末尾添加：

```
cma=256M
```

> **Pi 5 (8 GB) 上 `cma=1G` 或 `cma=512M` 会静默失败**。默认内核应用 `numa=fake=8`，因此 CMA 必须在单一 NUMA 节点边界 (1 GB) 内，超过 `256M` 时 `CmaTotal=0` (没有恐慌)。详细信息：[`docs/ja/hailo/PI5_NUMA_CMA_CONSTRAINTS.md`](../../hailo/PI5_NUMA_CMA_CONSTRAINTS.md)

重新启动后确认：

```bash
grep CmaTotal /proc/meminfo
# CmaTotal:         262144 kB  ← 256 MB 就成功了
```

如果是 `0 kB`，请检查值，必要时降低。

---

## 6. 与 hailo-ollama 共存 (可选)

如果在同一设备上运行 `hailo-ollama` (Ollama 的 Hailo NPU 版本)：

- **HailoRT 5.3.0 之后**：使用 `HAILO_OLLAMA_VDEVICE_GROUP_ID=YU_SHARED hailo-ollama` 启动，可以与 yu_ai_manager 侧 (group_id `YU_SHARED`) 共享物理设备，HailoRT 调度器使用 ROUND_ROBIN 进行时间分片
- **5.2.0 之前**：不接受 group_id，因此在 yu_ai_manager 启动前需要使用 `systemctl stop hailo-ollama` 停止

---

## 7. 动作确认

启动 `./start.sh` 后，在 WebUI 的 **设置 → 扩展功能** 中如果以下项目被启用则成功：

- `builtin_hailo_genai` (Hailo 聊天 / LLM / VLM / Speech2Text)
- `builtin_hailo_semantic_search` (CLIP 语义搜索)
- `builtin_hailo_yolo_detect` (YOLO 物体检测)

或直接在 CLI 中：

```bash
uv run python -c "
from hailo_platform import VDevice
v = VDevice()
print('VDevice OK')
v.release()
"
```

---

## 8. 故障排除

### Hailo 相关扩展功能全部显示「未加载」

→ Python wheel 可能未安装。请检查：

```bash
uv run python -c "import hailo_platform; print(hailo_platform.__file__)"
```

如果出现 `ModuleNotFoundError`，请将 wheel 放在主目录，然后重新启动 `./start.sh` (§4.2)。

### `hailortcli fw-control identify` 失败，显示 `HAILO_OPEN_FILE_FAILURE`

→ 驱动程序或设备节点问题。检查 `lsmod | grep hailo1x` 中 `hailo1x_pci` 是否加载，`ls /dev/h1x-0` 是否存在。如果两者都缺少，请重新执行 §2 并重新启动。

### LLM/VLM 加载时出现 `HAILO_OUT_OF_HOST_MEMORY` / Pi 冻结

→ CMA 不足。检查 `grep CmaTotal /proc/meminfo` 是否有 256 MB (§5)。由于 `VDevice.release()` 不会返回 CMA，在重复切换多个模型后可能需要重新启动进程。

### `HAILO_OUT_OF_PHYSICAL_DEVICES(74)`

→ 其他进程占用 VDevice。使用 `lsof /dev/h1x-0` 特定犯人 (典型情况是 `hailo-ollama` 或 Ctrl+C 没有正确终止的上一个进程)，然后 `kill` 并重新启动。

### Python 已升级为 3.14，与 wheel 不兼容

→ 本存储库已在 `pyproject.toml` 中固定为 `requires-python = ">=3.13,<3.14"`。clone 后的第一个 `uv sync` 会选择 3.13.x。如果手动写入了 `.python-version = 3.14`，请改回去。

---

## 9. 相关文件

- [`docs/ja/hailo/README.md`](../../hailo/README.md) — Hailo-10H 开发文件目录
- [`docs/ja/hailo/HAILORT_5_3_0_MIGRATION.md`](../../hailo/HAILORT_5_3_0_MIGRATION.md) — HailoRT 5.2.0 → 5.3.0 迁移说明
- [`docs/ja/hailo/PI5_NUMA_CMA_CONSTRAINTS.md`](../../hailo/PI5_NUMA_CMA_CONSTRAINTS.md) — Pi 5 的 CMA 限制详细信息
- [`scripts/install_hailo.py`](../../../../scripts/install_hailo.py) — wheel 自动检测脚本本体
