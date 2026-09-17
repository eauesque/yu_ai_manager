# Danbooru タグ自動生成 — 実装指示書

**ステータス**: 実装完了 (Phase 1-5: v2.77.0)
**対象**: YU AI Manager
**目的**: WD-Tagger ONNX (CPU) + VLM (OpenAI 互換 API) の二段構えで AI 画像に Danbooru タグを自動付与する
**実装先**: `extensions/builtin_wd_tagger/core_impl/` (12 files), `routes/wd_tagger.py` (11 APIs)

---

## 実装状況

| フェーズ | 状態 | 実装先 |
|---|---|---|
| Phase 1: WD-Tagger ONNX | **完了** | `extensions/builtin_wd_tagger/core_impl/engine_onnx.py` |
| Phase 2: VLM エンジン (OpenAI 互換) | **完了** (v2.77.0) | `extensions/builtin_wd_tagger/core_impl/engine_vlm.py` + `engine_composite.py` |
| Phase 3: タグ後処理 | **完了** (v2.77.0) | `extensions/builtin_wd_tagger/core_impl/tag_postprocess.py` |
| Phase 4: バッチ API | **完了** | `extensions/builtin_wd_tagger/core_impl/batch_ops.py` + `routes/wd_tagger.py` |
| Phase 5: UI | **完了** | Tools ページ + 詳細モーダル WDタグバッジ + XMP ビューア |

### Phase 2/3 実装概要 (v2.77.0-v2.77.1)

- **VLM エンジン** (`engine_vlm.py`): OpenAI 互換 API + Ollama ネイティブ API 自動フォールバック
- **Composite エンジン** (`engine_composite.py`): ONNX + VLM 二段構え (Mode B)
- **タグ後処理** (`tag_postprocess.py`): 正規化 (lowercase, underscore, 不正文字除去, 重複排除) + NSFW フィルタ (~30 タグ)
- **エンジンファクトリ**: `engine_type` ("onnx" / "vlm" / "both") によるルーティング
- **UI**: エンジンタイプ選択、VLM URL/モデル/タイムアウト設定、接続テスト、NSFW フィルタ
- **API**: `GET /api/wd-tagger/vlm/test`, `GET /api/wd-tagger/vlm/models`
- **MCP**: `wd_tagger_vlm_test`, `wd_tagger_vlm_models` ツール
- **テスト済み**: Ollama qwen2.5vl:7b で実画像タグ付け確認、ユニットテスト 23 件

---

## 先行実装の参考

### DeepDanbooru (KichangKim)
- **方式**: 画像分類モデル (TensorFlow) で直接タグを予測
- **強み**: 高速、タグ特化、ONNX変換可能
- **弱み**: 固定タグセット、新しいタグに対応できない
- **参考**: A1111に既に統合済みの実績あり

### WD-Tagger (SmilingWolf) — Phase 1 で採用
- **方式**: DeepDanbooru の後継。SwinV2/ViT/ConvNeXt/EVA02 の4アーキテクチャ
- **強み**: DeepDanbooru より高精度、カテゴリ分類付き (general/character/copyright/rating)
- **ONNX**: HuggingFace で公式 ONNX + `selected_tags.csv` を配布
- **入力**: 448x448 RGB (アスペクト比保持+白パディング)

### DanTagGen / DTG (KohakuBlueleaf)
- **方式**: LLaMA系LLM (400M) でタグを生成・補完
- **強み**: 文脈を理解してタグを補完できる
- **弱み**: LLMなので速度が遅い
- **HuggingFace**: `KBlueLeaf/DanTagGen-beta`

### 本実装の方針
WD-Tagger ONNX (高速・確実) と Qwen2-VL via hailo-ollama (柔軟・文脈理解) の**両対応**。
用途に応じて使い分けられるようにする。

---

## アーキテクチャ

```
[画像入力]
    |
[エンジン選択]  (engine_factory.py)
    |-- WD-Tagger ONNX (高速・固定タグセット ~10,000タグ)  [Phase 1: 実装済]
    |       | 信頼度スコア + カテゴリ付きタグリスト
    |-- Qwen2-VL via hailo-ollama (低速・柔軟・文脈理解)   [Phase 2]
    |       | JSON配列 -> タグパース
    |-- 二段構え: ONNX -> Qwen2-VL 補完                    [Phase 2 オプション]
    |       | ONNXタグをプロンプトに含めてLLMに追加タグを生成させる
    |
[後処理: タグ正規化・NSFWフィルタリング]  [Phase 3]
    |
[DB: file_wd_tags テーブルに保存]  (store.py)
[XMP: ファイルに埋め込み (オプション)]  (xmp_write.py)
```

