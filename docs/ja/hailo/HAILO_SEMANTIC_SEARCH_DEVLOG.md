# Hailo-10H Semantic Search — 開発ログ

**プロジェクト**: YU AI Manager — Hailo-10H CLIP セマンティック画像検索
**目標**: Raspberry Pi 5 + AI HAT 2 (Hailo-10H) で CLIP ベースの自然言語画像検索を実現する
**開始日**: 2026-03-01
**ステータス**: Phase 1-8 完了、Phase 9-12 (VLM キャプション連携、動画 S2T、LLM マルチターン、OpenAI 互換 API) 完了

---

## なぜこのプロジェクトが重要か

Hailo-10H (AI HAT 2) は 2025 年末にリリースされた比較的新しいエッジ AI アクセラレータで、
Raspberry Pi 5 の M.2 スロットに装着して使う。40 TOPS の推論性能を持つが、
**実用的なアプリケーションでの使用例はまだほとんど公開されていない**。

このプロジェクトは Hailo-10H を使って 20 万枚規模の画像ライブラリに対する
セマンティック検索（自然言語での画像検索）を実現する、おそらく初の実用ソフトウェアとなる。

---

## Phase 1: 実現可能性確認 (2026-03-01)

### 環境情報

| 項目 | 値 |
|------|-----|
| ハードウェア | Raspberry Pi 5 (8GB) + AI HAT 2 (Hailo-10H) |
| OS | Raspberry Pi OS Trixie (Linux 6.12.62+rpt-rpi-2712) |
| Python | 3.13.5 |
| HailoRT ドライバ | 5.2.0 (hailort-pcie-driver) |
| HailoRT ライブラリ | 5.2.0 (hailort deb) |
| HailoRT Python | 5.2.0 (**ソースビルド**) |

### Step 1-1: デバイス認識 — OK

```bash
$ hailortcli fw-control identify
Firmware Version: 5.2.0 (release,app)
Device Architecture: HAILO10H
```

デバイスは問題なく認識された。PCIe 接続、ドライバロードとも正常。

### Step 1-2: HEF ダウンロード — OK

Hailo Model Zoo v5.2.0 の S3 バケットから直接ダウンロード可能だった（認証不要）。

```
~/hailo_models/clip_vit_b_16_image_encoder.hef  (76 MB)
~/hailo_models/clip_vit_b_16_text_encoder.hef   (77 MB)
```

URL パターン:
```
https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/<model>.hef
```

### Step 1-3: Python バインディング — 要ソースビルド

#### 問題: パッケージバージョン不一致

Raspberry Pi OS のリポジトリには以下の 2 系統のパッケージが存在する:

| パッケージ系統 | バージョン | 備考 |
|---------------|-----------|------|
| `hailort` + `hailort-pcie-driver` | 5.2.0 | Hailo 公式 deb。Python バインディングなし |
| `h10-hailort` + `python3-h10-hailort` | 5.1.1 | Raspberry Pi チーム提供。Python あり |

**問題**: 2 系統は `Conflicts` 設定で共存不可。`h10-hailort` (5.1.1) を入れると
ドライバも 5.1.1 になるが、hailo-ollama は 5.2.0 が必要。

#### 解決: hailort 5.2.0 の Python wheel をソースビルド

**PyPI に wheel がない**。Hailo Developer Zone のダウンロードページにも
**aarch64 向け wheel は存在しない** (x86_64 のみ)。

GitHub リポジトリからソースビルドで解決:

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

**注意点**:
- `--plat-name linux_aarch64` は必須。省略すると `LIBHAILORT_PATH` のディレクトリ名パースで
  `ValueError: not enough values to unpack` が発生する (setup.py 163行目のバグ)
- `hailort` deb (C ライブラリ) は先にインストールしておく必要がある
- `h10-hailort` と `hailort` は `Conflicts` 設定で共存不可なので、
  `h10-hailort` を先に削除してから `hailort` 5.2.0 を入れる

### Step 1-4: 推論テスト — 成功（API 変更あり）

#### 重大な発見: Hailo-10H は旧 VStreams API 未サポート

仕様書に書いた `InferVStreams` + `ConfigureParams.create_from_hef()` のコードは
**Hailo-10H では動作しない**。`VDevice.configure()` が `HAILO_NOT_IMPLEMENTED (error 7)` を返す。

これは **Hailo-8/8L と Hailo-10H の根本的な API 差異** であり、
公式ドキュメントにも明確に記載されていない重要な事実。

#### 正しい API: InferModel

Hailo-10H では `VDevice.create_infer_model()` を使う:

