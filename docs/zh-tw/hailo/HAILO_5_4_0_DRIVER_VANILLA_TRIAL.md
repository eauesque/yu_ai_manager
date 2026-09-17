# HailoRT / driver 5.4.0 CMA 未回收判定的訂正與驗證記錄

建立: 2026-08-16 / 最終更新: 2026-08-17 / 對應版本: yu_ai_manager 4.623.1

針對曾被判定為 CMA 未回收的事件（參見 `docs/development/development_docs/HAILO_FORUM_FOLLOWUP_CMA_INFERENCE_LEAK.md`），使用 `hailo-ai/hailort-drivers` v5.4.0（2026-08-16 公開、GPL-2.0、原始碼公開）進行假設驗證，以及官方 vanilla 版與 `FOLL_LONGTERM` 修正版的 A/B 試驗，訂正了量測端的誤判定，本文記錄該過程。

---

## 1. 結論

**2026-08-17 最終追加試驗（第4回）: 直到第3回為止的 `VERDICT: FAIL` 判定，是因僅以首次 HEF 載入後 `CmaFree` 的絕對回復量作為 leak 判定依據所導致的誤判定。將官方 vanilla 5.4.0 與 `FOLL_LONGTERM` 修正版進行 A/B 比較，從低 `CmaFree` 狀態連續載入、同一行程內的釋放與重新載入、20 次生成、以及從更低 `CmaFree` 狀態開始的全部試驗反覆，全數成功。生成過程中的 RSS 與 `CmaFree` 未出現單調增減，CMA 分配失敗次數為 0。首次載入時的 `CmaFree` 下降，與 multi-GB HEF 造成的頁面快取增加相符，`MemAvailable` 維持在約 7GB。本次試驗使用 Pi 5 + Hailo-10H + HailoRT/driver 5.4.0、單一模型、單一裝置、短時間反覆的條件下，實務上的 CMA leak 未再現，`FOLL_LONGTERM` 修正亦無可量測的改善。長時間連續運作、多個模型同時使用、Hailo-8、IOMMU 環境下皆未經測試，超出本結論的適用範圍。**

### 1.1 判定的變遷

| 回 | 日期 | 當時的判定 | 更新・訂正依據 |
|---|---|---|---|
| 第1回 | 2026-08-16 | 無法判定 | 僅將 driver 升級至 5.4.0 時，因與 library 5.3.0 之間的完全一致檢查，API 遭拒絕（§3） |
| 第2回 | 2026-08-17 | 僅完成有限試驗 | driver / library / firmware 皆對齊 5.4.0，`run2` 反覆已趨於平台化，但尚未透過 pyhailort 進行直接 repro（§4） |
| 第3回 | 2026-08-17 | 暫定 `FAIL`（後判定為誤判） | 舊診斷結果僅以首次 HEF 載入後 `CmaFree` 的絕對回復量作為判定依據。單次量測無法區分記憶體喪失與頁面快取利用（§5、§7） |
| 第4回 | 2026-08-17 | 實務上的 leak 未再現 | 透過 vanilla / `FOLL_LONGTERM` A/B、低 CMA 反覆、同一行程重新載入、20 次生成、量測 RSS・`MemAvailable`・分配失敗，訂正了第3回的判定（§8） |

---

## 2. v5.3.0 → v5.4.0 原始碼差異（`hailo-ai/hailort-drivers`）

透過 GitHub API 對兩個 tag 之間的全部檔案進行 diff。由於採用單一 squash commit，無法從 commit message 讀取任何資訊，因此以實際檔案 diff 確認。CMA 分配・釋放的**邏輯本身**（`dma_alloc_coherent`/`dma_free_coherent` 配對）並無變更，以下以重構、防禦性修正為主:

| 檔案 | 變更內容 |
|---|---|
| `linux/utils/compact.h` → `compat.h` | 核心相容層的檔名重新命名 |
| `linux/vdma/memory.c` | 為 `hailo_desc_list_release()` 新增 NULL 檢查，釋放後將指標清為 NULL（**防止重複釋放**的防禦性修正） |
| `linux/vdma/vdma.h` | 從 `hailo_descriptors_list_buffer` 移除冗餘欄位 `kernel_address`（整合至 `desc_list.descs`） |
| `common/vdma_common.c` | 將 DMA 傳輸完成判定，從直接以 `hw_num_proc` 計算的方式，改寫為 `num_proc`/`num_avail` 比較方式（可能是傳輸完成追蹤的錯誤修正） |
| `linux/vdma/monitor.c` | `del_timer_sync` → `timer_delete_sync`（配合新版核心 API 名稱） |
| `common/pcie_common.c` | 從 FW 控制協定中移除 md5 欄位，SCU 記錄破損判定從僅檢查前 4 bytes 強化為檢查前 5 個 word 全體 |

錯誤訊息文字亦有變更（冗長說明文 → 簡化為 `out of CMA memory.`），但分配・釋放的控制流程相同。**僅從此 diff 無法讀出對應當時假設（模型重新載入時 CMA 未回收）的變更**。

---

## 3. 實機更換作業與遇到的問題（2026-08-16，第1回試驗）

以 Raspberry Pi 5 + Hailo-10H、運作中的 `hailo1x_pci 5.3.0`（由 dkms 管理）為對象，嘗試以手動建置方式更換至 v5.4.0。

### 3.1 `make install` 不依賴 `all`

`linux/pcie/Makefile` 的 `install` target 僅執行 `modules_install`，即使建置產物 (`.ko`) 不存在，也會在沒有警告的情況下完成（正確地說，會出現 `System.map` 缺失的警告，但無法從中得知原因是尚未建置）。

