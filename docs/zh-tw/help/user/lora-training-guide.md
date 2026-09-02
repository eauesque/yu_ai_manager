# LoRA 訓練指南

使用 YU AI Manager + MCP + kohya_ss 進行自然語言 LoRA 訓練的完整指南

---

## 前言

本指南說明如何透過 YU AI Manager 的 MCP 伺服器與 kohya_ss 整合，僅憑自然語言指示即可完成 LoRA 製作流程。

傳統 LoRA 製作的大部分工時花費在「資料集手動準備」上：圖片篩選、標籤審查與排除、caption 檔案整理、資料夾結構整頓——這些全由人工完成。

YU AI Manager 的 MCP 整合改變了這個流程。只需一句「請為○○製作 LoRA，排除△△標籤」，從素材收集、標記、資料集生成到啟動 kohya_ss 訓練，整個流程一貫作業。

---

## 整體流程

LoRA 製作分為以下五個階段：

| 階段 | 作業內容 | 負責方 |
|------|---------|--------|
| 1. 素材準備 | 收集並配置訓練用圖片 | 人工 / AI 代理 |
| 2. 標記 | 透過 WD-Tagger 自動標記 | MCP（自動） |
| 3. 資料集生成 | 建立專案、設定排除標籤、匯出 | MCP（自動） |
| 4. 執行訓練 | 呼叫 kohya_ss 進行訓練 | MCP（自動） |
| 5. 驗證 | 在 SD 中使用 LoRA 確認結果 | 人工 |

人工介入僅限於決定「要訓練什麼」與最終結果確認。

---

## 前置條件

### 必要軟體

- YU AI Manager — 含 MCP 伺服器功能
- Claude Desktop 或 Claude Code — MCP 用戶端
- kohya_ss — 需包含 sd-scripts
- Stable Diffusion WebUI（A1111 / ComfyUI / Forge）— 結果驗證用

### GPU 需求

| GPU VRAM | 支援模型 | 必要設定 |
|---------|---------|---------|
| 8GB | 僅 SD 1.5 實用 | `--gradient_checkpointing` 必要 |
| 12GB | SDXL 可運行（有限制） | `--gradient_checkpointing` + `--cache_latents_to_disk` |
| 16GB | SDXL 流暢 | 預設設定即可運行 |
| 24GB+ | SDXL 與 FLUX 均支援 | 幾乎無限制 |

> **注意**：RTX 3060 12GB 可進行 SDXL LoRA 訓練，但因需使用 gradient_checkpointing，24,000 步驟約需 10 小時。RTX 5060 Ti 16GB 預計可縮短至 3〜5 小時。

### kohya_ss 目錄結構

kohya_ss 的頂層目錄與實際腳本目錄通常是分離的：

```
O:\webui\kohya_ss\              ← 設定為 kohya_path 的頂層目錄
O:\webui\kohya_ss\venv\         ← Python 虛擬環境（自動偵測）
O:\webui\kohya_ss\sd-scripts\   ← 存放訓練腳本的目錄
```

> ⚠️ **注意**：將頂層目錄指定為 `kohya_path`，YU AI Manager 會自動偵測 `sd-scripts` 子資料夾與 venv。請勿直接指定 sd-scripts 路徑。

---

## YU AI Manager 設定

### Extension 設定

在 LoRA Dataset Manager 的設定頁籤中輸入以下內容：

| 設定項目 | 說明 | 範例 |
|---------|------|------|
| `kohya_path` | kohya_ss 頂層目錄 | `O:\webui\kohya_ss` |
| `output_base_dir` | 資料集輸出基底目錄 | `C:\lora_datasets` |
| `checkpoint_dir` | 基礎模型所在目錄 | `O:\webui\models\Stable-diffusion` |
| `default_base_model` | 預設模型類型 | `sdxl` |

### WD-Tagger 設定

LoRA 資料集用途不建議搭配 VLM（llava 等）。VLM 會產生大量自由格式標籤，降低 caption 品質。

```
engine_type: "onnx"  ← 僅使用 ONNX
```

> ⚠️ **注意**：將 `engine_type` 設為 `"both"` 會產生 VLM 衍生的複合標籤（如 `wooden_bear_and_fish_sculpture`）。這些標籤無法作為 kohya_ss 的 caption，會妨礙訓練。

---

## 透過 MCP 建立 LoRA 的步驟

### Step 1：準備素材圖片

將訓練用圖片配置到 YU AI Manager 的 scan root 並執行掃描。

- 在 YU AI Manager 的 Scan Root 設定中新增訓練資料夾
- 掃描完成後，目標圖片會登錄至 DB
- 最少 20〜30 張，建議 50〜200 張

> **注意**：圖片品質是訓練結果的最大決定因素。選擇解析度 512px 以上、主體清晰的圖片。

### Step 2：使用 WD-Tagger 標記

從 MCP 執行批次標記：

```python
# 取得目標檔案 ID 列表並批次標記
wd_tagger_batch(file_ids=[...], expected_count=N)
wait_for_batch(job_id="wd_tagger")
```

若已有現有標籤，請先刪除再重新執行：

