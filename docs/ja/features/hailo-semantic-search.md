# Hailo Semantic Search Extension — 実装指示書

**ステータス**: 実装完了 — Hailo 版は CLIP ONNX (v2.95.0) に発展的移行済み
**対象**: YU AI Manager Extension
**目的**: Hailo-10H (AI HAT 2) 上の CLIP/SigLIP を使ったセマンティック画像検索
**実装先**: `extensions/builtin_clip_search/core_impl/` (共有層) + `extensions/builtin_clip_onnx/core_impl/` (ONNX 実装)
**備考**: 本仕様書は初期の Hailo 専用設計。現在は ONNX マルチバックエンド方式に統合

---

## 概要

自然言語テキストで画像を検索できる機能を Extension として追加する。
例: 「青い空と海」「女の子 笑顔」「夜景 都市」などで類似画像を返す。

既存の FTS5 タグ検索・pHash 類似検索と**並列で使える**ことが要件。
Hailo デバイスが存在しない環境では Extension が無効化されるだけでよい。

---

## アーキテクチャ方針

```
[画像スキャン時]
画像ファイル → CLIP Image Encoder (Hailo HEF) → 512次元ベクトル → DB保存

[検索時]
テキスト入力 → CLIP Text Encoder (CPU / Hailo HEF) → 512次元ベクトル
              → コサイン類似度検索 → file_id リスト → 既存検索結果と統合
```

**CLIP と SigLIP の両対応**: 設定で切り替え可能にする。
SigLIP の方が精度が高いが、CLIP の方が実績・情報が多い。
まず CLIP で動かして、SigLIP は後から追加する方針でよい。

---

## フェーズ分割

### Phase 1: 実現可能性確認（最初にやること）

Pi5 環境に移ったら、Claude Code に以下の手順を **上から順に** 実行させること。
各ステップが通らなければそこで止めて対処する。

#### Step 1-1: HailoRT ランタイム確認

```bash
# デバイスが認識されているか
hailortcli fw-control identify

# Python バインディングが使えるか
python3 -c "import hailo_platform; print('HailoRT version:', hailo_platform.__version__)"
```

- **デバイスが見えない場合**: `dmesg | grep hailo` でドライバ状態を確認。AI HAT 2 の PCIe 接続を再確認
- **import できない場合**: `pip install hailort` または Hailo の APT リポジトリから `python3-hailort` をインストール

#### Step 1-2: CLIP HEF ファイルのダウンロード

```bash
mkdir -p ~/hailo_models && cd ~/hailo_models

# 画像エンコーダ
wget https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/clip_vit_b_16_image_encoder.hef

# テキストエンコーダ
wget https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/clip_vit_b_16_text_encoder.hef
```

