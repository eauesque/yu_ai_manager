# Hailo 語意搜尋擴充功能 — 實作規格

**狀態**：已實作 — Hailo 專用版本已被 CLIP ONNX (v2.95.0) 取代
**目標**：YU AI Manager 擴充功能
**目的**：在 Hailo-10H (AI HAT 2) 上使用 CLIP/SigLIP 進行語意圖片搜尋
**實作**：`extensions/builtin_clip_search/core_impl/`（共享層）+ `extensions/builtin_clip_onnx/core_impl/`（ONNX 實作）
**注意**：本規格描述的是初始 Hailo 專用設計。目前實作使用統一的 ONNX 多後端架構。

---

## 概述

此擴充功能新增了使用自然語言文字搜尋圖片的功能。
範例：「藍天和大海」、「微笑的女孩」、「夜晚城市風景」— 都會回傳視覺上相似的圖片。

需要與現有的 FTS5 標籤搜尋和 pHash 相似度搜尋**並行**運作。
在沒有 Hailo 裝置的環境中，擴充功能會自動停用。

---

## 架構

```
[圖片掃描時]
圖片檔案 -> CLIP Image Encoder (Hailo HEF) -> 512 維向量 -> DB 儲存

[搜尋時]
文字輸入 -> CLIP Text Encoder (CPU / Hailo HEF) -> 512 維向量
         -> 餘弦相似度搜尋 -> file_id 清單 -> 與現有搜尋結果合併
```

**同時支援 CLIP 和 SigLIP**，可透過設定切換。
SigLIP 提供更高的準確度，但 CLIP 有更強的實績和更多社群資源。
建議的做法是先從 CLIP 開始，之後再加入 SigLIP。

---

## Phase 分解

### Phase 1：可行性驗證（優先執行）

移至 Pi5 環境後，讓 Claude Code **按從上到下的順序**執行以下步驟。
在任何步驟失敗時停止，先解決問題再繼續。

#### 步驟 1-1：驗證 HailoRT 執行環境

```bash
# 檢查裝置辨識
hailortcli fw-control identify

# 檢查 Python 繫結
python3 -c "import hailo_platform; print('HailoRT version:', hailo_platform.__version__)"
```

- **裝置不可見**：使用 `dmesg | grep hailo` 檢查驅動程式狀態。驗證 AI HAT 2 的 PCIe 連線
- **匯入失敗**：透過 `pip install hailort` 或從 Hailo APT 儲存庫（`python3-hailort`）安裝

#### 步驟 1-2：下載 CLIP HEF 檔案

```bash
mkdir -p ~/hailo_models && cd ~/hailo_models

# Image encoder
wget https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/clip_vit_b_16_image_encoder.hef

# Text encoder
wget https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/clip_vit_b_16_text_encoder.hef
```