```python
wd_tagger_delete_tags_batch(file_ids=[...], expected_count=N)
```

### Step 3：建立專案

```python
create_lora_project(
    name="carved_bear",
    concept="carved_bear",   # 用作 kohya_ss 資料夾名稱
    base_model="sdxl",
    repeat=20
)
```

### Step 4：設定檔案與標籤

將檔案 ID 設定至專案並確認標籤統計：

```python
update_lora_project(project_id=N, file_ids=[...])
get_lora_project_tags(project_id=N)
```

查看標籤統計後決定要排除的標籤。

#### 排除標籤的設計思維

這是決定 LoRA 「要學習什麼」的核心。

**保留的標籤**：要學習的概念固有特徵（造形、風格、固有元素）

**排除的標籤**：基礎模型已知的通用標籤（`no_humans`、`realistic`、`animal`、`solo`、背景相關等）

範例——木雕熊 LoRA：

- 保留：`bear`、`fish`、`statue`、`sculpture`、`standing`、`full_body`、`open_mouth`
- 排除：`no_humans`、`animal_focus`、`animal`、`realistic`、`simple_background`、`solo`、`indoors`、`shadow`...

> ⚠️ **注意**：若無法精確切出概念，訓練會分散。若想保留 `bear` 或 `wood`，WD-Tagger ONNX 可能不一定會附加這些標籤。請透過 caption 預覽確認實際輸出。

```python
update_lora_project(
    project_id=N,
    tag_exclude=["no_humans", "animal_focus", "animal", "realistic", ...]
)
```

### Step 5：預覽 Caption

```python
preview_lora_caption(project_id=N, file_id=<任意檔案ID>)
```

輸出範例：

```
"fish, full_body, open_mouth, standing"
```

確認輸出為沒有 VLM 雜訊的簡潔標籤列表。若有許多空白 caption，請重新檢視排除標籤設定。

### Model Scope

Each project has a `model_scope` setting that controls which WD-Tagger model is used for captions, preview, and export.

- `active` (default for new projects): Use tags from the active WD model only. If no active model is set, it falls back to all models.
- `all` (default for existing projects): Mix tags from all models.
- `<model_id>` (for example, `wd-eva02-large-tagger-v3`): Use tags from the explicitly selected model only.

For files tagged by multiple models, `active` is usually sufficient. When you need an explicit model for comparison or validation, use the same model_id shown in the WD-Tagger profile dropdown on the Tools page.

### Step 6：匯出資料集

```python
export_lora_dataset(project_id=N)
```

輸出資料夾結構：

```
{output_base_dir}/{project_name}/{repeat}_{concept}/
    image001.jpeg
    image001.txt   ← caption
    image002.jpeg
    image002.txt
```

### Step 7：執行訓練

先用 dry_run 確認指令：

```python
preview_lora_train_command(
    project_id=N,
    checkpoint="完整路徑\checkpoint.safetensors"
)
```

確認無誤後啟動訓練：

```python
start_lora_training(
    project_id=N,
    checkpoint="完整路徑\checkpoint.safetensors",
    extra_args=["--gradient_checkpointing", "--xformers", "--cache_latents_to_disk"]
)
```

確認進度：

```python
get_lora_train_status(project_id=N, tail=20)
```

---

## 預設訓練參數

| 參數 | 預設值 | 說明 |
|-----|--------|------|
| `network_dim` | 32 | LoRA 的 rank。越大表現力越高，但檔案也越大 |
| `network_alpha` | 16 | 通常設為 dim 的一半 |
| `learning_rate` | 1e-4 | 學習率 |
| `max_train_epochs` | 10 | Epoch 數 |
| `save_every_n_epochs` | 2 | 中間儲存間隔 |
| `mixed_precision` | fp16 | 精度。某些情況下 bf16 可節省更多 VRAM |
| `resolution` | 1024,1024（SDXL） | 訓練解析度。SD1.5 使用 512,512 |

> **注意**：這些參數可在 Settings 頁籤或透過 `set_extension_config` 變更。額外引數可透過 `start_lora_training` 的 `extra_args` 新增。

---

## 各 GPU 推薦設定

| GPU VRAM | 推薦 extra_args |
|---------|---------------|
| 8GB | `--gradient_checkpointing --xformers --cache_latents_to_disk --optimizer_type=AdamW8bit` |
| 12GB | `--gradient_checkpointing --xformers --cache_latents_to_disk` |
| 16GB | （預設即可運行） |
| 24GB+ | （預設即可運行；可提高 batch_size） |

> ⚠️ **注意**：在 12GB GPU 上使用 gradient_checkpointing 時，SDXL 24,000 步驟約需 10〜12 小時。16GB 以上不受此限制，速度大幅提升。

---

## Repeat 數與 Epoch 數的參考標準

**總訓練步驟數 = 圖片數量 × repeat 數 × epoch 數**

| 概念複雜度 | 建議步驟數 | 範例（50 張圖片） |
|----------|----------|----------------|
| 簡單物件或風格 | 1,000〜3,000 | repeat=10, epoch=5 |
| 角色或造形物 | 3,000〜8,000 | repeat=20, epoch=5 |
| 複雜風格或人物 | 5,000〜15,000 | repeat=20, epoch=10 |

