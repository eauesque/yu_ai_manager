# Pi 5 上 `numa=fake=8` 下的 CMA 限制

在运行 Hailo-10H 工作负载的 Raspberry Pi 5（8 GB）上，关于 CMA 分配的实用经验总结。
本文记录 `cma=` 的上限、超过 512M 会静默失败的原因，以及显示驱动占用的 CMA 应如何回收。

**目标读者**：在 Raspberry Pi 5 上运行 Hailo GenAI 模型（LLM、Speech2Text）的开发者
（使用 AI HAT / AI HAT+）。

---

## ⚠️ 2026-05 firmware 回归注意事项

**自 2026-05-13 发布的 `raspi-firmware 1:1.20260513-1` + `pieeprom-2026-05-11` 起**，在 `/boot/firmware/cmdline.txt` 中写入 `cma=`（无论大小）都会导致 VC firmware mailbox 完全沉默（`vcgencmd ioctl_set_msg failed:-1`、`raspberrypi-clk -22`、HEVC `-517`、cpufreq sysfs 缺失）。

**自 2026-05-16 起确定的推荐方法**：不再使用 cmdline 的 `cma=`，而是在 `/boot/firmware/config.txt` 中写入 `dtoverlay=cma,cma-512`。该方式通过 DT 的 `linux,cma` reserved memory node 进行分配，不会与新 firmware 冲突。详情参见 §6 与 [`docs/development/investigations/pi5_firmware_cma_mailbox_regression_2026-05-16.md`](../../development/investigations/pi5_firmware_cma_mailbox_regression_2026-05-16.md)。

以下的旧记述（推荐 cmdline `cma=512M`）为 2026-04-15 时点的验证结果。基于 NUMA 节点边界得出的上限值（512M）这一发现依旧有效，但**设置位置已从 cmdline 迁移至 config.txt 的 overlay 参数**。

---

## TL;DR

- **设置位置为 `config.txt` 中的 `dtoverlay=cma,cma-512`**（2026-05-16 确定。cmdline 的 `cma=` 会在新 firmware 上破坏 mailbox）
- `cma-1024` 与 `cma-768` 在 Pi 5（8 GB）上会**静默失败** —— `CmaTotal` 变为 0，既无内核 panic 也无警告（源于 NUMA 节点边界的上限，推测通过 overlay 设置时该限制依然存在）
- **`cma-512` 是已确认的上限值，也是推荐值**（2026-05-16 通过 overlay 方式在 Pi 5 8 GB 上重新验证，确认分配到 `CmaTotal: 524288 kB`）
- 根本原因：默认的 Pi 5 内核应用了 `numa=fake=8`，将连续分配限制在 1 个 NUMA 节点（1 GB）以内
- **`dtoverlay=vc4-kms-v3d` + `max_framebuffers=2` 在启动时会消耗约 157 MB 的 CMA** —— 即使 DRM 驱动初始化失败也是如此（2026-04-15 验证）
- **`camera_auto_detect=1`** 会加载 `pisp_be` 与 `videobuf2_dma_contig`，并消耗额外的 CMA。无头（headless）系统建议禁用
- **无头优化后的基线**（两个 overlay 均禁用）：启动时使用约 98 MB CMA，可供 Hailo 模型使用的空间约 414 MB
- **YOLO InferModel 使用 0 MB CMA**（2026-04-15 确认）——只有 GenAI 模型（LLM、Speech2Text）会从 CMA 分配
- LLM（qwen2.5-1.5b）+ Whisper-base 同时加载：合计约 328 MB —— 仍在无头优化基线之内
- CMA 不会在服务器重启时被回收 —— 只有完整系统重启（PCIe 电源重新上电）才能释放（`hailo1x_pci` 驱动缺陷，已向 Hailo 报告）
- 将 VDevice 视为**进程生命周期内的单例**对待，禁止驱逐/重新加载

---

## 1. 症状

在 `/boot/firmware/cmdline.txt` 中设置 `cma=1G`（或 `cma=768M`）后重启，会出现如下情况：

```
$ grep CmaTotal /proc/meminfo
CmaTotal:              0 kB
```

系统正常启动，既无内核 panic 也无错误信息。`cmdline.txt` 中的 CMA 设置会被**静默忽略**，依赖 CMA 的组件（Hailo-10H NPU、V4L2 摄像头等）会初始化失败。

**每次修改 `cmdline.txt` 后都务必验证 CMA 分配：**

```bash
grep CmaTotal /proc/meminfo
```

---

## 2. 根本原因：`numa=fake=8` 节点边界

Pi 5 默认的 Raspberry Pi OS 内核应用了 `numa=fake=8`，将 8 GB 物理内存划分为**各 1 GB 的 8 个虚拟 NUMA 节点**：

