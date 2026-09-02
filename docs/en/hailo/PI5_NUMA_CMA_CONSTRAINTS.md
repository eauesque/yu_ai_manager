# CMA Constraints Under `numa=fake=8` on Pi 5

Practical findings on CMA allocation on a Raspberry Pi 5 (8 GB) when running Hailo-10H workloads.
This document covers the `cma=` ceiling, why values above 512M fail silently, and how to recover
CMA consumed by the display driver.

**Audience**: developers running Hailo GenAI models (LLM, Speech2Text) on a Raspberry Pi 5
(with AI HAT / AI HAT+).

---

## ⚠️ 2026-05 firmware regression warning

**As of the 2026-05-13 release of `raspi-firmware 1:1.20260513-1` + `pieeprom-2026-05-11`**, writing `cma=` to `/boot/firmware/cmdline.txt` — regardless of size — silences the VC firmware mailbox completely (`vcgencmd ioctl_set_msg failed:-1`, `raspberrypi-clk -22`, HEVC `-517`, missing cpufreq sysfs).

**Confirmed recommended method as of 2026-05-16**: instead of cmdline `cma=`, write `dtoverlay=cma,cma-512` to `/boot/firmware/config.txt`. This is reserved via the DT `linux,cma` reserved memory node, so it does not conflict with the new firmware. See §6 and [`docs/development/investigations/pi5_firmware_cma_mailbox_regression_2026-05-16.md`](../../development/investigations/pi5_firmware_cma_mailbox_regression_2026-05-16.md) for details.

The older description below (recommending cmdline `cma=512M`) reflects verification results as of 2026-04-15. The finding about the ceiling value (512M) imposed by the NUMA node boundary remains valid, but **the place to set it has moved from cmdline to the overlay argument in config.txt**.

---

## TL;DR

- **Set it via `dtoverlay=cma,cma-512` in `config.txt`** (confirmed 2026-05-16; cmdline `cma=` breaks the mailbox on the new firmware)
- `cma-1024` and `cma-768` **fail silently** on Pi 5 (8 GB) — `CmaTotal` becomes 0, with no kernel panic or warning (ceiling caused by the NUMA node boundary; the same constraint is presumed to remain via the overlay path)
- **`cma-512` is the confirmed ceiling and the recommended value** (re-verified via the overlay on Pi 5 8 GB on 2026-05-16; `CmaTotal: 524288 kB` confirmed allocated)
- Root cause: the default Pi 5 kernel applies `numa=fake=8`, which restricts contiguous allocation to a single NUMA node (1 GB)
- **`dtoverlay=vc4-kms-v3d` + `max_framebuffers=2` consume ~157 MB of CMA at boot** — even when the DRM driver fails to initialize (verified 2026-04-15)
- **`camera_auto_detect=1`** loads `pisp_be` and `videobuf2_dma_contig`, consuming additional CMA. Recommended to disable on headless systems
- **Headless-optimized baseline** (both overlays disabled): ~98 MB of CMA used at boot, leaving ~414 MB free for Hailo models
- **YOLO InferModel uses 0 MB of CMA** (confirmed 2026-04-15) — only GenAI models (LLM, Speech2Text) allocate from CMA
- LLM (qwen2.5-1.5b) + Whisper-base loaded simultaneously: ~328 MB total — fits within the headless-optimized baseline
- CMA is not reclaimed by a server restart — it is only released by a full system reboot (PCIe power cycle) (`hailo1x_pci` driver bug, reported to Hailo)
- Treat VDevice as a **process-lifetime singleton**. Do not evict/reload it

---

## 1. Symptom

If you set `cma=1G` (or `cma=768M`) in `/boot/firmware/cmdline.txt` and reboot, you get the following:

```
$ grep CmaTotal /proc/meminfo
CmaTotal:              0 kB
```

The system boots normally. There is no kernel panic or error message. The CMA setting in `cmdline.txt` is **silently ignored**, and anything that depends on CMA (Hailo-10H NPU, V4L2 camera, etc.) fails to initialize.

**Always verify CMA allocation after changing `cmdline.txt`:**

```bash
grep CmaTotal /proc/meminfo
```

---

## 2. Root cause: the `numa=fake=8` node boundary

The default Raspberry Pi OS kernel for Pi 5 applies `numa=fake=8`, splitting the 8 GB of physical memory into **eight virtual NUMA nodes of 1 GB each**:

