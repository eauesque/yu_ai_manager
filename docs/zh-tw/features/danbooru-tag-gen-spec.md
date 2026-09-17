# Danbooru 自動標籤 — 實作規格

**狀態**：已實作（Phase 1-5：v2.77.0）
**目標**：YU AI Manager
**目的**：使用兩層方案自動為 AI 圖片分配 Danbooru 標籤：WD-Tagger ONNX (CPU) + VLM (OpenAI 相容 API)
**實作**：`extensions/builtin_wd_tagger/core_impl/`（12 個檔案），`routes/wd_tagger.py`（11 個 API）

---

## 實作狀態

| Phase | 狀態 | 位置 |
|---|---|---|
| Phase 1：WD-Tagger ONNX | **完成** | `extensions/builtin_wd_tagger/core_impl/engine_onnx.py` |
| Phase 2：VLM 引擎（OpenAI 相容） | **完成**（v2.77.0） | `extensions/builtin_wd_tagger/core_impl/engine_vlm.py` + `engine_composite.py` |
| Phase 3：標籤後處理 | **完成**（v2.77.0） | `extensions/builtin_wd_tagger/core_impl/tag_postprocess.py` |
| Phase 4：批次 API | **完成** | `extensions/builtin_wd_tagger/core_impl/batch_ops.py` + `routes/wd_tagger.py` |
| Phase 5：UI | **完成** | Tools 頁面 + 詳情彈窗 WD 標籤徽章 + XMP 檢視器 |

### Phase 2/3 實作概要（v2.77.0-v2.77.1）

- **VLM 引擎**（`engine_vlm.py`）：在 OpenAI 相容 API 和 Ollama 原生 API 之間自動回退
- **複合引擎**（`engine_composite.py`）：兩層 ONNX + VLM 管線（Mode B）
- **標籤後處理**（`tag_postprocess.py`）：正規化（小寫、底線、無效字元移除、去重複）+ NSFW 過濾（約 30 個標籤）
- **引擎工廠**：依 `engine_type` 路由（"onnx" / "vlm" / "both"）
- **UI**：引擎類型選擇、VLM URL/模型/逾時設定、連線測試、NSFW 過濾
- **API**：`GET /api/wd-tagger/vlm/test`、`GET /api/wd-tagger/vlm/models`
- **MCP**：`wd_tagger_vlm_test`、`wd_tagger_vlm_models` 工具
- **已測試**：使用 Ollama qwen2.5vl:7b 確認真實圖片標籤功能，23 項單元測試通過

---

## 先行研究

### DeepDanbooru (KichangKim)
- **方法**：圖片分類模型（TensorFlow）直接預測標籤
- **優點**：快速、標籤專用、可轉換為 ONNX
- **缺點**：固定標籤集，無法適應新標籤
- **參考**：已整合到 A1111

### WD-Tagger (SmilingWolf) — Phase 1 採用
- **方法**：DeepDanbooru 的後繼者。四種架構：SwinV2/ViT/ConvNeXt/EVA02
- **優點**：比 DeepDanbooru 更高準確度，包含類別分類（general/character/copyright/rating）
- **ONNX**：官方 ONNX 模型 + `selected_tags.csv` 在 HuggingFace 上發布
- **輸入**：448x448 RGB（保持長寬比 + 白色填充）

### DanTagGen / DTG (KohakuBlueleaf)
- **方法**：基於 LLaMA 的 LLM（400M）進行標籤生成和補完
- **優點**：具上下文感知的標籤補完
- **缺點**：因 LLM 推論而速度較慢
- **HuggingFace**：`KBlueLeaf/DanTagGen-beta`

### 設計理念
系統同時支援 WD-Tagger ONNX（快速、可靠）和透過 hailo-ollama 使用 Qwen2-VL（靈活、具上下文感知），使用者可以根據需求選擇合適的工具。

---

## 架構