```
numa=fake=8 physical memory layout (8 GB total):

┌──────┬──────┬──────┬──────┬──────┬──────┬──────┬──────┐
│ 1GB  │ 1GB  │ 1GB  │ 1GB  │ 1GB  │ 1GB  │ 1GB  │ 1GB  │
│node0 │node1 │node2 │node3 │node4 │node5 │node6 │node7 │
└──────┴──────┴──────┴──────┴──────┴──────┴──────┴──────┘
```

Linux CMA（`cma_init_reserved_mem`）在启动时必须作为**不跨越 NUMA 节点边界的连续物理内存**分配。
这就带来了「1 个节点 = 1 GB」的硬性上限。由于内核自身也会占用同一节点的内存，因此无法恰好预留满 1 GB：

> **以下表格是基于 2026-04-15 时点 cmdline 方式的测量记录。**
> 源于 NUMA 节点边界的上限值（512M）这一发现目前仍然有效，但**现在不得使用 cmdline 的 `cma=`**（参见开头的 firmware 回归说明）。
> 当前的设置方法为 `config.txt` 中的 `dtoverlay=cma,cma-512`（§6）。

| `cmdline.txt` 设置（2026-04-15 时点的记录） | 结果 |
|---|---|
| `cma=1G` | 试图占满整个节点，内核没有余地 → **静默失败**，CmaTotal=0 |
| `cma=768M` | 超出可信的连续范围 → **静默失败**，CmaTotal=0（2026-04-15 验证） |
| `cma=512M` | 占 1 个节点的一半 → **确认稳定** ✓（2026-04-15 验证） ← 当时的推荐。**现在应使用 `dtoverlay=cma,cma-512`** |
| `cma=384M` | 未验证（已确认 512M 可用，无需 384M） |
| `cma=256M` | 稳定，但 LLM + Whisper 同时使用时会比较紧张 |
| `cma=128M` | 稳定，但对 Hailo GenAI 而言不足（仅 LLM 就需要约 234 MB） |

### 失败为何是静默的

`cma_init_reserved_mem` 在分配失败时不会 panic。内核会以 `CmaTotal=0` 启动，表现得如同从未请求过 CMA 一样。
写入 `cmdline.txt` 的数值实际上被完全忽略。

---

## 3. Hailo-10H 的 CMA 需求

在 Raspberry Pi 5、AI HAT+、HailoRT 5.3.0 环境下测得：

| 模型 / 组合 | CMA 使用量 | 备注 |
|---|---|---|
| LLM — qwen2.5-1.5b-chat（单独） | **约 234 MB** | 2026-04-15 测得 |
| YOLO InferModel（yolov8n，configure + bindings） | **0 MB** | 2026-04-15 确认 |
| Whisper-tiny（单独） | 约 70 MB | 估算 |
| Whisper-base（单独） | 约 100 MB | 估算 |
| Whisper-small（单独） | 约 150 MB | 估算 |
| **LLM + Whisper-tiny（同时）** | **约 246 MB** | 在 CMA 256 MB 下测得 |
| **LLM + Whisper-base（同时）** | **约 334 MB** | 估算。预期仍在无头基线之内 |

**YOLO 使用 0 MB CMA**：在 HailoRT 5.3.0 中，YOLO InferModel、`configure()`、`create_bindings()` 完全不会分配 CMA。
输入/输出 DMA 缓冲区并非来自 CMA，而是通过 `set_buffer()` 从预先分配好的 numpy 数组映射而来。
因此 YOLO 不属于 CMA 预算计算的考虑因素。

在应用 CMA 512 MB 与无头优化（参见 §5）后，预期以下组合可以正常工作：

- 仅 LLM（约 234 MB，约 180 MB 余量）
- 仅 Whisper-tiny / Whisper-base（轻松容纳）
- LLM + Whisper-base 同时使用（合计约 334 MB，约 80 MB 余量）

Whisper-small 与 LLM 的组合（估算约 384 MB）已接近理论极限 —— 在信任该结果之前请以实测确认。

同时加载测试的详细结果参见 [hailo_genai_concurrent_2026-04-15.md](../../development/investigations/hailo_genai_concurrent_2026-04-15.md)。

---

## 4. CMA 在完整重启之前不会被回收

由 HailoRT 分配的 CMA 会一直保留在内存中，直至完整系统重启为止。
无论是 `VDevice.release()`、服务器进程终止，还是内核模块重新加载，都不会改变这一点。

**根本原因**（2026-04-15 确认）：`hailo1x_pci` 即使在设备 fd 被关闭或模块被重新加载之后，仍然保留 DMA coherent 分配。
只有完整重启（PCIe 电源重新上电）才能释放。该缺陷已向 Hailo 报告。

