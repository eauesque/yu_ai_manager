# Hailo-10H Semantic Search — 開發日誌

**專案**：YU AI Manager — Hailo-10H CLIP 語義圖片搜尋
**目標**：在 Raspberry Pi 5 + AI HAT 2 (Hailo-10H) 上實現基於 CLIP 的自然語言圖片搜尋
**開始日期**：2026-03-01
**狀態**：Phase 1-8 完成、Phase 9-12（VLM 字幕連動、影片 S2T、LLM 多輪對話、OpenAI 相容 API）完成

---

## 為什麼這個專案很重要

Hailo-10H (AI HAT 2) 是 2025 年底發布的較新的邊緣 AI 加速器，
安裝在 Raspberry Pi 5 的 M.2 插槽上使用。擁有 40 TOPS 的推論效能，但
**實際應用程式中的使用案例幾乎尚未公開**。

本專案使用 Hailo-10H 對 20 萬張規模的圖片庫進行
語義搜尋（以自然語言搜尋圖片），可能是首個實用軟體。

---

## Phase 1：可行性確認 (2026-03-01)

### 環境資訊

| 項目 | 值 |
|------|-----|
| 硬體 | Raspberry Pi 5 (8GB) + AI HAT 2 (Hailo-10H) |
| OS | Raspberry Pi OS Trixie (Linux 6.12.62+rpt-rpi-2712) |
| Python | 3.13.5 |
| HailoRT 驅動程式 | 5.2.0 (hailort-pcie-driver) |
| HailoRT 函式庫 | 5.2.0 (hailort deb) |
| HailoRT Python | 5.2.0 (**從原始碼建置**) |

### Step 1-1：裝置辨識 — OK

```bash
$ hailortcli fw-control identify
Firmware Version: 5.2.0 (release,app)
Device Architecture: HAILO10H
```

裝置順利被辨識。PCIe 連接與驅動程式載入均正常。

### Step 1-2：HEF 下載 — OK

可從 Hailo Model Zoo v5.2.0 的 S3 儲存桶直接下載（無需認證）。

```
~/hailo_models/clip_vit_b_16_image_encoder.hef  (76 MB)
~/hailo_models/clip_vit_b_16_text_encoder.hef   (77 MB)
```

URL 模式：
```
https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/<model>.hef
```

### Step 1-3：Python 綁定 — 需從原始碼建置

#### 問題：套件版本不一致

Raspberry Pi OS 的套件庫中存在以下 2 個系統：

| 套件系統 | 版本 | 備註 |
|---------------|-----------|------|
| `hailort` + `hailort-pcie-driver` | 5.2.0 | Hailo 官方 deb。不含 Python 綁定 |
| `h10-hailort` + `python3-h10-hailort` | 5.1.1 | Raspberry Pi 團隊提供。含 Python |

**問題**：兩個系統設有 `Conflicts`，無法共存。安裝 `h10-hailort` (5.1.1) 後
驅動程式也會變成 5.1.1，但 hailo-ollama 需要 5.2.0。

#### 解決方案：從原始碼建置 hailort 5.2.0 的 Python wheel

**PyPI 上沒有 wheel**。Hailo Developer Zone 的下載頁面上
**也不存在 aarch64 版 wheel**（僅有 x86_64）。

從 GitHub 儲存庫以原始碼建置解決：

```bash
git clone --depth 1 --branch v5.2.0 https://github.com/hailo-ai/hailort.git ~/hailort

# ビルド依存
sudo apt install -y swig build-essential
pip install pybind11 setuptools wheel

# ビルド (約2分)
cd ~/hailort/hailort/libhailort/bindings/python/platform
HAILORT_INCLUDE_DIR=/usr/include/hailo \
LIBHAILORT_PATH=/usr/lib/libhailort.so.5.2.0 \
PYBIND11_PYTHON_VERSION=3.13 \
python3 setup.py bdist_wheel --plat-name linux_aarch64

# インストール
pip install dist/hailort-5.2.0-cp313-cp313-linux_aarch64.whl
```

**注意事項**：
- `--plat-name linux_aarch64` 為必須。省略時 `LIBHAILORT_PATH` 的目錄名稱解析會
  發生 `ValueError: not enough values to unpack`（setup.py 第 163 行的 bug）
- `hailort` deb（C 函式庫）需預先安裝
- `h10-hailort` 和 `hailort` 設有 `Conflicts` 無法共存，
  需先刪除 `h10-hailort` 再安裝 `hailort` 5.2.0

### Step 1-4：推論測試 — 成功（API 有變更）

#### 重大發現：Hailo-10H 不支援舊版 VStreams API

規格書中記載的 `InferVStreams` + `ConfigureParams.create_from_hef()` 程式碼
**在 Hailo-10H 上無法運作**。`VDevice.configure()` 會回傳 `HAILO_NOT_IMPLEMENTED (error 7)`。

這是 **Hailo-8/8L 與 Hailo-10H 之間根本性的 API 差異**，
官方文件中也未明確記載的重要事實。

#### 正確的 API：InferModel

