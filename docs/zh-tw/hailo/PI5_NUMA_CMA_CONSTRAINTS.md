# Pi 5 上 `numa=fake=8` 下的 CMA 限制

Raspberry Pi 5（8 GB）在執行 Hailo-10H 工作負載時，CMA 配置的實務知見。
本文記述 `cma=` 的上限、超過 512M 的值為何會靜默失敗，以及顯示驅動程式所消耗的 CMA 該如何回收。

**適用對象**：在 Raspberry Pi 5 上執行 Hailo GenAI 模型（LLM、Speech2Text）的開發者
（使用 AI HAT / AI HAT+）。

---

## ⚠️ 2026-05 firmware 退化（regression）注意

**自 2026-05-13 發佈的 `raspi-firmware 1:1.20260513-1` + `pieeprom-2026-05-11` 起**，在 `/boot/firmware/cmdline.txt` 中寫入 `cma=`（無論大小），會導致 VC firmware mailbox 完全沉默（`vcgencmd ioctl_set_msg failed:-1`、`raspberrypi-clk -22`、HEVC `-517`、cpufreq sysfs 缺失）。

**自 2026-05-16 起的確定推薦作法**：不使用 cmdline `cma=`，而是在 `/boot/firmware/config.txt` 寫入 `dtoverlay=cma,cma-512`。因為透過 DT 的 `linux,cma` reserved memory node 取得，不會與新 firmware 衝突。詳情請參閱 §6 及 [`docs/development/investigations/pi5_firmware_cma_mailbox_regression_2026-05-16.md`](../../development/investigations/pi5_firmware_cma_mailbox_regression_2026-05-16.md)。

以下的舊有敘述（推薦 cmdline `cma=512M`）為 2026-04-15 時點的驗證結果。因 NUMA 節點邊界而產生的上限值（512M）之知見依然有效，但**設定位置已由 cmdline 遷移至 config.txt 的 overlay 引數**。

---

## TL;DR

- **設定位置為 `config.txt` 的 `dtoverlay=cma,cma-512`**（2026-05-16 確定。cmdline 的 `cma=` 會在新 firmware 上破壞 mailbox）
- `cma-1024` 與 `cma-768` 在 Pi 5（8 GB）上會**靜默失敗** — `CmaTotal` 變為 0，且不會出現核心恐慌（kernel panic）或警告（因 NUMA 節點邊界而產生的上限。推測透過 overlay 途徑仍殘留相同限制）
- **`cma-512` 為已確認的上限值，亦為推薦值**（透過 overlay 途徑於 2026-05-16 在 Pi 5 8 GB 上重新驗證，確認取得 `CmaTotal: 524288 kB`）
- 根本原因：預設的 Pi 5 核心套用了 `numa=fake=8`，將連續配置限制在單一 NUMA 節點（1 GB）內
- **`dtoverlay=vc4-kms-v3d` + `max_framebuffers=2` 在開機時會消耗約 157 MB 的 CMA** — 即使 DRM 驅動程式初始化失敗也一樣（於 2026-04-15 驗證）
- **`camera_auto_detect=1`** 會載入 `pisp_be` 與 `videobuf2_dma_contig`，消耗額外的 CMA。無頭（headless）系統建議停用
- **無頭最佳化的基準線**（兩個 overlay 皆停用）：開機時使用約 98 MB CMA，Hailo 模型可用空間約 414 MB
- **YOLO InferModel 使用 0 MB CMA**（於 2026-04-15 確認） — 僅 GenAI 模型（LLM、Speech2Text）會從 CMA 配置記憶體
- LLM（qwen2.5-1.5b）+ Whisper-base 同時載入：合計約 328 MB — 落在無頭最佳化基準線之內
- CMA 不會因伺服器重新啟動而回收 — 僅透過完整系統重新開機（PCIe 電源重新投入）才會釋放（`hailo1x_pci` 驅動程式錯誤，已回報予 Hailo）
- 應將 VDevice 視為**行程生命週期單例（process-lifetime singleton）**處理。禁止驅逐 / 重新載入

