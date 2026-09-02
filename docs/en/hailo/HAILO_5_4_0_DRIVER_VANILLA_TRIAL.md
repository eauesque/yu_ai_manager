# HailoRT / driver 5.4.0 CMA Non-Reclaim Verdict Correction and Verification Record

Created: 2026-08-16 / Last updated: 2026-08-17 / Corresponding version: yu_ai_manager 4.623.1

A record of hypothesis testing and an A/B trial between the official vanilla build and the `FOLL_LONGTERM`-fixed build on `hailo-ai/hailort-drivers` v5.4.0 (published 2026-08-16, GPL-2.0, source available), regarding the phenomenon previously judged as "CMA not reclaimed" (see `docs/development/development_docs/HAILO_FORUM_FOLLOWUP_CMA_INFERENCE_LEAK.md`), correcting a misjudgment on the measurement side.

---

## 1. Conclusion

**2026-08-17 final retest (4th round): the `VERDICT: FAIL` results up through the 3rd round were a misjudgment caused by using only the absolute `CmaFree` recovery amount after the first HEF load as the leak criterion. An A/B comparison of the official vanilla 5.4.0 build and the `FOLL_LONGTERM`-fixed build showed that consecutive loading from a low `CmaFree` state, release-and-reload within the same process, 20 generations, and a full repeat of the trials from an even lower `CmaFree` state all succeeded. There was no monotonic increase or decrease in RSS or `CmaFree` during generation, and CMA allocation failures were 0. The initial `CmaFree` drop corresponded to increased page-cache usage from the multi-GB HEF, and `MemAvailable` remained at approximately 7 GB. Under the conditions tested this time — Pi 5 + Hailo-10H + HailoRT/driver 5.4.0, single model, single device, short-duration repetition — no practically significant CMA leak was reproduced, and no measurable improvement was seen from the `FOLL_LONGTERM` fix either. Long-running continuous operation, simultaneous use of multiple models, Hailo-8, and operation under IOMMU were not tested, and this conclusion is out of scope for those.**

### 1.1 History of the Verdict

| Round | Date | Verdict at the time | Basis for update / correction |
|---|---|---|---|
| 1st | 2026-08-16 | Undeterminable | Upgrading only the driver to 5.4.0 caused the API to be rejected by the exact-match check against library 5.3.0 (§3) |
| 2nd | 2026-08-17 | Only limited trials completed | Driver / library / firmware aligned to 5.4.0, and while `run2` repetitions plateaued, direct repro via pyhailort had not yet been run (§4) |
| 3rd | 2026-08-17 | Provisional `FAIL` (later found to be a misjudgment) | Old diagnostic result that judged only the absolute `CmaFree` recovery amount after the first HEF load. A single-shot measurement could not distinguish memory loss from page-cache usage (§5, §7) |
| 4th | 2026-08-17 | No practical leak reproduced | Corrected the 3rd-round verdict by measuring vanilla / `FOLL_LONGTERM` A/B, low-CMA repetition, same-process reload, 20 generations, RSS, `MemAvailable`, and allocation failures (§8) |

---

## 2. v5.3.0 → v5.4.0 Source Diff (`hailo-ai/hailort-drivers`)

All files between the two tags were diffed via the GitHub API. Since it is a single squashed commit, nothing could be read from the commit message, so confirmation was done via the actual file diff. There was no change to the **logic itself** of CMA allocation/release (the `dma_alloc_coherent`/`dma_free_coherent` pair), and the following are mostly refactors and defensive fixes:

| File | Change |
|---|---|
| `linux/utils/compact.h` → `compat.h` | Filename rename of the kernel compatibility layer |
| `linux/vdma/memory.c` | Added a NULL check to `hailo_desc_list_release()`, clears the pointer to NULL after release (a defensive fix for **double-free prevention**) |
| `linux/vdma/vdma.h` | Removed the redundant field `kernel_address` from `hailo_descriptors_list_buffer` (consolidated into `desc_list.descs`) |
| `common/vdma_common.c` | Rewrote DMA transfer completion detection from a direct `hw_num_proc` calculation method to a `num_proc`/`num_avail` comparison method (possibly a bug fix for transfer completion tracking) |
| `linux/vdma/monitor.c` | `del_timer_sync` → `timer_delete_sync` (following the newer kernel API name) |
| `common/pcie_common.c` | Removed the md5 field from the FW control protocol, strengthened SCU log corruption detection from checking only the first 4 bytes to checking all first 5 words |

The error message wording was also changed (a long explanatory text → shortened to `out of CMA memory.`), but the control flow of allocation/release is identical. **This diff alone does not reveal any change corresponding to the hypothesis at the time (CMA not reclaimed on model reload)**.

---

## 3. Real-Hardware Swap Work and Roadblocks (2026-08-16, 1st Trial)

On a Raspberry Pi 5 + Hailo-10H running `hailo1x_pci 5.3.0` (managed by dkms), attempted a manual-build swap to v5.4.0.

### 3.1 `make install` Does Not Depend on `all`

The `install` target of `linux/pcie/Makefile` only runs `modules_install`, and completes without warning even when no build artifact (`.ko`) exists (to be precise, a warning about a missing `System.map` is emitted, but it doesn't reveal that the build wasn't actually done).

```makefile
install:
	$(Q)$(MAKE) -C $(KERNEL_DIR) M=$(PWD) INSTALL_MOD_DIR=kernel/drivers/misc modules_install
	$(Q)$(DEPMOD) -a

all: $(TARGET_DIR) print-versions
	$(Q)$(MAKE)  -C $(KERNEL_DIR) M=$(PWD) $(GDB_FLAG) $(USER_FLAGS) modules
	$(Q)cp $(DRIVER_NAME_NO_EXT)* $(TARGET_DIR)
```

**Always run in the order `make all && sudo make install`.**