| 阶段 | CmaFree（CMA 512 MB，无头优化后） |
|---|---|
| 启动 | **约 426 MB** |
| LLM 加载后（约 234 MB） | 约 192 MB |
| Whisper-base 加载后（约 100 MB） | 约 92 MB |
| `VDevice.release()` 后 | 约 92 MB（**不会归还**） |
| 服务器进程终止后 | 约 92 MB（**不会归还**） |
| `rmmod hailo1x_pci && modprobe hailo1x_pci` 后 | 约 92 MB（**不会归还**） |
| 完整系统重启后 | **约 426 MB（恢复）** |

**含义**：在同一次启动会话中，CMA 消耗会跨服务器重启持续累积。
不要指望服务器重启能回收 CMA。请将 VDevice 设计为**进程生命周期内的单例**。
当 CMA 耗尽时，只有完整系统重启才能使其恢复。

---

## 5. 无头优化：`/boot/firmware/config.txt`

默认的 Pi OS `config.txt` 中包含两项设置，即使在无头（无显示器）系统上也会消耗大量 CMA。

### 5.1 `dtoverlay=vc4-kms-v3d` 与 `max_framebuffers=2`

**影响**：Pi 5 firmware 会在启动时为显示管线预先分配 CMA 帧缓冲区。
在 `max_framebuffers=2` 的情况下，这会在**用户空间进程运行之前**就消耗约 157 MB 的 CMA。

即使 Linux DRM 驱动之后初始化失败（例如出现 `[drm] Couldn't stop firmware display driver: -22` 或 `dmesg` 中的 `Couldn't get core clock`），该分配依然会持续存在。

| `config.txt` 状态 | 启动时 CmaFree |
|---|---|
| `dtoverlay=vc4-kms-v3d` + `max_framebuffers=2` 启用（默认） | **约 257 MB** |
| 两者均注释掉 | **约 305 MB**（+约 48 MB） |

**修复方法**（无头 / 服务器模式）：

```ini
# /boot/firmware/config.txt
#dtoverlay=vc4-kms-v3d
#max_framebuffers=2
```

**权衡**：硬件加速显示与 3D（V3D）需要 `vc4-kms-v3d`。
如果系统仅通过 SSH 或 Web 界面访问，禁用它是安全的。

### 5.2 `camera_auto_detect=1` 与 `display_auto_detect=1`

**影响**：这些 overlay 会在启动时探测 CSI 摄像头与 DSI 显示屏，并加载 `pisp_be`（Pi ISP 后端）与 `videobuf2_dma_contig`。
被加载的模块以及检测到的硬件会各自预先分配额外的 CMA。

| `config.txt` 状态 | 启动时 CmaFree |
|---|---|
| `camera_auto_detect=1` + `display_auto_detect=1` | 约 305 MB（禁用 vc4 之后） |
| 两者均设为 0 | **约 426 MB**（+约 121 MB） |

**修复方法**：

```ini
camera_auto_detect=0
display_auto_detect=0
```

**备注**：`camera_auto_detect=0` 只影响 CSI 摄像头。USB 摄像头（UVC / `uvcvideo`）不受影响，仍可正常工作。

### 5.3 面向无头 AI HAT+ 用途的推荐最小 `config.txt`

```ini
auto_initramfs=1
arm_64bit=1
arm_boost=1

[cm5]
dtoverlay=dwc2,dr_mode=host

[all]
dtparam=pciex1_gen=3
```

在此配置下，启动时的 CMA 估算值：**约使用 98 MB**，可供 Hailo 模型使用的空间约 414 MB。

### 5.4 CMA 预算汇总（CMA 512 MB，无头优化后）

| 配置 | CmaFree | 可供 Hailo 使用 |
|---|---|---|
| 默认（vc4-kms-v3d + 摄像头启用） | 约 257 MB | 约 257 MB |
| 禁用 vc4-kms-v3d + max_framebuffers | 约 305 MB | 约 305 MB |
| + camera/display_auto_detect=0 | **约 426 MB** | **约 426 MB** |
| LLM 加载后（约 234 MB） | 约 192 MB | 供 Whisper 使用 |
| LLM + Whisper-base 加载后（约 100 MB） | 约 92 MB | （余量） |

---

## 6. 推荐配置

### 设置 `dtoverlay=cma,cma-512`（2026-05-16 确定）