---

## 1. 症狀

在 `/boot/firmware/cmdline.txt` 中設定 `cma=1G`（或 `cma=768M`）並重新開機後，會出現以下情形：

```
$ grep CmaTotal /proc/meminfo
CmaTotal:              0 kB
```

系統會正常開機。不會出現核心恐慌，也不會有錯誤訊息。`cmdline.txt` 的 CMA 設定會被**靜默忽略**，而依賴 CMA 的元件（Hailo-10H NPU、V4L2 相機等）的初始化將會失敗。

**變更 `cmdline.txt` 後，請務必驗證 CMA 配置：**

```bash
grep CmaTotal /proc/meminfo
```

---

## 2. 根本原因：`numa=fake=8` 節點邊界

Pi 5 用的預設 Raspberry Pi OS 核心會套用 `numa=fake=8`，將 8 GB 的實體記憶體分割成**每個 1 GB 的 8 個虛擬 NUMA 節點**：

```
numa=fake=8 physical memory layout (8 GB total):

┌──────┬──────┬──────┬──────┬──────┬──────┬──────┬──────┐
│ 1GB  │ 1GB  │ 1GB  │ 1GB  │ 1GB  │ 1GB  │ 1GB  │ 1GB  │
│node0 │node1 │node2 │node3 │node4 │node5 │node6 │node7 │
└──────┴──────┴──────┴──────┴──────┴──────┴──────┴──────┘
```

Linux CMA（`cma_init_reserved_mem`）必須在開機時，被配置為**不跨越 NUMA 節點邊界**的連續實體記憶體。
這使得單一節點 = 1 GB 成為嚴格上限。由於核心本身會佔用同一節點內的部分記憶體，因此無法恰好保留 1 GB：

> **下表為 2026-04-15 時點以 cmdline 方式進行測量的歷史記錄。**
> 源於 NUMA 節點邊界之上限值（512M）的知見至今依然有效，但**現在不應再使用 cmdline 的 `cma=`**（參見開頭的 firmware 迴歸問題）。
> 目前的設定方式為 `config.txt` 的 `dtoverlay=cma,cma-512`（§6）。

| `cmdline.txt` 設定（2026-04-15 當時的記錄） | 結果 |
|---|---|
| `cma=1G` | 嘗試消耗整個節點。核心沒有剩餘空間 → **靜默失敗**，CmaTotal=0 |
| `cma=768M` | 超出可信賴的連續範圍 → **靜默失敗**，CmaTotal=0（於 2026-04-15 驗證） |
| `cma=512M` | 單一節點的一半 → **已確認穩定** ✓（於 2026-04-15 驗證） ← 當時的推薦。**現在請改用 `dtoverlay=cma,cma-512`** |
| `cma=384M` | 未驗證（512M 已確認可用，384M 為不必要） |
| `cma=256M` | 穩定，但同時使用 LLM + Whisper 時較為緊繃 |
| `cma=128M` | 穩定，但對 Hailo GenAI 而言不足（單是 LLM 就需要約 234 MB） |

### 失敗為何是靜默的

`cma_init_reserved_mem` 在配置失敗時不會觸發核心恐慌。核心會以 `CmaTotal=0` 啟動，其行為如同從未被要求配置 CMA 一般。
寫入 `cmdline.txt` 的數值實質上會被忽略。

---

## 3. Hailo-10H 的 CMA 需求

於 Raspberry Pi 5、AI HAT+、HailoRT 5.3.0 環境下測得：