> **注意**：以 120 張 × 20 repeat × 10 epoch = 24,000 步驟訓練可獲得良好品質。但 5〜6 epoch 也可能達到相同結果，建議先嘗試較少的 epoch 數。

---

## 疑難排解

### ModuleNotFoundError: No module named 'torch'

**原因**：YU AI Manager 嘗試在自己的 venv 中執行 kohya_ss 腳本。

**處理方式**：將 `kohya_path` 設定為頂層目錄（sd-scripts 的上層目錄）。YU AI Manager 會自動偵測 `kohya_path/venv/Scripts/python.exe`。

---

### AssertionError: resolution is required

**原因**：未指定 `--resolution`。

**處理方式**：最新版 YU AI Manager 會自動附加此參數（SDXL：1024,1024；SD1.5：512,512）。

---

### AssertionError: network for Text Encoder cannot be trained with caching

**原因**：`--cache_text_encoder_outputs` 與 `--network_train_unet_only` 未配對使用。

**處理方式**：最新版 YU AI Manager 在 SDXL 模式下會自動附加 `--network_train_unet_only`。

---

### torch.OutOfMemoryError: CUDA out of memory

**原因**：VRAM 不足。

**處理方式**：在 `extra_args` 中新增以下參數：

```python
extra_args=["--gradient_checkpointing", "--xformers", "--cache_latents_to_disk"]
```

---

### VLM 雜訊標籤混入

**原因**：`engine_type` 設為 `"both"`，導致 VLM（llava 等）產生自由格式標籤。

**處理方式**：在 WD-Tagger 設定中改為 `engine_type="onnx"`，刪除所有標籤後重新標記。

```python
wd_tagger_save_config({"engine_type": "onnx"})
wd_tagger_delete_tags_batch(file_ids=[...], expected_count=N)
wd_tagger_batch(file_ids=[...], expected_count=N)
```

---

### checkpoint must be inside checkpoint_dir（403 錯誤）

**原因**：checkpoint 路徑指向 `checkpoint_dir` 以外的位置。

**處理方式**：確認 Extension 設定中的 `checkpoint_dir` 是否指向正確目錄。

---

### output_base_dir not configured（400 錯誤）

**原因**：Extension 設定中的 `output_base_dir` 未設定或未儲存。

**處理方式**：在 UI 設定頁籤中重新儲存，或從 MCP 透過 `set_extension_config` 設定。

---

## 生成時的提示詞

### 基本提示詞結構

```
{concept_token}, {特徵標籤}, <lora:{lora_name}:{strength}>
```

木雕熊 LoRA 範例：

```
carved_bear, wooden sculpture, bear statue, wood texture, brown,
full_body, standing, open_mouth, fish, simple_background,
<lora:carved_bear:0.7>
```

負面提示詞：

```
blurry, lowres, bad anatomy, worst quality, flat color, monochrome
```

### 調整 LoRA 強度

| 強度 | 特性 |
|-----|------|
| 0.5〜0.6 | 基礎模型影響較強；顏色與風格偏向基礎模型 |
| 0.7〜0.8 | 建議範圍；LoRA 特徵與基礎模型平衡良好 |
| 0.9〜1.0 | LoRA 影響較強；造形明確但顏色易偏白/奶油色 |

> **注意**：若顏色偏白，請降低強度，或在提示詞中加入 `brown wood, warm tone` 來引導顏色。

---

## 未來擴展

### 素材收集自動化

目前素材圖片仍需人工手動準備。使用 Claude in Chrome 等瀏覽器代理，可透過「請從網路收集○○的圖片放入資料夾」的指示自動化素材收集。

將 YU AI Manager 自身的生成圖片作為素材也是有效的方向——由 SD/ComfyUI/NAI 生成的圖片可直接作為 LoRA 訓練素材再利用。

### LoRA 量產流程

搭配 MCP + Claude Desktop，可實現如下完全自動化：

1. 從網路收集素材圖片（Claude in Chrome）
2. 在 YU AI Manager 中掃描與標記（MCP）
3. 建立專案、設定排除標籤、匯出（MCP）
4. 啟動 kohya_ss 訓練（MCP）
5. 睡前下達指示 → 隔天早上 LoRA 完成

### 選擇基礎模型

waiSHUFFLENOOB 等 Illustrious 系基礎模型針對動漫風格生成優化。使用實拍素材（木雕熊等）訓練時容易產生白/奶油色調。

追求接近實拍質感時，請選擇 realisticPhoto 系基礎模型。LoRA 必須與訓練時使用的基礎模型相同才能使用。

---

## 總結

YU AI Manager + MCP + kohya_ss 的流程大幅降低了 LoRA 製作所需的工時。

- 從素材圖片到完整 epoch 訓練，僅需 MCP 指示即可完成
- 整個流程透過自然語言指示運作
- 生成圖片中清楚呈現訓練對象的造形

唯一剩餘的人工步驟是素材收集，與瀏覽器代理結合後即可實現完全自動化。