Hailo-10H 使用 `VDevice.create_infer_model()`：

```python
from hailo_platform import VDevice
import numpy as np

hef_path = "~/.hailo_models/clip_vit_b_16_image_encoder.hef"

with VDevice() as vdevice:
    infer_model = vdevice.create_infer_model(hef_path)

    # inputs/outputs 是屬性（不是可呼叫的）
    inp_info = infer_model.inputs[0]   # NOT inputs()
    out_info = infer_model.outputs[0]

    configured = infer_model.configure()
    bindings = configured.create_bindings()

    # 輸入：uint8 圖片
    dummy = np.random.randint(0, 255, inp_info.shape, dtype=np.uint8)
    bindings.input().set_buffer(dummy)

    # 輸出：明確配置 uint8 緩衝區
    output_buf = np.empty(out_info.shape, dtype=np.uint8)
    bindings.output().set_buffer(output_buf)

    configured.run([bindings], timeout=10000)

    vec = output_buf.flatten()  # (512,) uint8
```

#### 卡關的問題與解決方案

| 問題 | 錯誤 | 解決 |
|------|--------|------|
| `infer_model.inputs()` 出現 TypeError | `'list' object is not callable` | 是屬性所以用 `inputs[0]`（不加括號）|
| 輸出緩衝區未設定 | `not configured as view` | 用 `bindings.output().set_buffer(buf)` 明確配置 |
| 以 float32 配置輸出緩衝區 | `buffer size 2048 != expected 512` | 必須用 **uint8** 配置（512 bytes）。float32 會變成 2048 bytes |
| VDevice 結束時錯誤 | `Lost communication with server` | VDevice 清理順序的問題。**對推論結果無影響** |

### 推論效能

| 項目 | 值 |
|------|-----|
| 模型 | CLIP ViT-B/16 Image Encoder |
| 輸入 | (224, 224, 3) uint8 |
| 輸出 | (1, 1, 512) uint8 (已量化) |
| 推論時間 | **~20 ms** |
| 理論吞吐量 | **~50 images/sec** |

20 萬張的索引建置：僅推論約 67 分鐘。加上前處理也可在數小時內完成。

### Phase 1 判定

| 基準 | 結果 |
|------|------|
| 512 維向量輸出 | **OK**（uint8 量化，需反量化）|
| 推論速度 | **優秀**（20ms/image）|
| API 相容性 | 使用 InferModel API（規格書的 VStreams API 不可用）|
| 判定 | **進入 Phase 2** |

### 交接給下一階段的事項

1. **反量化**：需將 uint8 輸出轉換為 float32。
   HEF 中應包含量化參數 (scale/zero_point)。
   `hailo_platform.pyhailort._pyhailort.dequantize_output_buffer` 可能可用。
2. **文字編碼器**：HEF 存在但尚未測試。需確認是否可用相同的 InferModel API。
   按照規格書的方針以 CPU (sentence-transformers) 實作可能更安全。
3. **與 hailo-ollama 共存**：VDevice 會排他性地使用裝置。
   建置索引時需停止 hailo-ollama。
4. **VDevice 清理**：結束時的錯誤訊息無害，
   但在長時間運行的伺服器程序中需注意資源洩漏。

---

## Phase 2：DB 結構擴展 (2026-03-01)

### 實作內容

作為 Migration 25 新增 `file_vectors` 資料表。

```sql
CREATE TABLE file_vectors (
    file_id     INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
    model       TEXT NOT NULL DEFAULT 'clip_vit_b_16',
    vector      BLOB NOT NULL,        -- float32 numpy array tobytes() (512*4=2048 bytes)
    created_at  INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);
CREATE INDEX idx_file_vectors_model ON file_vectors(model);
```

**設計決策**：
- `vector` 儲存反量化後的 float32 BLOB。若以 uint8 儲存會導致精度劣化
- `file_id` 為 PRIMARY KEY（1 個檔案 1 個向量）。未來支援多模型時需改為 UNIQUE(file_id, model)
- `ON DELETE CASCADE` 在 files 刪除時自動刪除

**測試**：在記憶體 DB 中套用 migration → 確認資料表/索引存在 → OK

### 檔案

- `core/schema_core/schema_migrate_steps_25.py`（新增）
- `core/schema_core/schema_migrate.py`（import + `if current_version < 25` 新增）
- `core/schema_core/schema_constants.py`（`CURRENT_SCHEMA_VERSION = 25`）
- `core/hailo_clip_core/vector_store.py`（新增 - DB 向量 CRUD）*(現已移至 `extensions/builtin_hailo_semantic_search/core_impl/`)*

---

## Phase 3：Hailo 推論核心 (2026-03-01)

### 實作內容

新建 `core/hailo_clip_core/` 套件 *(現已移至 `extensions/builtin_hailo_semantic_search/core_impl/`)*：

| 檔案 | 職責 |
|---------|------|
| `hailo_inference.py` | HailoClipEncoder 單例模式。InferModel API 包裝器 |
| `image_preprocess.py` | 以 cv2 進行 224x224 縮放 + BGR→RGB 轉換 |
| `dequantize.py` | uint8→float32 反量化 + L2 正規化 + quant_params 提取 |
| `text_encoder.py` | CPU CLIP 文字編碼器 (`openai/clip-vit-base-patch16`) |