```python
from hailo_platform import VDevice
import numpy as np

hef_path = "~/.hailo_models/clip_vit_b_16_image_encoder.hef"

with VDevice() as vdevice:
    infer_model = vdevice.create_infer_model(hef_path)

    # inputs/outputs はプロパティ (callable ではない)
    inp_info = infer_model.inputs[0]   # NOT inputs()
    out_info = infer_model.outputs[0]

    configured = infer_model.configure()
    bindings = configured.create_bindings()

    # 入力: uint8 画像
    dummy = np.random.randint(0, 255, inp_info.shape, dtype=np.uint8)
    bindings.input().set_buffer(dummy)

    # 出力: uint8 バッファを明示的に確保
    output_buf = np.empty(out_info.shape, dtype=np.uint8)
    bindings.output().set_buffer(output_buf)

    configured.run([bindings], timeout=10000)

    vec = output_buf.flatten()  # (512,) uint8
```

#### 詰まったポイントと解決

| 問題 | エラー | 解決 |
|------|--------|------|
| `infer_model.inputs()` が TypeError | `'list' object is not callable` | プロパティなので `inputs[0]` (括弧なし) |
| 出力バッファ未設定 | `not configured as view` | `bindings.output().set_buffer(buf)` で明示確保 |
| 出力バッファ float32 で確保 | `buffer size 2048 != expected 512` | **uint8** で確保 (512 bytes)。float32 は 2048 bytes になる |
| VDevice 終了時エラー | `Lost communication with server` | VDevice のクリーンアップ順序の問題。**推論結果には影響なし** |

### 推論性能

| 項目 | 値 |
|------|-----|
| モデル | CLIP ViT-B/16 Image Encoder |
| 入力 | (224, 224, 3) uint8 |
| 出力 | (1, 1, 512) uint8 (量子化済み) |
| 推論時間 | **~20 ms** |
| 理論スループット | **~50 images/sec** |

20 万枚のインデックス構築: 推論だけなら約 67 分。前処理込みでも数時間以内に完了見込み。

### Phase 1 判定

| 基準 | 結果 |
|------|------|
| 512 次元ベクトル出力 | **OK** (uint8 量子化、脱量子化が必要) |
| 推論速度 | **優秀** (20ms/image) |
| API 互換性 | InferModel API を使用 (仕様書の VStreams API は不可) |
| 判定 | **Phase 2 に進む** |

### 次フェーズへの引き継ぎ事項

1. **脱量子化**: uint8 出力を float32 に変換する必要がある。
   HEF に量子化パラメータ (scale/zero_point) が含まれているはず。
   `hailo_platform.pyhailort._pyhailort.dequantize_output_buffer` が使える可能性あり。
2. **テキストエンコーダ**: HEF は存在するが未テスト。同じ InferModel API で動くか要確認。
   仕様書の方針通り CPU (sentence-transformers) で実装する方が安全かもしれない。
3. **hailo-ollama との共存**: VDevice はデバイスを排他的に使用する。
   インデックス構築時は hailo-ollama を停止する必要がある。
4. **VDevice クリーンアップ**: 終了時のエラーメッセージは無害だが、
   長時間稼働のサーバープロセスではリソースリークに注意。

---

## Phase 2: DB スキーマ拡張 (2026-03-01)

### 実装内容

Migration 25 として `file_vectors` テーブルを追加。

```sql
CREATE TABLE file_vectors (
    file_id     INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
    model       TEXT NOT NULL DEFAULT 'clip_vit_b_16',
    vector      BLOB NOT NULL,        -- float32 numpy array tobytes() (512*4=2048 bytes)
    created_at  INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);
CREATE INDEX idx_file_vectors_model ON file_vectors(model);
```

**設計判断**:
- `vector` は脱量子化後の float32 BLOB を保存。uint8 で保存すると精度劣化する
- `file_id` が PRIMARY KEY (1ファイル1ベクトル)。将来の複数モデル対応時に UNIQUE(file_id, model) への変更が必要
- `ON DELETE CASCADE` で files 削除時に自動削除

**テスト**: インメモリ DB で migration 適用 → テーブル/インデックス存在確認 → OK

### ファイル

- `core/schema_core/schema_migrate_steps_25.py` (新規)
- `core/schema_core/schema_migrate.py` (import + `if current_version < 25` 追加)
- `core/schema_core/schema_constants.py` (`CURRENT_SCHEMA_VERSION = 25`)
- `core/hailo_clip_core/vector_store.py` (新規 - DB ベクトル CRUD)  *(現在は `extensions/builtin_hailo_semantic_search/core_impl/` に移動済み)*

---

## Phase 3: Hailo 推論コア (2026-03-01)

### 実装内容

`core/hailo_clip_core/` パッケージを新規作成 *(現在は `extensions/builtin_hailo_semantic_search/core_impl/`)*:

| ファイル | 責務 |
|---------|------|
| `hailo_inference.py` | HailoClipEncoder シングルトン。InferModel API ラッパー |
| `image_preprocess.py` | cv2 で 224x224 リサイズ + BGR→RGB 変換 |
| `dequantize.py` | uint8→float32 脱量子化 + L2 正規化 + quant_params 抽出 |
| `text_encoder.py` | CPU CLIP テキストエンコーダ (`openai/clip-vit-base-patch16`) |