### 3.2 The Raspberry Pi Kernel Headers Do Not Bundle `System.map`

The following warning is emitted during `modules_install`, and `depmod` is silently skipped:

```
Warning: modules_install: missing 'System.map' file. Skipping depmod.
```

This is because `/usr/src/linux-headers-<kernelver>/System.map` does not exist. `/boot/System.map-<kernelver>` does exist, so copying it resolves the issue:

```bash
sudo cp /boot/System.map-$(uname -r) /usr/src/linux-headers-$(uname -r)/System.map
sudo depmod -a
```

Without doing this, `modprobe` cannot resolve the newly installed `.ko`, resulting in `FATAL: Module hailo1x_pci not found` (even though the `.ko` file itself does exist under `/lib/modules/<kernelver>/kernel/drivers/misc/`).

### 3.3 udev Rules Do Not Take Effect Immediately Without a reload/trigger

`/lib/udev/rules.d/51-hailo-pcie-udev.rules`:

```
SUBSYSTEM=="hailo1x", MODE="0666"
```

Immediately after swapping the module, `/dev/h1x-0` becomes `crw-------` (root-only). Resolved with the following:

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=hailo1x
```

### 3.4 A Driver/Library Version Mismatch Is Fatal

Running `hailortcli` while only the kernel driver is upgraded to 5.4.0:

```
dmesg: Mismatch Driver version pcie driver 5:4:0 pci_ep driver 5:3:0
dmesg: hailo_soc_get_driver_info has failed with err -22