---

## Phase 1: WD-Tagger ONNX エンジン — 実装済

**モデル**: SmilingWolf/wd-swinv2-tagger-v3 (推奨)、ViT v3、ConvNeXt v3、EVA02-Large v3

**実装ファイル** (`extensions/builtin_wd_tagger/core_impl/`):
| ファイル | 行数 | 役割 |
|---|---|---|
| `types.py` | ~60 | TagPrediction, WdTagResult, WdTaggerEngine ABC |
| `tag_csv.py` | ~70 | selected_tags.csv パース、カテゴリマッピング |
| `model_download.py` | ~120 | HuggingFace HTTP ダウンロード |
| `engine_onnx.py` | ~150 | ONNX 推論 (448x448, BGR, 閾値フィルタ) |
| `engine_factory.py` | ~50 | エンジンキャッシュ + 生成 |
| `store.py` | ~130 | DB CRUD (file_wd_tags テーブル) |
| `xmp_xml.py` | ~60 | XMP パケット構築 |
| `xmp_read.py` | ~90 | XMP 読み取り |
| `xmp_write.py` | ~160 | PNG/JPEG/WebP への XMP 書き込み |
| `config_ops.py` | ~70 | config.json 読み書き |
| `single_ops.py` | ~80 | 単体タグ付けパイプライン |
| `batch_ops.py` | ~120 | バッチ処理 (JobManager 連携) |

**DB**: `file_wd_tags` テーブル (schema v14)
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

**API**: `routes/wd_tagger.py` — 11 エンドポイント

---

## Phase 2: VLM エンジン (OpenAI 互換 API) — 実装済 (v2.77.0)

**用途**: WD-Tagger ONNX で取れない詳細な説明・文脈タグの補完
**実装**: `extensions/builtin_wd_tagger/core_impl/engine_vlm.py` (汎用 OpenAI 互換 VLM エンジン)
**備考**: 仕様書では hailo-ollama 専用の `engine_hailo.py` を予定していたが、
Ollama / hailo-ollama / その他 OpenAI 互換サーバーを統一的に扱える汎用エンジン `engine_vlm.py` として実装。
OpenAI 互換 API (`/v1/chat/completions`) + Ollama ネイティブ API (`/api/chat`) の自動フォールバック対応。

### ハードウェア構成

| 項目 | 仕様 |
|---|---|
| **デバイス** | Raspberry Pi 5 + Hailo-10H AI アクセラレータ |
| **メモリ** | 8GB RAM |
| **VLM モデル** | **Qwen2-VL-2B-Instruct** (Hailo Model Zoo で唯一の VLM) |
| **推論フレームワーク** | hailo-ollama (OpenAI 互換 API) |
| **エンドポイント** | `http://<pi-ip>:8000/v1/chat/completions` |

### モデル特性

- **Qwen2-VL-2B-Instruct**: Qwen ファミリーの Vision-Language モデル (2B パラメータ)
- llava 系ではなく Qwen ファミリー。画像理解の精度は一般的に llava 系より高い
- 2B なので Hailo-10H の 8GB RAM に余裕で収まる
- テキスト版 Qwen2 (1.5B) は hailo-ollama で動作実績あり
- **注意**: 2026-02 時点で Hailo-10H 向け VLM はこの 1 モデルのみ

### プロンプト設計

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

### 実装設計 (`extensions/builtin_wd_tagger/core_impl/engine_hailo.py` — ~100行)

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
    """Qwen2-VL-2B-Instruct via hailo-ollama (OpenAI 互換 API)."""

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

        # MIME type 推定
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

        # レスポンス形式: リスト or {"tags": [...]}
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
                    confidence=0.5,  # LLM は信頼度スコアを返さない
                    category="general",
                ))

        return WdTagResult(tags=tags, model=self._model)

    def get_name(self) -> str:
        return f"Qwen2-VL ({self._model})"

    def is_available(self) -> bool:
        """hailo-ollama サーバーに疎通確認。"""
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

### 動作モード

**モード A: Qwen2-VL 単独**
```
画像 -> Qwen2-VL -> JSON タグ配列 -> 正規化 -> DB 保存
```
- LLM が画像を直接見てタグを生成
- 信頼度スコアなし (一律 0.5)
- 柔軟なタグ付けが可能 (固定タグセットに縛られない)
- 速度: ~3-10秒/枚 (Hailo-10H 推定)