**設計判断**:
- 画像前処理は uint8 のまま Hailo に渡す (HEF 内部で正規化される)
- テキストエンコーダは `transformers` の CLIPModel を使用 (`sentence-transformers` ではなく)。
  理由: `openai/clip-vit-base-patch16` は Hailo HEF の CLIP ViT-B/16 と同じモデルで
  ベクトル空間が一致する
- 脱量子化パラメータは `infer_model.outputs[0].quant_infos[0]` から取得を試み、
  失敗時は scale=1.0, zero_point=0.0 にフォールバック

**依存パッケージ**: `opencv-python-headless`, `numpy` (必須), `transformers`, `torch` (テキスト検索用)

---

## Phase 4: インデクサー + Extension (2026-03-01)

### 実装内容

| ファイル | 責務 |
|---------|------|
| `core/hailo_clip_core/indexer.py` *(現在は `extensions/builtin_clip_search/core_impl/`)* | バックグラウンドスレッドでバッチインデックス構築 |
| `core/hailo_clip_core/event_handler.py` *(現在は `extensions/builtin_clip_search/core_impl/`)* | scan.complete イベントで自動インデックス |
| `extensions/builtin_hailo_semantic_search/extension.json` | Extension マニフェスト |
| `extensions/builtin_hailo_semantic_search/hailo_semantic_search.py` | Blueprint 5 API |

**API エンドポイント**:
- `GET /ext/hailo-semantic/api/status` — デバイス・インデックス状態
- `POST /ext/hailo-semantic/api/index/start` — インデックス構築開始
- `GET /ext/hailo-semantic/api/index/status` — 進捗
- `POST /ext/hailo-semantic/api/index/stop` — 中断
- `GET /ext/hailo-semantic/api/search` — セマンティック検索
- `POST /ext/hailo-semantic/api/index/clear` — インデックスクリア

**イベント**: `semantic_index.start/progress/complete` を event_bus に追加

---

## Phase 5: セマンティック検索エンジン (2026-03-01)

### 実装内容

`core/hailo_clip_core/search.py` *(現在は `extensions/builtin_clip_search/core_impl/search.py`)* — メモリキャッシュ付きコサイン類似度検索

**アルゴリズム**:
1. 全ベクトルを DB から一括ロード → メモリキャッシュ
2. ベクトルを事前 L2 正規化
3. クエリテキスト → CLIP テキストエンコーダ → 512 次元ベクトル
4. 行列積 (dot product) でコサイン類似度バッチ計算
5. threshold 以上をソート → 結果返却

**メモリ見積もり**: 200K x 512 x 4 bytes = ~400 MB (Pi5 8GB RAM で許容範囲)

**レスポンス形式**:
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

## Phase 6: UI 統合 (2026-03-01)

### 検索ページ

- 検索バー横にセマンティック検索トグル (脳アイコン `regex-pill` スタイル) を追加
- Hailo 利用可能 & インデックス構築済みの場合のみ表示
- トグル ON 時: 検索フォーム送信を横取り → セマンティック検索 API → 既存グリッドに結果表示
- プレースホルダーを英語テキスト例に差し替え

### Tools ページ

- Search & Analysis タブにセマンティック検索セクションを追加
- デバイス状態/インデックス状況の表示
- バッチサイズスライダー + 自動インデックスチェックボックス
- Build Index / Stop / Clear ボタン + プログレスバー (2 秒ポーリング)

---

## 技術ノート

### Hailo-10H vs Hailo-8/8L の主な違い (開発者視点)

| 項目 | Hailo-8/8L | Hailo-10H |
|------|-----------|-----------|
| VStreams API | サポート | **未サポート** (NOT_IMPLEMENTED) |
| InferModel API | サポート | サポート |
| ConfigureParams | create_from_hef(hef, interface) | 不要 (create_infer_model が代替) |
| 出力形式 | float32 or uint8 選択可 | uint8 固定 (要脱量子化) |
| Python パッケージ | PyPI wheel あり | **なし** (ソースビルド必要) |
| APT パッケージ | `hailort` 統合 | `h10-hailort` 別系統 (5.1.1 のみ) |

### ビルド済み wheel の保管

```
~/hailort/hailort/libhailort/bindings/python/platform/dist/
  hailort-5.2.0-cp313-cp313-linux_aarch64.whl
```

他の Pi5 環境への展開時はこの wheel をコピーしてインストール可能
(ただし libhailort.so.5.2.0 と hailort-pcie-driver 5.2.0 が必要)。

---

## Phase 2-6 実装後の不具合修正ログ (2026-03-01)

### 1. テキストエンコーダの `get_text_features` 互換性問題

**問題**: `CLIPModel.get_text_features(**inputs)` が transformers の新しいバージョンでは
`torch.Tensor` ではなく `BaseModelOutputWithPooling` オブジェクトを返すようになっていた。
そのため `.squeeze()` 呼び出しで `AttributeError` が発生し、セマンティック検索が `Search failed` エラーに。

**症状**: `curl /ext/hailo-semantic/api/search?q=girl` → `{"message":"Search failed","status":"error"}`