**設計決策**：
- 圖片前處理保持 uint8 直接傳給 Hailo（HEF 內部會進行正規化）
- 文字編碼器使用 `transformers` 的 CLIPModel（而非 `sentence-transformers`）。
  原因：`openai/clip-vit-base-patch16` 與 Hailo HEF 的 CLIP ViT-B/16 為相同模型，
  向量空間一致
- 反量化參數嘗試從 `infer_model.outputs[0].quant_infos[0]` 取得，
  失敗時回退為 scale=1.0, zero_point=0.0

**依賴套件**：`opencv-python-headless`, `numpy`（必須），`transformers`, `torch`（文字搜尋用）

---

## Phase 4：索引器 + Extension (2026-03-01)

### 實作內容

| 檔案 | 職責 |
|---------|------|
| `core/hailo_clip_core/indexer.py` *(現已移至 `extensions/builtin_clip_search/core_impl/`)* | 在背景執行緒中批次建置索引 |
| `core/hailo_clip_core/event_handler.py` *(現已移至 `extensions/builtin_clip_search/core_impl/`)* | scan.complete 事件觸發自動索引 |
| `extensions/builtin_hailo_semantic_search/extension.json` | Extension 清單 |
| `extensions/builtin_hailo_semantic_search/hailo_semantic_search.py` | Blueprint 5 個 API |

**API 端點**：
- `GET /ext/hailo-semantic/api/status` — 裝置與索引狀態
- `POST /ext/hailo-semantic/api/index/start` — 開始建置索引
- `GET /ext/hailo-semantic/api/index/status` — 進度
- `POST /ext/hailo-semantic/api/index/stop` — 中斷
- `GET /ext/hailo-semantic/api/search` — 語義搜尋
- `POST /ext/hailo-semantic/api/index/clear` — 清除索引

**事件**：在 event_bus 中新增 `semantic_index.start/progress/complete`

---

## Phase 5：語義搜尋引擎 (2026-03-01)

### 實作內容

`core/hailo_clip_core/search.py` *(現已移至 `extensions/builtin_clip_search/core_impl/search.py`)* — 帶記憶體快取的餘弦相似度搜尋

**演算法**：
1. 從 DB 一次載入所有向量 → 記憶體快取
2. 預先對向量進行 L2 正規化
3. 查詢文字 → CLIP 文字編碼器 → 512 維向量
4. 矩陣乘法（dot product）批次計算餘弦相似度
5. 篩選 threshold 以上 → 排序 → 回傳結果

**記憶體估計**：200K x 512 x 4 bytes = ~400 MB（Pi5 8GB RAM 可承受）

**回應格式**：
```json
{
    "status": "ok",
    "total": 25,
    "results": [{"file_id": 123, "score": 0.82, "path": "..."}],
    "query": "blue sky",
    "indexed_count": 200000,
    "threshold": 0.2,
    "timing": {"encode_ms": 150.3, "search_ms": 12.5}
}
```

---

## Phase 6：UI 整合 (2026-03-01)

### 搜尋頁面

- 在搜尋列旁新增語義搜尋切換按鈕（腦圖示 `regex-pill` 樣式）
- 僅在 Hailo 可用且索引建置完成時顯示
- 切換 ON 時：攔截搜尋表單送出 → 語義搜尋 API → 在現有網格中顯示結果
- 將佔位文字替換為英文範例

### Tools 頁面

- 在 Search & Analysis 分頁中新增語義搜尋區塊
- 顯示裝置狀態/索引狀況
- 批次大小滑桿 + 自動索引核取方塊
- Build Index / Stop / Clear 按鈕 + 進度條（2 秒輪詢）

---

## 技術筆記

### Hailo-10H vs Hailo-8/8L 的主要差異（開發者視角）

| 項目 | Hailo-8/8L | Hailo-10H |
|------|-----------|-----------|
| VStreams API | 支援 | **不支援**（NOT_IMPLEMENTED）|
| InferModel API | 支援 | 支援 |
| ConfigureParams | create_from_hef(hef, interface) | 不需要（create_infer_model 替代）|
| 輸出格式 | 可選 float32 或 uint8 | uint8 固定（需反量化）|
| Python 套件 | PyPI 有 wheel | **沒有**（需從原始碼建置）|
| APT 套件 | `hailort` 統合 | `h10-hailort` 另一系統（僅 5.1.1）|

### 已建置 wheel 的保管位置

```
~/hailort/hailort/libhailort/bindings/python/platform/dist/
  hailort-5.2.0-cp313-cp313-linux_aarch64.whl
```

部署到其他 Pi5 環境時可複製此 wheel 進行安裝
（但需要 libhailort.so.5.2.0 和 hailort-pcie-driver 5.2.0）。

---

## Phase 2-6 實作後的錯誤修復日誌 (2026-03-01)