```
[圖片輸入]
    |
[引擎選擇]  (engine_factory.py)
    |-- WD-Tagger ONNX（快速，固定標籤集 ~10,000 個標籤）  [Phase 1：已實作]
    |       | 信賴度分數 + 分類標籤清單
    |-- Qwen2-VL via hailo-ollama（慢，靈活，上下文感知）   [Phase 2]
    |       | JSON 陣列 -> 標籤解析
    |-- 兩層：ONNX -> Qwen2-VL 補充                    [Phase 2 選項]
    |       | 將 ONNX 標籤輸入提示詞，讓 LLM 生成額外標籤
    |
[後處理：標籤正規化、NSFW 過濾]  [Phase 3]
    |
[DB：儲存到 file_wd_tags 資料表]  (store.py)
[XMP：嵌入到檔案（選用）]  (xmp_write.py)
```

---

## Phase 1：WD-Tagger ONNX 引擎 — 已實作

**模型**：SmilingWolf/wd-swinv2-tagger-v3（推薦）、ViT v3、ConvNeXt v3、EVA02-Large v3

**實作檔案**（`extensions/builtin_wd_tagger/core_impl/`）：
| 檔案 | 行數 | 職責 |
|---|---|---|
| `types.py` | ~60 | TagPrediction、WdTagResult、WdTaggerEngine ABC |
| `tag_csv.py` | ~70 | selected_tags.csv 解析、類別對應 |
| `model_download.py` | ~120 | HuggingFace HTTP 下載 |
| `engine_onnx.py` | ~150 | ONNX 推論（448x448、BGR、門檻過濾） |
| `engine_factory.py` | ~50 | 引擎快取 + 建立 |
| `store.py` | ~130 | DB CRUD（file_wd_tags 資料表） |
| `xmp_xml.py` | ~60 | XMP 封包建構 |
| `xmp_read.py` | ~90 | XMP 讀取 |
| `xmp_write.py` | ~160 | XMP 寫入 PNG/JPEG/WebP |
| `config_ops.py` | ~70 | config.json 讀寫 |
| `single_ops.py` | ~80 | 單張圖片標籤管線 |
| `batch_ops.py` | ~120 | 批次處理（JobManager 整合） |

**DB**：`file_wd_tags` 資料表（schema v14）
```sql
CREATE TABLE file_wd_tags (
    id         INTEGER PRIMARY KEY,
    file_id    INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    tag_name   TEXT NOT NULL,
    confidence REAL NOT NULL,
    category   TEXT NOT NULL DEFAULT 'general',
    model      TEXT NOT NULL,
    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    UNIQUE(file_id, tag_name, model)
);
```

**API**：`routes/wd_tagger.py` — 11 個端點

---

## Phase 2：VLM 引擎（OpenAI 相容 API） — 已實作（v2.77.0）

**目的**：以 ONNX 無法捕捉的詳細描述和上下文標籤補充 WD-Tagger ONNX
**實作**：`extensions/builtin_wd_tagger/core_impl/engine_vlm.py`（通用 OpenAI 相容 VLM 引擎）
**注意**：原始規格計劃使用 Hailo 專用的 `engine_hailo.py`，但實際實作使用通用引擎 `engine_vlm.py`，統一處理 Ollama、hailo-ollama 和其他 OpenAI 相容伺服器。支援在 OpenAI 相容 API（`/v1/chat/completions`）和 Ollama 原生 API（`/api/chat`）之間自動回退。

### 硬體配置

| 項目 | 規格 |
|---|---|
| **裝置** | Raspberry Pi 5 + Hailo-10H AI 加速器 |
| **記憶體** | 8GB RAM |
| **VLM 模型** | **Qwen2-VL-2B-Instruct**（Hailo Model Zoo 中唯一的 VLM） |
| **推論框架** | hailo-ollama（OpenAI 相容 API） |
| **端點** | `http://<pi-ip>:8000/v1/chat/completions` |

### 模型特性

- **Qwen2-VL-2B-Instruct**：來自 Qwen 家族的視覺語言模型（20 億參數）
- 屬於 Qwen 家族，而非 llava 家族。圖片理解準確度通常高於基於 llava 的模型
- 20 億參數可輕鬆納入 Hailo-10H 的 8GB RAM 中
- 純文字的 Qwen2（1.5B）已確認可在 hailo-ollama 上運行
- **注意**：截至 2026-02，這是 Hailo-10H 唯一可用的 VLM

### 提示詞設計