**原因**: `_model.get_text_features()` の戻り値が transformers バージョンに依存する。
新バージョンではモデル出力オブジェクト全体が返り、`.pooler_output` 等を自分で取り出す必要がある。

**修正**: `text_encoder.py` で明示的に `text_model()` → `text_projection()` の 2 段階で処理するよう変更:

```python
# Before (broken)
text_features = _model.get_text_features(**inputs)
vec = text_features.squeeze().numpy()

# After (fixed)
text_out = _model.text_model(**inputs)
text_features = _model.text_projection(text_out.pooler_output)
vec = text_features.squeeze().numpy()
```

**パフォーマンス**:
- 初回クエリ (モデルロード込み): ~6 秒
- 2 回目以降: ~100-170ms (CPU 推論のみ)
- ベクトル検索: <1ms (51 件、メモリキャッシュ)

### 2. インデックス構築時の無限リトライループ

**問題**: デコード失敗したファイル (非画像ファイル、壊れたファイル等) を `failed_ids` として追跡しておらず、
`get_unindexed_file_ids()` が毎回同じ失敗ファイルを返してエラーカウントが 300 万超に。

**修正**: `indexer.py` に `failed_ids: set` を追加。失敗した file_id を記録し、次のバッチで除外。

### 3. アーカイブファイルの画像読み込み失敗

**問題**: `cv2.imread('test.7z!image.png')` はアーカイブメンバーパスを理解できない。

**修正**: `image_preprocess.py` で `is_archive_member()` を使ってアーカイブパスを検出し、
`read_bytes_from_zip` / `read_bytes_from_7z` + `cv2.imdecode()` パターンに切り替え。

### 4. SSE リアルタイム進捗更新

**問題**: 2 秒ポーリングでは進捗がカクカクで体験が悪い。

**修正**: `EventSource` SSE 接続に切り替え。`semantic_index.progress` イベントでリアルタイム更新。
`visibilitychange` でタブ非表示時は SSE 切断し、復帰時に再接続。

---

## Phase 7: YOLO オブジェクト検出 (2026-03-02)

### 概要

CLIP セマンティック検索に続き、同じ Hailo-10H 上で YOLO オブジェクト検出を実装。
画像・動画の 80 クラス COCO オブジェクト検出を行い、結果を `file_annotations` テーブルに保存。

### アーキテクチャ設計

#### VDevice 共有問題

Hailo-10H は単一プロセスから 1 つの VDevice しか使えず、InferModel も排他的。
CLIP と YOLO を同時には動かせない。

**解決策**: `core/hailo_device_core/device_manager.py` を新設。
- `acquire_device(owner, hef_path)` — 他の owner が保持中なら自動解放して切り替え
- 同一 owner + 同一 HEF なら再利用（再初期化を回避）
- `threading.Lock` でスレッドセーフ
- CLIP の `hailo_inference.py` を refactor して device_manager に委譲

#### YOLO 出力テンソルの扱い

CLIP は出力テンソルが 1 つだが、YOLO は複数出力テンソル（各 stride のヘッドに対応）を持つ。
`device_manager` は全出力の quantization parameters を収集して返す。

#### 後処理パイプライン

YOLO 後処理は以下のステップ:
1. uint8 → float32 脱量子化（output ごとの scale/zero_point を使用）
2. grid cell → pixel 座標へのデコード（sigmoid + grid offset + stride）
3. confidence フィルタ
4. クラスごとの NMS (pure numpy)
5. letterbox 座標 → 元画像の正規化座標 (0-1) への変換

#### 動画対応

ffmpeg でフレーム抽出 → 各フレームを独立して検出 → クラスごとに集約。
各クラスの最大 confidence + 出現フレーム数を保持。

### 新規モジュール構成

| モジュール | 役割 |
|---|---|
| `core/hailo_device_core/device_manager.py` | 共有 VDevice ライフサイクル管理 |
| `core/hailo_yolo_core/hailo_yolo_inference.py` | YOLODetector シングルトン |
| `core/hailo_yolo_core/yolo_postprocess.py` | NMS, box decode, dequantize |
| `core/hailo_yolo_core/yolo_labels.py` | COCO 80 クラスラベル |
| `core/hailo_yolo_core/yolo_preprocess.py` | 640x640 レターボックスリサイズ |
| `core/hailo_yolo_core/yolo_video.py` | 動画フレーム抽出 + 集約 |
| `core/hailo_yolo_core/yolo_indexer.py` | バックグラウンドバッチ検出 |
| `core/hailo_yolo_core/model_download.py` | HEF ダウンロード |
| `core/hailo_yolo_core/event_handler.py` | scan.complete ハンドラ |
| `extensions/builtin_hailo_yolo_detect/` | Extension + Blueprint API + UI |

### 技術ノート

- **マルチ出力テンソル**: YOLO HEF は複数出力テンソル（各 stride のヘッドに対応）を持つ。
  `infer_model.outputs` を走査して shape/quant_params を全て収集する必要がある
