# Hailo-10H 設置

在 Raspberry Pi 5 + Hailo AI Hat+ (Hailo-10H NPU) 上從 YU AI Manager 使用的主機端設置步驟。硬體和 OS 相關部分不能透過 PyPI 完成，因此需要進行一些手動準備。

> **目標**：僅當在搭載 Hailo-10H 硬體的 Raspberry Pi 5 (建議 8 GB) 上啟用 Hailo 相關擴充功能 (GenAI 聊天 / Semantic Search / YOLO Detect / Tagger / Whisper) 時。如果沒有 Hailo HW，則不需要執行此頁面的任何操作。

---

## 1. 先決條件

- Raspberry Pi 5 (強烈建議 8 GB。由於 CMA 限制，4 GB 在同時載入多個模型時會很困難)
- Hailo AI Hat+ (Hailo-10H)
- Raspberry Pi OS Bookworm 64-bit (aarch64)
- Python 3.13.x (已在 `pyproject.toml` 的 `requires-python` 中固定為 `<3.14`。`uv` 會自動選擇 3.13)

---

## 2. PCIe 驅動程式安裝

Hailo-10H 使用專用核心模組 `hailo1x_pci` (從 HailoRT 5.3.0 起從舊 `hailo_pci` 改名)。

```bash
sudo apt update
sudo apt install hailo-all
sudo reboot
```

重新啟動後確認：

```bash
lsmod | grep hailo1x
ls /dev/h1x-0
dmesg | grep -i hailo | tail -20
```

預期結果：

- `hailo1x_pci` 已載入
- 存在 `/dev/h1x-0` 裝置節點 (不是舊的 `/dev/hailo0`)
- `dmesg` 中有 `Firmware loaded in NNNN ms` `Device created at /dev/h1x-0` 的行

> **即使看起來沒有 `/dev/hailo0` 也沒關係**。HailoRT 5.3.0 之後 `/dev/h1x-0` 是預設的，本應用程式可識別兩者 (`core/llm_router/hailo_detect.py`)。

---

## 3. HailoRT (系統端) 安裝

`hailortcli` 二進制檔案和 `libhailort.so` 共用程式庫。雖然 `hailo-all` 套件中包含了它們，但如果需要最新版本，可以從 Hailo Developer Zone 取得 `.deb` 進行覆蓋安裝。

確認：

```bash
hailortcli fw-control identify
```

預期輸出 (要點)：

```
Device Architecture: HAILO10H
Firmware Version: 5.3.0 (release,app)
```

---

## 4. Python wheel (`hailort-*.whl`) 準備

這是 PyPI 不提供的部分。**aarch64 的 Hailo Python wheel 也不在 Hailo Developer Zone，因此需要自行構建。**

### 4.1 從原始碼構建

```bash
cd ~
git clone --branch v5.3.0 https://github.com/hailo-ai/hailort.git
cd hailort
./build.sh -aarch64
# 完成後，構建樹內會生成 hailort-5.3.0-cp313-cp313-linux_aarch64.whl
```

(構建步驟的詳細資訊和依賴套件請參考 Hailo 官方 README。)

### 4.2 將 wheel 放在主目錄

將構建的 wheel 複製到以下 **任何位置**，本應用程式在啟動時會自動偵測：

| 探索位置 (優先順序) | 用途 |
|---|---|
| `$HAILORT_WHEEL` 環境變數 | 任意完整路徑指定 (最優先) |
| `$HOME/share/` | **建議位置** |
| `$HOME/hailort/` | 在原始碼位置保留構建樹的情況 |
| `$HOME/Downloads/` | 下載後的暫時位置 |
| `$HOME/` (直下) | 最後的備用 |

建議位置：

```bash
mkdir -p ~/share
cp ~/hailort/hailort-5.3.0-cp313-cp313-linux_aarch64.whl ~/share/
```

### 4.3 自動安裝機制

執行 `./start.sh` 時，`scripts/install_hailo.py` 會運行，

1. 檢查 venv 內 `import hailo_platform` 是否成功
2. 失敗時，從上述探索位置搜尋 **符合現有 Python 版本 (cp313) + 架構 (aarch64) 的** wheel
3. 找到最新的 wheel 後使用 `uv pip install` 進行安裝
4. 如果沒有 wheel 或已安裝，則不執行任何操作 (無聲無操作)

也就是說，不需要手動 `uv pip install`。將 wheel 放在主目錄並重新啟動 `./start.sh` 即可恢復。

---

## 4.4 HEF 模型檔案放置

將各擴充功能使用的 HEF 檔案 (為 NPU 編譯的模型) 放在 `~/hailo_models/` 中。

| 檔案 | 用途 | 大小目安 |
|---|---|---:|
| `yolov8n.hef` | YOLO 物體偵測 | 7 MB |
| `clip_vit_b_16_image_encoder.hef` | **語義搜尋 (CLIP 影像)** | 76 MB |
| `clip_vit_b_16_text_encoder.hef` | 語義搜尋 (CLIP 文字，可選) | 77 MB |
| `Whisper-{Tiny,Base,Small}.hef` | 語音辨識 | 75-405 MB |
| `Qwen3-1.7B-Instruct.hef` | LLM 聊天 | 2.9 GB |
| `Qwen3-VL-2B-Instruct.hef` | VLM (影像+文字) | 3.2 GB |

可以從 Hailo Model Zoo 的 S3 bucket 無需認證直接下載 (URL 格式)：