### 1. 文字編碼器的 `get_text_features` 相容性問題

**問題**：`CLIPModel.get_text_features(**inputs)` 在新版 transformers 中
不再回傳 `torch.Tensor`，而是回傳 `BaseModelOutputWithPooling` 物件。
因此呼叫 `.squeeze()` 時發生 `AttributeError`，語義搜尋顯示 `Search failed` 錯誤。

**症狀**：`curl /ext/hailo-semantic/api/search?q=girl` → `{"message":"Search failed","status":"error"}`

**原因**：`_model.get_text_features()` 的回傳值取決於 transformers 版本。
新版本回傳整個模型輸出物件，需自行取出 `.pooler_output` 等。

**修復**：在 `text_encoder.py` 中改為明確以 `text_model()` → `text_projection()` 兩階段處理：

```python
# Before (broken)
text_features = _model.get_text_features(**inputs)
vec = text_features.squeeze().numpy()

# After (fixed)
text_out = _model.text_model(**inputs)
text_features = _model.text_projection(text_out.pooler_output)
vec = text_features.squeeze().numpy()
```

**效能**：
- 首次查詢（含模型載入）：~6 秒
- 第二次以後：~100-170ms（僅 CPU 推論）
- 向量搜尋：<1ms（51 筆，記憶體快取）

### 2. 索引建置時的無限重試迴圈

**問題**：未將解碼失敗的檔案（非圖片檔、損壞檔案等）追蹤為 `failed_ids`，
`get_unindexed_file_ids()` 每次都回傳相同的失敗檔案，錯誤計數超過 300 萬。

**修復**：在 `indexer.py` 中新增 `failed_ids: set`。記錄失敗的 file_id，下次批次時排除。

### 3. 壓縮檔內的圖片讀取失敗

**問題**：`cv2.imread('test.7z!image.png')` 無法理解壓縮檔成員路徑。

**修復**：在 `image_preprocess.py` 中使用 `is_archive_member()` 偵測壓縮檔路徑，
切換為 `read_bytes_from_zip` / `read_bytes_from_7z` + `cv2.imdecode()` 模式。

### 4. SSE 即時進度更新

**問題**：2 秒輪詢的進度更新不流暢，體驗差。

**修復**：切換為 `EventSource` SSE 連接。透過 `semantic_index.progress` 事件即時更新。
`visibilitychange` 在分頁隱藏時中斷 SSE，恢復時重新連接。

---

## Phase 7：YOLO 物件偵測 (2026-03-02)

### 概述

繼 CLIP 語義搜尋之後，在同一台 Hailo-10H 上實作 YOLO 物件偵測。
對圖片與影片進行 80 類別 COCO 物件偵測，並將結果儲存至 `file_annotations` 資料表。

### 架構設計

#### VDevice 共用問題

Hailo-10H 單一程序只能使用一個 VDevice，InferModel 也是排他的。
CLIP 和 YOLO 無法同時運行。

**解決方案**：新建 `core/hailo_device_core/device_manager.py`。
- `acquire_device(owner, hef_path)` — 若其他 owner 持有中則自動釋放並切換
- 相同 owner + 相同 HEF 時重複使用（避免重新初始化）
- 以 `threading.Lock` 確保執行緒安全
- 重構 CLIP 的 `hailo_inference.py`，委託給 device_manager

#### YOLO 輸出張量的處理

CLIP 只有一個輸出張量，但 YOLO 有多個輸出張量（對應各 stride 的 head）。
`device_manager` 收集所有輸出的 quantization parameters 並回傳。

#### 後處理流水線

YOLO 後處理包含以下步驟：
1. uint8 → float32 反量化（使用各 output 的 scale/zero_point）
2. grid cell → 像素座標解碼（sigmoid + grid offset + stride）
3. confidence 過濾
4. 各類別的 NMS（pure numpy）
5. letterbox 座標 → 原圖的正規化座標 (0-1) 轉換

#### 影片支援

以 ffmpeg 提取影格 → 各影格獨立偵測 → 按類別彙總。
保持各類別的最大 confidence + 出現影格數。

### 新模組結構

| 模組 | 職責 |
|---|---|
| `core/hailo_device_core/device_manager.py` | 共用 VDevice 生命週期管理 |
| `core/hailo_yolo_core/hailo_yolo_inference.py` | YOLODetector 單例模式 |
| `core/hailo_yolo_core/yolo_postprocess.py` | NMS、box decode、dequantize |
| `core/hailo_yolo_core/yolo_labels.py` | COCO 80 類別標籤 |
| `core/hailo_yolo_core/yolo_preprocess.py` | 640x640 letterbox 縮放 |
| `core/hailo_yolo_core/yolo_video.py` | 影片影格提取 + 彙總 |
| `core/hailo_yolo_core/yolo_indexer.py` | 背景批次偵測 |
| `core/hailo_yolo_core/model_download.py` | HEF 下載 |
| `core/hailo_yolo_core/event_handler.py` | scan.complete 處理器 |
| `extensions/builtin_hailo_yolo_detect/` | Extension + Blueprint API + UI |