```
numa=fake=8 physical memory layout (8 GB total):

┌──────┬──────┬──────┬──────┬──────┬──────┬──────┬──────┐
│ 1GB  │ 1GB  │ 1GB  │ 1GB  │ 1GB  │ 1GB  │ 1GB  │ 1GB  │
│node0 │node1 │node2 │node3 │node4 │node5 │node6 │node7 │
└──────┴──────┴──────┴──────┴──────┴──────┴──────┴──────┘
```

Linux CMA (`cma_init_reserved_mem`) must be allocated at boot as **contiguous physical memory that does not cross a NUMA node boundary**.
This imposes a strict ceiling of 1 GB per node. Because the kernel itself occupies memory on the same node, it is not possible to reserve exactly 1 GB:

> **The table below is a measurement record under the cmdline-based approach as of 2026-04-15.**
> The finding about the ceiling value (512M) imposed by the NUMA node boundary remains valid, but **cmdline `cma=` must not be used now** (see the firmware regression note at the top of this document).
> The current configuration method is `dtoverlay=cma,cma-512` in `config.txt` (§6).

| `cmdline.txt` setting (record as of 2026-04-15) | Result |
|---|---|
| `cma=1G` | Attempts to consume the entire node. No room left for the kernel → **silent failure**, CmaTotal=0 |
| `cma=768M` | Exceeds the reliable contiguous range → **silent failure**, CmaTotal=0 (verified 2026-04-15) |
| `cma=512M` | Half of one node → **confirmed stable** ✓ (verified 2026-04-15) ← the recommendation at that time. **Use `dtoverlay=cma,cma-512` now** |
| `cma=384M` | Untested (512M is confirmed; 384M is unnecessary) |
| `cma=256M` | Stable, but tight when using LLM + Whisper simultaneously |
| `cma=128M` | Stable, but insufficient for Hailo GenAI (LLM alone needs ~234 MB) |

### Why the failure is silent

`cma_init_reserved_mem` does not panic on allocation failure. The kernel boots with `CmaTotal=0` and behaves as if CMA had never been requested.
The value written to `cmdline.txt` is effectively ignored.

---

## 3. Hailo-10H CMA requirements

Measured on Raspberry Pi 5, AI HAT+, HailoRT 5.3.0:

| Model / combination | CMA usage | Note |
|---|---|---|
| LLM — qwen2.5-1.5b-chat (alone) | **~234 MB** | measured 2026-04-15 |
| YOLO InferModel (yolov8n, configure + bindings) | **0 MB** | confirmed 2026-04-15 |
| Whisper-tiny (alone) | ~70 MB | estimated |
| Whisper-base (alone) | ~100 MB | estimated |
| Whisper-small (alone) | ~150 MB | estimated |
| **LLM + Whisper-tiny (concurrent)** | **~246 MB** | measured at CMA 256 MB |
| **LLM + Whisper-base (concurrent)** | **~334 MB** | estimated; expected to fit within the headless baseline |

**YOLO uses 0 MB of CMA**: on HailoRT 5.3.0, YOLO InferModel, `configure()`, and `create_bindings()` allocate no CMA at all.
Input/output DMA buffers are mapped from pre-allocated numpy arrays via `set_buffer()`, not from CMA.
YOLO is therefore not a factor in CMA budget calculations.

With CMA 512 MB and headless optimisation applied (see §5), the following configurations are expected to work:

- LLM only (~234 MB, ~180 MB headroom)
- Whisper-tiny / Whisper-base only (comfortably fits)
- LLM + Whisper-base concurrently (~334 MB total, ~80 MB headroom)

The combination of Whisper-small and LLM (estimated ~384 MB) approaches the theoretical limit — confirm with an actual measurement before relying on it.

See [hailo_genai_concurrent_2026-04-15.md](../../development/investigations/hailo_genai_concurrent_2026-04-15.md) for concurrent-load test results in detail.

---

## 4. CMA is not reclaimed until a full reboot

CMA allocated by HailoRT stays resident in memory until a full system reboot.
This holds regardless of `VDevice.release()`, the server process exiting, or a kernel module reload.

**Root cause** (confirmed 2026-04-15): `hailo1x_pci` retains DMA-coherent allocations even after the device fd is closed or the module is reloaded.
It is only released by a full reboot (PCIe power cycle). The bug has been reported to Hailo.