```
https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/<model>.hef
```

範例 (CLIP 影像編碼器)：

```bash
mkdir -p ~/hailo_models
curl -L -o ~/hailo_models/clip_vit_b_16_image_encoder.hef \
  https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/clip_vit_b_16_image_encoder.hef
```

> **如果 HEF 檔案不足，擴充功能將顯示 `無法使用`**。例如，如果語義搜尋狀態顯示 `hailo-10h (CLIP HEF 未配置)`，表示 `clip_vit_b_16_image_encoder.hef` 不在 `~/hailo_models/` 中。為了易於區分硬體或 Python 執行階段問題，`runtime_ok` / `hardware_ok` / `hef_ok` 這 3 階段的原因包含在回應中 (將滑鼠懸停在狀態文字上以查看詳細資訊)。

也可以用 `HAILO_HEF_DIR` 環境變數指定別的目錄。

---

## 5. 核心參數 (CMA)

Hailo 的 GenAI 模型 (LLM/VLM/Whisper) 需要 CMA (Contiguous Memory Allocator) 用於 DMA。

在 `/boot/firmware/cmdline.txt` 末尾添加：

```
cma=256M
```

> **Pi 5 (8 GB) 上 `cma=1G` 或 `cma=512M` 會靜默失敗**。預設核心應用 `numa=fake=8`，因此 CMA 必須在單一 NUMA 節點邊界 (1 GB) 內，超過 `256M` 時 `CmaTotal=0` (沒有恐慌)。詳細資訊：[`docs/ja/hailo/PI5_NUMA_CMA_CONSTRAINTS.md`](../../hailo/PI5_NUMA_CMA_CONSTRAINTS.md)

重新啟動後確認：

```bash
grep CmaTotal /proc/meminfo
# CmaTotal:         262144 kB  ← 256 MB 就成功了
```

如果是 `0 kB`，請檢查值，必要時降低。

---

## 6. 與 hailo-ollama 共存 (可選)

如果在同一裝置上運行 `hailo-ollama` (Ollama 的 Hailo NPU 版本)：

- **HailoRT 5.3.0 之後**：使用 `HAILO_OLLAMA_VDEVICE_GROUP_ID=YU_SHARED hailo-ollama` 啟動，可以與 yu_ai_manager 側 (group_id `YU_SHARED`) 共享物理裝置，HailoRT 排程器使用 ROUND_ROBIN 進行時間分片
- **5.2.0 之前**：不接受 group_id，因此在 yu_ai_manager 啟動前需要使用 `systemctl stop hailo-ollama` 停止

---

## 7. 動作確認

啟動 `./start.sh` 後，在 WebUI 的 **設定 → 擴充功能** 中如果以下項目被啟用則成功：

- `builtin_hailo_genai` (Hailo 聊天 / LLM / VLM / Speech2Text)
- `builtin_hailo_semantic_search` (CLIP 語義搜尋)
- `builtin_hailo_yolo_detect` (YOLO 物體偵測)

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

### Hailo 相關擴充功能全部顯示「未載入」

→ Python wheel 可能未安裝。請檢查：

```bash
uv run python -c "import hailo_platform; print(hailo_platform.__file__)"
```

如果出現 `ModuleNotFoundError`，請將 wheel 放在主目錄，然後重新啟動 `./start.sh` (§4.2)。

### `hailortcli fw-control identify` 失敗，顯示 `HAILO_OPEN_FILE_FAILURE`

→ 驅動程式或裝置節點問題。檢查 `lsmod | grep hailo1x` 中 `hailo1x_pci` 是否載入，`ls /dev/h1x-0` 是否存在。如果兩者都缺少，請重新執行 §2 並重新啟動。

### LLM/VLM 載入時出現 `HAILO_OUT_OF_HOST_MEMORY` / Pi 凍結

→ CMA 不足。檢查 `grep CmaTotal /proc/meminfo` 是否有 256 MB (§5)。由於 `VDevice.release()` 不會返回 CMA，在重複切換多個模型後可能需要重新啟動程序。

### `HAILO_OUT_OF_PHYSICAL_DEVICES(74)`

→ 其他程序佔用 VDevice。使用 `lsof /dev/h1x-0` 特定犯人 (典型情況是 `hailo-ollama` 或 Ctrl+C 沒有正確終止的上一個程序)，然後 `kill` 並重新啟動。

### Python 已升級為 3.14，與 wheel 不相容

→ 本儲存庫已在 `pyproject.toml` 中固定為 `requires-python = ">=3.13,<3.14"`。clone 後的第一個 `uv sync` 會選擇 3.13.x。如果手動寫入了 `.python-version = 3.14`，請改回去。

---

## 9. 相關文件

- [`docs/ja/hailo/README.md`](../../hailo/README.md) — Hailo-10H 開發文件目錄
- [`docs/ja/hailo/HAILORT_5_3_0_MIGRATION.md`](../../hailo/HAILORT_5_3_0_MIGRATION.md) — HailoRT 5.2.0 → 5.3.0 移行說明
- [`docs/ja/hailo/PI5_NUMA_CMA_CONSTRAINTS.md`](../../hailo/PI5_NUMA_CMA_CONSTRAINTS.md) — Pi 5 的 CMA 限制詳細資訊
- [`scripts/install_hailo.py`](../../../../scripts/install_hailo.py) — wheel 自動偵測指令碼本體
