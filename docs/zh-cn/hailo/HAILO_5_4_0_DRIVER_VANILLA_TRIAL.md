# HailoRT / driver 5.4.0 CMA 未释放判定的订正与验证记录

创建：2026-08-16 / 最终更新：2026-08-17 / 对应版本：yu_ai_manager 4.623.1

针对此前被判定为 CMA 未释放的现象（参见 `docs/development/development_docs/HAILO_FORUM_FOLLOWUP_CMA_INFERENCE_LEAK.md`），使用 `hailo-ai/hailort-drivers` v5.4.0（2026-08-16 发布，GPL-2.0，源码公开）进行了假设验证，以及官方 vanilla 版与 `FOLL_LONGTERM` 修复版的 A/B 试验，本记录订正了测量侧的误判定。

---

## 1. 结论

**2026-08-17 最终追加试验（第4回）：第3回为止的 `VERDICT: FAIL` 判定，是仅使用首次 HEF 加载后 `CmaFree` 的绝对回收量作为泄漏判定标准所导致的误判定。将官方 vanilla 5.4.0 与 `FOLL_LONGTERM` 修复版进行 A/B 比较后，低 `CmaFree` 状态下的连续加载、同一进程内的释放与再加载、20 次生成、以及在更低 `CmaFree` 状态下的全部试验反复均全部成功。生成过程中的 RSS 与 `CmaFree` 未出现单调增减，CMA 分配失败次数为 0。首次的 `CmaFree` 下降与 multi-GB HEF 的页缓存增加相对应，`MemAvailable` 始终维持约 7GB。本次试验条件为 Pi 5 + Hailo-10H + HailoRT/driver 5.4.0、单一模型、单一设备、短时间反复，在该条件下未再现实用上的 CMA 泄漏，`FOLL_LONGTERM` 修复也未带来可测量的改善。长时间连续运行、多模型并发使用、Hailo-8、IOMMU 环境下均未经测试，均不在本结论适用范围之内。**

### 1.1 判定的变迁

| 回合 | 日期 | 当时的判定 | 更新・订正依据 |
|---|---|---|---|
| 第1回 | 2026-08-16 | 无法判定 | 仅将 driver 升级至 5.4.0 时，被 library 5.3.0 的完全一致性检查拒绝了 API 调用（§3） |
| 第2回 | 2026-08-17 | 仅完成有限试验 | driver / library / firmware 均统一为 5.4.0，`run2` 反复趋于平稳，但未执行经由 pyhailort 的直接 repro（§4） |
| 第3回 | 2026-08-17 | 暂定 `FAIL`（后被订正为误判定） | 旧诊断结果仅判定了首次 HEF 加载后 `CmaFree` 的绝对回收量。单次测量无法区分内存丧失与页缓存利用（§5、§7） |
| 第4回 | 2026-08-17 | 实用上的泄漏未再现 | 通过 vanilla / `FOLL_LONGTERM` A/B 比较、低 CMA 反复、同一进程再加载、20 次生成，以及 RSS、`MemAvailable`、分配失败的测量，订正了第3回的判定（§8） |

---

## 2. v5.3.0 → v5.4.0 源码差异（`hailo-ai/hailort-drivers`）

通过 GitHub API 对两个标签之间的全部文件进行 diff。由于是单一压缩提交，commit message 无法读出任何信息，因此以实际文件 diff 为准确认。CMA 分配・释放的**逻辑本身**（`dma_alloc_coherent`/`dma_free_coherent` 配对）没有变化，以下改动以重构与防御性修复为主：

| 文件 | 变更内容 |
|---|---|
| `linux/utils/compact.h` → `compat.h` | 内核兼容层文件重命名 |
| `linux/vdma/memory.c` | 在 `hailo_desc_list_release()` 中新增 NULL 检查，释放后将指针清为 NULL（**防止双重释放**的防御性修复） |
| `linux/vdma/vdma.h` | 从 `hailo_descriptors_list_buffer` 中删除了冗余字段 `kernel_address`（并入 `desc_list.descs`） |
| `common/vdma_common.c` | DMA 传输完成判定从 `hw_num_proc` 直接计算方式改写为 `num_proc`/`num_avail` 比较方式（可能是传输完成追踪的 bug 修复） |
| `linux/vdma/monitor.c` | `del_timer_sync` → `timer_delete_sync`（追随新内核 API 命名） |
| `common/pcie_common.c` | 从 FW 控制协议中删除了 md5 字段，SCU 日志损坏判定从仅检查前 4 字节强化为检查前 5 个 word 全部 |

错误信息文案也有变化（长说明文 → 缩短为 `out of CMA memory.`），但分配・释放的控制流程相同。**仅凭此 diff，无法读出与当时假设（模型重新加载时 CMA 未释放）相对应的改动**。

---

## 3. 实机替换作业与遇到的问题（2026-08-16，第1回试验）

以 Raspberry Pi 5 + Hailo-10H、正在运行的 `hailo1x_pci 5.3.0`（由 dkms 管理）为对象，尝试手动构建替换为 v5.4.0。

### 3.1 `make install` 不依赖 `all`

`linux/pcie/Makefile` 的 `install` 目标只执行 `modules_install`，即使构建产物（`.ko`）不存在也会在无警告的情况下完成（准确地说会出现 `System.map` 缺失的警告，但无法从中判断出是因为未执行构建）。