| Phase | CmaFree (CMA 512 MB, headless optimisation) |
|---|---|
| Boot | **~426 MB** |
| After loading LLM (~234 MB) | ~192 MB |
| After loading Whisper-base (~100 MB) | ~92 MB |
| After `VDevice.release()` | ~92 MB (**not returned**) |
| After the server process exits | ~92 MB (**not returned**) |
| After `rmmod hailo1x_pci && modprobe hailo1x_pci` | ~92 MB (**not returned**) |
| After a full system reboot | **~426 MB (restored)** |

**Implication**: CMA consumption accumulates across server restarts within the same boot session.
Do not expect a server restart to reclaim CMA. Design VDevice as a **process-lifetime singleton**.
If CMA becomes exhausted, only a full system reboot restores it.

---

## 5. Headless optimization: `/boot/firmware/config.txt`

The default Pi OS `config.txt` includes two settings that consume a large amount of CMA even on a headless (display-less) system.

### 5.1 `dtoverlay=vc4-kms-v3d` and `max_framebuffers=2`

**Effect**: the Pi 5 firmware pre-allocates CMA framebuffers for the display pipeline at boot.
With `max_framebuffers=2`, this consumes ~157 MB of CMA **before any userspace process runs**.

The allocation persists even if the Linux DRM driver later fails to initialize (e.g. `[drm] Couldn't stop firmware display driver: -22` or `Couldn't get core clock` in `dmesg`).

| `config.txt` state | CmaFree at boot |
|---|---|
| `dtoverlay=vc4-kms-v3d` + `max_framebuffers=2` enabled (default) | **~257 MB** |
| Both commented out | **~305 MB** (+~48 MB) |

**Fix** (headless / server mode):

```ini
# /boot/firmware/config.txt
#dtoverlay=vc4-kms-v3d
#max_framebuffers=2
```

**Trade-off**: `vc4-kms-v3d` is required for hardware-accelerated display and 3D (V3D).
If the system is only accessed via SSH or a web interface, disabling it is safe.

### 5.2 `camera_auto_detect=1` and `display_auto_detect=1`

**Effect**: these overlays probe for CSI cameras and DSI displays at boot and load `pisp_be` (the Pi ISP backend) and `videobuf2_dma_contig`.
The loaded modules and any detected hardware pre-allocate additional CMA.

| `config.txt` state | CmaFree at boot |
|---|---|
| `camera_auto_detect=1` + `display_auto_detect=1` | ~305 MB (after disabling vc4) |
| Both set to 0 | **~426 MB** (+~121 MB) |

**Fix**:

```ini
camera_auto_detect=0
display_auto_detect=0
```

**Note**: `camera_auto_detect=0` only affects CSI cameras. USB cameras (UVC / `uvcvideo`) are unaffected and continue to work normally.

### 5.3 Recommended minimal `config.txt` for headless AI HAT+ use

```ini
auto_initramfs=1
arm_64bit=1
arm_boost=1

[cm5]
dtoverlay=dwc2,dr_mode=host

[all]
dtparam=pciex1_gen=3
```

Estimated CMA usage at boot with this configuration: **~98 MB used**, ~414 MB free for Hailo models.

### 5.4 CMA budget summary (CMA 512 MB, headless optimisation)

| Configuration | CmaFree | Available for Hailo |
|---|---|---|
| Default (vc4-kms-v3d + camera enabled) | ~257 MB | ~257 MB |
| vc4-kms-v3d + max_framebuffers disabled | ~305 MB | ~305 MB |
| + camera/display_auto_detect=0 | **~426 MB** | **~426 MB** |
| After loading LLM (~234 MB) | ~192 MB | for Whisper |
| After loading LLM + Whisper-base (~100 MB) | ~92 MB | (headroom) |

---

## 6. Recommended configuration

### Set `dtoverlay=cma,cma-512` (confirmed 2026-05-16)