| 模型 / 組合 | CMA 使用量 | 註記 |
|---|---|---|
| LLM — qwen2.5-1.5b-chat（單獨） | **約 234 MB** | 於 2026-04-15 測量 |
| YOLO InferModel（yolov8n、configure + bindings） | **0 MB** | 於 2026-04-15 確認 |
| Whisper-tiny（單獨） | 約 70 MB | 估算值 |
| Whisper-base（單獨） | 約 100 MB | 估算值 |
| Whisper-small（單獨） | 約 150 MB | 估算值 |
| **LLM + Whisper-tiny（同時）** | **約 246 MB** | 以 CMA 256 MB 測量 |
| **LLM + Whisper-base（同時）** | **約 334 MB** | 估算值。預期落在無頭基準線之內 |

**YOLO 使用 0 MB CMA**：在 HailoRT 5.3.0 中，YOLO InferModel、`configure()`、`create_bindings()` 完全不會配置 CMA。
輸入 / 輸出 DMA 緩衝區並非來自 CMA，而是透過 `set_buffer()` 從預先配置的 numpy 陣列映射而來。
因此 YOLO 並非 CMA 預算計算中的考量因素。

在套用 CMA 512 MB 與無頭最佳化（見 §5）後，預期以下組合可正常運作：

- 僅 LLM（約 234 MB，餘裕約 180 MB）
- 僅 Whisper-tiny / Whisper-base（可輕鬆容納）
- LLM + Whisper-base 同時（合計約 334 MB，餘裕約 80 MB）

Whisper-small 與 LLM 的組合（估算約 384 MB）已接近理論極限 — 在信任此數值之前，請以實際測量確認。

詳情請參閱 [hailo_genai_concurrent_2026-04-15.md](../../development/investigations/hailo_genai_concurrent_2026-04-15.md) 中的同時載入測試結果。

---

## 4. CMA 在完整重新開機之前不會被回收

由 HailoRT 配置的 CMA，會一直留存於記憶體中直到完整系統重新開機為止。
無論是否執行 `VDevice.release()`、伺服器行程結束，或核心模組重新載入，皆是如此。

**根本原因**（於 2026-04-15 確認）：`hailo1x_pci` 即使在裝置 fd 被關閉或模組被重新載入後，仍會保留 DMA coherent 配置。
僅有完整重新開機（PCIe 電源重新投入）才能釋放。此錯誤已回報予 Hailo。

| 階段 | CmaFree（CMA 512 MB，無頭最佳化） |
|---|---|
| 開機 | **約 426 MB** |
| LLM 載入後（約 234 MB） | 約 192 MB |
| Whisper-base 載入後（約 100 MB） | 約 92 MB |
| 執行 `VDevice.release()` 後 | 約 92 MB（**未歸還**） |
| 伺服器行程結束後 | 約 92 MB（**未歸還**） |
| 執行 `rmmod hailo1x_pci && modprobe hailo1x_pci` 後 | 約 92 MB（**未歸還**） |
| 完整系統重新開機後 | **約 426 MB（已還原）** |

**含意**：CMA 的消耗會跨越同一開機工作階段（boot session）內的多次伺服器重新啟動而累積。
請勿期待伺服器重新啟動能回收 CMA。請將 VDevice 設計為**行程生命週期單例**。
若 CMA 已耗盡，僅有完整系統重新開機才能將其還原。

---

## 5. 無頭最佳化：`/boot/firmware/config.txt`

預設的 Pi OS `config.txt` 中，包含兩項即使在無頭（無顯示器）系統上也會消耗大量 CMA 的設定。

### 5.1 `dtoverlay=vc4-kms-v3d` 與 `max_framebuffers=2`

**效果**：Pi 5 firmware 會在開機時，為顯示管線預先配置 CMA framebuffer。
在 `max_framebuffers=2` 的情況下，這會在**使用者空間行程執行之前**就消耗約 157 MB 的 CMA。

即使 Linux DRM 驅動程式之後初始化失敗（例如 `[drm] Couldn't stop firmware display driver: -22`，或 `dmesg` 中出現 `Couldn't get core clock`），此配置仍會持續存在。

| `config.txt` 狀態 | 開機時 CmaFree |
|---|---|
| `dtoverlay=vc4-kms-v3d` + `max_framebuffers=2` 啟用（預設） | **約 257 MB** |
| 兩者皆註解 | **約 305 MB**（+約 48 MB） |