```makefile
install:
	$(Q)$(MAKE) -C $(KERNEL_DIR) M=$(PWD) INSTALL_MOD_DIR=kernel/drivers/misc modules_install
	$(Q)$(DEPMOD) -a

all: $(TARGET_DIR) print-versions
	$(Q)$(MAKE)  -C $(KERNEL_DIR) M=$(PWD) $(GDB_FLAG) $(USER_FLAGS) modules
	$(Q)cp $(DRIVER_NAME_NO_EXT)* $(TARGET_DIR)
```

**务必按 `make all && sudo make install` 的顺序执行。**

### 3.2 Raspberry Pi 的内核头文件未附带 `System.map`

执行 `modules_install` 时会出现以下警告，`depmod` 会被静默跳过：

```
Warning: modules_install: missing 'System.map' file. Skipping depmod.
```

原因是 `/usr/src/linux-headers-<kernelver>/System.map` 不存在。`/boot/System.map-<kernelver>` 是存在的，复制过去即可解决：

```bash
sudo cp /boot/System.map-$(uname -r) /usr/src/linux-headers-$(uname -r)/System.map
sudo depmod -a
```

不这样做的话，`modprobe` 将无法解析新安装的 `.ko`，会报 `FATAL: Module hailo1x_pci not found`（尽管 `.ko` 文件本身确实存在于 `/lib/modules/<kernelver>/kernel/drivers/misc/` 下）。

### 3.3 udev 规则不 reload/trigger 就不会立即生效

`/lib/udev/rules.d/51-hailo-pcie-udev.rules`:

```
SUBSYSTEM=="hailo1x", MODE="0666"
```

模块替换后 `/dev/h1x-0` 会立即变为 `crw-------`（仅限 root 访问）。可用以下方式解决：

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=hailo1x
```

### 3.4 驱动与库的版本不一致是致命的

仅将内核驱动升级到 5.4.0 的状态下执行 `hailortcli` 会出现：

```
dmesg: Mismatch Driver version pcie driver 5:4:0 pci_ep driver 5:3:0
dmesg: hailo_soc_get_driver_info has failed with err -22