- **403 / アクセス拒否の場合**: Hailo Developer Zone (https://hailo.ai/developer-zone/) のアカウント登録が必要。
  登録後、Model Zoo CLI (`hailo_model_zoo`) 経由でダウンロードを試す
- **HEF のサイズ確認**: 正常なら各ファイル数十MB〜100MB 程度。極端に小さい場合はダウンロード失敗

#### Step 1-3: Python 依存パッケージのインストール

```bash
# 画像前処理に必要（Phase 1 で使う）
pip install opencv-python-headless numpy

# 動作確認
python3 -c "import cv2; import numpy; print('cv2:', cv2.__version__, 'numpy:', numpy.__version__)"
```

#### Step 1-4: 最小推論テスト

```python
from hailo_platform import HEF, VDevice, HailoStreamInterface, InferVStreams, ConfigureParams
import numpy as np

hef_path = "/home/<user>/hailo_models/clip_vit_b_16_image_encoder.hef"
hef = HEF(hef_path)

# HEF の入出力レイヤー情報を確認（レイヤー名はモデルによって異なる）
print("Input layers:", [l.name for l in hef.get_input_vstream_infos()])
print("Output layers:", [l.name for l in hef.get_output_vstream_infos()])

with VDevice() as target:
    configure_params = ConfigureParams.create_from_hef(hef, interface=HailoStreamInterface.PCIe)
    network_groups = target.configure(hef, configure_params)
    network_group = network_groups[0]

    input_info = hef.get_input_vstream_infos()[0]
    input_name = input_info.name
    input_shape = input_info.shape  # 期待値: (224, 224, 3) など
    print(f"Input: name={input_name}, shape={input_shape}")

    # ダミー画像で推論テスト
    dummy = np.random.randint(0, 255, (1, *input_shape), dtype=np.uint8)
    with InferVStreams(network_group, {}) as pipeline:
        result = pipeline.infer({input_name: dummy})
        for name, data in result.items():
            print(f"Output: name={name}, shape={data.shape}, dtype={data.dtype}")
            # 512次元ベクトルが出れば成功
```

- **VDevice エラー (`not enough free devices`)**: hailo-ollama が起動中の可能性。`systemctl stop hailo-ollama` してから再試行
- **推論は通るが出力が 512 次元でない場合**: HEF バージョン / モデルバリアントの確認が必要

#### Step 1-5: 判定基準

| 結果 | 次のアクション |
|------|----------------|
| 512 次元ベクトルが出力された | Phase 2 以降に進む |
| HEF ロードは成功、出力次元が異なる | 別のモデルバリアント (clip_resnet_50 等) を試す |
| HEF ダウンロードできない | Developer Zone 登録 → Model Zoo CLI 経由でダウンロード |
| hailo_platform が import できない | HailoRT の再インストール。解決しなければ CPU CLIP で進む |
| デバイスが認識されない | h/w 接続・ドライバの問題。本 Extension 開発は一時保留 |

Phase 1 でこれが動けば本実装に進む。動かなければ代替案（CPU CLIP）を検討。

---

### Phase 2: DB スキーマ拡張

既存の DB migration に追加:

```sql
-- migration 14: semantic search vectors
CREATE TABLE IF NOT EXISTS file_vectors (
    file_id     INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
    model       TEXT NOT NULL DEFAULT 'clip',   -- 'clip' | 'siglip'
    vector      BLOB NOT NULL,                  -- float32 numpy array → bytes
    created_at  INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);

CREATE INDEX IF NOT EXISTS idx_file_vectors_model ON file_vectors(model);
```

ベクトルの保存: `numpy.ndarray.tobytes()` → BLOB
ベクトルの読み込み: `numpy.frombuffer(blob, dtype=numpy.float32)`

**注意**: SQLite は ANN (近似最近傍) インデックスを持たないので、
200,000件全件コサイン類似度計算が必要。numpy でバッチ計算すれば Pi5 でも許容範囲のはず（要測定）。
将来的に件数が増えたら `sqlite-vec` 拡張の導入を検討。

---

### Phase 3: Hailo 推論コア

**ファイル構成**:
```
extensions/hailo_semantic_search/
├── __init__.py
├── extension.py          # Extension エントリポイント
├── core/
│   ├── hailo_clip.py     # Hailo CLIP 推論ラッパー
│   ├── cpu_clip.py       # Hailo なし環境向け CPU フォールバック（optional）
│   └── vector_store.py   # DB ベクトル CRUD
├── routes/
│   └── semantic_search.py  # API エンドポイント
└── templates/
    └── _semantic_search_ui.html
```

**`hailo_clip.py` の責務**:
- HEF ロード・VDevice 初期化（シングルトン、起動時1回）
- 画像 → 前処理（224×224 リサイズ、正規化）→ HEF 推論 → 512次元ベクトル
- テキスト → トークナイズ → HEF 推論 → 512次元ベクトル
  ※ テキストエンコーダの HEF が Hailo-10H 向けにあれば使う、なければ CPU (transformers ライブラリ)

**前処理**:
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

### Phase 4: インデックス構築 API

**エンドポイント**:
```
POST /api/extensions/hailo-semantic/index
```
- バックグラウンドスレッドで未インデックス画像を順次処理
- SSE で進捗を `semantic_index.progress` イベントとして送信
- 既存スキャン完了イベント `scan.complete` をフックして自動実行（オプション）

**バッチサイズ**: 32枚単位で処理（メモリと速度のバランス）

```
GET /api/extensions/hailo-semantic/index/status
→ { "total": 200000, "indexed": 12500, "running": true }
```

---

### Phase 5: セマンティック検索 API

```
GET /api/extensions/hailo-semantic/search?q=青い空&limit=50&threshold=0.25
```

**処理フロー**:
1. テキスト `q` → ベクトル化
2. `file_vectors` から全ベクトルを読み込み（numpy）
3. コサイン類似度をバッチ計算
4. `threshold` 以上のものを類似度降順でソート
5. `file_id` リストを既存の `/api/search` フォーマットで返す

**コサイン類似度計算**:
```python
def cosine_similarity_batch(query_vec: np.ndarray, stored_vecs: np.ndarray) -> np.ndarray:
    # query_vec: (512,), stored_vecs: (N, 512)
    query_norm = query_vec / np.linalg.norm(query_vec)
    stored_norm = stored_vecs / np.linalg.norm(stored_vecs, axis=1, keepdims=True)
    return stored_norm @ query_norm  # (N,)
```

**パフォーマンス目標**: 200,000件で 1秒以内（numpy バッチ計算で Pi5 でも達成可能なはず）

---

### Phase 6: UI 統合

既存の検索 UI に「セマンティック検索」タブを追加する。
既存の condition-builder とは独立した UI でよい（統合は将来）。

```html
<!-- 検索バーの横にトグルボタン追加 -->
<button id="semantic-search-toggle" class="btn-secondary">
  🔍 意味検索 (Hailo)
</button>
```

- Hailo デバイスが未検出の場合はボタンを非表示またはグレーアウト
- 検索結果は既存グリッドをそのまま流用
- インデックス未構築の場合は「インデックス構築が必要です」の案内

---

## 設定項目 (config.json 追加)

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

## 調査済み事実（2026-02-27 時点）

以下は事前調査で確認済みの情報。Phase 1 実行時の参考にすること。

### CLIP HEF の所在

Hailo Model Zoo v5.2.0 に Hailo-10H 向けの CLIP/SigLIP が **画像・テキスト両エンコーダ** 存在する:

| モデル | Image Encoder HEF | Text Encoder HEF |
|--------|-------------------|-------------------|
| clip_vit_b_16 | あり | あり |
| clip_vit_b_32 | あり | あり |
| clip_vit_l_14 | あり | あり |
| clip_resnet_50 | あり | あり |
| siglip_b_16 | あり | あり |
| siglip_l_16_256 | あり | あり |
| siglip2_b_32_256 | あり | あり |
| TinyCLIP 各種 | あり | あり |

S3 URL パターン: `https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/<model>.hef`

### テキストエンコーダの現状

- 公式 `hailo-CLIP` アプリは **テキストエンコーダを CPU (PyTorch)** で実行している
- Model Zoo に Hailo-10H 向け Text Encoder HEF は存在するが、**これを使ったアプリの公開事例がない**
- 推奨方針: **テキストエンコーダは CPU (`sentence-transformers`) で実装**。検索時に 1 回走るだけなので速度は問題にならない
- 画像エンコーダこそ Hailo で高速化する価値がある（20 万枚のバッチインデックス構築）

### hailo-ollama との共存

- `SHARED_VDEVICE_GROUP_ID` による共有は公式にはサポートされている
- しかし **hailo-ollama バイナリはこの共有に参加しない**（独自にデバイスを占有する）
- コミュニティ事例: カスタムデバイスマネージャを自作して 6 サービス同時動作に成功した例あり
- **実用的な方針**: インデックス構築時は hailo-ollama を停止して時分割で使う
  - `systemctl stop hailo-ollama` → インデックス構築 → `systemctl start hailo-ollama`

### 200,000 件ベクトル検索の見積もり

- 200K x 512 float32 = 約 400MB — Pi5 (8GB) の RAM に収まる
- numpy バッチ cosine similarity は Pi5 の Cortex-A76 で 1 秒以内が見込める

### FAISS による大規模ベクトル検索の高速化 (v3.26.0)

v3.26.0 で FAISS (Facebook AI Similarity Search) に対応。`faiss-cpu` がインストール
されていると自動検出し、NumPy ブルートフォースの代わりに近似最近傍探索を使用する。

| 規模 | NumPy (O(N)) | FAISS IndexFlatIP | FAISS IndexIVFFlat |
|------|-------------|-------------------|-------------------|
| 10K | ~10ms | ~2ms | - |
| 100K | ~100ms | ~20ms | ~5ms |
| 500K | ~500ms | ~100ms | ~10ms |
| 1.5M | ~1.5s | ~300ms | ~20ms |

- **< 50K**: IndexFlatIP (正確な内積検索) を自動選択
- **>= 50K**: IndexIVFFlat (IVF クラスタリング) を自動選択、nprobe = nlist/10
- FAISS 未インストール時は従来の NumPy フォールバック (影響なし)

**インストール**:
```bash
source venv/bin/activate
uv pip install faiss-cpu  # x86_64 なら pip で直接入る
# aarch64 (RPi) は conda install -c conda-forge faiss-cpu または ソースビルド
```

起動ログで `FAISS x.x.x detected — using accelerated vector search` と表示されれば有効。

### hailo-CLIP アプリの注意点

- `hailo-ai/hailo-CLIP` は **Hailo-8/8L 向け**。Hailo-10H は未サポート
- リアルタイムゼロショット分類用であり、画像検索パイプラインではない
- 参考にはなるが直接流用はできない。HailoRT API で自前パイプラインを構築する必要がある

---

## 代替案（Hailo が使えない場合）

CPU のみで動く CLIP として `sentence-transformers` の `clip-ViT-B-32` が使える。
速度は遅いが、Hailo なし環境でも同じ Extension を動かせる。

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('clip-ViT-B-32')
image_embedding = model.encode(Image.open(path))
text_embedding  = model.encode("青い空")
```

Extension の設定で `"device": "cpu"` にすれば CPU モードで動く、
という二重構造にしておくと移植性が高い。

---

## 実装優先度

```
Phase 1 (動作確認)  → 必須、まずここだけやる
Phase 2 (DB)        → Phase 1 成功後
Phase 3 (推論コア) → Phase 2 後
Phase 4 (インデックス) → Phase 3 後
Phase 5 (検索API)   → Phase 4 後
Phase 6 (UI)        → Phase 5 後、最後
```

Phase 1 で動かなければ全体を CPU CLIP で進める判断をする。

---

## 参考リポジトリ

- `hailo-ai/hailo-apps`: CLIP zero-shot classification サンプルあり
- `hailo-ai/hailort`: pyHailoRT API リファレンス
- `hailo-ai/Hailo-Application-Code-Examples`: Python 推論サンプル
- `hailo-ai/hailo_model_zoo`: CLIP/SigLIP HEF ダウンロード先

---

*作成: 2026-02-27*
*調査追記: 2026-02-27 — Phase 1 手順の具体化、HEF 所在確認、hailo-ollama 共存問題の整理*