```python
SYSTEM_PROMPT = """You are a Danbooru image tagging assistant.
Analyze the image and output ONLY Danbooru-style tags as a JSON array.
Rules:
- Use underscores instead of spaces (e.g., long_hair, blue_eyes)
- Output ONLY the JSON array, no other text
- Include tags for: character count, gender, hair, eyes, clothing, pose, background, art style
- Do NOT include copyright or character name tags unless clearly identifiable
- Maximum 40 tags
Example output: ["1girl", "solo", "long_hair", "blue_eyes", "smile"]"""

USER_PROMPT = "Tag this image with Danbooru tags."
```

### 實作設計（`extensions/builtin_wd_tagger/core_impl/engine_hailo.py` — 約 100 行）

```python
import base64
import json
import logging
import urllib.request
from pathlib import Path

from .types import TagPrediction, WdTagResult, WdTaggerEngine

logger = logging.getLogger(__name__)

_USER_AGENT = "YU-AI-Manager/2.0 (WD-Tagger Qwen2-VL)"

class HailoQwen2VLEngine(WdTaggerEngine):
    """Qwen2-VL-2B-Instruct via hailo-ollama (OpenAI-compatible API)."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        model: str = "qwen2-vl:2b",
        timeout: int = 60,
    ):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    def tag_image(self, image_path: str) -> WdTagResult:
        with open(image_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode()

        # MIME type inference
        suffix = Path(image_path).suffix.lower()
        mime = {"png": "image/png", "webp": "image/webp"}.get(
            suffix.lstrip("."), "image/jpeg"
        )

        payload = json.dumps({
            "model": self._model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {
                            "url": f"data:{mime};base64,{image_b64}"
                        }},
                        {"type": "text", "text": USER_PROMPT},
                    ],
                },
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": 512,
            "temperature": 0.3,
        }).encode()

        req = urllib.request.Request(
            f"{self._base_url}/v1/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": _USER_AGENT,
            },
        )

        resp = urllib.request.urlopen(req, timeout=self._timeout)
        data = json.loads(resp.read())
        content = data["choices"][0]["message"]["content"]
        raw_tags = json.loads(content)

        # Response format: list or {"tags": [...]}
        if isinstance(raw_tags, dict) and "tags" in raw_tags:
            raw_tags = raw_tags["tags"]
        if not isinstance(raw_tags, list):
            raw_tags = []

        tags = []
        for t in raw_tags:
            name = str(t).strip().lower().replace(" ", "_")
            if name:
                tags.append(TagPrediction(
                    tag=name,
                    confidence=0.5,  # LLMs do not return confidence scores
                    category="general",
                ))

        return WdTagResult(tags=tags, model=self._model)

    def get_name(self) -> str:
        return f"Qwen2-VL ({self._model})"

    def is_available(self) -> bool:
        """Check connectivity to the hailo-ollama server."""
        try:
            req = urllib.request.Request(
                f"{self._base_url}/v1/models",
                headers={"User-Agent": _USER_AGENT},
            )
            resp = urllib.request.urlopen(req, timeout=5)
            return resp.status == 200
        except Exception:
            return False
```

### 運作模式

**Mode A：Qwen2-VL 獨立模式**
```
圖片 -> Qwen2-VL -> JSON 標籤陣列 -> 正規化 -> DB 儲存
```
- LLM 直接分析圖片並生成標籤
- 無信賴度分數（統一設為 0.5）
- 不受固定標籤集限制的靈活標籤
- 速度：每張圖片約 3-10 秒（Hailo-10H 上的估計值）

**Mode B：WD-Tagger ONNX -> Qwen2-VL 補充（兩層）**
```
圖片 -> WD-Tagger ONNX -> 高信賴度標籤 (>=0.7)
                              |
                              v
    Qwen2-VL：「這些標籤描述了圖片。請建議額外的標籤。」
                              |
                              v
    ONNX 標籤 + LLM 補充標籤 -> 合併 -> 正規化 -> DB 儲存
```
- 結合可靠的 ONNX 標籤與 LLM 的上下文理解
- 將 ONNX 標籤納入提示詞應能提高 LLM 的準確度
- 速度：ONNX（約 0.5 秒）+ LLM（約 3-10 秒）= 每張圖片約 4-11 秒