```makefile
install:
	$(Q)$(MAKE) -C $(KERNEL_DIR) M=$(PWD) INSTALL_MOD_DIR=kernel/drivers/misc modules_install
	$(Q)$(DEPMOD) -a

all: $(TARGET_DIR) print-versions
	$(Q)$(MAKE)  -C $(KERNEL_DIR) M=$(PWD) $(GDB_FLAG) $(USER_FLAGS) modules
	$(Q)cp $(DRIVER_NAME_NO_EXT)* $(TARGET_DIR)
```

**務必依 `make all && sudo make install` 的順序執行。**

### 3.2 Raspberry Pi 的核心標頭檔未附帶 `System.map`

執行 `modules_install` 時會出現以下警告，`depmod` 遭靜默跳過:

```
Warning: modules_install: missing 'System.map' file. Skipping depmod.
```

原因是 `/usr/src/linux-headers-<kernelver>/System.map` 不存在。由於 `/boot/System.map-<kernelver>` 存在，複製即可解決:

```bash
sudo cp /boot/System.map-$(uname -r) /usr/src/linux-headers-$(uname -r)/System.map
sudo depmod -a
```

若不執行此步驟，`modprobe` 將無法解析新安裝的 `.ko`，導致 `FATAL: Module hailo1x_pci not found`（即使 `.ko` 檔案本身確實存在於 `/lib/modules/<kernelver>/kernel/drivers/misc/`）。

### 3.3 udev 規則不 reload/trigger 就不會立即生效

`/lib/udev/rules.d/51-hailo-pcie-udev.rules`:

```
SUBSYSTEM=="hailo1x", MODE="0666"
```

模組更換後 `/dev/h1x-0` 會立即變為 `crw-------`（僅限 root）。以下可解決:

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=hailo1x
```

### 3.4 driver 與 library 版本不一致是致命問題

僅將核心 driver 升級至 5.4.0 的狀態下執行 `hailortcli`，會出現:

```
dmesg: Mismatch Driver version pcie driver 5:4:0 pci_ep driver 5:3:0
dmesg: hailo_soc_get_driver_info has failed with err -22