### 技術筆記

- **多輸出張量**：YOLO HEF 有多個輸出張量（對應各 stride 的 head）。
  需遍歷 `infer_model.outputs` 收集所有的 shape/quant_params
- **輸出緩衝區**：為各輸出張量個別配置 uint8 緩衝區，
  以 `bindings.output(out.name).set_buffer(buf)` 指定名稱綁定
- **張量佈局**：形狀通常為 `(1, H, W, C)`。C 中包含 bbox (4) + class scores (80)
- **HEF 下載**：從 Hailo Model Zoo v5.2.0 直接下載。不設定 User-Agent 會
  被 Cloudflare 阻擋，因此設定 `_USER_AGENT`
- **偵測結果的儲存**：以 JSON 陣列儲存在 `file_annotations` 資料表的 `source='hailo:<model>'`, `key='detections'` 中。
  直接活用現有的 annotation CRUD API

---

## Phase 8：GenAI (LLM / VLM / Speech2Text) 整合 (2026-03-02)

### 目標

將 Hailo-10H 的 `hailo_platform.genai` 模組（LLM、VLM、Speech2Text）
整合到 device_manager，從 WebUI 使用文字生成、圖片理解、語音轉文字。

### device_manager 擴展

- **問題**：現有的 device_manager 僅支援 InferModel API（CLIP/YOLO）。
  GenAI 類別不使用 InferModel，而是直接接收 VDevice 的另一種模式
- **解決方案**：以 `_mode` 變數（`"infer"` | `"genai"`）區分模式。
  新增 `acquire_genai(owner, model_path, genai_factory)`，
  以 factory 模式生成 LLM/VLM/S2T 的實例
- **釋放處理的差異**：
  - InferModel：`del configured` → `del infer_model` → `del vdevice`
  - GenAI：`instance.release()` → `vdevice.release()`（明確的 release 方法）

### GenAI API 的發現事項

- **訊息格式**：OpenAI 相容的 role/content 結構。content 為陣列，`{"type": "text", "text": "..."}` 格式
- **VLM 圖片輸入**：336x336 RGB uint8 numpy 陣列。以 `frames=[image]` 列表傳遞。
  在提示中放置 `{"type": "image"}` 佔位符
- **S2T 輸入**：little-endian float32 (`<f4`)，單聲道，16kHz。int16→float32 正規化為必須
- **S2T 區段**：`generate_all_segments()` 回傳 `SegmentInfo` 物件的列表。
  具有 `.text`, `.start`, `.end` 屬性
- **上下文管理**：LLM/VLM 以 `get_context_usage_size()`, `max_context_capacity()`,
  `clear_context()` 管理上下文視窗
- **串流**：`generate()` 回傳迭代器，逐 token yield

### 模型 HEF 下載 URL

- 模式：`https://dev-public.hailo.ai/v{hailort_version}/blob/{ModelName}.hef`
- HailoRT 5.2.0 → `v5.2.0`
- 模型名稱為 CamelCase（例：`Qwen2.5-1.5B-Instruct.hef`, `Whisper-Base.hef`）
- 可在 `hailo-apps-infra` 的 `download_resources.py` 的 `gen-ai-mz` source type 中確認

### 新增檔案

| 檔案 | 說明 |
|----------|------|
| `core/hailo_genai_core/__init__.py` | 套件 init |
| `core/hailo_genai_core/genai_types.py` | GenAIModelType enum + GenAIModelInfo dataclass |
| `core/hailo_genai_core/model_download.py` | 7 個模型 HEF 下載管理 |
| `core/hailo_genai_core/llm_inference.py` | HailoLLM 包裝器（singleton, streaming）|
| `core/hailo_genai_core/vlm_inference.py` | HailoVLM 包裝器（singleton, 圖片前處理）|
| `core/hailo_genai_core/s2t_inference.py` | HailoS2T 包裝器（singleton, 區段支援）|
| `extensions/builtin_hailo_genai/extension.json` | Extension 清單 |
| `extensions/builtin_hailo_genai/hailo_genai_ext.py` | Blueprint 8 個 API（SSE streaming）|
| `extensions/.../templates/hailo_genai/_genai_ui.html` | Tools 頁面 UI（4 面板）|

### 技術筆記

- **VDevice.create_params()**：GenAI 模式以 `VDevice.create_params()` 建立參數，
  以 `VDevice(params)` 實例化。與 InferModel 模式的 `VDevice()`（無引數）不同
- **SSE 串流**：Flask 的 `Response(generator(), mimetype='text/event-stream')`
  逐 token 發送 `data: {"token": "..."}\n\n`。完成時發送 `data: {"done": true}\n\n`
- **VLM 的 FormData 送出**：因需同時發送圖片檔案 + 文字提示，
  VLM API 使用 `multipart/form-data` 而非 JSON
- **S2T 的 WAV 讀取**：伺服器端以 `wave` 模組 + `io.BytesIO`
  從上傳的 WAV 位元組串直接讀取

---

## Phase 9：語義搜尋 + VLM 字幕連動 (2026-03-03)

### 目標