```bash
# 确认当前 CMA 状态
grep CmaTotal /proc/meminfo

# 1) 从 cmdline.txt 中删除现有的 cma=（因为它会在新 firmware 上破坏 mailbox）
sudo sed -i 's/ *cma=[^ ]*//g' /boot/firmware/cmdline.txt

# 2) 在 config.txt 的 [all] 段中追加 dtoverlay=cma,cma-512
sudo sed -i '/^\[all\]$/a dtoverlay=cma,cma-512' /boot/firmware/config.txt

# 3) 建议冷重启（拔插电源）
sudo sync && sudo poweroff

# 重启后验证（必须确认全部 4 项）
vcgencmd version                                # 必须有 Broadcom 响应（沉默即为失败）
grep CmaTotal /proc/meminfo                     # 期望 524288 kB
journalctl -b -k | grep 'linux,cma'             # 应出现 initialized node linux,cma
journalctl -b -k | grep '0x00030087'            # 不应出现
```

若 dmesg 中出现 `OF: reserved mem: initialized node linux,cma, compatible id shared-dma-pool`，即为通过 DT 路径分配成功的证据。
反之，若出现 `Reserved memory: bypass linux,cma node, using cmdline CMA params instead`，说明 cmdline 中仍残留 `cma=`，需要删除。

### 若要启用 `vc4-kms-v3d`

如需 KMS DRM 显示，可以整合到 overlay 参数中：
```ini
dtoverlay=vc4-kms-v3d,cma-512
```
但如 §5.1 所述，vc4-kms-v3d 会占用约 157 MB 的 CMA，因此在 Hailo GenAI 用途下建议禁用。

### 每次内核 / firmware / 配置变更后都要验证

对 `/boot/firmware/cmdline.txt` 或 `config.txt` 的修改，以及内核/firmware 升级后，CMA 状态与 mailbox 响应都可能悄然改变。
请将上述 4 项验证纳入重启后的例行流程。

---

## 7. 与其他 `numa=fake=8` 问题的相互影响

`numa=fake=8` 在本项目中至少引发了两个不同的问题：

| 问题 | 症状 | 根本原因 |
|---|---|---|
| CMA 静默失败 | 设置 `cma=1G`、`cma=768M` 后出现 `CmaTotal=0` | NUMA 节点边界限制了连续分配 |
| Node.js 安装失败 | npm/node 安装程序因内存错误而中止 | 每个 NUMA 节点的内存（1 GB）被误判为总 RAM。已作为 [anthropics/claude-code#33864](https://github.com/anthropics/claude-code/issues/33864) 向上游报告 |
| `vc4-kms-v3d` 消耗 CMA | 启动时消耗约 157 MB，即使 DRM 初始化失败也不会归还 | `max_framebuffers=2` 会让 firmware 预留 CMA 帧缓冲区，发生在 Linux 驱动启动之前 |

静默失败与 vc4 消耗均源于同一根本限制（低 4 GB DMA 区域、NUMA 节点边界）。
如遇到意外的内存相关故障，请首先检查 `/proc/meminfo` 与 `config.txt`。

---

## 8. 快速诊断清单

```bash
# 1. mailbox 响应（新 firmware 下须优先确认）
vcgencmd version                     # 沉默则怀疑 cmdline 中仍残留 cma=

# 2. 确认 CMA 分配
grep CmaTotal /proc/meminfo          # 0 kB = 静默失败

# 3. 确认 DT 路径 vs cmdline 路径
journalctl -b -k | grep 'linux,cma'
# 期望："initialized node linux,cma, compatible id shared-dma-pool"（DT 路径 = 正常）
# 异常："bypass linux,cma node, using cmdline CMA params instead"（cmdline 残留）

# 4. 确认 NUMA 拓扑
numactl --hardware                   # 显示节点数与各节点内存

# 5. 确认当前命令行与 overlay 设置
cat /boot/firmware/cmdline.txt       # 确认不包含 cma=
grep '^dtoverlay=cma' /boot/firmware/config.txt   # 确认存在 dtoverlay=cma,cma-512

# 6. 确认 Hailo 设备可用性
ls /dev/h1x-*                        # HailoRT 5.3.0: /dev/h1x-0
hailortcli fw-control identify       # 确认 NPU 可访问

# 7. 检查 config.txt 中的 CMA 消耗方
grep -E 'vc4-kms-v3d|camera_auto_detect|display_auto_detect|max_framebuffers' \
  /boot/firmware/config.txt

# 8. 确认已加载的内核模块（CMA 使用者）
lsmod | grep -E 'vc4|v3d|pisp|videobuf2_dma'
```

---

**验证环境**：Raspberry Pi 5 8 GB、Raspberry Pi OS
（Linux 6.12.62+rpt-rpi-2712、aarch64）、HailoRT 5.3.0、AI HAT+、CMA=512M
（**2026-05-16 重新验证**：Linux 6.18.29+rpt-rpi-2712 / raspi-firmware 1:1.20260513-1 / pieeprom-2026-05-11 / Hailo-10H AI HAT，通过 `dtoverlay=cma,cma-512` 分配到 524288 kB，mailbox 响应确认正常）