- **出力バッファ**: 各出力テンソルに個別の uint8 バッファを確保し、
  `bindings.output(out.name).set_buffer(buf)` で名前指定でバインド
- **テンソルレイアウト**: 形状は `(1, H, W, C)` が一般的。C には bbox (4) + class scores (80) が格納
- **HEF ダウンロード**: Hailo Model Zoo v5.2.0 から直接ダウンロード。User-Agent を設定しないと
  Cloudflare にブロックされるため `_USER_AGENT` を設定
- **検出結果の保存**: `file_annotations` テーブルの `source='hailo:<model>'`, `key='detections'` に
  JSON 配列で保存。既存のアノテーション CRUD API をそのまま活用

---

## Phase 8: GenAI (LLM / VLM / Speech2Text) 統合 (2026-03-02)

### 目標

Hailo-10H の `hailo_platform.genai` モジュール (LLM, VLM, Speech2Text) を
device_manager に統合し、テキスト生成・画像理解・音声文字起こしを WebUI から利用可能にする。

### device_manager 拡張

- **問題**: 既存の device_manager は InferModel API (CLIP/YOLO) のみ対応。
  GenAI クラスは InferModel ではなく VDevice を直接受け取る別モード
- **解決策**: `_mode` 変数 (`"infer"` | `"genai"`) でモードを区別。
  `acquire_genai(owner, model_path, genai_factory)` を追加し、
  factory パターンで LLM/VLM/S2T のインスタンスを生成
- **リリース処理の違い**:
  - InferModel: `del configured` → `del infer_model` → `del vdevice`
  - GenAI: `instance.release()` → `vdevice.release()` (明示的 release メソッド)

### GenAI API の発見事項

- **メッセージ形式**: OpenAI 互換の role/content 構造。content は配列で `{"type": "text", "text": "..."}` 形式
- **VLM 画像入力**: 336x336 RGB uint8 numpy 配列。`frames=[image]` でリスト渡し。
  プロンプト中に `{"type": "image"}` プレースホルダを配置
- **S2T 入力**: little-endian float32 (`<f4`), モノラル, 16kHz。int16→float32 正規化が必須
- **S2T セグメント**: `generate_all_segments()` が `SegmentInfo` オブジェクトのリストを返す。
  `.text`, `.start`, `.end` 属性あり
- **コンテキスト管理**: LLM/VLM は `get_context_usage_size()`, `max_context_capacity()`,
  `clear_context()` でコンテキストウィンドウを管理
- **ストリーミング**: `generate()` がイテレータを返し、トークンごとに yield

### モデル HEF ダウンロード URL

- パターン: `https://dev-public.hailo.ai/v{hailort_version}/blob/{ModelName}.hef`
- HailoRT 5.2.0 → `v5.2.0`
- モデル名は CamelCase (例: `Qwen2.5-1.5B-Instruct.hef`, `Whisper-Base.hef`)
- `hailo-apps-infra` の `download_resources.py` の `gen-ai-mz` ソースタイプで確認

### 新規ファイル

| ファイル | 説明 |
|----------|------|
| `core/hailo_genai_core/__init__.py` | パッケージ init |
| `core/hailo_genai_core/genai_types.py` | GenAIModelType enum + GenAIModelInfo dataclass |
| `core/hailo_genai_core/model_download.py` | 7 モデル HEF ダウンロード管理 |
| `core/hailo_genai_core/llm_inference.py` | HailoLLM ラッパー (singleton, streaming) |
| `core/hailo_genai_core/vlm_inference.py` | HailoVLM ラッパー (singleton, 画像前処理) |
| `core/hailo_genai_core/s2t_inference.py` | HailoS2T ラッパー (singleton, セグメント対応) |
| `extensions/builtin_hailo_genai/extension.json` | Extension マニフェスト |
| `extensions/builtin_hailo_genai/hailo_genai_ext.py` | Blueprint 8 API (SSE streaming) |
| `extensions/.../templates/hailo_genai/_genai_ui.html` | Tools ページ UI (4 パネル) |

### 技術ノート

- **VDevice.create_params()**: GenAI モードでは `VDevice.create_params()` でパラメータを作成し
  `VDevice(params)` でインスタンス化する。InferModel モードの `VDevice()` (引数なし) とは異なる
- **SSE ストリーミング**: Flask の `Response(generator(), mimetype='text/event-stream')` で
  トークンごとに `data: {"token": "..."}\n\n` を送信。完了時に `data: {"done": true}\n\n`
- **VLM の FormData 送信**: 画像ファイル + テキストプロンプトを同時に送るため、
  VLM API は JSON ではなく `multipart/form-data` を使用
- **S2T の WAV 読み込み**: サーバー側で `wave` モジュール + `io.BytesIO` で
  アップロードされた WAV バイト列から直接読み込み

---

## Phase 9: セマンティック検索 + VLM キャプション連携 (2026-03-03)

### 目標