對 CLIP 搜尋結果的圖片以 VLM（Qwen2-VL）批次生成字幕，
儲存到 `file_annotations`。

### 實作

- **`core/hailo_clip_core/caption_runner.py`** *(現已移至 `extensions/builtin_hailo_semantic_search/core_impl/caption_runner.py`)*（~150 行）：在背景執行緒中批次執行 VLM 字幕生成。沿用 `indexer.py` 的 `_state_lock` + `_stop_requested` + `_progress` 模式。SSE 事件 `vlm_caption.start/progress/complete`
- **Blueprint 擴展**：在 `hailo_semantic_search.py` 中新增 `/api/caption/start`, `/api/caption/status`, `/api/caption/stop` 共 3 個端點
- **UI**：在 Tools 頁面的 Semantic Search 區塊中新增「VLM Caption Generation」面板。提示輸入、SSE 進度條、搜尋結果 file_ids 自動連動

### VDevice 互斥控制

- 以 `acquire_genai("vlm", ...)` 取得 VLM。若 CLIP 索引器正在運行，device_manager 的現有行為會自動釋放
- 字幕完成後 VLM 持續持有裝置，CLIP 索引的重啟需要卸載模型

### Annotation 儲存規範

- `source="hailo:vlm"`, `key="caption"`, `value=<字幕文字>`

---

## Phase 10：影片音訊轉文字 — S2T 流水線 (2026-03-03)

### 目標

從影片檔案以 ffmpeg 提取音訊 → 以 Whisper (S2T) 轉文字 → 儲存到 `file_annotations`。

### 實作

- **`core/files_core/video_audio.py`**（~80 行）：`extract_audio_wav()` 以 ffmpeg 提取音訊（mono PCM s16le 16kHz）。從影片的 duration 動態計算逾時時間（最大 120 秒）。`check_ffmpeg()` 從 `media_video.py` 重複使用
- **Blueprint 擴展**：在 `hailo_genai_ext.py` 中新增 3 個端點：
  - `POST /api/s2t/transcribe-video`：單一影片的轉文字（file_id, language）
  - `POST /api/s2t/batch-transcribe`：多個影片的批次轉文字（file_ids, language），背景執行緒 + SSE 進度（`video_s2t.*`）
  - `GET /api/s2t/transcript/<file_id>`：取得已儲存的轉文字
- **UI**：在 S2T 面板中新增「Video Transcription」子區塊。file_id 輸入、語言選擇（ja/en）、取得已儲存按鈕

### Annotation 儲存規範

- `source="hailo:s2t"`, `key="transcript"`, `value=<全文文字>`
- `source="hailo:s2t"`, `key="transcript_segments"`, `value=<JSON [{text, start, end}, ...]>`

### 注意事項

- 暫存 WAV 以 `tempfile.NamedTemporaryFile` 建立，在 finally 中必定刪除
- S2T 與 LLM/VLM 裝置互斥（無法同時使用）

---

## Phase 11：LLM 多輪對話 UI 改善 (2026-03-03)

### 目標

將單次提示擴展為支援對話歷史。上下文延續、重置、泡泡型 UI。

### 實作

- **API 修改**：`api_llm_generate()` 可接收 `messages` 陣列。向後相容：僅有 `prompt` 時按照既有方式轉換為 system + user 訊息。`generate_stream()` 已支援多輪對話（透過 `_normalise_prompt()`）
- **泡泡型聊天 UI**：`hg-chat-container` + `hg-bubble`（user=右對齊紫色，AI=左對齊灰色）。CSS 類別：`hg-bubble-user`, `hg-bubble-ai`, `hg-bubble-label`
- **對話歷史管理**：JS 端以 `_chatHistory = []` 陣列累積 `{role, content}`。API 送出時傳 `messages: [systemMsg, ..._chatHistory]`。`hgLlmClear()` 重置陣列 + 清除 HailoRT 上下文
- **串流**：先將 AI 泡泡插入 DOM，SSE token 逐次追加

### 錯誤修復：多輪對話的 system role 錯誤 (2026-03-03)

透過 MCP 除錯查詢 + hailort 日誌發現。第 2 輪以後的 `generate()` 呼叫發生以下錯誤：

```
[HailoRT] [error] CHECK failed - System role messages can only be provided on the first prompt
[HailoRT] [error] CHECK_SUCCESS failed with status=HAILO_INVALID_OPERATION(6)
```

**原因**：UI 範本每次都以 `[systemMsg].concat(_chatHistory)` 將 system role 放在開頭送出。HailoRT 的 LLM API 在上下文存在的狀態下（第 2 輪以後）不接受 system role。

**修復**：
1. 在 `llm_inference.py` 中新增 `_prepare_prompt()` 方法：`get_context_usage_size() > 0` 時自動排除 system role 訊息
2. UI 範本（`_genai_ui.html`）：僅在 `_chatHistory.length <= 1`（僅首次使用者訊息）時附加 system

**技術筆記**：HailoRT 的限制是 `LLM.generate()` 僅在首次呼叫時處理 system role。這與 OpenAI API 的行為不同，在實作多輪對話時需要注意