**モード B: WD-Tagger ONNX -> Qwen2-VL 補完 (二段構え)**
```
画像 -> WD-Tagger ONNX -> 高信頼度タグ (>=0.7)
                              |
                              v
    Qwen2-VL に「これらのタグが付いた画像です。追加すべきタグを提案してください」
                              |
                              v
    ONNX タグ + LLM 補完タグ -> マージ -> 正規化 -> DB 保存
```
- ONNX の確実なタグ + LLM の文脈理解を組み合わせる
- ONNX タグをプロンプトに含めることで LLM の精度向上が期待できる
- 速度: ONNX (~0.5秒) + LLM (~3-10秒) = ~4-11秒/枚

**モード B 用プロンプト**:
```python
补完_SYSTEM_PROMPT = """You are a Danbooru image tagging assistant.
The image already has these tags from automated classification: {existing_tags}
Analyze the image and suggest ADDITIONAL Danbooru-style tags not in the list above.
Output ONLY a JSON array of new tags. Use underscores instead of spaces.
Focus on: composition, mood, background details, specific clothing items, art style.
Maximum 20 additional tags.
Example: ["looking_at_viewer", "outdoors", "cloudy_sky", "pleated_skirt"]"""
```

### engine_factory.py への追加

```python
# engine_factory.py の get_engine() に追加

engine_type = config.get("engine_type", "onnx")  # "onnx" | "hailo" | "both"

if engine_type == "hailo":
    from .engine_hailo import HailoQwen2VLEngine
    engine = HailoQwen2VLEngine(
        base_url=config.get("hailo_url", "http://localhost:8000"),
        model=config.get("hailo_model", "qwen2-vl:2b"),
        timeout=config.get("hailo_timeout", 60),
    )
elif engine_type == "both":
    # 二段構え: ONNX -> Hailo 補完 (Phase 2 オプション)
    ...
```

### config.json エントリ

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

### 実装前の確認事項 (Pi 実機テスト)

1. **hailo-ollama で Qwen2-VL-2B-Instruct が起動するか**
   ```bash
   # Pi 上で
   hailo-ollama run qwen2-vl:2b
   ```

2. **OpenAI 互換 API で Vision リクエストが通るか**
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

3. **Danbooru タグ形式の JSON 出力が安定するか**
   - `response_format: json_object` が hailo-ollama でサポートされているか
   - 非サポート時はテキスト出力から JSON 部分を正規表現で抽出するフォールバックが必要

4. **推論速度の実測** — 1枚あたり何秒かかるか (バッチサイズ計算に必要)

---

## Phase 3: タグ後処理 — 実装済 (v2.77.0)

**実装**: `extensions/builtin_wd_tagger/core_impl/tag_postprocess.py`
**統合**: `single_ops.py` / `batch_ops.py` の推論後に自動適用

```python
class TagPostProcessor:
    INVALID_CHARS = set('[](){}"\'/\\')
    MAX_TAG_LEN = 100

    def normalize(self, tags: list[str]) -> list[str]:
        result = []
        for tag in tags:
            tag = tag.strip().lower()
            tag = tag.replace(" ", "_")
            # 不正文字除去
            tag = "".join(c for c in tag if c not in self.INVALID_CHARS)
            if 1 <= len(tag) <= self.MAX_TAG_LEN:
                result.append(tag)
        # 重複除去・ソート
        return sorted(set(result))

    def filter_nsfw(self, tags: list[str], allow_nsfw: bool) -> list[str]:
        # NSFWタグリスト（別ファイルで管理）
        if allow_nsfw:
            return tags
        return [t for t in tags if t not in NSFW_TAG_SET]
```

**Phase 1 との統合**:
- WD-Tagger ONNX はカテゴリ 9 (rating) で rating タグを分離済み
- NSFW フィルタは rating タグ (`explicit`, `questionable`) + 追加 NSFW リストで実現
- `extensions/builtin_wd_tagger/core_impl/tag_postprocess.py` として実装済み (~80行)

---

## Phase 4: バッチ処理 API — 実装済

**API** (`routes/wd_tagger.py`):