```bash
# Check the current CMA state
grep CmaTotal /proc/meminfo

# 1) Remove any existing cma= from cmdline.txt (it breaks the mailbox on the new firmware)
sudo sed -i 's/ *cma=[^ ]*//g' /boot/firmware/cmdline.txt

# 2) Append dtoverlay=cma,cma-512 to the [all] section of config.txt
sudo sed -i '/^\[all\]$/a dtoverlay=cma,cma-512' /boot/firmware/config.txt

# 3) A cold reboot is recommended (unplug/replug power)
sudo sync && sudo poweroff

# Verify after reboot (check all 4 items)
vcgencmd version                                # must get a Broadcom response (silence = failure)
grep CmaTotal /proc/meminfo                     # expect 524288 kB
journalctl -b -k | grep 'linux,cma'             # should show "initialized node linux,cma"
journalctl -b -k | grep '0x00030087'            # should show nothing
```

If `OF: reserved mem: initialized node linux,cma, compatible id shared-dma-pool` appears in dmesg, this is evidence that allocation went through the DT path.
Conversely, if `Reserved memory: bypass linux,cma node, using cmdline CMA params instead` appears, `cma=` is still present in cmdline and must be removed.

### If you want to enable `vc4-kms-v3d`

If display KMS DRM is needed, it can be combined in the overlay argument form:
```ini
dtoverlay=vc4-kms-v3d,cma-512
```
However, as noted in §5.1, vc4-kms-v3d consumes ~157 MB of CMA, so disabling it is recommended for Hailo GenAI use.

### Verify after every kernel / firmware / config change

Changes to `/boot/firmware/cmdline.txt` or `config.txt`, or kernel/firmware upgrades, can silently change the CMA state and mailbox responsiveness.
Make the 4-item verification above a routine step after every reboot.

---

## 7. Interaction with other `numa=fake=8` issues

`numa=fake=8` causes at least two other distinct issues relevant to this project:

| Issue | Symptom | Root cause |
|---|---|---|
| CMA silent failure | `CmaTotal=0` after `cma=1G`, `cma=768M` | NUMA node boundary restricts contiguous allocation |
| Node.js install failure | npm/node installer aborts with a memory error | Per-NUMA-node memory (1 GB) is misdetected as total RAM. Reported upstream as [anthropics/claude-code#33864](https://github.com/anthropics/claude-code/issues/33864) |
| `vc4-kms-v3d` CMA drain | ~157 MB consumed at boot; not returned even if DRM init fails | `max_framebuffers=2` causes the firmware to reserve CMA framebuffers before the Linux driver starts |

Both the silent failure and the vc4 drain stem from the same underlying constraint (the low-4GB DMA zone, NUMA node boundaries).
If you encounter an unexpected memory-related failure, check `/proc/meminfo` and `config.txt` first.

---

## 8. Quick diagnostic checklist

```bash
# 1. Mailbox response (check this first on the new firmware)
vcgencmd version                     # silence suggests cma= is still present in cmdline

# 2. Check CMA allocation
grep CmaTotal /proc/meminfo          # 0 kB = silent failure

# 3. Check whether the DT path or the cmdline path was used
journalctl -b -k | grep 'linux,cma'
# expected: "initialized node linux,cma, compatible id shared-dma-pool" (DT path = normal)
# bad:      "bypass linux,cma node, using cmdline CMA params instead" (cmdline leftover)

# 4. Check NUMA topology
numactl --hardware                   # shows node count and per-node memory

# 5. Check the current cmdline and overlay settings
cat /boot/firmware/cmdline.txt       # confirm cma= is not present
grep '^dtoverlay=cma' /boot/firmware/config.txt   # confirm dtoverlay=cma,cma-512 is present

# 6. Check Hailo device availability
ls /dev/h1x-*                        # HailoRT 5.3.0: /dev/h1x-0
hailortcli fw-control identify       # confirm the NPU is accessible

# 7. Check config.txt for CMA consumers
grep -E 'vc4-kms-v3d|camera_auto_detect|display_auto_detect|max_framebuffers' \
  /boot/firmware/config.txt

# 8. Check loaded kernel modules (CMA users)
lsmod | grep -E 'vc4|v3d|pisp|videobuf2_dma'
```

---

**Verification environment**: Raspberry Pi 5 8 GB, Raspberry Pi OS
(Linux 6.12.62+rpt-rpi-2712, aarch64), HailoRT 5.3.0, AI HAT+, CMA=512M
(**re-verified 2026-05-16**: Linux 6.18.29+rpt-rpi-2712 / raspi-firmware 1:1.20260513-1 / pieeprom-2026-05-11 / Hailo-10H AI HAT — confirmed 524288 kB allocated via `dtoverlay=cma,cma-512`, mailbox response verified)