CLIP 検索結果の画像を VLM (Qwen2-VL) で一括キャプション生成し、
`file_annotations` に保存する。

### 実装

- **`core/hailo_clip_core/caption_runner.py`** *(現在は `extensions/builtin_hailo_semantic_search/core_impl/caption_runner.py`)* (~150行): バックグラウンドスレッドで VLM キャプション生成をバッチ実行。`indexer.py` の `_state_lock` + `_stop_requested` + `_progress` パターンを踏襲。SSE イベント `vlm_caption.start/progress/complete`
- **Blueprint 拡張**: `hailo_semantic_search.py` に `/api/caption/start`, `/api/caption/status`, `/api/caption/stop` の 3 エンドポイント追加
- **UI**: Tools ページの Semantic Search セクションに「VLM Caption Generation」パネル追加。プロンプト入力、SSE 進捗バー、検索結果 file_ids を自動連携

### VDevice 排他制御

- `acquire_genai("vlm", ...)` で VLM を取得。CLIP インデクサが動作中なら device_manager の既存動作で自動解放される
- キャプション完了後は VLM がデバイスを保持し続けるため、CLIP インデックスの再開はモデルアンロードが必要

### アノテーション保存規約

- `source="hailo:vlm"`, `key="caption"`, `value=<キャプションテキスト>`

---

## Phase 10: 動画音声文字起こし — S2T パイプライン (2026-03-03)

### 目標

動画ファイルから ffmpeg で音声抽出 → Whisper (S2T) で文字起こし → `file_annotations` に保存。

### 実装

- **`core/files_core/video_audio.py`** (~80行): `extract_audio_wav()` で ffmpeg 音声抽出 (mono PCM s16le 16kHz)。動画の duration から動的タイムアウト算出 (最大 120 秒)。`check_ffmpeg()` は `media_video.py` から再利用
- **Blueprint 拡張**: `hailo_genai_ext.py` に 3 エンドポイント追加:
  - `POST /api/s2t/transcribe-video`: 単一動画の文字起こし (file_id, language)
  - `POST /api/s2t/batch-transcribe`: 複数動画のバッチ文字起こし (file_ids, language)、バックグラウンドスレッド + SSE 進捗 (`video_s2t.*`)
  - `GET /api/s2t/transcript/<file_id>`: 保存済み文字起こし取得
- **UI**: S2T パネル内に「Video Transcription」サブセクション追加。file_id 入力、言語選択 (ja/en)、保存済み取得ボタン

### アノテーション保存規約

- `source="hailo:s2t"`, `key="transcript"`, `value=<全文テキスト>`
- `source="hailo:s2t"`, `key="transcript_segments"`, `value=<JSON [{text, start, end}, ...]>`

### 注意点

- 一時 WAV は `tempfile.NamedTemporaryFile` で作成、finally で必ず削除
- S2T と LLM/VLM はデバイス排他 (同時使用不可)

---

## Phase 11: LLM マルチターン会話 UI 改善 (2026-03-03)

### 目標

単発プロンプトを会話履歴対応に拡張。コンテキスト継続・リセット・バブル型 UI。

### 実装

- **API 修正**: `api_llm_generate()` が `messages` 配列を受け取り可能に。後方互換: `prompt` のみの場合は従来通り system + user メッセージに変換。`generate_stream()` は既にマルチターン対応済み (`_normalise_prompt()` 経由)
- **バブル型チャット UI**: `hg-chat-container` + `hg-bubble` (user=右寄せ紫、AI=左寄せグレー)。CSS クラス: `hg-bubble-user`, `hg-bubble-ai`, `hg-bubble-label`
- **会話履歴管理**: JS 側に `_chatHistory = []` 配列で `{role, content}` を蓄積。API 送信時に `messages: [systemMsg, ..._chatHistory]` を渡す。`hgLlmClear()` で配列リセット + HailoRT コンテキストクリア
- **ストリーミング**: AI バブルを先に DOM 挿入し、SSE トークンを逐次追記

### バグ修正: マルチターン会話の system role エラー (2026-03-03)

MCP デバッグクエリ + hailort ログで発見。2 ターン目以降の `generate()` 呼び出しで以下のエラーが発生:

```
[HailoRT] [error] CHECK failed - System role messages can only be provided on the first prompt
[HailoRT] [error] CHECK_SUCCESS failed with status=HAILO_INVALID_OPERATION(6)
```

**原因**: UI テンプレートが毎回 `[systemMsg].concat(_chatHistory)` で system role を先頭に付けて送信していた。HailoRT の LLM API はコンテキストが存在する状態 (2 ターン目以降) では system role を受け付けない。

**修正**:
1. `llm_inference.py` に `_prepare_prompt()` メソッド追加: `get_context_usage_size() > 0` の場合、system role メッセージを自動除外
2. UI テンプレート (`_genai_ui.html`): `_chatHistory.length <= 1` (初回ユーザーメッセージのみ) の場合にだけ system を付与