**Mode B 提示詞**：
```python
补完_SYSTEM_PROMPT = """You are a Danbooru image tagging assistant.
The image already has these tags from automated classification: {existing_tags}
Analyze the image and suggest ADDITIONAL Danbooru-style tags not in the list above.
Output ONLY a JSON array of new tags. Use underscores instead of spaces.
Focus on: composition, mood, background details, specific clothing items, art style.
Maximum 20 additional tags.
Example: ["looking_at_viewer", "outdoors", "cloudy_sky", "pleated_skirt"]"""
```

### engine_factory.py 的新增

```python
# Addition to get_engine() in engine_factory.py

engine_type = config.get("engine_type", "onnx")  # "onnx" | "hailo" | "both"

if engine_type == "hailo":
    from .engine_hailo import HailoQwen2VLEngine
    engine = HailoQwen2VLEngine(
        base_url=config.get("hailo_url", "http://localhost:8000"),
        model=config.get("hailo_model", "qwen2-vl:2b"),
        timeout=config.get("hailo_timeout", 60),
    )
elif engine_type == "both":
    # Two-tier: ONNX -> Hailo complement (Phase 2 option)
    ...
```

### config.json 項目

```json
{
  "wd_tagger": {
    "model": "SmilingWolf/wd-swinv2-tagger-v3",
    "general_threshold": 0.35,
    "character_threshold": 0.85,
    "write_xmp": true,
    "auto_download": true,
    "engine_type": "onnx",
    "hailo_url": "http://localhost:8000",
    "hailo_model": "qwen2-vl:2b",
    "hailo_timeout": 60
  }
}
```

### 實作前驗證（Pi 硬體測試）

1. **確認 Qwen2-VL-2B-Instruct 可在 hailo-ollama 上啟動**
   ```bash
   # 在 Pi 上
   hailo-ollama run qwen2-vl:2b
   ```

2. **確認視覺請求可透過 OpenAI 相容 API 運作**
   ```bash
   curl -X POST http://localhost:8000/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{
       "model": "qwen2-vl:2b",
       "messages": [{"role": "user", "content": [
         {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,/9j/..."}},
         {"type": "text", "text": "What is in this image?"}
       ]}],
       "max_tokens": 256
     }'
   ```

3. **確認 Danbooru 格式的 JSON 輸出穩定**
   - 檢查 hailo-ollama 是否支援 `response_format: json_object`
   - 若不支援，需要基於正規表達式的 JSON 提取作為後備方案

4. **測量實際推論速度** — 每張圖片的秒數（批次大小計算所需）

---

## Phase 3：標籤後處理 — 已實作（v2.77.0）

**實作**：`extensions/builtin_wd_tagger/core_impl/tag_postprocess.py`
**整合**：在 `single_ops.py` / `batch_ops.py` 推論後自動套用

```python
class TagPostProcessor:
    INVALID_CHARS = set('[](){}"\'/\\')
    MAX_TAG_LEN = 100

    def normalize(self, tags: list[str]) -> list[str]:
        result = []
        for tag in tags:
            tag = tag.strip().lower()
            tag = tag.replace(" ", "_")
            # Remove invalid characters
            tag = "".join(c for c in tag if c not in self.INVALID_CHARS)
            if 1 <= len(tag) <= self.MAX_TAG_LEN:
                result.append(tag)
        # Deduplicate and sort
        return sorted(set(result))

    def filter_nsfw(self, tags: list[str], allow_nsfw: bool) -> list[str]:
        # NSFW tag list (managed in a separate file)
        if allow_nsfw:
            return tags
        return [t for t in tags if t not in NSFW_TAG_SET]
```

**與 Phase 1 的整合**：
- WD-Tagger ONNX 已使用類別 9（rating）分離評分標籤
- NSFW 過濾使用評分標籤（`explicit`、`questionable`）加上額外的 NSFW 清單
- 已實作：`extensions/builtin_wd_tagger/core_impl/tag_postprocess.py`（約 80 行）

---

## Phase 4：批次處理 API — 已實作

**API**（`routes/wd_tagger.py`）：