---

## WD-Tagger VLM x Hailo-10H 實機測試 (2026-03-03)

### 測試環境
- Raspberry Pi 5 + Hailo AI HAT 2 (Hailo-10H)
- HailoRT FW 5.2.0, hailo_platform Python 5.2.0
- hailo-ollama v0.5.1（建置版）
- Qwen2-VL-2B-Instruct.hef (3.0 GB)

### 重要發現：hailo-ollama 不支援 VLM

hailo-ollama 的官方文件 (USAGE.rst) 中明確記載：
> "The Hailo-Ollama API is currently limited to language models (LLMs) and cannot be used for VLMs."

MODELS 表格中 `Qwen2-VL-2B-Instruct` 的 Inference API 欄位也僅有 "C++, Python"，不含 "Hailo-Ollama"。

`/hailo/v1/list` 回傳的模型清單：
```
deepseek_r1:1.5b, llama3.2:1b, qwen2.5-coder:1.5b, qwen2.5:1.5b, qwen2:1.5b
```
不含 `qwen2-vl`。

### hailo-ollama 測試結果

**config 的注意事項**：建置版二進位檔使用 `NLOHMANN_DEFINE_TYPE_NON_INTRUSIVE` 巨集，config JSON 中 `limits` 鍵為必須。官方 config 範本中未包含，需新增以下內容：
```json
"limits": {"max_in_flight": 4, "max_queue": 10, "retry_after_sec": 1}
```

- **LLM 文字生成 (qwen2.5:1.5b)**：OpenAI + Ollama native 兩者 OK，6.5 TPS
- **OpenAI API vision 請求**：500 錯誤 (`Node is NOT a STRING`)
- **Ollama native API + images**：被接受但 LLM 無法處理圖片
- **VlmWdTaggerEngine 回退**：OpenAI 500 → Ollama native 自動切換 OK
- **response_format: json_object**：被接受但 JSON 輸出不會被強制

### Hailo Python SDK VLM 直接測試結果

VLM 需在訊息格式中包含 `{"type": "image"}`：
```python
messages = [
    {"role": "user", "content": [
        {"type": "image"},
        {"type": "text", "text": "Tag this image."}
    ]}
]
vlm.generate_all(messages, frames=[frame_336x336_rgb_uint8])
```

- **模型載入**：33 秒（首次冷啟動。與公稱 6.2 秒的差距主要由磁碟 I/O 支配）
- **推論速度**：~5.1 TPS（128 token / 20 秒）。與公稱 6.73 TPS 的差距因包含 TTFT
- **圖片辨識精度**：正確理解圖片內容（準確描述「雪景中牽手的兩位女性」）
- **JSON 輸出品質**：低。2B 模型的結構化 JSON 生成精度不穩定（逗號缺失、markdown 代碼圍欄混入）

### 發現的 Bug

1. **`engines_hailo_vlm.py` 提示格式**：對 VLM 傳送了純文字訊息 → 修改為包含 `{"type": "image"}` 的列表格式
2. **`vlm_inference.py` frames 引數**：VLM 的 `generate_all()` 需要 `frames`，但宣告為 Optional → 改為必須

### 技術筆記

- **VDevice 排他限制**：hailo-ollama 啟動中無法取得 `hailo_platform.VDevice()`。VLM 直接推論時需停止 hailo-ollama
- **VLM.generate_all() frames 為必須**：純文字推論會產生 `HAILO_INVALID_OPERATION` 錯誤。LLM 和 VLM 的 API 前提條件不同
- **Qwen2-VL 的 prompt template**：以 Jinja2 範本插入 `<|vision_start|><|image_pad|><|vision_end|>`。在訊息格式中包含 `{"type": "image"}` 後 SDK 會自動處理

---

## Phase 12：OpenAI 相容 API + 裝置切換 Bug 修復 (2026-03-14)

### 目標

1. 提供 OpenAI 相容 API，讓 OpenAI SDK / LiteLLM / Continue.dev / Open WebUI 等外部工具可直接使用 Hailo GenAI
2. 修復 Quart async 的不完善之處
3. MCP 工具的 SSE 端點支援

### 實作：OpenAI 相容 API (`hailo_openai_routes.py`)

新建 `extensions/builtin_hailo_genai/hailo_openai_routes.py`。實作以下 4 個端點：

| 端點 | 功能 | 對應模型 |
|---|---|---|
| `GET /v1/models` | 可用模型一覽 | 全模型 + CLIP |
| `POST /v1/chat/completions` | 文字/圖片聊天（支援 stream）| LLM + VLM |
| `POST /v1/audio/transcriptions` | 語音轉文字 | Whisper |
| `POST /v1/embeddings` | 文字→CLIP 向量 | CLIP ViT-B/16 |

#### 設計上的決策