**技術ノート**: HailoRT の制約として、`LLM.generate()` は最初の呼び出しでのみ system role を処理する。これは OpenAI API とは異なる挙動で、マルチターン会話を実装する際は注意が必要

---

## WD-Tagger VLM × Hailo-10H 実機テスト (2026-03-03)

### テスト環境
- Raspberry Pi 5 + Hailo AI HAT 2 (Hailo-10H)
- HailoRT FW 5.2.0, hailo_platform Python 5.2.0
- hailo-ollama v0.5.1 (ビルド版)
- Qwen2-VL-2B-Instruct.hef (3.0 GB)

### 重要な発見: hailo-ollama は VLM 非対応

hailo-ollama の公式ドキュメント (USAGE.rst) に明記:
> "The Hailo-Ollama API is currently limited to language models (LLMs) and cannot be used for VLMs."

MODELS テーブルでも `Qwen2-VL-2B-Instruct` の Inference API 欄は "C++, Python" のみで、"Hailo-Ollama" を含まない。

`/hailo/v1/list` で返されるモデルリスト:
```
deepseek_r1:1.5b, llama3.2:1b, qwen2.5-coder:1.5b, qwen2.5:1.5b, qwen2:1.5b
```
`qwen2-vl` は含まれない。

### hailo-ollama テスト結果

**config の注意点**: ビルド版バイナリは `NLOHMANN_DEFINE_TYPE_NON_INTRUSIVE` マクロを使用しており、config JSON に `limits` キーが必須。公式 config テンプレートには含まれていないため、以下を追加する必要がある:
```json
"limits": {"max_in_flight": 4, "max_queue": 10, "retry_after_sec": 1}
```

- **LLM テキスト生成 (qwen2.5:1.5b)**: OpenAI + Ollama native 両方 OK, 6.5 TPS
- **OpenAI API vision リクエスト**: 500 エラー (`Node is NOT a STRING`)
- **Ollama native API + images**: 受理されるが LLM は画像処理不可
- **VlmWdTaggerEngine フォールバック**: OpenAI 500 → Ollama native 自動切替 OK
- **response_format: json_object**: 受理されるが JSON 出力は強制されない

### Hailo Python SDK VLM 直接テスト結果

VLM はメッセージ形式で `{"type": "image"}` を含める必要がある:
```python
messages = [
    {"role": "user", "content": [
        {"type": "image"},
        {"type": "text", "text": "Tag this image."}
    ]}
]
vlm.generate_all(messages, frames=[frame_336x336_rgb_uint8])
```

- **モデルロード**: 33 秒 (初回コールドスタート。公称 6.2 秒との差はディスク I/O が支配的)
- **推論速度**: ~5.1 TPS (128 トークン / 20 秒)。公称 6.73 TPS との差は TTFT を含むため
- **画像認識精度**: 画像内容を正しく理解 (「雪景色の中で手をつなぐ二人の女性」と正確に描写)
- **JSON 出力品質**: 低い。2B モデルでは構造化 JSON の生成精度が不安定 (カンマ欠落、マークダウンコードフェンス混入)

### 発見したバグ

1. **`engines_hailo_vlm.py` プロンプト形式**: VLM に対してテキストのみメッセージを渡していた → `{"type": "image"}` を含むリスト形式に修正
2. **`vlm_inference.py` frames 引数**: VLM の `generate_all()` は `frames` 必須だが Optional 宣言されていた → 必須に修正

### 技術ノート

- **VDevice 排他制約**: hailo-ollama 起動中は `hailo_platform.VDevice()` を取得できない。VLM 直接推論時は hailo-ollama を停止する必要がある
- **VLM.generate_all() は frames 必須**: テキストのみ推論は `HAILO_INVALID_OPERATION` エラーになる。LLM と VLM で API の前提条件が異なる
- **Qwen2-VL の prompt template**: Jinja2 テンプレートで `<|vision_start|><|image_pad|><|vision_end|>` を挿入する。メッセージ形式で `{"type": "image"}` を含めれば SDK が自動処理する

---

## Phase 12: OpenAI 互換 API + デバイス切り替えバグ修正 (2026-03-14)

### 目標

1. OpenAI SDK / LiteLLM / Continue.dev / Open WebUI など外部ツールから Hailo GenAI を直接利用できる OpenAI 互換 API を提供する
2. Quart async 対応の不備を修正する
3. MCP ツールの SSE エンドポイント対応

### 実装: OpenAI 互換 API (`hailo_openai_routes.py`)

新規ファイル `extensions/builtin_hailo_genai/hailo_openai_routes.py` を作成。以下の 4 エンドポイントを実装:

| エンドポイント | 機能 | 対応モデル |
|---|---|---|
| `GET /v1/models` | 利用可能モデル一覧 | 全モデル + CLIP |
| `POST /v1/chat/completions` | テキスト/画像チャット (stream 対応) | LLM + VLM |
| `POST /v1/audio/transcriptions` | 音声文字起こし | Whisper |
| `POST /v1/embeddings` | テキスト→CLIP ベクトル | CLIP ViT-B/16 |