hailortcli: [HailoRT] [error] CHECK failed - Driver version (5.4.0) is different from library version (5.3.0)
hailortcli: [HailoRT] [error] Driver version mismatch, status HAILO_INVALID_DRIVER_VERSION(76)
```

HailoRT library 要求與核心 driver **完全一致**，僅單方先行升級會導致全部 API 呼叫立即被拒絕。無法單獨對 driver 進行 vanilla 驗證，必須同時升級 `hailort`（SDK 本體）的使用者空間套件。

- `apt-cache policy hailort` → 候選版本為 5.3.0（截至當日，官方 apt 尚未發布 5.4.0）
- `gh api repos/hailo-ai/hailort/releases` → 存在 `v5.4.0` tag，但 `assets` 為空（無已建置 deb，僅提供原始碼）

也就是說 **除非以 deb 安裝 HailoRT 本體，或從原始碼完整建置，否則無法對 5.4.0 進行實機驗證**。完整建置會涉及大規模的 C++ CMake + Python binding 建置作業，並可能牽連 `hailo-tappas`・`python3-hailort` 等依賴套件，因此第1回暫時擱置，判斷等待官方 deb 發布。

---

## 4. 自行建置手順記錄（2026-08-17，第2回試驗）

不等待 apt/官方 deb 發布，直接從 GitHub 原始碼（driver: GPL-2.0、`hailort` 本體: MIT）自行建置並導入系統時的手順與遇到的問題。

### 4.1 建置環境

- 導入 `checkinstall`（`sudo apt-get install -y checkinstall`）。然而核心模組的 `xz` 壓縮步驟與 `installwatch`（checkinstall 基於 LD_PRELOAD 的檔案追蹤機制）發生衝突，透過 checkinstall 執行 `make install` 每次都會以 `xz: ... そのようなファイルやディレクトリはありません`（找不到該檔案或目錄）失敗。**核心模組的封裝不應使用 checkinstall，應使用 dkms（driver 本體時）或純粹的 `make install`（使用者空間 library 時）**
- 建置前先確保記憶體: 暫停 `headroom mcp serve` 的重複行程及 `rust-analyzer`（共釋放約 1GB 不到）。Pi 的記憶體為 7.9Gi，建置過程中 available 仍維持在約 3.8Gi

### 4.2 `hailort`（使用者空間 library）建置

```bash
git clone --branch v5.4.0 --depth 1 https://github.com/hailo-ai/hailort.git
cd hailort/build   # 先建立目錄
cmake .. -DCMAKE_BUILD_TYPE=Release   # 透過 FetchContent 自動取得外部依賴(protobuf/spdlog/eigen等)，約4分鐘
cmake --build . -j2   # 限制為 -j2（避免記憶體吃緊），約15分鐘
sudo make install     # 安裝至 /usr/local/{include,lib,bin}。可與 apt 版(5.3.0, /usr 底下)共存
```

由於預設的 `option()` 值全部關閉了重量級元件（GStreamer、測試、伺服器、Ollama 整合等），因此僅建置 `libhailort.so`・`hailortcli`・`libhailopp`，屬於相對輕量的組成。

**注意**: `make install` 的成果物置於 `/usr/local` 底下，不會覆蓋 apt 版（`/usr` 底下，5.3.0）。確認運作時，需如 `LD_LIBRARY_PATH=/usr/local/lib /usr/local/bin/hailortcli ...` 般明確指定路徑。

### 4.3 driver（核心模組）更換與 firmware 更新

driver 本身透過 dkms（依附錄 A 的復原手順同樣要領，替換為 `-v 5.4.0`）建置・安裝，並以 `rmmod`/`modprobe` 重新載入。此時 `hailortcli` 出現 `HAILO_DRIVER_OPERATION_FAILED(36)`／dmesg 顯示 `Mismatch Driver version pcie driver 5:4:0 pci_ep driver 5:3:0`，得知 **裝置上的 firmware（SoC 端、pci_ep）也需另外升級至 5.4.0**。

```bash
# 從官方 S3 取得 firmware（使用 driver repository 附帶的腳本）
bash hailort-drivers/download_firmware_hailo10h.sh
# 備份既有 firmware 後替換為新版
sudo cp -r /lib/firmware/hailo/hailo10h /lib/firmware/hailo/hailo10h.backup-5.3.0
sudo cp <展開先>/hailo10h_fw_5.4.0/* /lib/firmware/hailo/hailo10h/
sudo chown -R root:root /lib/firmware/hailo/hailo10h/
```

此時嘗試重新載入模組（`rmmod`/`modprobe`，含指定 `support_soft_reset=1`），但 dmesg 持續回傳 `SOC Firmware batch was already loaded`。查閱 driver 原始碼後確認，`load_soc_firmware()`（Hailo-10H 的 SoC firmware 讀取路徑）並未實作以 `support_soft_reset` 進行軟重置的處理（僅 Hailo-8 的 `load_nnc_firmware()` 有實作），只要 `hailo_pcie_is_firmware_loaded()` 回傳 true 就會無條件跳過。也就是說 **SoC 上的 firmware 狀態無法透過模組重新載入變更，必須實機重新開機**。

重新開機後，dmesg 記錄了 firmware batch 的寫入（依序為 `customer_certificate.bin`・`scu_fw.bin`・`u-boot-*.dtb.signed`・`u-boot-spl.bin`・`fitImage`・`image-fs`，耗時 4064ms）→ `SOC Firmware Batch loaded successfully`，`hailortcli fw-control identify` 也以 `Firmware Version: 5.4.0 (release,app)` 正常回應。

### 4.4 簡易 CMA 行為確認與其限制

以 `hailortcli run2`（resnet_v1_18.hef，`hailo_tutorials` 套件附帶的小型模型）執行單次 load/run/exit，以及觀測連續執行 8 次時 `CmaFree`（`/proc/meminfo`）的推移:

| 執行 | CmaFree (kB) |
|---|---|
| baseline（重新開機直後） | 170464 |
| iter 1 | 134864 |
| iter 2 | 134144 |
| iter 3〜8 | 133744（無變化，平台化） |

數次後即達到平台化，直到第8次為止未觀測到額外的 leak。但這僅是透過 CLI 進行的單純 load/run/exit（各行程獨立啟動），與 `docs/development/development_docs/HAILO_FORUM_FOLLOWUP_CMA_INFERENCE_LEAK.md` 所報告的兩個已知 leak——(a) **同一行程內**的 `VDevice.release()`/模型重新載入時未回收、(b) `generate_stream()`（LLM 推論）執行過程中持續 leak——皆屬不同路徑，此結果無法作為「已解決」的證據。

真正的 repro（`tools/diag_hailo_cma_reclaim.py` 及 forum-followup doc 所記載的腳本）是透過 Python 的 `hailo_platform`（pyhailort）binding 載入 GenAI LLM 的方式，因此在 5.4.0 環境下無法直接執行:

```
$ .venv 內的 hailo_platform 固定連結至 libhailort.so.5.3.0（以 ldd 確認）
$ 建構 VDevice() 時，因 driver(5.4.0)/library(5.3.0) 版本不一致，預期會發生相同的 HAILO_INVALID_DRIVER_VERSION
```

此時尚未著手將 pyhailort（Python binding）從 5.4.0 原始碼重新建置並替換至 `.venv` 中，該作業已於第3回試驗（§5）執行。

---

## 5. pyhailort 重新建置與 repro 重新執行（2026-08-17，第3回試驗）

本節記錄第3回試驗時點的暫定判定。判定方法與結論已於第4回 A/B 試驗（§8）訂正。

### 5.1 pyhailort（Python binding）建置

`hailort` 本體 repository 中的 `hailort/libhailort/bindings/python/platform/` 為 pyhailort 的 pip 套件原始碼（`pyproject.toml`，基於 scikit-build-core + pybind11）。明確連結至 §4.2 已安裝於 `/usr/local` 的 libhailort 5.4.0 後進行建置:

```bash
cd hailort/libhailort/bindings/python/platform
CMAKE_ARGS="-DLIBHAILORT_PATH=/usr/local/lib/libhailort.so.5.4.0 -DHAILORT_INCLUDE_DIR=/usr/local/include" \
  <venv>/bin/python -m pip install .
```

在 build isolation 中自動從 PyPI 取得 `scikit-build-core`/`pybind11` 並建置，將 `.venv` 的 `hailort` 從 5.3.0 wheel 替換為 5.4.0 wheel。以 `ldd` 確認 `_pyhailort*.so` 已連結至 `/usr/local/lib/libhailort.so.5.4.0`，`VDevice()` 的 construct/release 單獨測試也正常運作。

### 5.2 既有 repro（`tools/diag_hailo_cma_reclaim.py`）重新執行

以與 2026-05 相同的 repro 腳本・相同的判定基準・相同 HEF（`~/hailo_models/Qwen3-1.7B-Instruct.hef`），在 `.venv` 的 `hailo_platform` 替換為 5.4.0 的相同環境下重新量測:

```bash
uv run python tools/diag_hailo_cma_reclaim.py --signal terminate
```

結果（`logs/hailo_cma_reclaim_poc.json`）:

| 事件 | CmaFree (MB) |
|---|---|
| baseline_before_spawn | 159 |
| after_vdevice_created / after_llm_loaded | 22（消耗 137 MB） |
| child kill (`terminate`) 直後 | 23 |
| post_wait +5s | 26 |
| post_wait +10s | 28 |
| post_wait +15s | 29 |
| post_wait +20s〜+30s | **0**（從 29 MB 再進一步下降約 28.5 MB，其後即使經過數分鐘，`CmaFree` 仍維持在 512 kB 附近） |

此次從 29 MB 再度下降至 512 kB 附近的現象，未能確認與同一時刻的其他行程競爭有關，僅憑此次量測無法特定原因，故作為尚未釐清的觀測結果保留。首次載入後的頁面快取利用（§8.4）無法單獨說明此中間過程，且本次執行並未同時採集 RSS・`MemAvailable`・分配失敗的反覆試驗數據，因此不作為 §8 最終判定的依據。

不過，此 512 kB 附近的數值，與 §8.3 `FOLL_LONGTERM` 試驗中觀測到的 464→1,648 kB 屬同一區間，而從該狀態出發，20 次生成、釋放、重新載入皆已成功。抵達低值的過程雖仍未釐清，但實機已確認 **此區間的 `CmaFree` 本身並不直接意味著危險狀態或無法載入**。

舊診斷工具輸出的原文（第3回時點的暫定判定，最終判定已於 §8 訂正）:

```
VERDICT: FAIL — only -22 MB recovered after kill+wait. spec hypothesis invalid → pivot to auto-reboot alternatives
```

此次試驗所確定的，僅是首次 HEF 載入後的 `CmaFree` 未依照舊判定基準回復這一事實。並未證實行程結束後可用記憶體的喪失，或 v5.4.0 的 leak 尚未修正。第3回時暫定解讀為未回收，但該解讀與判定方法已於 §8 訂正。

---

## 6. 第3回試驗中的核心當機與 CMA 除錯程式碼的復原（2026-08-17）

### 6.1 事件與可能原因

為了調查 CMA 的釋放路徑，曾在本地 DKMS 原始碼的 `linux/vdma/memory.c` 中加入 `linux/mm.h` 的 include，以及在 `dma_free_coherent()` 執行前呼叫 `virt_to_page()` / `page_count()` 的量測程式碼。載入含此變更的模組後，在使用 Hailo 時發生 hang，導致無法開機，目前以 `/boot/firmware/cmdline.txt` 中的 `module_blacklist=hailo1x_pci,hailo_pci` 停止自動載入。

將 `dma_alloc_coherent()` 回傳的 CPU 虛擬位址直接以 `virt_to_page()` 轉換為頁面，並非 DMA API 的契約行為。回傳位址的映射形式由 allocator 決定，由此取得的 `page_count()` 並非正確觀測 CMA 參照數的手段，可能產生非法的頁面參照。此量測程式碼在 descriptor list 與 continuous buffer 兩者的釋放路徑中皆會執行。

新增時間為 10:15:36，該次 DKMS 建置開始於 10:15:39，可判斷發生 hang 的模組確實包含此程式碼。由於未取得當機前一刻的 stack trace，無法嚴格確定原因，但此為唯一不存在於 vanilla v5.4.0 中的本地執行程式碼變更，判定為最有力的原因候選。

### 6.2 已復原狀態

已移除以下 7 行程式碼（`linux/mm.h` 的 include，以及兩處 `virt_to_page()` / `page_count()` 的紀錄），重新建置 DKMS 並完成 `depmod`。

- 核心: `6.18.39+rpt-rpi-2712`
- 重新建置的模組: `/lib/modules/6.18.39+rpt-rpi-2712/updates/dkms/hailo1x_pci.ko.xz`
- 上述模組已登記於 `modules.dep`
- blacklist 仍維持中，重新建置後的模組尚未載入

下次將先確保序列主控台等復原路徑，再解除 blacklist，並於重新開機後確認首次載入正常。針對 CMA 未回收問題本身的調查，不再重新導入將 DMA API 回傳位址轉換為內部頁面的量測方式，而以驅動程式所持有的緩衝區帳冊、分配大小、`dma_free_coherent()` 呼叫次數作為觀測對象。

**追記（2026-08-17 稍晚）**: 準備好 `cmdline.txt` 備份（`cmdline.txt.bak-blacklisted`）後解除 blacklist 並重新開機，已確認能正常開機（也已設定序列主控台 `console=serial0,115200`，確保復原路徑）。此後以 §7 所述的安全計裝方式（不檢視原始頁面，僅輸出既有計數器・大小的紀錄）繼續調查。

---

## 7. 原因假設的形成與排除 — `FOLL_LONGTERM` 的驗證與反證（2026-08-17）

本節記錄基於第3回試驗形成的原因假設，以及透過實驗所能排除的原因候選。此處的角色是候選的篩選，CMA leak 有無的最終判定取決於第4回 A/B 試驗（§8）。

考量到 §6 的當機，改以避免直接存取頁面內部（如 `virt_to_page()` 等）的安全計裝方式（僅以 `dev_err()` 輸出記錄，不檢查・轉換原始指標）繼續調查。

### 7.1 計裝內容

在 `linux/vdma/memory.c` / `linux/vdma/ioctl.c` / `linux/vdma/vdma.c` 的以下位置，新增輸出既有的 atomic 計數器（`controller->desc_cma_in_use` / `controller->cma_in_use`）與分配大小的紀錄（完全不存取頁面內部）:

- `hailo_desc_list_create`/`hailo_desc_list_release`（descriptor list 的 alloc/free）
- `hailo_vdma_continuous_buffer_alloc`/`hailo_vdma_continuous_buffer_free`（continuous buffer 的 alloc/free）
- `hailo_desc_list_release_ioctl`/`hailo_vdma_continuous_buffer_free_ioctl`（明確釋放的 ioctl 路徑）
- `hailo_vdma_buffer_map`/`hailo_vdma_buffer_destroy`（使用者空間緩衝區的 DMA 映射・解除映射路徑。同時輸出 `buffer_type`/`is_mmio`/`is_dmabuf`）
- `hailo_vdma_file_context_finalize`（fops_release 時的統一清理，於 ENTER/EXIT 輸出計數器）

### 7.2 觀測結果

從重新開機後（`CmaFree` ≈ 451 MB）執行 `tools/diag_hailo_cma_reclaim.py --signal terminate`，以 `sudo dmesg | grep CMA_DBG` 回收並彙整全部紀錄。

- **`/proc/meminfo` 的 `CmaFree`**: 451 MB → 195 MB（**消耗 256 MB**）→ kill+等待30秒後仍為 204 MB（**較 baseline 低 247 MB**）
- **驅動程式自身的 `desc_cma_in_use`（descriptor list，經由 `dma_alloc_coherent`）**: 最大也僅約 2〜4 MB。在 `file_context_finalize` 的 EXIT 時點確實回到 0
- **`cma_in_use`（continuous buffer，經由 `dma_alloc_coherent`）**: 本次 session 中始終為 0（continuous buffer 一次都未使用）
- **使用者空間緩衝區的 DMA 映射（`hailo_vdma_buffer_map`，`buffer_type=0`=`HAILO_DMA_USER_PTR_BUFFER`、`is_mmio=0`、`is_dmabuf=0`）**: 呼叫 621 次，其中 **342 次為 8 MB（`0x800000`）大小**（合計 2.7 GB 分的映射呼叫，推測是相同的 host 端 staging buffer 在管線處理中被重複使用）。`hailo_vdma_buffer_destroy` 呼叫 628 次，與 `buffer_map` 幾乎一對一對應，**驅動程式自身的映射帳冊並未失衡**（`dma_unmap_sg` 正確被呼叫）
- **SWIOTLB（`/sys/kernel/debug/swiotlb/`）**: `io_tlb_used_hiwater=0`。bounce buffer 一次都未使用
- Hailo 裝置不在 IOMMU 之下（`/sys/bus/pci/devices/0001:01:00.0/iommu_group` 不存在）

此時點的解讀，是將原因候選從 `dma_alloc_coherent()` 系統的驅動程式自身分配（desc list・continuous buffer），轉向 `hailo_vdma_buffer_map()` 所處理的「將使用者空間已分配的既有記憶體映射為 DMA 用途」路徑（`HAILO_DMA_USER_PTR_BUFFER`）。此路徑中驅動程式並不會新分配 CMA，而是為了使既有使用者頁面可供 DMA 使用而將其固定（pin）。

### 7.3 原因假設: `get_user_pages()` 未指定 `FOLL_LONGTERM`

確認 `linux/vdma/memory.c` 的 `prepare_sg_table()`（於 `hailo_vdma_buffer_map()` 內部呼叫）後發現:

```c
pinned_pages = compat_get_user_pages(user_address, npages, FOLL_WRITE | FOLL_FORCE, pages);
```

由於本次核心 6.18.39 符合 `LINUX_VERSION_CODE >= KERNEL_VERSION(6, 5, 0)`，`compat_get_user_pages` 只是單純的 `get_user_pages()` 別名，**未指定 `FOLL_LONGTERM` flag**。釋放端（`clear_sg_table()`）也呼叫對應的 `put_page()`，並非使用新版的 `pin_user_pages()`/`unpin_user_pages()` API 系列，而是沿用舊有的 `get_user_pages()`/`put_page()`。

依照 Linux 核心文件化的作法（`Documentation/core-api/pin_user_pages.rst`），**如同 DMA 傳輸般需要長時間持有頁面參照的程式碼，應使用附帶 `FOLL_LONGTERM` 的 `pin_user_pages()`**。若未指定 `FOLL_LONGTERM`，即使碰巧位於 CMA 區域內的使用者頁面被 `get_user_pages()` 固定，CMA 原本具有的「可視需要移往其他用途（migratable）」性質，將在長時間內失效。CMA allocator 通常會在長期固定前，先將該頁面遷移至 CMA 區域外，但在不使用 `FOLL_LONGTERM` 的路徑中不會發生此遷移，因此 **在固定期間內，該部分實質上從 CMA 區域中喪失，即使釋放（`put_page()`）後，也不會立即被視為 CMA 的空閒區域**（因為還需要額外的遷移・壓縮處理）。

此假設與第3回時點的單次量測（§7.2）相符:
- 驅動程式自身的 CMA 計數器無關（`get_user_pages` 不經由 `dma_alloc_coherent`）
- map/destroy 呼叫次數正確平衡（`put_page()` 本身確實被呼叫。問題在於釋放後「回到」CMA 的速度緩慢／不完全）
- 若載入如 Qwen3-1.7B-Instruct 般的大型 LLM，會在 host 記憶體上分配・DMA 映射大量的 8 MB buffer，一旦其中部分含有 CMA 區域內的頁面，此問題便會顯現
- 也與 kill 後緩慢且部分回復的 `CmaFree`（30秒約 +15〜30MB，其後數分鐘內緩慢增加）相符（`put_page()` 本身在行程結束時確實會被呼叫，但要回收為 CMA 的空閒區域，似乎還需要額外處理）

### 7.4 修正候選的實作與實機驗證 → 反證（2026-08-17 續報）

將 `prepare_sg_table()` 由 `get_user_pages(FOLL_WRITE | FOLL_FORCE)` + `put_page()` 實際替換為 `pin_user_pages(FOLL_WRITE | FOLL_FORCE | FOLL_LONGTERM)` + `unpin_user_page()`，新增 `<linux/mm.h>` 的 include，完成建置・dkms 重新登記・實機載入（已透過 `modprobe --dump-modversions` 確認 `pin_user_pages`/`unpin_user_page` 符號正常解析）。

從重新開機後的高 `CmaFree`（453 MB）狀態執行相同 repro 的結果:

| | 修正前（n=多次） | 修正後（n=1） |
|---|---|---|
| baseline | 436〜451 MB | 453 MB |
| after_llm_loaded | 173〜195 MB（消耗 256〜263 MB） | 180 MB（消耗 273 MB） |
| after_post_wait | 188〜204 MB（回收 9〜15 MB） | 190 MB（**回收 10 MB**） |
| 依舊判定基準之 `VERDICT` | `FAIL` | **`FAIL`（無變化）** |

> 此表的執行次數與彙整方式並不對稱，並非嚴格的 A/B 比較。A/B 的判定以相同條件反覆執行的 §8 結果為準。

以 `dmesg` 確認 `CMA_DBG buffer_map` 後，修正後同樣的 0x800000（8 MB）大小 buffer 也透過 `pin_user_pages` 順利映射（未出現 pin 失敗或核心警告），程式碼路徑本身依預期執行。以 `echo 1 > /proc/sys/vm/compact_memory` 強制壓縮亦無效果。`MemAvailable` 維持在健全的 7.1 GB，與修正前相同，並非系統整體記憶體不足，而僅是 `CmaFree` 此特定會計項目未能回復。

**結論: `FOLL_LONGTERM` 缺失假設經實驗反證。** 從 `get_user_pages()` 改為 `pin_user_pages()`+`FOLL_LONGTERM`，雖然是符合 Linux 核心文件化作法的正當改善，但並非本 session 中觀測到的 CMA 未回收症狀的直接原因。此假設本身在理論上合乎邏輯（CMA 的遷移機制與長期固定之間的交互作用是實際存在的已知問題類型），作為程式碼品質上的指摘依然有效，但**並非能單獨說明本次實測結果的根本原因**。

### 7.5 原因候選的排除（最終判定於 §8）

以下是透過實驗明確**排除**的原因候選。此清單作為假設驗證的成果有效，但並非 leak 有無的判定本身。

- 驅動程式自身經由 `dma_alloc_coherent()` 的分配（desc list・continuous buffer）— 僅數 MB，正確回到 0
- SG 映射的 map/destroy 呼叫不一致 — 已平衡
- SWIOTLB bounce buffer — 一次都未使用（`io_tlb_used_hiwater=0`）
- `get_user_pages()` 缺少 `FOLL_LONGTERM` — 已實作修正並經實機驗證，但無改善

截至第3回試驗為止殘留的事實，是 `MemAvailable` 維持健全的情況下，僅 `CmaFree` 在首次載入後下降。當時將此解讀為未回收，但單次試驗無法區分「可用記憶體的喪失」與「movable CMA 頁面轉用為頁面快取」。第4回中以低 `CmaFree` 狀態重新試驗，量測實際的載入可否・反覆時的淨減少量・RSS・CMA 分配失敗，訂正了判定。

---

## 8. 第4回試驗: vanilla / `FOLL_LONGTERM` A/B 追加試驗與誤判定的確定（2026-08-17）

### 8.1 比較對象

- `FOLL_LONGTERM` 修正版: `pin_user_pages(FOLL_LONGTERM)` / `unpin_user_page()`，載入時 `srcversion=C84A00ABB326748A1832CE1`
- 官方 vanilla 5.4.0: tag `v5.4.0`、commit `b6dd17c609504e648eb516ff4a867167edf56f3c`、`get_user_pages()` / `put_page()`，載入時 `srcversion=A260C39C9F2C06DD4FB072E`
- 核心: `6.18.39+rpt-rpi-2712`
- HEF: `Qwen3-1.7B-Instruct.hef`（2,880,748,478 bytes）

### 8.2 獨立行程中連續載入2次

| 驅動程式 | 試行 | baseline | loaded | exit後 | 較 baseline 增減 | 載入 |
|---|---:|---:|---:|---:|---:|---|
| `FOLL_LONGTERM` | 1 | 338 MB | 34 MB | 25 MB | **-313 MB（減少）** | 成功 |
| `FOLL_LONGTERM` | 2 | 5 MB | 6 MB | 7 MB | **+2 MB（增加）** | 成功 |
| vanilla | 1 | 376 MB | 99 MB | 112 MB | **-264 MB（減少）** | 成功 |
| vanilla | 2 | 125 MB | 118 MB | 124 MB | **-1 MB（減少）** | 成功 |

兩種驅動程式皆僅在首次出現 `CmaFree` 大幅下降，從此較低數值開始的第2次載入皆成功，淨減少量幾近於 0。舊有診斷方式僅以「載入過程中消耗量有多少回復」作為判定依據，因此如第2次這般起始時 `CmaFree` 已偏低的正常情況，也一併被判定為 `FAIL`。

### 8.3 同一行程內的生成・釋放・重新載入

| 指標 | `FOLL_LONGTERM` | vanilla 第1次 | vanilla 低CMA反覆 |
|---|---:|---:|---:|
| 生成完成 | 20/20 | 20/20 | 20/20 |
| 第1次載入 | 成功 | 成功 | 成功 |
| 釋放後的第2次載入 | 成功 | 成功 | 成功 |
| 生成1→20的 `CmaFree` | 464→1,648 kB | 115,376→123,728 kB | 82,320→83,296 kB |
| 生成1→20的 `MemAvailable` | 6,706,208→6,788,432 kB | 6,830,352→6,910,560 kB | 6,871,504→6,906,368 kB |
| 生成過程中 RSS | 固定於 63,888 kB | 63,904〜63,920 kB | 63,936〜63,952 kB |
| CMA 分配失敗 | 0 | 0 | 0 |

vanilla 低CMA反覆從 `CmaFree=87,424 kB` 開始，全部釋放後直為79,520 kB，其後回到87,344 kB（淨差80 kB）。反覆進行載入・生成・釋放並未出現逐漸喪失的行為。vanilla 的 `nr_foll_pin_*` 為0，是因為未使用 `FOLL_PIN` API，無法用於 pin 釋放成敗的比較。

### 8.4 首次下降的解讀

從 vanilla 重新開機直後到全部追加試驗結束為止，`Cached` 從 1,845,872 kB 增加至約 4,988,224 kB，而 `MemAvailable` 則從 7,071,280 kB 維持在約 6,962,816 kB。此增加量與 multi-GB HEF 的讀取相符，可說明首次 `CmaFree` 下降並非無法存取的記憶體喪失，而是包含 movable CMA 頁面在內的空閒頁面被用於頁面快取。

### 8.5 運用上的結論

1. 不應僅以 `CmaFree` 的絕對值作為拒絕模型載入的依據。實機中即使從不到 1 MB 也成功完成 Qwen 的載入。
2. 將低 `CmaFree` 記錄為遙測資料，並以實際的 HailoRT 記憶體分配錯誤作為失敗判定依據。
3. 不混淆 `CmaFree` 的觀測值、實際載入失敗、leak 診斷，以下列3種狀態區分處理。

| 狀態 | 判定條件 | 產品端處置 | 重新開機・調查 |
|---|---|---|---|
| `INCONCLUSIVE` | 僅首次下降、未滿3次，或不滿足下述 `FAIL` 條件 | 記錄遙測資料並嘗試載入。不會僅因低 `CmaFree` 而拒絕 | 不重新開機。以相同條件追加量測 |
| `OPERATIONAL_FAIL` | HailoRT 實際回傳 host-memory allocation error | 僅將該次載入請求判定為失敗，停止不必要的 Hailo workload 後重試 | 單次不重新開機。僅當實際失敗反覆發生，且釋放 workload 後仍未回復時，依運用政策處理。現行 Phase 0.5 僅記錄 `would_fire`，不自動重新開機 |
| `FAIL` | 從低 CMA 狀態以相同條件反覆3次，釋放後較 baseline 的淨減少量 **單次超過10 MB的試行達3次中2次以上**，3次的正向淨減少合計 **超過20 MB**，且伴隨 RSS 單調增加或 `MemAvailable` 下降超過128 MB | 作為與個別載入可否不同的 leak 診斷紀錄 | 重新開始核心 / HailoRT 端的調查，採集直接證據。僅憑診斷成立不自動重新開機 |

此3次基準為今後診斷之用，未追溯適用於本節 §8.2 中各驅動程式僅執行2次的獨立行程試驗。第4回的結論，是綜合 §8.2 的 A/B 加上 §8.3 的同一行程20次生成・釋放・重新載入及低 CMA 反覆而得出的。
4. `FOLL_LONGTERM` 替換作為 Linux DMA API 的一般作法雖屬妥當，但對本案並無效果，實機已恢復為官方 vanilla 5.4.0。
5. 自動重新開機判定不應僅因低 `CmaFree` 而發動，須以實際載入失敗的觀測作為必要條件。

---

## 9. 今後的行動（截至2026-08-17）

1. `FOLL_LONGTERM` 修正的檢討與實機反證已完成。可重現用的差異與復原方法保存於附錄 B，不會套用至正式 driver。
2. **產品端已因應完成**: `core/hailo_device_core/device_manager_genai.py::acquire_genai` 已於 v4.620.8 改為即使推估所需量高於 `CmaFree`，也會記錄 `acquire_low_cma_observed` 並繼續實際載入。僅將 factory 回傳的實際 HailoRT host-memory error 記錄至拒絕 tracker，`tests/test_hailo_cma_false_positive.py` 已固定測試低值狀態下持續載入的行為。
3. 已對舊論壇草稿中「後續 `LLM(...)` 因 insufficient host CMA 遭 HailoRT 拒絕」的記述，依日誌及舊實作重新查核。所引用的 PID 3237 session 中並無 release 後的 acquire 紀錄，同日日誌中可追蹤到的低 CMA 拒絕，全部是在呼叫 HailoRT 之前發生的自有事件 `acquire_rejected_low_cma`。另一 session 中確實到達 factory 的失敗，status 為 8 (`HAILO_INTERNAL_FAILURE`)，並非 host-memory error 的 status 3。因此沒有可佐證舊記述的 HailoRT OOM 證據，在 `docs/development/development_docs/HAILO_FORUM_FOLLOWUP_CMA_INFERENCE_LEAK.md` 中明確記載將自有防護機制產生的拒絕誤植入報告一事，並撤回該記述。
4. 訂正投稿將 §8 的數值・適用範圍、實作防護的訂正、`FOLL_LONGTERM` 反證、計裝上的警示整合為單一現行草稿，不留下可複製的舊英文草稿。
5. 僅當實際載入失敗，或反覆發生累積性的可用記憶體喪失再現時，才重新開始核心 / HailoRT 端的 leak 調查。屆時將採集 `page_owner`、CMA debug 資訊、分配失敗 status、RSS、`MemAvailable` 等直接證據。

---

## 附錄 A. 復原至 v5.3.0 的步驟

從 dkms 執行過一次 `remove --all` 後的復原，若 apt 快取中未留下 `.deb`，`apt-get install --reinstall` 會失敗（本次亦失敗: `ダウンロードできないため、再インストールは不可能`（因無法下載而無法重新安裝））。由於 dpkg 仍將 `hailort-pcie-driver` 套件識別為 `ii`（已安裝），只要套件的原始碼展開位置 `/usr/src/hailort-pcie-driver/` 未被刪除，即可從該處手動重建 dkms 樹:

```bash
sudo rmmod hailo1x_pci

sudo rm -rf /usr/src/hailo1x_pci-5.3.0
sudo cp -r /usr/src/hailort-pcie-driver /usr/src/hailo1x_pci-5.3.0
sudo sed 's/@PCIE_DRIVER_VERSION@/5.3.0/' \
  /usr/src/hailo1x_pci-5.3.0/linux/pcie/dkms.conf.in \
  | sudo tee /usr/src/hailo1x_pci-5.3.0/linux/pcie/dkms.conf > /dev/null

# dkms.conf 必須放在樹狀結構的最上層（放在 linux/pcie/ 底下會出錯）
sudo cp /usr/src/hailo1x_pci-5.3.0/linux/pcie/dkms.conf /usr/src/hailo1x_pci-5.3.0/dkms.conf

sudo dkms add -m hailo1x_pci -v 5.3.0
sudo dkms build -m hailo1x_pci -v 5.3.0 -k $(uname -r)
sudo dkms install -m hailo1x_pci -v 5.3.0 -k $(uname -r) --force
sudo depmod -a
sudo modprobe hailo1x_pci
sudo udevadm trigger --subsystem-match=hailo1x
```

復原確認:

```bash
cat /sys/module/hailo1x_pci/version   # → 5.3.0
hailortcli fw-control identify        # → 正常回應即代表復原完成
```

---

## 附錄 B. 反證實驗用 driver patch 的保存・套用・vanilla 復原步驟

### B.1 保存物與定位

將 A/B 試驗實際使用的 driver 差異，原封不動保存至以下檔案。

- `docs/development/patches/hailo1x_pci-5.4.0-foll-longterm-cma-debug-experiment.patch`
- SHA-256: `7b5c4027f37432dbbbe39e4bdec2f0f5e8dd87e133473b5a44c44b1e86c5503f`
- 基準原始碼: `hailo-ai/hailort-drivers` tag `v5.4.0`、commit `b6dd17c609504e648eb516ff4a867167edf56f3c`
- 對象檔案: `linux/vdma/ioctl.c`、`linux/vdma/memory.c`、`linux/vdma/vdma.c`

此 patch 不僅包含替換為 `pin_user_pages(FOLL_LONGTERM)` / `unpin_user_page()`，也包含 §7.1 所使用的 `CMA_DBG` 計裝。也就是說，這是為了重現 A/B 試驗時的實驗模組所準備的**驗證用完整差異**，並非正式環境建議套用的 patch。實驗中未確認有效果，現行實機已復原至官方 vanilla 5.4.0。HailoRT 使用者空間 library 未做任何變更。

在相同核心・原始碼・建置環境下確認到的識別值如下。

| 狀態 | `srcversion` |
|---|---|
| 實驗 patch | `C84A00ABB326748A1832CE1` |
| 官方 vanilla 5.4.0 | `A260C39C9F2C06DD4FB072E` |

### B.2 套用前的確認

以下僅在 Raspberry Pi 上的 `/usr/src/hailo1x_pci-5.4.0` 指向上述官方 commit、且對象 3 檔案無本地變更時執行。commit、patch checksum、vanilla `memory.c` checksum 三者中若有任一項不一致，須停止作業，不得強行套用 patch。

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

### B.3 套用實驗 patch

確認全部成功後，方可套用 patch，並將 DKMS 模組安裝為下次開機用。不對載入中的模組以 `rmmod` / `modprobe` 手動替換，而是建置完成後以一般重開機方式切換。

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

`modinfo` 顯示的是下次開機用已安裝的模組，`/sys/module/.../srcversion` 顯示的是目前載入中的模組。此時兩者值不同屬正常。準備就緒後重新啟動，開機後確認兩者一致。

```bash
sudo reboot

# 重新連線後
modinfo -F srcversion hailo1x_pci
head -n 1 /sys/module/hailo1x_pci/srcversion
```

在相同的驗證環境下，套用 patch 後的預期值為 `C84A00ABB326748A1832CE1`。若不同，切勿憑猜測繼續試驗，應檢查原始碼差異、核心版本、DKMS 建置日誌。

### B.4 復原至官方 vanilla 5.4.0

復原時不依賴 patch 的逆向套用，而是從已驗證的 commit 明確還原對象 3 檔案。藉此避免只剩部分套用或計裝殘留的狀態。

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

在相同的驗證環境下，已安裝 vanilla 模組的預期值為 `A260C39C9F2C06DD4FB072E`。確認目前載入中的值不同後重新啟動，重新連線後確認兩者皆為 `A260C39C9F2C06DD4FB072E`。

---

## 參考: 相關文件

- `docs/development/development_docs/HAILO_FORUM_FOLLOWUP_CMA_INFERENCE_LEAK.md` — 基於舊測量的 CMA 洩漏實測數據、repro 指令碼、論壇貼文草稿（結論已於本文 §8 訂正）
- [HAILORT_5_3_0_MIGRATION.md](HAILORT_5_3_0_MIGRATION.md) — v5.2.0 → v5.3.0 遷移時的記錄（設備節點名稱變更為 `/dev/h1x-0` 等）
- [HAILO_CMA_LEAK_HAILORT_5_3_0.md](HAILO_CMA_LEAK_HAILORT_5_3_0.md) — 基於舊診斷的 CMA 洩漏問題日文記錄（結論已於本文 §8 訂正）
- `hailo-ai/hailort-drivers` GitHub 儲存庫（GPL-2.0，原始碼公開）: <https://github.com/hailo-ai/hailort-drivers>