- **Vision 支援**：直接接受 OpenAI Vision API 格式（`image_url` with `data:` base64）。另外支援 `file_id:123` 格式直接參照 YU 圖庫的圖片
- **HTTP URL 不支援**：為防止 SSRF，`image_url` 不接受 `http://` / `https://`
- **模型別名**：`whisper-1` → `whisper-base`、`clip` → `clip-vit-b-16` 等 OpenAI 相容別名
- **非 WAV 音訊**：以 ffmpeg 自動轉換（16kHz mono PCM16）
- **Usage 欄位**：Hailo SDK 不回傳 token 數，因此固定為 `0`。未來有改善空間

#### MCP 工具

- `hailo_genai_openai_info`：回傳端點一覽與使用方法的輔助工具（不呼叫 API，在本地生成）

### 修復：Quart async SSE 產生器

所有路由檔案的 SSE 產生器均有 async 支援的不完善：

| 檔案 | 問題 | 修復 |
|---|---|---|
| `hailo_llm_routes.py` | `def generate_sse()` 為同步函式 | 改為 `async def`，`get_llm()` 和 `next(it)` 以 `asyncio.to_thread` 執行 |
| `hailo_vlm_routes.py` | 同上 + DB 參照為同步 | 同上 + 以 `run_db_sync` 包裝 |
| `hailo_s2t_routes.py` | transcribe 為同步執行 + DB 為同步 | 以 `asyncio.to_thread` + `run_db_sync` 包裝 |
| `hailo_chat_routes.py` | 同上（LLM/VLM 兩者）| 將所有阻塞呼叫改為 async 化 |

Quart (ASGI) 中若產生器不是 `async def`，會阻塞事件迴圈，SSE 傳送中其他請求無法處理。

### 發現的 Bug：裝置切換時的 Singleton 不一致

#### 症狀

VLM 使用後呼叫 LLM 時發生 `'NoneType' object has no attribute 'get_context_usage_size'` 錯誤。反方向（LLM→VLM→LLM）也必定發生。

#### 原因分析

Hailo-10H 只能保持一個 VDevice，因此由 `device_manager.py` 進行排他管理。模型切換時的流程：

1. VLM 的 `get_vlm()` → `acquire_genai("vlm", ...)` → 內部 `_release_internal()` 釋放 LLM 的 VDevice
2. VLM 使用完成
3. LLM 的 `get_llm()` → `_instance` 仍存在 + `model_name` 也一致 → **重複使用現有實例**
4. `_instance._llm` 背後的 VDevice 已被釋放 → `get_context_usage_size()` 在 `None` 上被呼叫而崩潰

問題的根本：即使 Singleton 的 `_instance` 仍存在，其內部的 Hailo SDK 物件 (`self._llm`) 所指向的 VDevice 已被 `device_manager` 的 `_release_internal()` 呼叫 `.release()`。Python 的參照計數下 `_instance._llm` 仍然存活，但 Hailo SDK 原生端的資源已被釋放。

#### 修復

在 `get_llm()` / `get_vlm()` / `get_s2t()` 的 Singleton 重複使用檢查中新增 `device_manager.get_current_owner()` 確認：

```python
def get_llm(model_name="qwen2.5-1.5b-chat"):
    global _instance
    with _lock:
        if _instance is not None and _instance.model_name == model_name:
            from core.hailo_device_core.device_manager import get_current_owner
            if get_current_owner() == "llm":
                return _instance  # デバイスを保持中 → 再利用 OK
            # デバイスが他のモデルに奪われている → 再作成
            _instance = None
        ...
```

對 LLM / VLM / S2T 三個 Singleton 全部套用相同修復。

#### 驗證

LLM → VLM → LLM → VLM 連續 4 次切換全部正常運作已確認。

### 其他修復

- **MCP `post_sse` 方法**：在 `mcp_server/client.py` 中新增消費 SSE 串流並以 JSON 回傳最終文字的 `post_sse()` 方法。`hailo_llm_generate` 和 `hailo_vlm_generate` 工具使用此方法
- **MCP `yolo_search` 參數**：`labels` → `class_name` 重新命名（與 API 端參數名稱一致）
- **Circuit Breaker**：新增 `_READ_SUFFIXES`（`_status`, `_info`, `_list`, `_stats`）。half_open 狀態下 `hailo_genai_status` 等狀態系工具得以被允許
- **Semantic Search async**：以 `run_db_sync` 包裝 `get_encoder_info()` 和 `semantic_search()`（防止 Quart 事件迴圈阻塞）

### 技術筆記

- **VDevice 的排他限制在 SDK 層級**：即使 Python 端持有物件的參照，Hailo SDK 原生端的資源被釋放後就無法使用。使用 Singleton 模式時，需另外檢查原生資源的有效性
- **Quart + 同步產生器**：將同步產生器傳給 Quart 的 SSE 回應雖然可運作，但 `yield` 之間的處理會阻塞事件迴圈。如 Hailo 推論等重度處理，務必以 `asyncio.to_thread` 移到其他執行緒
- **OpenAI Vision API 與 VLM 的連動**：OpenAI Vision API 以 `image_url` 欄位接收圖片，但 Hailo VLM 以 `frames`（numpy array）接收。在轉換層進行 base64 解碼 → OpenCV 解碼 → 336x336 RGB 縮放