hailortcli: [HailoRT] [error] CHECK failed - Driver version (5.4.0) is different from library version (5.3.0)
hailortcli: [HailoRT] [error] Driver version mismatch, status HAILO_INVALID_DRIVER_VERSION(76)
```

HailoRT 库要求与内核驱动**完全一致**，只要单方面先行升级，全部 API 调用都会被立即拒绝。仅驱动本身无法进行 vanilla 验证，`hailort`（SDK 本体）的用户空间包也必须同时升级。

- `apt-cache policy hailort` → 候选版本为 5.3.0（截至当日，官方 apt 尚未分发 5.4.0）
- `gh api repos/hailo-ai/hailort/releases` → `v5.4.0` 标签存在，但 `assets` 为空（无预构建 deb，仅有源码）

也就是说，**除非通过 deb 安装 HailoRT 本体或从源码完整构建，否则无法对 5.4.0 进行实地验证**。完整构建将是 C++ CMake + Python 绑定的大工程，还可能牵连 `hailo-tappas`、`python3-hailort` 等依赖包，因此第1回暂时搁置，判断等待官方 deb 分发。

---

## 4. 自行构建步骤记录（2026-08-17，第2回试验）

不等待 apt/官方 deb 的分发，而是从 GitHub 源码（driver：GPL-2.0，`hailort` 本体：MIT）自行构建并部署到系统时的步骤与遇到的问题。

### 4.1 构建环境

- 引入了 `checkinstall`（`sudo apt-get install -y checkinstall`）。但由于内核模块的 `xz` 压缩步骤与 `installwatch`（checkinstall 基于 LD_PRELOAD 的文件追踪机制）冲突，经由 checkinstall 执行 `make install` 每次都会以 `xz: ... 没有那个文件或目录` 失败。**内核模块的打包不要使用 checkinstall，应使用 dkms（驱动本体的情况）或单纯的 `make install`（用户空间库的情况）**
- 构建前腾出内存：暂停了 `headroom mcp serve` 的重复进程以及 `rust-analyzer`（共释放约 1GB 内存不到）。Pi 的内存为 7.9Gi，构建过程中 available 也维持在约 3.8Gi

### 4.2 `hailort`（用户空间库）构建

```bash
git clone --branch v5.4.0 --depth 1 https://github.com/hailo-ai/hailort.git
cd hailort/build   # 先创建目录
cmake .. -DCMAKE_BUILD_TYPE=Release   # 通过 FetchContent 自动获取外部依赖（protobuf/spdlog/eigen 等），约4分钟
cmake --build . -j2   # 限制为 -j2（避免内存紧张），约15分钟
sudo make install     # 部署到 /usr/local/{include,lib,bin}。可与 apt 版本（5.3.0, /usr 下）共存
```

各项 `option()` 默认值均为关闭（GStreamer・测试・服务端・Ollama 联动等重量级组件均为 OFF），因此仅构建了 `libhailort.so`、`hailortcli`、`libhailopp`，是相对轻量的配置。

**注意**：`make install` 的产物进入 `/usr/local` 下，不会覆盖 apt 版本（`/usr` 下，5.3.0）。核对动作时需要显式指定路径，例如 `LD_LIBRARY_PATH=/usr/local/lib /usr/local/bin/hailortcli ...`。

### 4.3 driver（内核模块）替换与 firmware 更新

driver 本身经由 dkms（与附录 A 的复原步骤相同要领，替换为 `-v 5.4.0`）构建・安装，再用 `rmmod`/`modprobe` 重新加载。此时 `hailortcli` 报 `HAILO_DRIVER_OPERATION_FAILED(36)`，dmesg 上出现 `Mismatch Driver version pcie driver 5:4:0 pci_ep driver 5:3:0`，由此判明**设备上的固件（SoC 侧，pci_ep）也必须单独升级到 5.4.0**。

```bash
# 从官方 S3 获取 firmware（使用 driver 仓库自带的脚本）
bash hailort-drivers/download_firmware_hailo10h.sh
# 先备份现有 firmware 再替换为新版本
sudo cp -r /lib/firmware/hailo/hailo10h /lib/firmware/hailo/hailo10h.backup-5.3.0
sudo cp <展开先>/hailo10h_fw_5.4.0/* /lib/firmware/hailo/hailo10h/
sudo chown -R root:root /lib/firmware/hailo/hailo10h/
```

此后尝试模块重新加载（包括 `rmmod`/`modprobe`、指定 `support_soft_reset=1`），但 dmesg 始终一贯返回 `SOC Firmware batch was already loaded`。确认驱动源码后发现，`load_soc_firmware()`（Hailo-10H 的 SoC 固件加载路径）并未实现基于 `support_soft_reset` 的软复位处理（该处理仅在 Hailo-8 的 `load_nnc_firmware()` 中实现），只要 `hailo_pcie_is_firmware_loaded()` 返回 true 就会被无条件跳过。也就是说，**SoC 上的固件状态无法通过模块重新加载来改变，必须对实机进行断电重启**。

重启后，dmesg 记录了固件批次写入（依次为 `customer_certificate.bin`・`scu_fw.bin`・`u-boot-*.dtb.signed`・`u-boot-spl.bin`・`fitImage`・`image-fs`，耗时 4064ms）→ `SOC Firmware Batch loaded successfully`，`hailortcli fw-control identify` 也正常返回了 `Firmware Version: 5.4.0 (release,app)`。

### 4.4 简易 CMA 行为核对与局限性

用 `hailortcli run2`（resnet_v1_18.hef，`hailo_tutorials` 包自带的小型模型）执行了单次 load/run/exit，以及连续执行 8 次时的 `CmaFree`（`/proc/meminfo`）变化观测：

| 执行 | CmaFree (kB) |
|---|---|
| baseline（重启后立即） | 170464 |
| iter 1 | 134864 |
| iter 2 | 134144 |
| iter 3〜8 | 133744（无变化，趋于平稳） |

数次后即达到平稳，直至第 8 次都未观测到额外泄漏。但这只是经由 CLI 的单纯 load/run/exit（每次都是独立进程启动），与 `docs/development/development_docs/HAILO_FORUM_FOLLOWUP_CMA_INFERENCE_LEAK.md` 所报告的两个已知泄漏——(a) **同一进程内** `VDevice.release()`/模型重新加载时的未释放、(b) `generate_stream()`（LLM 推理）执行过程中的持续泄漏——都是不同的路径，因此该结果并不能作为"已解决"的证据。

本命的 repro（`tools/diag_hailo_cma_reclaim.py` 以及 forum-followup 文档记载的脚本）是经由 Python 的 `hailo_platform`（pyhailort）绑定加载 GenAI LLM 的方式，无法在原封不动的 5.4.0 环境下运行：

```
$ .venv 内的 hailo_platform 固定链接到 libhailort.so.5.3.0（用 ldd 确认）
$ 构建 VDevice() 时，driver(5.4.0)/library(5.3.0) 版本不一致，预计会对应到同样的 HAILO_INVALID_DRIVER_VERSION
```

此时尚未着手将 pyhailort（Python 绑定）从 5.4.0 源码重新构建并替换到 `.venv` 中，该工作在第3回试验（§5）中实施。

---

## 5. pyhailort 重新构建与 repro 再执行（2026-08-17，第3回试验）

本节记录第3回试验时点的暂定判定。判定方法与结论已在第4回 A/B 试验（§8）中被订正。

### 5.1 pyhailort（Python 绑定）构建

`hailort` 本体仓库中的 `hailort/libhailort/bindings/python/platform/` 是 pyhailort 的 pip 包源码（`pyproject.toml`，基于 scikit-build-core + pybind11）。显式链接 §4.2 中已部署到 `/usr/local` 的 libhailort 5.4.0 进行构建：

```bash
cd hailort/libhailort/bindings/python/platform
CMAKE_ARGS="-DLIBHAILORT_PATH=/usr/local/lib/libhailort.so.5.4.0 -DHAILORT_INCLUDE_DIR=/usr/local/include" \
  <venv>/bin/python -m pip install .
```

在 build isolation 内从 PyPI 自动获取 `scikit-build-core`/`pybind11` 并构建，将 `.venv` 的 `hailort` 从 5.3.0 wheel 替换为 5.4.0 wheel。用 `ldd` 确认 `_pyhailort*.so` 已链接到 `/usr/local/lib/libhailort.so.5.4.0`，`VDevice()` 的 construct/release 单独测试也均正常工作。

### 5.2 既有 repro（`tools/diag_hailo_cma_reclaim.py`）的再执行

使用与 2026-05 相同的 repro 脚本、相同的判定标准、相同的 HEF（`~/hailo_models/Qwen3-1.7B-Instruct.hef`），在将 `.venv` 的 `hailo_platform` 替换为 5.4.0 的同一环境下重新测量：

```bash
uv run python tools/diag_hailo_cma_reclaim.py --signal terminate
```

结果（`logs/hailo_cma_reclaim_poc.json`）：

| 事件 | CmaFree (MB) |
|---|---|
| baseline_before_spawn | 159 |
| after_vdevice_created / after_llm_loaded | 22（消耗 137 MB） |
| child kill (`terminate`) 后立即 | 23 |
| post_wait +5s | 26 |
| post_wait +10s | 28 |
| post_wait +15s | 29 |
| post_wait +20s〜+30s | **0**（从 29 MB 进一步下降约 28.5 MB，此后经过数分钟 `CmaFree` 依旧贴在 512 kB 附近不动） |

这次从 29 MB → 512 kB 附近的再次下降，未能确认是与同时段其他进程的竞争有关，但仅凭本次测量无法特定原因，作为未解明的观测记录保留。仅凭初次加载后的页缓存利用（§8.4）无法说明这一中间过程，且本次执行没有同时采集 RSS、`MemAvailable`、分配失败的反复试验，因此不用作 §8 最终判定的依据。

不过，这个 512 kB 附近的数值与 §8.3 中 `FOLL_LONGTERM` 试验中观测到的 464→1,648 kB 属于同一带宽，从该状态出发的 20 次生成、释放、再加载均已成功。到达该低值的过程虽然仍未解明，但**该带宽的 `CmaFree` 本身并不直接意味着危险状态或无法加载**这一点已在实机上得到确认。

旧诊断工具输出的原文（第3回时点的暂定判定，最终判定已在 §8 中订正）：

```
VERDICT: FAIL — only -22 MB recovered after kill+wait. spec hypothesis invalid → pivot to auto-reboot alternatives
```

本次试验所能确定的，仅仅是首次 HEF 加载后的 `CmaFree` 按旧判定标准未能恢复这一事实。进程结束后的可用内存丧失，或 v5.4.0 泄漏未修复，均未被证实。第3回曾暂定解读为未释放，但该解读与判定方法已在 §8 中订正。

---

## 6. 第3回试验中的内核崩溃与 CMA 调试代码的复原（2026-08-17）

### 6.1 事件与原因候选

为调查 CMA 的释放路径，在本地 DKMS 源码的 `linux/vdma/memory.c` 中加入了 `linux/mm.h` 的 include，以及在 `dma_free_coherent()` 调用前调用 `virt_to_page()` / `page_count()` 的测量代码。加载包含此变更的模块后，使用 Hailo 时发生挂起，无法启动，目前通过 `/boot/firmware/cmdline.txt` 中的 `module_blacklist=hailo1x_pci,hailo_pci` 阻止其自动加载。

对 `dma_alloc_coherent()` 返回的 CPU 虚拟地址直接用 `virt_to_page()` 转换为页面，并不属于 DMA API 的契约。返回地址的映射形式由 allocator 一方决定，因此由此得到的 `page_count()` 并非正确观测 CMA 引用计数的手段，有可能产生非法的页面引用。该测量代码在 descriptor list 与 continuous buffer 两条释放路径中都会执行。

代码添加时刻为 10:15:36，对应的 DKMS 构建开始时刻为 10:15:39，可判断挂起的模块中包含了该代码。由于未能取得崩溃前的堆栈跟踪，并非严格意义上的原因确定，但这是相对于原版 v5.4.0 唯一的本地实际执行代码变更，因此列为最有力的原因候选。

### 6.2 复原后的状态

已删除以下 7 行（`linux/mm.h` 的 include、两处 `virt_to_page()` / `page_count()` 日志），并重新构建 DKMS 直至完成 `depmod`。

- 内核：`6.18.39+rpt-rpi-2712`
- 重新构建的模块：`/lib/modules/6.18.39+rpt-rpi-2712/updates/dkms/hailo1x_pci.ko.xz`
- `modules.dep` 中已登记上述模块
- blacklist 维持有效，重新构建的模块尚未加载

下一步将在确保串口控制台等复原路径后解除 blacklist，通过重启确认首次加载。对于 CMA 未释放问题本身的调查，将不再重新引入把 DMA API 返回地址转换为内部页面的测量方式，改以观测驱动持有的缓冲区台账、分配大小、`dma_free_coherent()` 调用次数为对象。

**补记（2026-08-17 后续）**：在准备好 `cmdline.txt` 备份（`cmdline.txt.bak-blacklisted`）后解除 blacklist 并重启，确认已正常启动（串口控制台 `console=serial0,115200` 也已配置好，复原路径已确保）。此后以 §7 中安全的插桩方式（不检查原始页面，仅输出既有计数器与大小的日志）继续调查。

---

## 7. 原因假设的形成与排除 — `FOLL_LONGTERM` 的验证与反证（2026-08-17）

本节记录承接第3回试验而形成的原因假设，以及通过实验能够排除的原因候选。此处的作用是候选的收窄，CMA 泄漏有无的最终判定依赖于第4回 A/B 试验（§8）。

基于 §6 的崩溃教训，以避免直接访问 `virt_to_page()` 等页面内部的安全插桩（仅用 `dev_err()` 输出日志，不检查・转换原始指针）继续进行调查。

### 7.1 插桩内容

在 `linux/vdma/memory.c` / `linux/vdma/ioctl.c` / `linux/vdma/vdma.c` 的以下位置，添加了输出既有原子计数器（`controller->desc_cma_in_use` / `controller->cma_in_use`）与分配大小的日志（完全不访问页面内部）：

- `hailo_desc_list_create`/`hailo_desc_list_release`（descriptor list 的 alloc/free）
- `hailo_vdma_continuous_buffer_alloc`/`hailo_vdma_continuous_buffer_free`（continuous buffer 的 alloc/free）
- `hailo_desc_list_release_ioctl`/`hailo_vdma_continuous_buffer_free_ioctl`（显式释放 ioctl 路径）
- `hailo_vdma_buffer_map`/`hailo_vdma_buffer_destroy`（用户空间缓冲区的 DMA 映射・解除映射路径。同时输出 `buffer_type`/`is_mmio`/`is_dmabuf`）
- `hailo_vdma_file_context_finalize`（fops_release 时的批量清理，在 ENTER/EXIT 输出计数器）

### 7.2 观测结果

从重启后立即（`CmaFree` ≈ 451 MB）执行 `tools/diag_hailo_cma_reclaim.py --signal terminate`，通过 `sudo dmesg | grep CMA_DBG` 回收并汇总了全部日志。

- **`/proc/meminfo` 的 `CmaFree`**：451 MB → 195 MB（**消耗 256 MB**）→ kill+30秒等待后仍为 204 MB（**比 baseline 低 247 MB**）
- **驱动自身的 `desc_cma_in_use`（descriptor list，经由 `dma_alloc_coherent`）**：最大也仅 2〜4 MB 左右。在 `file_context_finalize` 的 EXIT 时点确实回到了 0
- **`cma_in_use`（continuous buffer，经由 `dma_alloc_coherent`）**：本次会话中始终为 0（continuous buffer 一次都没有被使用）
- **用户空间缓冲区的 DMA 映射（`hailo_vdma_buffer_map`，`buffer_type=0`=`HAILO_DMA_USER_PTR_BUFFER`，`is_mmio=0`，`is_dmabuf=0`）**：被调用 621 次，其中 **342 次为 8 MB（`0x800000`）大小**（合计 2.7 GB 的映射调用。推测是同一份主机侧暂存缓冲区在管线处理中被反复复用）。`hailo_vdma_buffer_destroy` 被调用 628 次，与 `buffer_map` 几乎一一对应，**驱动自身的映射台账并未失衡**（`dma_unmap_sg` 被正确调用）
- **SWIOTLB（`/sys/kernel/debug/swiotlb/`）**：`io_tlb_used_hiwater=0`。反弹缓冲区一次都没有被使用
- Hailo 设备不在 IOMMU 之下（`/sys/bus/pci/devices/0001:01:00.0/iommu_group` 不存在）

此时，CMA 下降的原因候选被解读为并非 `dma_alloc_coherent()` 系统的驱动自身分配（desc list・continuous buffer），而是 `hailo_vdma_buffer_map()` 所处理的"将用户空间已分配的既有内存映射为 DMA 用"这一路径（`HAILO_DMA_USER_PTR_BUFFER`）。此路径中驱动并不新分配 CMA，而是为了让既有用户页面可供 DMA 使用而将其固定（pin）。

### 7.3 原因假设：`get_user_pages()` 未指定 `FOLL_LONGTERM`

确认 `linux/vdma/memory.c` 中的 `prepare_sg_table()`（在 `hailo_vdma_buffer_map()` 内部被调用）后发现：

```c
pinned_pages = compat_get_user_pages(user_address, npages, FOLL_WRITE | FOLL_FORCE, pages);
```

`compat_get_user_pages`（由于本内核 6.18.39 符合 `LINUX_VERSION_CODE >= KERNEL_VERSION(6, 5, 0)`）只是 `get_user_pages()` 的别名，**未指定 `FOLL_LONGTERM` 标志**。释放侧（`clear_sg_table()`）也调用对应的 `put_page()`，仍然沿用旧式的 `get_user_pages()`/`put_page()`，而非较新的 `pin_user_pages()`/`unpin_user_pages()` API 体系。

按照 Linux 内核文档化的做法（`Documentation/core-api/pin_user_pages.rst`），像 DMA 传输那样**需要长时间保持页面引用的代码应当使用带 `FOLL_LONGTERM` 的 `pin_user_pages()`**。若不指定 `FOLL_LONGTERM`，即便碰巧位于 CMA 区域内的用户页面被 `get_user_pages()` 固定，CMA 本应具备的"必要时可迁移至其他用途（migratable）"这一性质也会在很长一段时间内失效。CMA allocator 通常会在长期固定前将该页面迁移出 CMA 区域，但在不使用 `FOLL_LONGTERM` 的路径中这一迁移不会发生，因此**固定期间该部分实质上从 CMA 中丧失，释放（`put_page()`）后也不会立即被识别为 CMA 的空闲区域**（因为还需要另外的迁移・整理（compaction）过程）。

该假设与第3回时点的单次测量（§7.2）是吻合的：
- 驱动自身的 CMA 计数器与之无关（`get_user_pages` 不经由 `dma_alloc_coherent`）
- map/destroy 调用次数正确平衡（`put_page()` 本身被正确调用。问题在于释放后向 CMA 的"回归"缓慢/不完整）
- 加载像 Qwen3-1.7B-Instruct 这样的大型 LLM 时，会在主机内存上分配・DMA 映射大量 8 MB 缓冲区，若其中一部分包含 CMA 区域内的页面，本问题就会显现
- 与 kill 后 `CmaFree` 缓慢且部分的恢复（30秒内约恢复 +15〜30MB，此后数分钟内也缓慢增加）也是吻合的（`put_page()` 本身在进程结束时确实会被调用，但作为 CMA 空闲区域的回收似乎还需要额外的处理）

### 7.4 修复候选的实现与实机验证 → 反证（2026-08-17 续报）

将 `prepare_sg_table()` 从 `get_user_pages(FOLL_WRITE | FOLL_FORCE)` + `put_page()` 实际替换为 `pin_user_pages(FOLL_WRITE | FOLL_FORCE | FOLL_LONGTERM)` + `unpin_user_page()`，并追加 `<linux/mm.h>` 的 include，完成了构建・dkms 重新注册・实机加载（已用 `modprobe --dump-modversions` 确认 `pin_user_pages`/`unpin_user_page` 符号被正确解析）。

从重启后立即的高 `CmaFree`（453 MB）状态开始执行相同 repro，结果如下：

| | 修复前（n=多次运行） | 修复后（n=1） |
|---|---|---|
| baseline | 436〜451 MB | 453 MB |
| after_llm_loaded | 173〜195 MB（消耗 256〜263 MB） | 180 MB（消耗 273 MB） |
| after_post_wait | 188〜204 MB（回收 9〜15 MB） | 190 MB（**回收 10 MB**） |
| 按旧判定标准得出的 `VERDICT` | `FAIL` | **`FAIL`（无变化）** |

> 该表中运行次数与汇总方法并不对称，并非严格的 A/B 比较。A/B 的判定以在相同条件下反复执行的 §8 结果为准。

用 `dmesg` 确认 `CMA_DBG buffer_map` 后发现，修复后同样的 0x800000（8 MB）大小缓冲区也经由 `pin_user_pages` 顺利完成映射（未出现 pin 失败或内核警告），代码路径本身按预期执行。通过 `echo 1 > /proc/sys/vm/compact_memory` 强制整理（compaction）也无效果。`MemAvailable` 依旧健康地保持在 7.1 GB，说明并非系统整体内存不足，而是只有 `CmaFree` 这一特定会计项无法恢复，这一点与修复前相同。

**结论：`FOLL_LONGTERM` 缺失假设已被实验反证。** 从 `get_user_pages()` 换成 `pin_user_pages()`+`FOLL_LONGTERM` 虽然符合 Linux 内核文档化做法、是正当的改进，但并非本次会话中观测到的 CMA 未释放症状的直接原因。该假设本身在理论上是成立的（CMA 的迁移机制与长期固定之间的相互作用确实是已知的一类问题），作为代码质量方面的建议依然有效，但**并非能单独解释本次实测结果的根本原因**。

### 7.5 原因候选的排除（最终判定见 §8）

以下是通过实验能够明确**排除**的原因候选。这份清单作为假设验证的成果是有效的，但并不等于泄漏有无的判定本身。

- 驱动自身经由 `dma_alloc_coherent()` 的分配（desc list・continuous buffer）— 仅数 MB，正确归零
- SG 映射的 map/destroy 调用不一致 — 已平衡
- SWIOTLB 反弹缓冲区 — 一次都未被使用（`io_tlb_used_hiwater=0`）
- `get_user_pages()` 缺失 `FOLL_LONGTERM` — 已实现修复并在实机验证，但无改善

第3回试验结束时留下的事实是，`MemAvailable` 保持健康的同时，`CmaFree` 在首次加载后下降。当时将其解读为未释放，但单次试验无法区分"可用内存丧失"与"movable CMA 页面被挪用于页缓存"。第4回在低 `CmaFree` 状态下重新试验，通过实际的可加载性、反复时的净减少量、RSS、CMA 分配失败等测量订正了该判定。

---

## 8. 第4回试验：vanilla / `FOLL_LONGTERM` A/B 追加试验与误判定的确定（2026-08-17）

### 8.1 比较对象

- `FOLL_LONGTERM` 修复版：`pin_user_pages(FOLL_LONGTERM)` / `unpin_user_page()`，加载时 `srcversion=C84A00ABB326748A1832CE1`
- 官方 vanilla 5.4.0：标签 `v5.4.0`，commit `b6dd17c609504e648eb516ff4a867167edf56f3c`，`get_user_pages()` / `put_page()`，加载时 `srcversion=A260C39C9F2C06DD4FB072E`
- 内核：`6.18.39+rpt-rpi-2712`
- HEF：`Qwen3-1.7B-Instruct.hef`（2,880,748,478 字节）

### 8.2 独立进程下的连续两次加载

| 驱动 | 试验 | baseline | loaded | exit后 | 相对 baseline 增减 | 加载 |
|---|---:|---:|---:|---:|---:|---|
| `FOLL_LONGTERM` | 1 | 338 MB | 34 MB | 25 MB | **-313 MB（减少）** | 成功 |
| `FOLL_LONGTERM` | 2 | 5 MB | 6 MB | 7 MB | **+2 MB（增加）** | 成功 |
| vanilla | 1 | 376 MB | 99 MB | 112 MB | **-264 MB（减少）** | 成功 |
| vanilla | 2 | 125 MB | 118 MB | 124 MB | **-1 MB（减少）** | 成功 |

两种驱动均仅在首次出现 `CmaFree` 大幅下降，从该较低值开始的第2次加载均能成功，净减少量几乎为 0。以往的诊断仅以"加载过程中消耗的量中有多少被回收"作为判定标准，因此像第2次那样起始时点 `CmaFree` 已经较低的正常情况，也被错误地判为 `FAIL`。

### 8.3 同一进程内的生成・释放・再加载

| 指标 | `FOLL_LONGTERM` | vanilla 第1次 | vanilla 低 CMA 反复 |
|---|---:|---:|---:|
| 生成完成 | 20/20 | 20/20 | 20/20 |
| 第1次加载 | 成功 | 成功 | 成功 |
| 释放后的第2次加载 | 成功 | 成功 | 成功 |
| 生成1→20 的 `CmaFree` | 464→1,648 kB | 115,376→123,728 kB | 82,320→83,296 kB |
| 生成1→20 的 `MemAvailable` | 6,706,208→6,788,432 kB | 6,830,352→6,910,560 kB | 6,871,504→6,906,368 kB |
| 生成过程中 RSS | 固定为 63,888 kB | 63,904〜63,920 kB | 63,936〜63,952 kB |
| CMA 分配失败 | 0 | 0 | 0 |

vanilla 低 CMA 反复从 `CmaFree=87,424 kB` 开始，全部释放后立即为 79,520 kB，之后恢复至 87,344 kB（净差 80 kB）。反复进行加载・生成・释放并不会出现持续丧失的行为。vanilla 的 `nr_foll_pin_*` 为 0 是因为不使用 `FOLL_PIN` API，无法用于比较 pin 释放成功与否。

### 8.4 首次下降的解释

从 vanilla 重启后立即到全部追加试验后，`Cached` 从 1,845,872 kB 增至约 4,988,224 kB，而 `MemAvailable` 从 7,071,280 kB 维持在约 6,962,816 kB。增加量与 multi-GB HEF 的读取相符，可以说明首次 `CmaFree` 下降并非不可访问内存的丧失，而是包含 movable CMA 页面在内的空闲页面被用于页缓存。

### 8.5 运用上的结论

1. 不应仅凭 `CmaFree` 绝对值拒绝模型加载。实机上即使从不足 1 MB 出发，Qwen 加载也曾成功。
2. 低 `CmaFree` 应作为遥测数据记录，将实际的 HailoRT 内存分配错误用作失败判定标准。
3. 不应混淆 `CmaFree` 的观测值、实际加载失败、泄漏诊断，应按以下 3 种状态区分处理。

| 状态 | 判定条件 | 产品侧处置 | 重启・调查 |
|---|---|---|---|
| `INCONCLUSIVE` | 仅首次下降、不足3次，或不满足下述 `FAIL` 条件 | 记录遥测数据并尝试加载。不应仅凭低 `CmaFree` 单独拒绝 | 不重启。在相同条件下追加测量 |
| `OPERATIONAL_FAIL` | HailoRT 实际返回了 host-memory allocation error | 仅将该次加载请求判为失败，停止不必要的 Hailo workload 后重试 | 单次不重启。仅当实际失败反复出现，且释放 workload 后仍无法恢复时，才按运营策略处理。当前 Phase 0.5 仅记录 `would_fire`，不自动重启 |
| `FAIL` | 在低 CMA 状态下相同条件反复3次，且释放后相对 baseline 的净减少量在 **3次中有2次以上单次超过 10 MB**、3次的正净减少量合计**超过 20 MB**，并伴随 RSS 单调增加或 `MemAvailable` 下降超过 128 MB | 作为与单次加载可否不同的泄漏诊断记录 | 重新开始内核 / HailoRT 侧调查，采集直接证据。仅诊断成立本身不触发自动重启 |

该 3 次基准为今后诊断所用，不追溯适用于本节 §8.2 中每种驱动各仅试验 2 次的独立进程试验。第4回的结论综合了 §8.2 的 A/B 试验，以及 §8.3 的同一进程 20 次生成・释放・再加载和低 CMA 反复试验。
4. `FOLL_LONGTERM` 替换作为 Linux DMA API 的一般做法是妥当的，但对本问题没有效果，实机已恢复为官方 vanilla 5.4.0。
5. 自动重启判定不应仅凭低 `CmaFree` 单独触发，须以观测到实际加载失败为必要条件。

---

## 9. 今后的行动（2026-08-17 时点）

1. `FOLL_LONGTERM` 修复的探讨与实机反证已完成。用于复现的差异与复原方法保存于附录 B，不会应用于生产驱动。
2. **产品侧已完成对应**：`core/hailo_device_core/device_manager_genai.py::acquire_genai` 已在 v4.620.8 中改进，即使 `CmaFree` 低于预估所需量，也会记录 `acquire_low_cma_observed` 并继续执行实际加载。仅记录 factory 实际返回的 HailoRT host-memory error 到拒绝 tracker，`tests/test_hailo_cma_false_positive.py` 已固定住了从低值继续加载的行为。
3. 已用日志与旧实现重新核查旧论坛草稿中"后续 `LLM(...)` 因 insufficient host CMA 而被 HailoRT 拒绝"的记述。引用来源的 PID 3237 会话中没有 release 后的 acquire 记录，同日日志中能追踪到的低 CMA 拒绝，全部都是 HailoRT 调用之前的自有事件 `acquire_rejected_low_cma`。另一会话中到达 factory 的失败为 status 8（`HAILO_INTERNAL_FAILURE`），并非 host-memory error 的 status 3。因此没有能够支持旧记述的 HailoRT OOM 证据，`docs/development/development_docs/HAILO_FORUM_FOLLOWUP_CMA_INFERENCE_LEAK.md` 明确记载了自有守卫导致的拒绝被混入报告这一事实，并予以撤回。
4. 订正投稿将 §8 的数值・适用范围、实现守卫的订正、`FOLL_LONGTERM` 反证、插桩相关的告诫整合到一份现行草稿中，不再保留可复制的旧英文草稿。
5. 仅当实际加载失败，或每次反复出现累积性的可用内存丧失得到再现时，才重新开始内核 / HailoRT 侧的泄漏调查。届时应采集 `page_owner`、CMA debug 信息、分配失败 status、RSS、`MemAvailable` 等直接证据。

---

## 附录 A. 复原到 v5.3.0 的步骤

从 dkms 执行一次 `remove --all` 后进行复原时，若 apt 缓存中没有残留 `.deb`，`apt-get install --reinstall` 会失败（本次也失败了：`无法下载，因此无法重新安装`）。dpkg 仍将 `hailort-pcie-driver` 包识别为 `ii`（已安装）状态，因此只要包的源码展开目的地 `/usr/src/hailort-pcie-driver/` 未被删除，就可以从那里手动重建 dkms 树：

```bash
sudo rmmod hailo1x_pci

sudo rm -rf /usr/src/hailo1x_pci-5.3.0
sudo cp -r /usr/src/hailort-pcie-driver /usr/src/hailo1x_pci-5.3.0
sudo sed 's/@PCIE_DRIVER_VERSION@/5.3.0/' \
  /usr/src/hailo1x_pci-5.3.0/linux/pcie/dkms.conf.in \
  | sudo tee /usr/src/hailo1x_pci-5.3.0/linux/pcie/dkms.conf > /dev/null

# dkms.conf must be placed directly under the tree root (an error occurs if left under linux/pcie/)
sudo cp /usr/src/hailo1x_pci-5.3.0/linux/pcie/dkms.conf /usr/src/hailo1x_pci-5.3.0/dkms.conf

sudo dkms add -m hailo1x_pci -v 5.3.0
sudo dkms build -m hailo1x_pci -v 5.3.0 -k $(uname -r)
sudo dkms install -m hailo1x_pci -v 5.3.0 -k $(uname -r) --force
sudo depmod -a
sudo modprobe hailo1x_pci
sudo udevadm trigger --subsystem-match=hailo1x
```

复原确认：

```bash
cat /sys/module/hailo1x_pci/version   # → 5.3.0
hailortcli fw-control identify        # → 正常应答即复原完成
```

---

## 附录 B. 反证实验用驱动补丁的保存・应用・vanilla 复原步骤

### B.1 保存物与定位

将 A/B 实际使用的驱动差异原样保存到以下文件。

- `docs/development/patches/hailo1x_pci-5.4.0-foll-longterm-cma-debug-experiment.patch`
- SHA-256: `7b5c4027f37432dbbbe39e4bdec2f0f5e8dd87e133473b5a44c44b1e86c5503f`
- 基准源码：`hailo-ai/hailort-drivers` 标签 `v5.4.0`，commit `b6dd17c609504e648eb516ff4a867167edf56f3c`
- 对象文件：`linux/vdma/ioctl.c`、`linux/vdma/memory.c`、`linux/vdma/vdma.c`

此 patch 不仅包含替换为 `pin_user_pages(FOLL_LONGTERM)` / `unpin_user_page()`，还包含 §7.1 中使用的 `CMA_DBG` 插桩。也就是说，这是用于复现 A/B 时实验模块的**验证用完整差异**，并非生产推荐 patch。实验中未确认有效果，当前实机已复原为官方 vanilla 5.4.0。HailoRT 用户空间库未做任何更改。

在相同内核・源码・构建环境下确认的识别值如下。

| 状态 | `srcversion` |
|---|---|
| 实验 patch | `C84A00ABB326748A1832CE1` |
| 官方 vanilla 5.4.0 | `A260C39C9F2C06DD4FB072E` |

### B.2 应用前的确认

以下操作仅在 Raspberry Pi 上的 `/usr/src/hailo1x_pci-5.4.0` 指向上述官方 commit，且对象 3 个文件没有本地改动的情况下才可执行。若 commit、patch checksum、vanilla `memory.c` checksum 有任一项不一致，应停止操作，不得强行应用 patch。

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

### B.3 实验 patch 的应用

仅当全部确认成功时，才应用 patch，将 DKMS 模块安装为下次启动使用。不通过 `rmmod` / `modprobe` 手动切换正在加载的模块，而是构建后通过常规重启进行切换。

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

`modinfo` 表示的是安装为下次启动使用的模块，`/sys/module/.../srcversion` 表示的是当前已加载的模块。此时两者数值不同属于正常状态。准备就绪后重启，启动后确认两者一致。

```bash
sudo reboot

# 重新连接后
modinfo -F srcversion hailo1x_pci
head -n 1 /sys/module/hailo1x_pci/srcversion
```

在相同验证环境下，应用 patch 后的期望值为 `C84A00ABB326748A1832CE1`。若不一致，不应凭猜测继续试验，应核查源码差异、内核、DKMS 构建日志。

### B.4 复原到官方 vanilla 5.4.0

复原不依赖 patch 的逆应用，而是从已验证的 commit 明确恢复对象 3 个文件。这样可以避免出现部分应用或仅残留插桩的状态。

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

在相同验证环境下，安装完成的 vanilla 模块期望值为 `A260C39C9F2C06DD4FB072E`。确认当前已加载的值与之不同后再重启，重新连接后确认两者均为 `A260C39C9F2C06DD4FB072E`。

---

## 参考：相关文档

- `docs/development/development_docs/HAILO_FORUM_FOLLOWUP_CMA_INFERENCE_LEAK.md` — 基于旧测量的 CMA 泄漏实测数据・repro 脚本・论坛投稿草稿（结论已在本文档 §8 中订正）
- [HAILORT_5_3_0_MIGRATION.md](HAILORT_5_3_0_MIGRATION.md) — v5.2.0 → v5.3.0 迁移时的记录（设备节点名变更为 `/dev/h1x-0` 等）
- [HAILO_CMA_LEAK_HAILORT_5_3_0.md](HAILO_CMA_LEAK_HAILORT_5_3_0.md) — 基于旧诊断的 CMA 泄漏问题日语记录（结论已在本文档 §8 中订正）
- `hailo-ai/hailort-drivers` GitHub 仓库（GPL-2.0，源码公开）：<https://github.com/hailo-ai/hailort-drivers>