hailortcli: [HailoRT] [error] CHECK failed - Driver version (5.4.0) is different from library version (5.3.0)
hailortcli: [HailoRT] [error] Driver version mismatch, status HAILO_INVALID_DRIVER_VERSION(76)
```

The HailoRT library requires an **exact match** with the kernel driver, and upgrading only one side causes every API call to be immediately rejected. Vanilla verification of the driver alone is impossible; the `hailort` (SDK proper) userspace package must be upgraded at the same time.

- `apt-cache policy hailort` → candidate 5.3.0 (as of today, 5.4.0 not yet distributed on the official apt)
- `gh api repos/hailo-ai/hailort/releases` → the `v5.4.0` tag exists, but `assets` is empty (no prebuilt deb, source only)

In other words, **real-hardware verification of 5.4.0 is impossible unless HailoRT itself is installed via a deb or fully built from source**. A full build is a large-scale build involving C++ CMake + Python bindings, and risks dragging in dependency packages such as `hailo-tappas` and `python3-hailort`, so for the 1st trial this was deferred, and the decision was made to wait for official deb distribution.

---

## 4. Self-Build Procedure Record (2026-08-17, 2nd Trial)

Without waiting for apt / official deb distribution, the procedure and roadblocks encountered when self-building from GitHub source (driver: GPL-2.0, `hailort` proper: MIT) and deploying it to the system.

### 4.1 Build Environment

- Installed `checkinstall` (`sudo apt-get install -y checkinstall`). However, the kernel module's `xz` compression step conflicted with `installwatch` (checkinstall's LD_PRELOAD-based file-tracking mechanism), and running `make install` via checkinstall failed every time with `xz: ... No such file or directory`. **Do not use checkinstall for packaging kernel modules — use dkms (for the driver proper) or plain `make install` (for the userspace library)**
- Freed memory before building: temporarily stopped duplicate `headroom mcp serve` processes and `rust-analyzer` (freeing roughly 1 GB in total). The Pi has 7.9 Gi of memory, and available memory during the build stayed around 3.8 Gi

### 4.2 Building `hailort` (Userspace Library)

```bash
git clone --branch v5.4.0 --depth 1 https://github.com/hailo-ai/hailort.git
cd hailort/build   # after creating the directory
cmake .. -DCMAKE_BUILD_TYPE=Release   # auto-fetches external deps (protobuf/spdlog/eigen etc.) via FetchContent, ~4 minutes
cmake --build . -j2   # limited to -j2 (to avoid memory pressure), ~15 minutes
sudo make install     # installed to /usr/local/{include,lib,bin}. Coexists with the apt version (5.3.0, under /usr)
```

Since the default `option()` values all have heavyweight components (GStreamer, tests, server, Ollama integration, etc.) OFF, only `libhailort.so`, `hailortcli`, and `libhailopp` were built — a relatively lightweight configuration.

**Note**: the artifacts of `make install` go under `/usr/local` and do not overwrite the apt version (under `/usr`, 5.3.0). When verifying operation, an explicit path must be specified, e.g., `LD_LIBRARY_PATH=/usr/local/lib /usr/local/bin/hailortcli ...`.

### 4.3 driver (Kernel Module) Swap and firmware Update

The driver itself was built and installed via dkms (same procedure as the recovery steps in Appendix A, swapped to `-v 5.4.0`), and reread with `rmmod`/`modprobe`. At this point `hailortcli` returned `HAILO_DRIVER_OPERATION_FAILED(36)` / dmesg showed `Mismatch Driver version pcie driver 5:4:0 pci_ep driver 5:3:0`, revealing that **the firmware on the device (SoC side, pci_ep) also needed to be upgraded to 5.4.0 separately**.

```bash
# Fetch firmware from the official S3 (using the script bundled in the driver repository)
bash hailort-drivers/download_firmware_hailo10h.sh
# Back up the existing firmware before swapping in the new version
sudo cp -r /lib/firmware/hailo/hailo10h /lib/firmware/hailo/hailo10h.backup-5.3.0
sudo cp <extracted-location>/hailo10h_fw_5.4.0/* /lib/firmware/hailo/hailo10h/
sudo chown -R root:root /lib/firmware/hailo/hailo10h/
```

Attempting a module reload here (`rmmod`/`modprobe`, including with `support_soft_reset=1`) resulted in dmesg consistently returning `SOC Firmware batch was already loaded`. Checking the driver source revealed that `load_soc_firmware()` (the SoC firmware-loading path for Hailo-10H) has no soft-reset handling via `support_soft_reset` implemented (only `load_nnc_firmware()` for Hailo-8 has it), and it is unconditionally skipped as long as `hailo_pcie_is_firmware_loaded()` returns true. In other words, **the firmware state on the SoC cannot be changed by a module reload — a physical power cycle of the device itself is required**.

After the reboot, dmesg recorded the firmware batch write (`customer_certificate.bin`, `scu_fw.bin`, `u-boot-*.dtb.signed`, `u-boot-spl.bin`, `fitImage`, `image-fs`, in that order, 4064ms) → `SOC Firmware Batch loaded successfully`, and `hailortcli fw-control identify` responded normally with `Firmware Version: 5.4.0 (release,app)`.

### 4.4 Simple CMA Behavior Check and Its Limits

Observed `CmaFree` (`/proc/meminfo`) behavior over a single load/run/exit and 8 consecutive runs with `hailortcli run2` (resnet_v1_18.hef, a small model bundled with the `hailo_tutorials` package):

| Run | CmaFree (kB) |
|---|---|
| baseline (immediately after reboot) | 170464 |
| iter 1 | 134864 |
| iter 2 | 134144 |
| iter 3–8 | 133744 (no change, plateaued) |

It reached a plateau within a few runs, and no additional leak was observed through the 8th run. However, this is a simple CLI-driven load/run/exit (a fresh process spawn each time), which is a different path from either of the two known leaks reported by `docs/development/development_docs/HAILO_FORUM_FOLLOWUP_CMA_INFERENCE_LEAK.md` — (a) non-release on `VDevice.release()`/model reload **within the same process**, and (b) a continuous leak during `generate_stream()` (LLM inference) execution — and this result is not evidence that the issue has "been resolved."

The main repro (`tools/diag_hailo_cma_reclaim.py` and the script recorded in the forum-followup doc) loads a GenAI LLM via the Python `hailo_platform` (pyhailort) binding, so it could not be run as-is in the 5.4.0 environment:

```
$ hailo_platform inside .venv is statically linked to libhailort.so.5.3.0 (confirmed via ldd)
$ Expected to hit the same HAILO_INVALID_DRIVER_VERSION due to a driver(5.4.0)/library(5.3.0) version mismatch when constructing VDevice()
```

At this point, the work of rebuilding pyhailort (the Python binding) from the 5.4.0 source and swapping it into `.venv` had not yet started, but was carried out in the 3rd trial (§5).

---

## 5. Rebuilding pyhailort and Rerunning the Repro (2026-08-17, 3rd Trial)

This section records the provisional verdict as of the 3rd trial. The judgment method and conclusion have since been corrected by the 4th-round A/B trial (§8).

### 5.1 Building pyhailort (Python Binding)

`hailort/libhailort/bindings/python/platform/` in the `hailort` main repository is the pip package source for pyhailort (`pyproject.toml`, scikit-build-core + pybind11 based). Built while explicitly linking against the libhailort 5.4.0 placed under `/usr/local` in §4.2:

```bash
cd hailort/libhailort/bindings/python/platform
CMAKE_ARGS="-DLIBHAILORT_PATH=/usr/local/lib/libhailort.so.5.4.0 -DHAILORT_INCLUDE_DIR=/usr/local/include" \
  <venv>/bin/python -m pip install .
```

Auto-fetched `scikit-build-core`/`pybind11` from PyPI within build isolation and built, swapping the `.venv`'s `hailort` from the 5.3.0 → 5.4.0 wheel. Confirmed via `ldd` that `_pyhailort*.so` is linked against `/usr/local/lib/libhailort.so.5.4.0`, and `VDevice()` construct/release also operated normally standalone.

### 5.2 Rerunning the Existing Repro (`tools/diag_hailo_cma_reclaim.py`)

Remeasured in the same environment (with the `.venv`'s `hailo_platform` swapped to 5.4.0), using the same repro script, the same judgment criteria, and the same HEF (`~/hailo_models/Qwen3-1.7B-Instruct.hef`) as in 2026-05:

```bash
uv run python tools/diag_hailo_cma_reclaim.py --signal terminate
```

Results (`logs/hailo_cma_reclaim_poc.json`):

| Event | CmaFree (MB) |
|---|---|
| baseline_before_spawn | 159 |
| after_vdevice_created / after_llm_loaded | 22 (consumed 137 MB) |
| immediately after child kill (`terminate`) | 23 |
| post_wait +5s | 26 |
| post_wait +10s | 28 |
| post_wait +15s | 29 |
| post_wait +20s–+30s | **0** (dropped a further ~28.5 MB from 29 MB, and after that `CmaFree` stayed pinned around 512 kB for several more minutes) |

This drop back down from 29 MB → around 512 kB could not be confirmed as coinciding with contention from another process, but this measurement alone cannot identify the cause, so it is left as an unexplained observation. Page-cache usage after the first load (§8.4) alone does not explain this intermediate progression, and since a repeated trial that simultaneously captured RSS, `MemAvailable`, and allocation failures was not part of this run, it is not used as the basis for the final verdict in §8.

However, this figure of around 512 kB falls in the same band as the 464→1,648 kB observed during the `FOLL_LONGTERM` trial in §8.3, and from that state 20 generations, release, and reload all succeeded. The process leading to the low value remains unexplained, but it has been confirmed on real hardware that **the `CmaFree` value in this band does not by itself immediately mean a dangerous state or an inability to load**.

The raw output from the old diagnostic tool (the provisional verdict at the time of the 3rd round; the final verdict has since been corrected in §8):

```
VERDICT: FAIL — only -22 MB recovered after kill+wait. spec hypothesis invalid → pivot to auto-reboot alternatives
```

What this trial established was only that `CmaFree` after the first HEF load did not recover according to the old judgment criteria. It did not prove either a loss of available memory after process exit, or that v5.4.0 had not fixed the leak. The 3rd round provisionally interpreted this as non-reclaim, but that interpretation and the judgment method have been corrected in §8.

---

## 6. Kernel Crash During the 3rd Trial and Recovery of the CMA Debug Code (2026-08-17)

### 6.1 Incident and Candidate Causes

To investigate the CMA release path, an `include` of `linux/mm.h` and instrumentation calling `virt_to_page()` / `page_count()` immediately before `dma_free_coherent()` had been added to `linux/vdma/memory.c` in the local DKMS source. Loading a module containing this change caused a hang when Hailo was used, leaving the system unbootable, so `module_blacklist=hailo1x_pci,hailo_pci` in `/boot/firmware/cmdline.txt` is currently blocking auto-load.

Directly converting the CPU virtual address returned by `dma_alloc_coherent()` to a page via `virt_to_page()` is not part of the DMA API contract. Since the mapping format of the returned address is left up to the allocator, the `page_count()` obtained from it is not a valid means of observing CMA reference counts, and can produce invalid page references. The instrumentation ran on both the descriptor list and continuous buffer release paths.

The addition timestamp was 10:15:36, and the corresponding DKMS build started at 10:15:39, so it can be determined that the hung module included this code. A stack trace immediately before the crash could not be obtained, so this is not a strict determination of the cause, but it is the sole local execution-code change not present in vanilla v5.4.0, and is treated as the leading candidate cause.

### 6.2 Recovered State

Removed the following 7 lines (the `linux/mm.h` include, and two locations of `virt_to_page()` / `page_count()` logging), rebuilt DKMS, and completed through `depmod`.

- Kernel: `6.18.39+rpt-rpi-2712`
- Rebuilt module: `/lib/modules/6.18.39+rpt-rpi-2712/updates/dkms/hailo1x_pci.ko.xz`
- The above module is registered in `modules.dep`
- The blacklist remains in place; the rebuilt module has not yet been loaded

Next time, secure a recovery path such as a serial console before removing the blacklist and confirming the initial load via reboot. For the investigation of the CMA non-reclaim issue itself, do not reintroduce instrumentation that converts the DMA API's returned address into internal pages, and instead observe the driver's own buffer ledger, allocation sizes, and `dma_free_coherent()` call counts.

**Addendum (2026-08-17, later)**: With a `cmdline.txt` backup (`cmdline.txt.bak-blacklisted`) prepared, removed the blacklist and rebooted, confirming that it starts normally (a serial console `console=serial0,115200` was also configured, so a recovery path is secured). From this point, the investigation continued in §7 using safe instrumentation (no raw page inspection, only logging of existing counters and sizes).

---

## 7. Formation and Elimination of Cause Hypotheses — Verification and Refutation of `FOLL_LONGTERM` (2026-08-17)

This section records the formation of cause hypotheses following the 3rd trial, and candidate causes that could be eliminated experimentally. Its role here is narrowing down candidates; the final verdict on whether a CMA leak exists depends on the 4th-round A/B trial (§8).

Given the crash in §6, the investigation continued using safe instrumentation that avoided direct access to page internals such as `virt_to_page()` (logging only via `dev_err()`; no inspection or conversion of raw pointers).

### 7.1 Instrumentation Content

Added logging at the following locations in `linux/vdma/memory.c` / `linux/vdma/ioctl.c` / `linux/vdma/vdma.c` to output existing atomic counters (`controller->desc_cma_in_use` / `controller->cma_in_use`) and allocation sizes (no access to page internals at all):

- `hailo_desc_list_create`/`hailo_desc_list_release` (descriptor list alloc/free)
- `hailo_vdma_continuous_buffer_alloc`/`hailo_vdma_continuous_buffer_free` (continuous buffer alloc/free)
- `hailo_desc_list_release_ioctl`/`hailo_vdma_continuous_buffer_free_ioctl` (explicit release ioctl paths)
- `hailo_vdma_buffer_map`/`hailo_vdma_buffer_destroy` (DMA mapping/unmapping path for userspace buffers; also outputs `buffer_type`/`is_mmio`/`is_dmabuf`)
- `hailo_vdma_file_context_finalize` (bulk cleanup at fops_release, outputs counters at ENTER/EXIT)

### 7.2 Observation Results

From immediately after reboot (`CmaFree` ≈ 451 MB), ran `tools/diag_hailo_cma_reclaim.py --signal terminate`, and collected and aggregated all logs with `sudo dmesg | grep CMA_DBG`.

- **`CmaFree` in `/proc/meminfo`**: 451 MB → 195 MB (**256 MB consumed**) → 204 MB even after kill + 30s wait (**247 MB below baseline**)
- **The driver's own `desc_cma_in_use` (descriptor list, via `dma_alloc_coherent`)**: at most 2–4 MB. Confirmed to reliably return to 0 by the EXIT point of `file_context_finalize`
- **`cma_in_use` (continuous buffer, via `dma_alloc_coherent`)**: 0 throughout this session (continuous buffer was never used)
- **DMA mapping of userspace buffers (`hailo_vdma_buffer_map`, `buffer_type=0`=`HAILO_DMA_USER_PTR_BUFFER`, `is_mmio=0`, `is_dmabuf=0`)**: called 621 times, of which **342 were 8 MB (`0x800000`) in size** (totaling 2.7 GB worth of mapping calls; the same host-side staging buffer appears to be reused across pipeline processing). `hailo_vdma_buffer_destroy` was called 628 times, nearly 1:1 with `buffer_map`, and **the driver's own mapping ledger is not broken** (`dma_unmap_sg` is correctly called)
- **SWIOTLB (`/sys/kernel/debug/swiotlb/`)**: `io_tlb_used_hiwater=0`. The bounce buffer was never used
- The Hailo device is not under IOMMU (no `/sys/bus/pci/devices/0001:01:00.0/iommu_group`)

At this point, the interpretation shifted from the driver's own allocations via `dma_alloc_coherent()` (desc list, continuous buffer) toward the path handled by `hailo_vdma_buffer_map()` — "mapping existing userspace-allocated memory for DMA" (`HAILO_DMA_USER_PTR_BUFFER`) — as the candidate cause for the `CmaFree` drop. On this path the driver does not newly allocate CMA; it pins (fixes) existing user pages to make them DMA-capable.

### 7.3 Cause Hypothesis: `FOLL_LONGTERM` Is Not Specified for `get_user_pages()`

Checking `prepare_sg_table()` (called internally from `hailo_vdma_buffer_map()`) in `linux/vdma/memory.c`:

```c
pinned_pages = compat_get_user_pages(user_address, npages, FOLL_WRITE | FOLL_FORCE, pages);
```

`compat_get_user_pages` (since this kernel, 6.18.39, satisfies `LINUX_VERSION_CODE >= KERNEL_VERSION(6, 5, 0)`) is a simple alias for `get_user_pages()`, and **the `FOLL_LONGTERM` flag is not specified**. The release side (`clear_sg_table()`) also calls the corresponding `put_page()`, staying with the old `get_user_pages()`/`put_page()` rather than the newer `pin_user_pages()`/`unpin_user_pages()` API family.

The Linux kernel's documented convention (`Documentation/core-api/pin_user_pages.rst`) states that code that **holds page references for a long time, as DMA transfers do, should use `pin_user_pages()` with `FOLL_LONGTERM`**. When `FOLL_LONGTERM` is not specified, if a userspace page that happens to reside within a CMA region is pinned via `get_user_pages()`, CMA's inherent "movable (can be migrated to another use when needed)" property is disabled for a long period. The CMA allocator normally migrates such pages out of the CMA region before a long-term pin, but on paths that don't use `FOLL_LONGTERM` this migration does not happen, so **while pinned, that amount is effectively lost from the CMA region, and even after release (`put_page()`) it is not immediately recognized as free CMA space** (because migration/compaction is separately required).

This hypothesis was consistent with the single-shot measurement at the 3rd round (§7.2):
- The driver's own CMA counters are unrelated (`get_user_pages` does not go through `dma_alloc_coherent`)
- The map/destroy call counts are correctly balanced (`put_page()` itself is correctly called; the problem is that the "return" to CMA after release is slow/incomplete)
- Loading a large LLM such as Qwen3-1.7B-Instruct allocates and DMA-maps a large number of 8 MB buffers on host memory, and this issue would manifest if some of them happened to include pages within a CMA region
- Consistent also with the slow, partial recovery of `CmaFree` after kill (roughly +15–30 MB in 30 seconds, then a further gradual increase over several minutes) (`put_page()` itself is reliably called on process exit, but reclamation as free CMA space appears to require additional processing)

### 7.4 Implementation and Real-Hardware Verification of the Candidate Fix → Refuted (2026-08-17, Follow-up)

Actually replaced `prepare_sg_table()` from `get_user_pages(FOLL_WRITE | FOLL_FORCE)` + `put_page()` with `pin_user_pages(FOLL_WRITE | FOLL_FORCE | FOLL_LONGTERM)` + `unpin_user_page()`, added an `<linux/mm.h>` include, and carried this all the way through build, dkms re-registration, and real-hardware loading (confirmed that the `pin_user_pages`/`unpin_user_page` symbols resolved correctly via `modprobe --dump-modversions`).

Result of running the same repro from a high-`CmaFree` state immediately after reboot (453 MB):

| | Before fix (n=multiple runs) | After fix (n=1) |
|---|---|---|
| baseline | 436–451 MB | 453 MB |
| after_llm_loaded | 173–195 MB (consumed 256–263 MB) | 180 MB (consumed 273 MB) |
| after_post_wait | 188–204 MB (recovered 9–15 MB) | 190 MB (**recovered 10 MB**) |
| `VERDICT` under the old judgment criteria | `FAIL` | **`FAIL` (no change)** |

> This table is not a strict A/B comparison, since the run counts and aggregation method are asymmetric. The A/B verdict is based on the results of §8, which repeated under identical conditions.

Checking `CMA_DBG buffer_map` in `dmesg` showed that the same 0x800000 (8 MB) sized buffers were being mapped without issue via `pin_user_pages` even after the fix (no pin failures or kernel warnings at all), and the code path itself executed as intended. Forced compaction via `echo 1 > /proc/sys/vm/compact_memory` also had no effect. `MemAvailable` remained healthy at 7.1 GB, and — same as before the fix — it was not overall system memory pressure but specifically the `CmaFree` accounting that failed to recover.

**Conclusion: the `FOLL_LONGTERM`-missing hypothesis was refuted by experiment.** The replacement of `get_user_pages()` → `pin_user_pages()` + `FOLL_LONGTERM` is a legitimate improvement in line with the Linux kernel's documented convention, but it was not the direct cause of the CMA non-reclaim symptom observed in this session. The hypothesis itself remains theoretically sound (the interaction between CMA's migration mechanism and long-term pinning is a real, known class of issue), and remains a valid point of code-quality feedback, but **it is not, on its own, the root cause that explains this trial's measured results**.

### 7.5 Elimination of Candidate Causes (Final Verdict in §8)

The following are candidate causes that were clearly **eliminated** by experiment. This list is a valid product of hypothesis testing, but is not itself the verdict on whether a leak exists.

- The driver's own `dma_alloc_coherent()`-based allocations (desc list, continuous buffer) — only a few MB, and correctly returns to 0
- Inconsistency in SG mapping map/destroy calls — balanced
- SWIOTLB bounce buffer — never used (`io_tlb_used_hiwater=0`)
- Missing `FOLL_LONGTERM` on `get_user_pages()` — the fix was implemented and verified on real hardware, with no improvement

What remained a fact through the 3rd trial was that `MemAvailable` stayed healthy while `CmaFree` alone dropped after the first load. This was interpreted as non-reclaim at the time, but a single trial cannot distinguish between "loss of available memory" and "diversion of movable CMA pages into the page cache." In the 4th round, the trial was repeated while staying at a low `CmaFree`, and the actual load success/failure, net change per repetition, RSS, and CMA allocation failures were measured to correct the verdict.

---

## 8. 4th Trial: vanilla / `FOLL_LONGTERM` A/B Retest and Confirmation of the Misjudgment (2026-08-17)

### 8.1 Comparison Targets

- `FOLL_LONGTERM`-fixed build: `pin_user_pages(FOLL_LONGTERM)` / `unpin_user_page()`, loaded with `srcversion=C84A00ABB326748A1832CE1`
- Official vanilla 5.4.0: tag `v5.4.0`, commit `b6dd17c609504e648eb516ff4a867167edf56f3c`, `get_user_pages()` / `put_page()`, loaded with `srcversion=A260C39C9F2C06DD4FB072E`
- Kernel: `6.18.39+rpt-rpi-2712`
- HEF: `Qwen3-1.7B-Instruct.hef` (2,880,748,478 bytes)

### 8.2 Two Consecutive Loads in Independent Processes

| Driver | Trial | baseline | loaded | after exit | change vs. baseline | Load |
|---|---:|---:|---:|---:|---:|---|
| `FOLL_LONGTERM` | 1 | 338 MB | 34 MB | 25 MB | **-313 MB (decrease)** | Success |
| `FOLL_LONGTERM` | 2 | 5 MB | 6 MB | 7 MB | **+2 MB (increase)** | Success |
| vanilla | 1 | 376 MB | 99 MB | 112 MB | **-264 MB (decrease)** | Success |
| vanilla | 2 | 125 MB | 118 MB | 124 MB | **-1 MB (decrease)** | Success |

For both drivers, `CmaFree` dropped sharply only on the first run, and the second load from that already-low value succeeded with a net change close to 0. The previous diagnosis judged based solely on "how many MB out of what was consumed during loading came back," which caused even the normal case of the 2nd run — which already started from a low `CmaFree` — to be marked `FAIL`.

### 8.3 Generate/Release/Reload Within the Same Process

| Metric | `FOLL_LONGTERM` | vanilla, 1st run | vanilla, low-CMA repetition |
|---|---:|---:|---:|
| Generations completed | 20/20 | 20/20 | 20/20 |
| 1st load | Success | Success | Success |
| 2nd load after release | Success | Success | Success |
| `CmaFree` for generations 1→20 | 464→1,648 kB | 115,376→123,728 kB | 82,320→83,296 kB |
| `MemAvailable` for generations 1→20 | 6,706,208→6,788,432 kB | 6,830,352→6,910,560 kB | 6,871,504→6,906,368 kB |
| RSS during generation | fixed at 63,888 kB | 63,904–63,920 kB | 63,936–63,952 kB |
| CMA allocation failures | 0 | 0 | 0 |

The vanilla low-CMA repetition started at `CmaFree=87,424 kB`, was 79,520 kB immediately after full release, and returned to 87,344 kB afterward (net difference of 80 kB). There is no behavior of progressive loss the more that load/generate/release is repeated. `nr_foll_pin_*` being 0 for vanilla is because it does not use the `FOLL_PIN` API, so it cannot be used to compare pin-release success/failure.

### 8.4 Interpretation of the Initial Drop

From immediately after the vanilla reboot through the end of all retests, `Cached` grew from 1,845,872 kB to approximately 4,988,224 kB, while `MemAvailable` was maintained from 7,071,280 kB to approximately 6,962,816 kB. The magnitude of the increase is consistent with reading in the multi-GB HEF, and the initial `CmaFree` drop can be explained as page-cache usage of free pages including movable CMA pages, rather than a loss of inaccessible memory.

### 8.5 Operational Conclusions

1. Model loading must not be rejected based solely on the absolute value of `CmaFree`. On real hardware, Qwen loaded successfully even from under 1 MB.
2. Record low `CmaFree` as telemetry, and use the actual HailoRT memory allocation error for the failure verdict.
3. Do not conflate the observed `CmaFree` value, actual load failure, and leak diagnosis; handle them as the following 3 states.

| State | Judgment condition | Product-side action | Reboot / investigation |
|---|---|---|---|
| `INCONCLUSIVE` | Only an initial drop, fewer than 3 trials, or does not meet the `FAIL` condition below | Record telemetry and attempt the load. Do not reject based on low `CmaFree` alone | Do not reboot. Add more measurements under the same conditions |
| `OPERATIONAL_FAIL` | HailoRT actually returned a host-memory allocation error | Fail only that load request; stop unneeded Hailo workloads and retry | Do not reboot on a single occurrence. Follow operational policy only if actual failures repeat and do not recover after workload release. Current Phase 0.5 only records `would_fire` and does not auto-reboot |
| `FAIL` | Repeating the same conditions 3 times from a low-CMA state, where the net decrease vs. baseline after release is **over 10 MB in 2 or more of the 3 trials**, the sum of positive net decreases across the 3 trials is **over 20 MB**, and it is accompanied by a monotonic increase in RSS or a drop of over 128 MB in `MemAvailable` | Record it as a leak diagnosis separate from individual load success/failure | Resume kernel / HailoRT investigation and collect direct evidence. Diagnosis alone does not trigger an auto-reboot |

This 3-trial criterion is for future diagnostics and is not applied retroactively to §8.2 of this section, where the independent process trial was only 2 runs per driver. The 4th round's conclusion combines the A/B in §8.2 with the same-process 20-generation-cycle/release/reload and low-CMA repetition in §8.3.
4. The `FOLL_LONGTERM` replacement is a legitimate practice per general Linux DMA API convention, but has no effect on this issue, and the real hardware has been reverted to official vanilla 5.4.0.
5. Automatic reboot decisions must not fire on low `CmaFree` alone, and must require an observed actual load failure as a mandatory condition.

---

## 9. Future Actions (as of 2026-08-17)

1. Investigation and real-hardware refutation of the `FOLL_LONGTERM` fix is complete. The reproduction diff and restoration method are stored in Appendix B, and are not applied to the production driver.
2. **The product side has already been addressed**: `core/hailo_device_core/device_manager_genai.py::acquire_genai` was modified in v4.620.8 to record `acquire_low_cma_observed` and continue with the actual load even when `CmaFree` is lower than the estimated required amount. Only an actual HailoRT host-memory error returned by the factory is recorded to the rejection tracker, and `tests/test_hailo_cma_false_positive.py` pins the behavior of continuing to load from a low value.
3. Re-audited the old forum draft's statement that "a subsequent `LLM(...)` was rejected by HailoRT with insufficient host CMA" against the logs and the old implementation. The PID 3237 session cited had no acquire record after release, and every low-CMA rejection traceable in that day's logs was the self-issued event `acquire_rejected_low_cma` before any HailoRT call. In a separate session, a failure that did reach the factory had status 8 (`HAILO_INTERNAL_FAILURE`), not the host-memory error status 3. There is therefore no HailoRT OOM evidence supporting the old statement, and this is retracted with an explicit note in `docs/development/development_docs/HAILO_FORUM_FOLLOWUP_CMA_INFERENCE_LEAK.md` that rejections originating from the self-issued guard were mixed into the report.
4. The correction posting integrates the figures and scope in §8, the correction of the implementation guard, the refutation of `FOLL_LONGTERM`, and the instrumentation-level caveats into a single current draft, without leaving the old English draft in a copyable form.
5. Kernel / HailoRT-side leak investigation will only be resumed if an actual load failure or a cumulative loss of available memory across repetitions is reproduced. At that point, direct evidence such as `page_owner`, CMA debug info, allocation failure status, RSS, and `MemAvailable` will be collected.

---

## Appendix A. Recovery Procedure to v5.3.0

After a `remove --all` from dkms, recovery fails if the `.deb` no longer exists in the apt cache (this also failed in this case: `download not possible, reinstall is not possible`). Since dpkg still recognizes the `hailort-pcie-driver` package as `ii` (installed), as long as the package's extracted source location `/usr/src/hailort-pcie-driver/` still exists, the dkms tree can be manually rebuilt from it:

```bash
sudo rmmod hailo1x_pci

sudo rm -rf /usr/src/hailo1x_pci-5.3.0
sudo cp -r /usr/src/hailort-pcie-driver /usr/src/hailo1x_pci-5.3.0
sudo sed 's/@PCIE_DRIVER_VERSION@/5.3.0/' \
  /usr/src/hailo1x_pci-5.3.0/linux/pcie/dkms.conf.in \
  | sudo tee /usr/src/hailo1x_pci-5.3.0/linux/pcie/dkms.conf > /dev/null

# dkms.conf must be placed directly under the tree root (an error occurs under linux/pcie/)
sudo cp /usr/src/hailo1x_pci-5.3.0/linux/pcie/dkms.conf /usr/src/hailo1x_pci-5.3.0/dkms.conf

sudo dkms add -m hailo1x_pci -v 5.3.0
sudo dkms build -m hailo1x_pci -v 5.3.0 -k $(uname -r)
sudo dkms install -m hailo1x_pci -v 5.3.0 -k $(uname -r) --force
sudo depmod -a
sudo modprobe hailo1x_pci
sudo udevadm trigger --subsystem-match=hailo1x
```

Recovery confirmation:

```bash
cat /sys/module/hailo1x_pci/version   # → 5.3.0
hailortcli fw-control identify        # → recovery complete if a normal response is returned
```

---

## Appendix B. Storage, Application, and vanilla Restoration Procedure for the Refutation-Experiment Driver Patch

### B.1 What Is Stored and Its Purpose

The driver diff actually used for the A/B is stored as-is in the following file.

- `docs/development/patches/hailo1x_pci-5.4.0-foll-longterm-cma-debug-experiment.patch`
- SHA-256: `7b5c4027f37432dbbbe39e4bdec2f0f5e8dd87e133473b5a44c44b1e86c5503f`
- Base source: `hailo-ai/hailort-drivers` tag `v5.4.0`, commit `b6dd17c609504e648eb516ff4a867167edf56f3c`
- Target files: `linux/vdma/ioctl.c`, `linux/vdma/memory.c`, `linux/vdma/vdma.c`

This patch includes not only the replacement with `pin_user_pages(FOLL_LONGTERM)` / `unpin_user_page()`, but also the `CMA_DBG` instrumentation used in §7.1. In other words, it is a **complete verification diff** for reproducing the experimental module used during the A/B, and is not a production-recommended patch. The experiment showed no effect, and the real hardware has already been restored to official vanilla 5.4.0. No changes were made to the HailoRT userspace library.

The identifying values confirmed on the same kernel, source, and build environment are as follows.

| State | `srcversion` |
|---|---|
| Experimental patch | `C84A00ABB326748A1832CE1` |
| Official vanilla 5.4.0 | `A260C39C9F2C06DD4FB072E` |

### B.2 Pre-Application Verification

The following should only be run when `/usr/src/hailo1x_pci-5.4.0` on the Raspberry Pi points to the above official commit and there are no local changes to the 3 target files. If any of the commit, patch checksum, or vanilla `memory.c` checksum does not match, stop and do not force-apply the patch.

```bash
set -euo pipefail

REPO=/home/pi/GitHub/yu_ai_manager
SRC=/usr/src/hailo1x_pci-5.4.0
PATCH="$REPO/docs/development/patches/hailo1x_pci-5.4.0-foll-longterm-cma-debug-experiment.patch"
EXPECTED_HEAD=b6dd17c609504e648eb516ff4a867167edf56f3c
EXPECTED_PATCH_SHA=7b5c4027f37432dbbbe39e4bdec2f0f5e8dd87e133473b5a44c44b1e86c5503f
EXPECTED_MEMORY_SHA=85d564acaa70cdb41eb18bad35ad958d3b2af168ae03c17466976cbe64b1e58c

test "$(sudo git -c safe.directory="$SRC" -C "$SRC" rev-parse HEAD)" = "$EXPECTED_HEAD"
printf '%s  %s\n' "$EXPECTED_PATCH_SHA" "$PATCH" | sha256sum -c -
printf '%s  %s\n' "$EXPECTED_MEMORY_SHA" "$SRC/linux/vdma/memory.c" | sha256sum -c -
sudo git -c safe.directory="$SRC" -C "$SRC" diff --exit-code -- \
  linux/vdma/ioctl.c linux/vdma/memory.c linux/vdma/vdma.c
sudo git -c safe.directory="$SRC" -C "$SRC" apply --check "$PATCH"
```

### B.3 Applying the Experimental Patch

Only if all verifications succeed, apply the patch and install the DKMS module for the next boot. Do not manually swap the loaded module with `rmmod` / `modprobe`; switch over via a normal reboot after the build.

```bash
set -euo pipefail

SRC=/usr/src/hailo1x_pci-5.4.0
PATCH=/home/pi/GitHub/yu_ai_manager/docs/development/patches/hailo1x_pci-5.4.0-foll-longterm-cma-debug-experiment.patch
KERNEL_VERSION="$(uname -r)"

sudo git -c safe.directory="$SRC" -C "$SRC" apply "$PATCH"
sudo dkms build -m hailo1x_pci -v 5.4.0 -k "$KERNEL_VERSION" --force
sudo dkms install -m hailo1x_pci -v 5.4.0 -k "$KERNEL_VERSION" --force
sudo depmod -a "$KERNEL_VERSION"

modinfo -n hailo1x_pci
modinfo -F srcversion hailo1x_pci
head -n 1 /sys/module/hailo1x_pci/srcversion
```

`modinfo` shows the module installed for the next boot; `/sys/module/.../srcversion` shows the currently loaded module. It is normal for the values to differ at this point. Once ready, reboot and confirm that both match after startup.

```bash
sudo reboot

# after reconnecting
modinfo -F srcversion hailo1x_pci
head -n 1 /sys/module/hailo1x_pci/srcversion
```

In this same verification environment, the expected value after patch application is `C84A00ABB326748A1832CE1`. If it differs, do not continue testing by guesswork; check the source diff, kernel, and DKMS build log.

### B.4 Restoring Official vanilla 5.4.0

Restoration does not rely on reverse-applying the patch; it explicitly restores the 3 target files from the verified commit. This avoids a state where a partial application or only the instrumentation remains.

```bash
set -euo pipefail

SRC=/usr/src/hailo1x_pci-5.4.0
EXPECTED_HEAD=b6dd17c609504e648eb516ff4a867167edf56f3c
EXPECTED_MEMORY_SHA=85d564acaa70cdb41eb18bad35ad958d3b2af168ae03c17466976cbe64b1e58c
KERNEL_VERSION="$(uname -r)"

test "$(sudo git -c safe.directory="$SRC" -C "$SRC" rev-parse HEAD)" = "$EXPECTED_HEAD"
sudo git -c safe.directory="$SRC" -C "$SRC" restore --source="$EXPECTED_HEAD" -- \
  linux/vdma/ioctl.c linux/vdma/memory.c linux/vdma/vdma.c
sudo git -c safe.directory="$SRC" -C "$SRC" diff --exit-code -- \
  linux/vdma/ioctl.c linux/vdma/memory.c linux/vdma/vdma.c
printf '%s  %s\n' "$EXPECTED_MEMORY_SHA" "$SRC/linux/vdma/memory.c" | sha256sum -c -

sudo dkms build -m hailo1x_pci -v 5.4.0 -k "$KERNEL_VERSION" --force
sudo dkms install -m hailo1x_pci -v 5.4.0 -k "$KERNEL_VERSION" --force
sudo depmod -a "$KERNEL_VERSION"

modinfo -F srcversion hailo1x_pci
head -n 1 /sys/module/hailo1x_pci/srcversion
```

In this same verification environment, the expected value of the installed vanilla module is `A260C39C9F2C06DD4FB072E`. Confirm that the currently loaded value differs, then reboot, and after reconnecting confirm that both now show `A260C39C9F2C06DD4FB072E`.

---

## Reference: Related Documents

- `docs/development/development_docs/HAILO_FORUM_FOLLOWUP_CMA_INFERENCE_LEAK.md` — CMA leak measured data, repro script, and forum-post draft based on the old measurement (conclusion corrected in §8 of this document)
- [HAILORT_5_3_0_MIGRATION.md](HAILORT_5_3_0_MIGRATION.md) — Record of the v5.2.0 → v5.3.0 migration (device node rename to `/dev/h1x-0`, etc.)
- [HAILO_CMA_LEAK_HAILORT_5_3_0.md](HAILO_CMA_LEAK_HAILORT_5_3_0.md) — Japanese-language record of the CMA leak issue based on the old diagnosis (conclusion corrected in §8 of this document)
- `hailo-ai/hailort-drivers` GitHub repository (GPL-2.0, source available): <https://github.com/hailo-ai/hailort-drivers>