| Method | Path | 用途 |
|---|---|---|
| POST | `/api/wd-tagger/batch` | バッチ開始 (file_ids, limit, force) |
| POST | `/api/wd-tagger/tag/<file_id>` | 単体タグ付け |
| GET | `/api/wd-tagger/tags/<file_id>` | タグ取得 |
| DELETE | `/api/wd-tagger/tags/<file_id>` | タグ削除 |
| GET | `/api/wd-tagger/stats` | 統計 |
| GET | `/api/wd-tagger/untagged` | 未タグ一覧 |
| GET/POST | `/api/wd-tagger/config` | 設定 CRUD |
| POST | `/api/wd-tagger/model/download` | モデル DL |
| GET | `/api/wd-tagger/model/status` | モデル状態 |
| GET | `/api/wd-tagger/xmp/<file_id>` | XMP 読み取り |

**処理フロー** (`batch_ops.py`):
1. `file_ids` のファイルを順次処理 (未指定時は `meta_source=unknown` の未タグ付けファイル)
2. エンジンで推論
3. `file_wd_tags` テーブルに UPSERT (model カラムでエンジン識別)
4. XMP ファイル埋め込み (オプション)
5. JobManager で進捗管理、キャンセル対応

---

## Phase 5: UI — 実装済

**Tools ページ** (`templates/tools/content/primary/_wd_tagger.html`):
- モデル選択 (4モデル)、閾値スライダー (general/character)
- XMP 書き込みトグル、モデルダウンロードボタン
- バッチ実行ボタン + 進捗バー
- 統計表示 (タグ数、カテゴリ別、未タグ付け数)

**詳細モーダル**:
- WD タグバッジ表示 (general=blue, character=green, copyright=orange, rating=red)
- XMP ビューアボタン (dc:subject + wdtag namespace + 生 XML)
- タグクリックで検索連動

---

## ファイル構成 (現在)

```
extensions/builtin_wd_tagger/core_impl/
├── __init__.py              # モジュール初期化
├── types.py                 # TagPrediction, WdTagResult, WdTaggerEngine ABC
├── tag_csv.py               # selected_tags.csv パース
├── model_download.py        # HuggingFace モデルダウンロード
├── engine_onnx.py           # WD-Tagger ONNX 推論 [Phase 1]
├── engine_vlm.py            # VLM エンジン (OpenAI 互換) [Phase 2: 完了]
├── engine_composite.py      # ONNX + VLM 二段構え [Phase 2: 完了]
├── engine_factory.py        # エンジン生成 + キャッシュ
├── store.py                 # DB CRUD (file_wd_tags)
├── xmp_xml.py               # XMP パケット構築
├── xmp_read.py              # XMP 読み取り
├── xmp_write.py             # XMP 書き込み (PNG/JPEG/WebP)
├── config_ops.py            # config.json 読み書き
├── single_ops.py            # 単体タグ付けパイプライン
├── batch_ops.py             # バッチ処理 (JobManager)
├── batch_processors.py      # バッチ処理内部ロジック
└── tag_postprocess.py       # タグ正規化・NSFW フィルタ [Phase 3: 完了]

routes/wd_tagger.py          # API エンドポイント (11本)

src/ts/tools-page/wd-tagger/
├── core.ts                  # 設定 CRUD、バッチ、モデルDL
└── render.ts                # DOM レンダリング

src/ts/runtime-tools-ui/tools/
└── wd-tags.ts               # 詳細モーダル WDタグ + XMP ビューア
```

---

## 実装優先度 (更新版)

```
Phase 1 (WD-Tagger ONNX)        -> 完了
Phase 4 (バッチ API)             -> 完了
Phase 5 (UI)                     -> 完了
Phase 3 (後処理・NSFWフィルタ)   -> 次回 (追加 ~80行)
Phase 2 (Qwen2-VL hailo-ollama) -> Pi実機テスト後 (追加 ~100行 + factory改修)
```

---

## 参考リンク

- WD-Tagger (SmilingWolf): https://huggingface.co/SmilingWolf/wd-swinv2-tagger-v3
- DeepDanbooru: https://github.com/KichangKim/DeepDanbooru
- DanTagGen: https://huggingface.co/KBlueLeaf/DanTagGen-beta
- Hailo Model Zoo VLM: Qwen2-VL-2B-Instruct (hailo.ai Model Explorer)
- hailo-ollama API仕様: 改良版フォークのソースを参照

---

*作成: 2026-02-27 / 更新: 2026-02-27 (Phase 1 実装完了、Phase 2 を Qwen2-VL ベースに改訂)*