| 方法 | 路徑 | 用途 |
|---|---|---|
| POST | `/api/wd-tagger/batch` | 啟動批次（file_ids、limit、force） |
| POST | `/api/wd-tagger/tag/<file_id>` | 單張圖片標籤 |
| GET | `/api/wd-tagger/tags/<file_id>` | 取得標籤 |
| DELETE | `/api/wd-tagger/tags/<file_id>` | 刪除標籤 |
| GET | `/api/wd-tagger/stats` | 統計 |
| GET | `/api/wd-tagger/untagged` | 列出未標籤檔案 |
| GET/POST | `/api/wd-tagger/config` | 設定 CRUD |
| POST | `/api/wd-tagger/model/download` | 模型下載 |
| GET | `/api/wd-tagger/model/status` | 模型狀態 |
| GET | `/api/wd-tagger/xmp/<file_id>` | XMP 讀取 |

**處理流程**（`batch_ops.py`）：
1. 依序處理 `file_ids` 中的檔案（未指定時預設為 `meta_source=unknown` 的未標籤檔案）
2. 透過引擎執行推論
3. UPSERT 到 `file_wd_tags` 資料表（引擎以 model 欄位識別）
4. 將 XMP 嵌入檔案（選用）
5. 透過 JobManager 追蹤進度並支援取消

---

## Phase 5：UI — 已實作

**Tools 頁面**（`templates/tools/content/primary/_wd_tagger.html`）：
- 模型選擇（4 個模型）、門檻滑桿（general/character）
- XMP 寫入切換、模型下載按鈕
- 批次執行按鈕 + 進度條
- 統計顯示（標籤數量、各類別明細、未標籤數量）

**詳情彈窗**：
- WD 標籤徽章（general=藍色、character=綠色、copyright=橙色、rating=紅色）
- XMP 檢視器按鈕（dc:subject + wdtag 命名空間 + 原始 XML）
- 點擊標籤觸發搜尋

---

## 檔案結構（目前）

```
extensions/builtin_wd_tagger/core_impl/
├── __init__.py              # 模組初始化
├── types.py                 # TagPrediction、WdTagResult、WdTaggerEngine ABC
├── tag_csv.py               # selected_tags.csv 解析
├── model_download.py        # HuggingFace 模型下載
├── engine_onnx.py           # WD-Tagger ONNX 推論 [Phase 1]
├── engine_vlm.py            # VLM 引擎（OpenAI 相容）[Phase 2：已完成]
├── engine_composite.py      # ONNX + VLM 雙層方案 [Phase 2：已完成]
├── engine_factory.py        # 引擎建立 + 快取
├── store.py                 # DB CRUD（file_wd_tags）
├── xmp_xml.py               # XMP 封包建構
├── xmp_read.py              # XMP 讀取
├── xmp_write.py             # XMP 寫入（PNG/JPEG/WebP）
├── config_ops.py            # config.json 讀寫
├── single_ops.py            # 單張圖片標籤管線
├── batch_ops.py             # 批次處理（JobManager）
├── batch_processors.py      # 批次處理內部邏輯
└── tag_postprocess.py       # 標籤正規化、NSFW 過濾 [Phase 3：已完成]

routes/wd_tagger.py          # API 端點（共 11 個）

src/ts/tools-page/wd-tagger/
├── core.ts                  # 設定 CRUD、批次、模型下載
└── render.ts                # DOM 渲染

src/ts/runtime-tools-ui/tools/
└── wd-tags.ts               # 詳情彈窗 WD 標籤 + XMP 檢視器
```

---

## 實作優先順序（已更新）

```
Phase 1（WD-Tagger ONNX）       -> 完成
Phase 4（批次 API）              -> 完成
Phase 5（UI）                    -> 完成
Phase 3（後處理/NSFW）           -> 下一步（約新增 80 行）
Phase 2（Qwen2-VL hailo-ollama）-> Pi 硬體測試後（約新增 100 行 + factory 變更）
```

---

## 參考資料

- WD-Tagger (SmilingWolf)：https://huggingface.co/SmilingWolf/wd-swinv2-tagger-v3
- DeepDanbooru：https://github.com/KichangKim/DeepDanbooru
- DanTagGen：https://huggingface.co/KBlueLeaf/DanTagGen-beta
- Hailo Model Zoo VLM：Qwen2-VL-2B-Instruct (hailo.ai Model Explorer)
- hailo-ollama API 規格：參閱修改版 fork 原始碼

---

*建立：2026-02-27 / 更新：2026-02-27（Phase 1 實作完成，Phase 2 修改為 Qwen2-VL 基礎）*