- **403 / 存取被拒**：需要在 Hailo Developer Zone (https://hailo.ai/developer-zone/) 註冊。
  註冊後，嘗試透過 Model Zoo CLI（`hailo_model_zoo`）下載
- **大小檢查**：每個檔案應為數十到約 100 MB。異常小的檔案表示下載失敗

#### 步驟 1-3：安裝 Python 依賴套件

```bash
# 圖片前處理所需（Phase 1 使用）
pip install opencv-python-headless numpy

# 驗證
python3 -c "import cv2; import numpy; print('cv2:', cv2.__version__, 'numpy:', numpy.__version__)"
```

#### 步驟 1-4：最小推論測試

```python
from hailo_platform import HEF, VDevice, HailoStreamInterface, InferVStreams, ConfigureParams
import numpy as np

hef_path = "/home/<user>/hailo_models/clip_vit_b_16_image_encoder.hef"
hef = HEF(hef_path)

# 檢查 HEF 輸入/輸出層資訊（層名稱因模型而異）
print("Input layers:", [l.name for l in hef.get_input_vstream_infos()])
print("Output layers:", [l.name for l in hef.get_output_vstream_infos()])

with VDevice() as target:
    configure_params = ConfigureParams.create_from_hef(hef, interface=HailoStreamInterface.PCIe)
    network_groups = target.configure(hef, configure_params)
    network_group = network_groups[0]

    input_info = hef.get_input_vstream_infos()[0]
    input_name = input_info.name
    input_shape = input_info.shape  # Expected: (224, 224, 3) etc.
    print(f"Input: name={input_name}, shape={input_shape}")

    # 使用虛擬圖片進行推論測試
    dummy = np.random.randint(0, 255, (1, *input_shape), dtype=np.uint8)
    with InferVStreams(network_group, {}) as pipeline:
        result = pipeline.infer({input_name: dummy})
        for name, data in result.items():
            print(f"Output: name={name}, shape={data.shape}, dtype={data.dtype}")
            # 輸出 512 維向量即為成功
```

- **VDevice 錯誤（`not enough free devices`）**：hailo-ollama 可能正在執行。使用 `systemctl stop hailo-ollama` 停止後重試
- **推論成功但輸出不是 512 維**：驗證 HEF 版本和模型變體

#### 步驟 1-5：判斷標準

| 結果 | 後續行動 |
|------|----------------|
| 輸出 512 維向量 | 繼續 Phase 2 以後的步驟 |
| HEF 載入成功但輸出維度不同 | 嘗試其他模型變體（clip_resnet_50 等） |
| 無法下載 HEF | 在 Developer Zone 註冊 -> 透過 Model Zoo CLI 下載 |
| 無法匯入 hailo_platform | 重新安裝 HailoRT。若仍無法解決，退回 CPU CLIP |
| 裝置未被辨識 | 硬體連線/驅動程式問題。暫停此擴充功能開發 |

Phase 1 成功則繼續完整實作。若不成功則考慮 CPU CLIP 作為替代方案。

---

### Phase 2：DB Schema 擴充

加入現有的 DB 遷移：

```sql
-- migration 14: semantic search vectors
CREATE TABLE IF NOT EXISTS file_vectors (
    file_id     INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
    model       TEXT NOT NULL DEFAULT 'clip',   -- 'clip' | 'siglip'
    vector      BLOB NOT NULL,                  -- float32 numpy array -> bytes
    created_at  INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);

CREATE INDEX IF NOT EXISTS idx_file_vectors_model ON file_vectors(model);
```

儲存：`numpy.ndarray.tobytes()` -> BLOB
載入：`numpy.frombuffer(blob, dtype=numpy.float32)`

**注意**：SQLite 沒有 ANN（近似最近鄰）索引，因此所有 200,000 筆記錄都需要完整的餘弦相似度計算。使用 numpy 批次計算在 Pi5 上應可維持在可接受的範圍內（需實測）。若記錄數量大幅增長，考慮使用 `sqlite-vec` 擴充功能。

---

### Phase 3：Hailo 推論核心

**檔案結構**：
```
extensions/hailo_semantic_search/
├── __init__.py
├── extension.py          # 擴充功能進入點
├── core/
│   ├── hailo_clip.py     # Hailo CLIP 推論封裝
│   ├── cpu_clip.py       # 無 Hailo 環境的 CPU 後備方案（選用）
│   └── vector_store.py   # DB 向量 CRUD
├── routes/
│   └── semantic_search.py  # API 端點
└── templates/
    └── _semantic_search_ui.html
```

**`hailo_clip.py` 的職責**：
- HEF 載入和 VDevice 初始化（單例，啟動時執行一次）
- 圖片 -> 前處理（224x224 縮放、正規化）-> HEF 推論 -> 512 維向量
- 文字 -> 分詞 -> HEF 推論 -> 512 維向量
  * 若 Hailo-10H 有可用的文字編碼器 HEF 則使用；否則使用 CPU（transformers 函式庫）

**前處理**：
```python
import cv2
import numpy as np

def preprocess_image(path: str) -> np.ndarray:
    img = cv2.imread(path)
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    img = cv2.resize(img, (224, 224))
    img = img.astype(np.float32) / 255.0
    mean = np.array([0.48145466, 0.4578275, 0.40821073])
    std  = np.array([0.26862954, 0.26130258, 0.27577711])
    img = (img - mean) / std
    return img[np.newaxis, ...]  # (1, 224, 224, 3)
```

---

### Phase 4：索引建置 API

**端點**：
```
POST /api/extensions/hailo-semantic/index
```
- 在背景執行緒中依序處理未建立索引的圖片
- 透過 SSE 以 `semantic_index.progress` 事件發送進度
- 可選擇性地掛載到現有的 `scan.complete` 事件以自動執行

**批次大小**：每批 32 張圖片（平衡記憶體和速度）

```
GET /api/extensions/hailo-semantic/index/status
-> { "total": 200000, "indexed": 12500, "running": true }
```

---

### Phase 5：語意搜尋 API

```
GET /api/extensions/hailo-semantic/search?q=blue sky&limit=50&threshold=0.25
```

**處理流程**：
1. 將文字 `q` 轉換為向量
2. 從 `file_vectors` 載入所有向量（numpy）
3. 批次計算餘弦相似度
4. 將超過 `threshold` 的結果依相似度降序排列
5. 以現有 `/api/search` 格式回傳 `file_id` 清單

**餘弦相似度計算**：
```python
def cosine_similarity_batch(query_vec: np.ndarray, stored_vecs: np.ndarray) -> np.ndarray:
    # query_vec: (512,), stored_vecs: (N, 512)
    query_norm = query_vec / np.linalg.norm(query_vec)
    stored_norm = stored_vecs / np.linalg.norm(stored_vecs, axis=1, keepdims=True)
    return stored_norm @ query_norm  # (N,)
```

**效能目標**：200,000 筆記錄在 1 秒以內（使用 numpy 批次計算，即使在 Pi5 上也可達成）

---

### Phase 6：UI 整合

在現有搜尋 UI 中新增「語意搜尋」分頁。
可以是獨立於現有條件建構器的獨立 UI（整合留待未來）。

```html
<!-- 在搜尋列旁新增切換按鈕 -->
<button id="semantic-search-toggle" class="btn-secondary">
  🔍 語義搜尋 (Hailo)
</button>
```

- 未偵測到 Hailo 裝置時隱藏或灰化按鈕
- 搜尋結果復用現有的網格顯示
- 無索引時顯示建置索引的提示

---

## 設定（config.json 新增）

```json
{
  "hailo_semantic_search": {
    "enabled": true,
    "model": "clip",           // "clip" | "siglip"
    "device": "auto",          // "auto" | "hailo" | "cpu"
    "batch_size": 32,
    "similarity_threshold": 0.25,
    "auto_index_on_scan": false,
    "hef_dir": "~/.local/share/hailo-ollama/models"
  }
}
```

---

## 已驗證事實（截至 2026-02-27）

以下資訊已透過先前研究確認。在執行 Phase 1 時作為參考使用。

### CLIP HEF 可用性

Hailo Model Zoo v5.2.0 包含 Hailo-10H 的 CLIP/SigLIP 各變體的**影像編碼器和文字編碼器** HEF：

| 模型 | Image Encoder HEF | Text Encoder HEF |
|--------|-------------------|-------------------|
| clip_vit_b_16 | 可用 | 可用 |
| clip_vit_b_32 | 可用 | 可用 |
| clip_vit_l_14 | 可用 | 可用 |
| clip_resnet_50 | 可用 | 可用 |
| siglip_b_16 | 可用 | 可用 |
| siglip_l_16_256 | 可用 | 可用 |
| siglip2_b_32_256 | 可用 | 可用 |
| TinyCLIP 變體 | 可用 | 可用 |

S3 URL 格式：`https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/<model>.hef`

### 文字編碼器狀態

- 官方 `hailo-CLIP` 應用程式在 **CPU（PyTorch）上執行文字編碼器**
- Hailo-10H 的 Text Encoder HEF 存在於 Model Zoo 中，但**尚無已發布的應用程式使用它們**
- 建議做法：**在 CPU 上實作文字編碼器（`sentence-transformers`）**。每次搜尋查詢只執行一次，速度不是問題
- 影像編碼器才是 Hailo 加速真正發揮價值的地方（批次索引 200K 張圖片）

### 與 hailo-ollama 共存

- 透過 `SHARED_VDEVICE_GROUP_ID` 的裝置共享獲官方支援
- 然而，**hailo-ollama 二進位檔不參與此共享**（它獨佔裝置）
- 社群範例：有人建立了自訂裝置管理器以同時執行 6 個服務
- **實際做法**：在索引建置期間停止 hailo-ollama，分時共享裝置
  - `systemctl stop hailo-ollama` -> 建置索引 -> `systemctl start hailo-ollama`

### 200,000 筆記錄的向量搜尋估算

- 200K x 512 float32 = 約 400MB — 可納入 Pi5（8GB）的 RAM
- numpy 批次餘弦相似度在 Pi5 Cortex-A76 上應可在 1 秒內完成

### FAISS 加速大規模向量搜尋（v3.26.0）

FAISS（Facebook AI Similarity Search）支援在 v3.26.0 中新增。系統在安裝 `faiss-cpu` 時自動偵測，並使用近似最近鄰搜尋取代 NumPy 暴力搜尋。

| 規模 | NumPy (O(N)) | FAISS IndexFlatIP | FAISS IndexIVFFlat |
|------|-------------|-------------------|-------------------|
| 10K | ~10ms | ~2ms | - |
| 100K | ~100ms | ~20ms | ~5ms |
| 500K | ~500ms | ~100ms | ~10ms |
| 1.5M | ~1.5s | ~300ms | ~20ms |

- **< 50K**：自動選擇 IndexFlatIP（精確內積搜尋）
- **>= 50K**：自動選擇 IndexIVFFlat（IVF 分群），nprobe = nlist/10
- 未安裝 FAISS 時退回 NumPy（無影響）

**安裝**：
```bash
source venv/bin/activate
uv pip install faiss-cpu  # x86_64 上可直接 pip install
# 在 aarch64（RPi）上：conda install -c conda-forge faiss-cpu 或從原始碼建置
```

啟用時啟動日誌會顯示 `FAISS x.x.x detected — using accelerated vector search`。

### 關於 hailo-CLIP 應用程式的注意事項

- `hailo-ai/hailo-CLIP` 目標為 **Hailo-8/8L**。不支援 Hailo-10H
- 設計用於即時零樣本分類，而非圖片搜尋管線
- 可作為參考資料，但無法直接使用。必須使用 HailoRT API 建置自訂管線

---

## 替代方案（Hailo 不可用時）

`sentence-transformers` 搭配 `clip-ViT-B-32` 提供純 CPU 的 CLIP 支援。
速度較慢，但允許同一擴充功能在沒有 Hailo 的環境中運行。

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('clip-ViT-B-32')
image_embedding = model.encode(Image.open(path))
text_embedding  = model.encode("blue sky")
```

在擴充功能設定中設定 `"device": "cpu"` 即可啟用 CPU 模式。此雙架構方案可最大化可攜性。

---

## 實作優先順序

```
Phase 1（驗證）       -> 必要，優先執行
Phase 2（DB）         -> Phase 1 成功後
Phase 3（推論核心）   -> Phase 2 之後
Phase 4（索引建置）   -> Phase 3 之後
Phase 5（搜尋 API）   -> Phase 4 之後
Phase 6（UI）         -> Phase 5 之後，最後
```

Phase 1 失敗則將整體方案切換為 CPU CLIP。

---

## 參考儲存庫

- `hailo-ai/hailo-apps`：CLIP 零樣本分類範例
- `hailo-ai/hailort`：pyHailoRT API 參考
- `hailo-ai/Hailo-Application-Code-Examples`：Python 推論範例
- `hailo-ai/hailo_model_zoo`：CLIP/SigLIP HEF 下載來源

---

*建立：2026-02-27*
*研究附錄：2026-02-27 — Phase 1 程序細節、HEF 可用性確認、hailo-ollama 共存分析*