**修正方式**（無頭 / 伺服器模式）：

```ini
# /boot/firmware/config.txt
#dtoverlay=vc4-kms-v3d
#max_framebuffers=2
```

**取捨**：硬體加速顯示與 3D（V3D）需要 `vc4-kms-v3d`。
若系統僅透過 SSH 或網頁介面存取，停用它是安全的。

### 5.2 `camera_auto_detect=1` 與 `display_auto_detect=1`

**效果**：這些 overlay 會在開機時探測 CSI 相機與 DSI 顯示器，並載入 `pisp_be`（Pi ISP backend）與 `videobuf2_dma_contig`。
被載入的模組及偵測到的硬體，會預先配置各種額外的 CMA。

| `config.txt` 狀態 | 開機時 CmaFree |
|---|---|
| `camera_auto_detect=1` + `display_auto_detect=1` | 約 305 MB（vc4 停用後） |
| 兩者皆設為 0 | **約 426 MB**（+約 121 MB） |

**修正方式**：

```ini
camera_auto_detect=0
display_auto_detect=0
```

**註記**：`camera_auto_detect=0` 僅影響 CSI 相機。USB 相機（UVC / `uvcvideo`）不受影響，會持續正常運作。

### 5.3 無頭 AI HAT+ 用途推薦的最小 `config.txt`

```ini
auto_initramfs=1
arm_64bit=1
arm_boost=1

[cm5]
dtoverlay=dwc2,dr_mode=host

[all]
dtparam=pciex1_gen=3
```

此設定下的開機時 CMA 估算值：**約使用 98 MB**，Hailo 模型可用空間約 414 MB。

### 5.4 CMA 預算摘要（CMA 512 MB，無頭最佳化）

| 組態 | CmaFree | Hailo 可用空間 |
|---|---|---|
| 預設（vc4-kms-v3d + 相機啟用） | 約 257 MB | 約 257 MB |
| 停用 vc4-kms-v3d + max_framebuffers | 約 305 MB | 約 305 MB |
| + camera/display_auto_detect=0 | **約 426 MB** | **約 426 MB** |
| LLM 載入後（約 234 MB） | 約 192 MB | 供 Whisper 使用 |
| LLM + Whisper-base 載入後（約 100 MB） | 約 92 MB | （餘裕） |

---

## 6. 推薦組態

### 設定 `dtoverlay=cma,cma-512`（2026-05-16 確定）

```bash
# 確認目前的 CMA 狀態
grep CmaTotal /proc/meminfo

# 1) 從 cmdline.txt 移除既有的 cma=（因其會在新 firmware 上破壞 mailbox）
sudo sed -i 's/ *cma=[^ ]*//g' /boot/firmware/cmdline.txt

# 2) 在 config.txt 的 [all] 區段附加 dtoverlay=cma,cma-512
sudo sed -i '/^\[all\]$/a dtoverlay=cma,cma-512' /boot/firmware/config.txt

# 3) 建議冷開機重新啟動（拔插電源）
sudo sync && sudo poweroff

# 重新開機後驗證（務必確認以下全部 4 項）
vcgencmd version                                # 必須有 Broadcom 回應（沉默即為失敗）
grep CmaTotal /proc/meminfo                     # 預期為 524288 kB
journalctl -b -k | grep 'linux,cma'             # 應出現 initialized node linux,cma
journalctl -b -k | grep '0x00030087'            # 應不出現
```

若 dmesg 中出現 `OF: reserved mem: initialized node linux,cma, compatible id shared-dma-pool`，即為透過 DT 途徑成功配置的證明。
反之，若出現 `Reserved memory: bypass linux,cma node, using cmdline CMA params instead`，代表 cmdline 中仍殘留 `cma=`，須將其移除。

### 若要啟用 `vc4-kms-v3d`