#### 設計上の判断

- **Vision 対応**: OpenAI Vision API 形式 (`image_url` with `data:` base64) をそのまま受け付ける。加えて `file_id:123` 形式で YU ライブラリの画像を直接参照可能
- **HTTP URL 非対応**: SSRF 防止のため、`image_url` に `http://` / `https://` は受け付けない
- **モデルエイリアス**: `whisper-1` → `whisper-base`、`clip` → `clip-vit-b-16` などの OpenAI 互換エイリアスを定義
- **非 WAV 音声**: ffmpeg で自動変換 (16kHz mono PCM16)
- **Usage フィールド**: Hailo SDK はトークン数を返さないため `0` 固定。将来改善の余地あり

#### MCP ツール

- `hailo_genai_openai_info`: エンドポイント一覧と利用方法を返すヘルパーツール（API を呼ばずローカルで生成）

### 修正: Quart async SSE ジェネレーター

全ルートファイルの SSE ジェネレーターに async 対応の不備があった:

| ファイル | 問題 | 修正 |
|---|---|---|
| `hailo_llm_routes.py` | `def generate_sse()` が同期関数 | `async def` に変更、`get_llm()` と `next(it)` を `asyncio.to_thread` で実行 |
| `hailo_vlm_routes.py` | 同上 + DB 参照が同期 | 同上 + `run_db_sync` でラップ |
| `hailo_s2t_routes.py` | transcribe が同期実行 + DB が同期 | `asyncio.to_thread` + `run_db_sync` でラップ |
| `hailo_chat_routes.py` | 同上 (LLM/VLM 両方) | 全ブロッキング呼び出しを async 化 |

Quart (ASGI) ではジェネレーターが `async def` でないとイベントループをブロックし、SSE 配信中に他のリクエストが処理されなくなる。

### 発見したバグ: デバイス切り替え時のシングルトン不整合

#### 症状

VLM 使用後に LLM を呼ぶと `'NoneType' object has no attribute 'get_context_usage_size'` エラー。逆方向 (LLM→VLM→LLM) でも必ず発生。

#### 原因分析

Hailo-10H は VDevice を 1 つしか保持できないため、`device_manager.py` が排他管理している。モデル切り替え時のフロー:

1. VLM の `get_vlm()` → `acquire_genai("vlm", ...)` → 内部で `_release_internal()` が LLM の VDevice を解放
2. VLM 使用完了
3. LLM の `get_llm()` → `_instance` が残っている + `model_name` も一致 → **既存インスタンスを再利用**
4. `_instance._llm` の裏の VDevice は既に解放されている → `get_context_usage_size()` が `None` 上で呼ばれてクラッシュ

問題の根本: シングルトンの `_instance` が残っていても、その内部の Hailo SDK オブジェクト (`self._llm`) が指す VDevice が `device_manager` の `_release_internal()` で `.release()` 済みになっている。Python のリファレンスカウントでは `_instance._llm` はまだ生きているが、Hailo SDK 側のネイティブリソースが解放されている。

#### 修正

`get_llm()` / `get_vlm()` / `get_s2t()` のシングルトン再利用チェックに `device_manager.get_current_owner()` 確認を追加:

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

LLM / VLM / S2T の 3 つのシングルトン全てに同じ修正を適用。

#### 検証

LLM → VLM → LLM → VLM の 4 回連続切り替えで全て正常動作を確認。

### その他の修正

- **MCP `post_sse` メソッド**: `mcp_server/client.py` に SSE ストリームを消費して最終テキストを JSON で返す `post_sse()` メソッドを追加。`hailo_llm_generate` と `hailo_vlm_generate` ツールがこれを使用
- **MCP `yolo_search` パラメータ**: `labels` → `class_name` にリネーム（API 側パラメータ名と一致）
- **Circuit Breaker**: `_READ_SUFFIXES` (`_status`, `_info`, `_list`, `_stats`) を追加。half_open 状態で `hailo_genai_status` 等のステータス系ツールが許可されるように
- **Semantic Search async**: `get_encoder_info()` と `semantic_search()` を `run_db_sync` でラップ（Quart イベントループブロック防止）

### 技術ノート

- **VDevice の排他制約は SDK レベル**: Python 側でオブジェクトの参照を持っていても、Hailo SDK のネイティブ側でリソースが解放されると使えなくなる。シングルトンパターンを使う場合、ネイティブリソースの有効性を別途チェックする必要がある
- **Quart + 同期ジェネレーター**: Quart の SSE レスポンスに同期ジェネレーターを渡すと動作はするが、`yield` 間の処理がイベントループをブロックする。Hailo 推論のような重い処理は必ず `asyncio.to_thread` で別スレッドに逃がす
- **OpenAI Vision API と VLM の連携**: OpenAI Vision API は `image_url` フィールドで画像を受け取るが、Hailo VLM は `frames` (numpy array) を受け取る。変換レイヤーで base64 デコード → OpenCV デコード → 336x336 RGB リサイズを行う