若需要顯示用的 KMS DRM，可以 overlay 引數的形式整合：
```ini
dtoverlay=vc4-kms-v3d,cma-512
```
但如 §5.1 所述，vc4-kms-v3d 會消耗約 157 MB 的 CMA，對 Hailo GenAI 用途而言建議停用。

### 每次核心 / firmware / 設定變更後皆須驗證

對 `/boot/firmware/cmdline.txt` 或 `config.txt` 的變更，以及核心 / firmware 升級後，CMA 狀態與 mailbox 回應皆有可能靜默改變。
請將上述 4 項驗證納入每次重新開機後的例行程序。

---

## 7. 與其他 `numa=fake=8` 問題的交互作用

`numa=fake=8` 會在本專案中引起至少 2 個不同的問題：

| 問題 | 症狀 | 根本原因 |
|---|---|---|
| CMA 靜默失敗 | 設定 `cma=1G`、`cma=768M` 後出現 `CmaTotal=0` | NUMA 節點邊界限制了連續配置 |
| Node.js 安裝失敗 | npm/node 安裝程式因記憶體錯誤而中止 | 每個 NUMA 節點的記憶體（1 GB）被誤判為總 RAM。已作為 [anthropics/claude-code#33864](https://github.com/anthropics/claude-code/issues/33864) 回報予上游 |
| `vc4-kms-v3d` CMA 消耗 | 開機時消耗約 157 MB，即使 DRM init 失敗也不會歸還 | `max_framebuffers=2` 使 firmware 預先保留 CMA framebuffer，發生於 Linux 驅動程式啟動之前 |

靜默失敗與 vc4 消耗兩者，皆源自相同的根本限制（低 4 GB DMA 區域、NUMA 節點邊界）。
若遇到非預期的記憶體相關故障，請先檢查 `/proc/meminfo` 與 `config.txt`。

---

## 8. 快速診斷檢查清單

```bash
# 1. mailbox 回應（在新 firmware 上須優先確認）
vcgencmd version                     # 沉默即懷疑 cmdline 中殘留 cma=

# 2. 確認 CMA 配置
grep CmaTotal /proc/meminfo          # 0 kB = 靜默失敗

# 3. 確認 DT 途徑 vs cmdline 途徑
journalctl -b -k | grep 'linux,cma'
# 預期："initialized node linux,cma, compatible id shared-dma-pool"（DT 途徑 = 正常）
# 異常："bypass linux,cma node, using cmdline CMA params instead"（cmdline 殘留）

# 4. 確認 NUMA 拓樸
numactl --hardware                   # 顯示節點數與每節點記憶體

# 5. 確認目前的命令列與 overlay 設定
cat /boot/firmware/cmdline.txt       # 確認不含 cma=
grep '^dtoverlay=cma' /boot/firmware/config.txt   # 確認存在 dtoverlay=cma,cma-512

# 6. 確認 Hailo 裝置可用性
ls /dev/h1x-*                        # HailoRT 5.3.0: /dev/h1x-0
hailortcli fw-control identify       # 確認 NPU 可存取

# 7. 確認 config.txt 中的 CMA 消耗來源
grep -E 'vc4-kms-v3d|camera_auto_detect|display_auto_detect|max_framebuffers' \
  /boot/firmware/config.txt

# 8. 確認已載入的核心模組（CMA 使用者）
lsmod | grep -E 'vc4|v3d|pisp|videobuf2_dma'
```

---

**驗證環境**：Raspberry Pi 5 8 GB、Raspberry Pi OS
（Linux 6.12.62+rpt-rpi-2712、aarch64）、HailoRT 5.3.0、AI HAT+、CMA=512M
（**2026-05-16 重新驗證**：Linux 6.18.29+rpt-rpi-2712 / raspi-firmware 1:1.20260513-1 / pieeprom-2026-05-11 / Hailo-10H AI HAT，透過 `dtoverlay=cma,cma-512` 確認取得 524288 kB，mailbox 回應正常）
